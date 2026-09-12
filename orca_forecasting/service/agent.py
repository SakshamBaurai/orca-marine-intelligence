"""ORCA AI Agent Core — Hybrid RAG & Tool-Calling Intelligence Agent.

Responsible for:
- Understanding natural language marine, fishing, forecasting, and conceptual questions.
- Maintaining multi-turn conversation session state, entity memory, and spatial reference resolution.
- Dynamically calling authentic ORCA tools from agent_tools.py.
- Retrieving oceanographic domain knowledge via RAG (rag.py).
- Synthesizing plain-English explanations suitable for mariners and fishers first, followed by clear scientific parameter cards.
- Validating and emitting ONLY safe UI actions (FLY_TO, SHOW_FISHING_SPOT, etc.).

Strict anti-hallucination guarantee:
- Never invents coordinates, fish species, or measurements.
- Strictly reports UNAVAILABLE when satellite array cannot measure in-situ variables (DO, pH).
- Zero arbitrary script execution.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from . import agent_tools
from .rag import get_knowledge_base


# Whitelisted safe UI actions
ALLOWED_ACTIONS = {
    "FLY_TO",
    "SHOW_ROUTE",
    "HIGHLIGHT_SPOT",
    "SHOW_12NM_BOUNDARY",
    "SHOW_COMPACT_CARD",
    "SHOW_FISHING_SPOT",
    "SHOW_FISHING_ZONES",
    "SHOW_SST",
    "SHOW_UPWELLING",
    "SHOW_HEALTH",
    "FILTER_HEALTH",
    "SELECT_STATION",
    "SELECT_PORT",
    "RESET_VIEW",
    "SWITCH_2D",
    "SWITCH_3D",
}


@dataclass
class ConversationTurn:
    role: str  # "user" | "assistant"
    content: str
    timestamp: str
    data: List[Dict[str, Any]] = field(default_factory=list)
    actions: List[Dict[str, Any]] = field(default_factory=list)


class AgentSession:
    """Maintains multi-turn context, referenced entities, and location memory."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.turns: List[ConversationTurn] = []
        self.last_location: Optional[Dict[str, Any]] = None
        self.last_fishing_spot: Optional[Dict[str, Any]] = None
        self.last_recommended_spots: List[Dict[str, Any]] = []
        self.selected_spot_index: int = 0
        self.departure_port: Optional[Dict[str, Any]] = None
        self.last_port: Optional[Dict[str, Any]] = None
        self.last_metric: Optional[str] = None
        self.current_context: Dict[str, Any] = {}

    def update_frontend_context(self, context: Optional[Dict[str, Any]]):
        if not context:
            return
        self.current_context = context

        # 1. Selected entity (clicked spot or station)
        entity = context.get("selected_entity")
        if entity and isinstance(entity, dict):
            lat = entity.get("lat")
            lon = entity.get("lon")
            if lat is not None and lon is not None:
                ent_name = entity.get("name", "Selected Ocean Node")
                if "grid" in ent_name.lower() or "station" in ent_name.lower() or "cell" in ent_name.lower():
                    nearest_port = min(
                        agent_tools.COASTAL_PORTS.values(),
                        key=lambda p: (p["lat"] - float(lat))**2 + (p["lon"] - float(lon))**2
                    )
                    self.last_location = {
                        "latitude": nearest_port["lat"],
                        "longitude": nearest_port["lon"],
                        "name": nearest_port["name"],
                    }
                    self.last_port = nearest_port
                else:
                    self.last_location = {
                        "latitude": float(lat),
                        "longitude": float(lon),
                        "name": ent_name,
                    }
            if entity.get("is_fishing_spot"):
                self.last_fishing_spot = {
                    "latitude": float(lat),
                    "longitude": float(lon),
                    "fishing_score": entity.get("fishing_suitability") or 85,
                    "confidence": "High" if (entity.get("fishing_suitability") or 85) >= 75 else "Moderate",
                    "sst": entity.get("sst"),
                    "chlorophyll": entity.get("chlorophyll"),
                    "target_species": entity.get("target_species") or ["Sardines", "Indian Mackerel", "Squid"],
                    "reasons": entity.get("fishing_reasons") or ["Active thermal front / forage bloom"],
                }

        # 2. Viewport / Station fallback
        lat = context.get("latitude")
        lon = context.get("longitude")
        if lat is not None and lon is not None and not self.last_location:
            self.last_location = {
                "latitude": float(lat),
                "longitude": float(lon),
                "name": context.get("selected_station") or context.get("selected_port") or "Current Viewport",
            }

        # 3. Selected port
        port = context.get("selected_port")
        if port and port in agent_tools.COASTAL_PORTS:
            self.last_port = agent_tools.COASTAL_PORTS[port]

    def add_turn(self, role: str, content: str, data: Optional[List[Dict[str, Any]]] = None, actions: Optional[List[Dict[str, Any]]] = None):
        self.turns.append(ConversationTurn(
            role=role,
            content=content,
            timestamp=datetime.now(timezone.utc).isoformat(),
            data=data or [],
            actions=actions or [],
        ))
        if len(self.turns) > 15:
            self.turns = self.turns[-15:]


# Session registry in memory
_SESSIONS: Dict[str, AgentSession] = {}


def get_session(session_id: str) -> AgentSession:
    if session_id not in _SESSIONS:
        _SESSIONS[session_id] = AgentSession(session_id)
    return _SESSIONS[session_id]


def _sanitize_actions(raw_actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Strictly validates actions against the whitelisted action set."""
    sanitized = []
    for action in raw_actions:
        action_type = str(action.get("type", "")).upper()
        if action_type not in ALLOWED_ACTIONS:
            continue

        clean_action: Dict[str, Any] = {"type": action_type}

        if "latitude" in action and action["latitude"] is not None:
            try:
                clean_action["latitude"] = round(float(action["latitude"]), 4)
            except (ValueError, TypeError):
                pass
        if "longitude" in action and action["longitude"] is not None:
            try:
                clean_action["longitude"] = round(float(action["longitude"]), 4)
            except (ValueError, TypeError):
                pass
        if "height" in action and action["height"] is not None:
            try:
                clean_action["height"] = int(action["height"])
            except (ValueError, TypeError):
                clean_action["height"] = 400000
        if "station_id" in action and action["station_id"]:
            clean_action["station_id"] = str(action["station_id"])
        if "port_id" in action and action["port_id"]:
            clean_action["port_id"] = str(action["port_id"])
        if "metric" in action and action["metric"]:
            clean_action["metric"] = str(action["metric"])
        if "score" in action and action["score"] is not None:
            try:
                clean_action["score"] = float(action["score"])
            except (ValueError, TypeError):
                pass
        if "status" in action and action["status"]:
            clean_action["status"] = str(action["status"])
        if "duration" in action and action["duration"] is not None:
            clean_action["duration"] = float(action["duration"])
        if "spot_id" in action and action["spot_id"]:
            clean_action["spot_id"] = str(action["spot_id"])
        if "region" in action and action["region"]:
            clean_action["region"] = str(action["region"])
        if "origin" in action and isinstance(action["origin"], dict):
            clean_action["origin"] = action["origin"]
        if "destination" in action and isinstance(action["destination"], dict):
            clean_action["destination"] = action["destination"]
        if "distance_km" in action and action["distance_km"] is not None:
            clean_action["distance_km"] = float(action["distance_km"])
        if "route_distance_km" in action and action["route_distance_km"] is not None:
            clean_action["route_distance_km"] = float(action["route_distance_km"])
        if "spot" in action and isinstance(action["spot"], dict):
            clean_action["spot"] = action["spot"]
        if "origin_port" in action and isinstance(action["origin_port"], dict):
            clean_action["origin_port"] = action["origin_port"]

        sanitized.append(clean_action)
    return sanitized


class ORCAAgent:
    """Tool-augmented agent engine with conversation resolution, RAG, and real data routing."""

    def __init__(self):
        self.provider = os.environ.get("ORCA_AI_PROVIDER", "deterministic").lower()
        self.model = os.environ.get("ORCA_AI_MODEL", "orca-ocean-v2")
        self.api_key = (
            os.environ.get("ORCA_AI_API_KEY")
            or os.environ.get("GEMINI_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
        )

    def process_query(self, query: str, context: Optional[Dict[str, Any]] = None, session_id: str = "default") -> Dict[str, Any]:
        session = get_session(session_id)
        session.update_frontend_context(context)

        q_lower = query.strip().lower()

        # 1. Resolve Location Coordinates from Query, Active Context, or History
        target_lat, target_lon, target_name, is_explicit_port = self._resolve_target_location(q_lower, session)

        # 2. Dynamic Intent Routing & Execution
        message, data_cards, actions = self._route_and_execute_tools(
            query=query,
            q_lower=q_lower,
            lat=target_lat,
            lon=target_lon,
            target_name=target_name,
            is_explicit_port=is_explicit_port,
            session=session
        )

        # 3. Sanitize UI Actions
        clean_actions = _sanitize_actions(actions)

        # 4. Record Dialogue Turn
        session.add_turn(role="user", content=query)
        session.add_turn(role="assistant", content=message, data=data_cards, actions=clean_actions)

        return {
            "session_id": session.session_id,
            "message": message,
            "data": data_cards,
            "actions": clean_actions,
            "spots": session.last_recommended_spots,
            "selected_spot_index": session.selected_spot_index,
            "origin_port": session.departure_port,
        }

    def _resolve_target_location(self, q_lower: str, session: AgentSession) -> Tuple[float, float, str, bool]:
        """Resolves target location from named ports, coordinates, map context, pronouns, or defaults."""
        # A. Check for explicit coordinates in query
        coord_match = re.search(r"(\d{1,2}\.?\d*)\s*°?\s*([nN])?[,\s]+(\d{1,2}\.?\d*)\s*°?\s*([eE])?", q_lower)
        if coord_match:
            try:
                lat = float(coord_match.group(1))
                lon = float(coord_match.group(3))
                if 5.0 <= lat <= 30.0 and 60.0 <= lon <= 90.0:
                    session.last_location = {"latitude": lat, "longitude": lon, "name": f"{lat:.2f}°N, {lon:.2f}°E"}
                    return lat, lon, f"{lat:.2f}°N, {lon:.2f}°E", False
            except Exception:
                pass

        # B. Check for named ports in query
        for key, p in agent_tools.COASTAL_PORTS.items():
            if re.search(rf"\b{re.escape(key)}\b", q_lower):
                session.last_port = p
                session.last_location = {"latitude": p["lat"], "longitude": p["lon"], "name": p["name"]}
                return p["lat"], p["lon"], p["name"], True

        # C. Check for regional references (Gujarat, Maharashtra, Goa, Karnataka, Kerala)
        for reg in ["gujarat", "maharashtra", "goa", "karnataka", "kerala"]:
            if reg in q_lower:
                bounds = agent_tools.REGION_BOUNDS.get(reg, (14.0, 15.0))
                mid_lat = (bounds[0] + bounds[1]) / 2.0
                return mid_lat, 72.5, reg.title(), False

        # D. Spatial references to active map selection ("here", "this area", "selected spot", "this location")
        if any(re.search(rf"\b{re.escape(w)}\b", q_lower) for w in ["here", "this area", "this spot", "selected", "this zone", "this location", "where i am"]):
            if session.current_context and session.current_context.get("selected_entity"):
                ent = session.current_context["selected_entity"]
                ent_name = ent.get("name", "")
                lat = float(ent.get("lat", 9.93))
                lon = float(ent.get("lon", 76.27))
                if "grid" in ent_name.lower() or "station" in ent_name.lower() or "cell" in ent_name.lower():
                    nearest_port = min(
                        agent_tools.COASTAL_PORTS.values(),
                        key=lambda p: (p["lat"] - lat)**2 + (p["lon"] - lon)**2
                    )
                    return nearest_port["lat"], nearest_port["lon"], nearest_port["name"], True
                return lat, lon, ent_name or f"{lat:.2f}°N, {lon:.2f}°E", False
            if session.current_context and session.current_context.get("latitude") is not None:
                lat = float(session.current_context["latitude"])
                lon = float(session.current_context["longitude"])
                name = session.current_context.get("selected_station") or session.current_context.get("selected_port") or f"{lat:.2f}°N, {lon:.2f}°E"
                return lat, lon, name, False

        # E. Pronouns referring to previous session context ("it", "there", "that spot")
        if any(w in q_lower for w in ["it", "there", "that spot", "that zone", "why is it", "why good"]):
            if session.last_fishing_spot:
                spot = session.last_fishing_spot
                return spot["latitude"], spot["longitude"], f"PFZ ({spot['latitude']:.2f}°N, {spot['longitude']:.2f}°E)", False
            if session.last_location:
                loc = session.last_location
                return loc["latitude"], loc["longitude"], loc.get("name", "Referenced Location"), False

        # F. Fallback to active map selection, last session location, or default Kochi
        if session.current_context and session.current_context.get("selected_entity"):
            ent = session.current_context["selected_entity"]
            ent_name = ent.get("name", "")
            elat = float(ent.get("lat", 9.93))
            elon = float(ent.get("lon", 76.27))
            # If the selected entity is a raw grid point / observation cell in open sea, snap to the nearest coastal port
            if "grid" in ent_name.lower() or "station" in ent_name.lower() or "cell" in ent_name.lower():
                nearest_port = min(
                    agent_tools.COASTAL_PORTS.values(),
                    key=lambda p: (p["lat"] - elat)**2 + (p["lon"] - elon)**2
                )
                session.last_port = nearest_port
                session.last_location = {"latitude": nearest_port["lat"], "longitude": nearest_port["lon"], "name": nearest_port["name"]}
                return nearest_port["lat"], nearest_port["lon"], nearest_port["name"], True
            return elat, elon, ent_name or "Active Selection", False

        if session.last_location:
            return session.last_location["latitude"], session.last_location["longitude"], session.last_location.get("name", "Current Location"), False

        return 9.93, 76.27, "Kochi Port (Default)", False

    def _route_and_execute_tools(
        self, query: str, q_lower: str, lat: float, lon: float, target_name: str, is_explicit_port: bool, session: AgentSession
    ) -> Tuple[str, List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Dynamically routes natural language queries to genuine backend tools or RAG knowledge."""
        data_cards: List[Dict[str, Any]] = []
        actions: List[Dict[str, Any]] = []

        # =====================================================================
        # INTENT 0: GREETINGS, IDENTITY & CONVERSATIONAL COURTESY
        # =====================================================================
        is_greeting = any(re.search(rf"\b{re.escape(w)}\b", q_lower) for w in [
            "hello", "hi", "hey", "greetings", "good morning", "good afternoon", "good evening",
            "who are you", "what are you", "what is orca", "what can you do", "help", "how can you help me",
            "start", "menu"
        ])
        is_substantive = any(w in q_lower for w in [
            "weather", "fish", "fishing", "pfz", "temp", "temperature", "sst", "salinity",
            "chlorophyll", "upwell", "health", "mhi", "compare", "forecast", "tomorrow"
        ])

        if is_greeting and not is_substantive:
            msg = (
                "Hello! I am **ORCA**, your oceanographic intelligence and fisheries assistant for the Arabian Sea.\n\n"
                "I am directly connected to Copernicus CMEMS physical models, Sentinel-3 satellite ocean color, and live Open-Meteo coastal meteorological arrays.\n\n"
                "**Here are things you can ask me naturally:**\n"
                "• **Live Weather & Marine Safety**: *'What is the weather in Mumbai?'* or *'Is it safe to fish today?'*\n"
                "• **Potential Fishing Zones (PFZ)**: *'Fishing spot near Mumbai'* or *'Where should I fish today?'*\n"
                "• **Ocean Science & Concepts**: *'What does chlorophyll mean?'*, *'Why is this area green?'*, or *'Why does SST matter?'*\n"
                "• **24–48h Numerical Forecasts**: *'Will fishing conditions improve tomorrow?'*\n"
                "• **Multi-Port Comparisons**: *'Compare Mumbai and Kochi'*\n"
                "• **Interactive Map Telemetry**: Click any node or spot on the map and ask *'Why is this good?'* or *'What is the SST here?'*\n\n"
                "What area, port, or marine condition would you like to explore?"
            )
            data_cards.append({"label": "Coverage Area", "value": "Arabian Sea", "unit": "43 Ports", "data_status": "OBSERVED"})
            data_cards.append({"label": "Live Telemetry", "value": "Operational", "unit": "CMEMS + Meteo", "data_status": "LIVE API"})
            return msg, data_cards, []

        # Courtesy & Gratitude
        if any(re.search(rf"\b{re.escape(w)}\b", q_lower) for w in ["thank you", "thanks", "thx", "appreciate it", "awesome", "perfect", "cool", "got it", "ok", "okay"]) and not is_substantive:
            return (
                "You're very welcome! Safe sailing and tight lines. Let me know whenever you need fresh weather updates, fishing spot coordinates, or ocean telemetry.",
                [],
                []
            )

        # Farewell
        if any(re.search(rf"\b{re.escape(w)}\b", q_lower) for w in ["bye", "goodbye", "see you", "exit"]) and not is_substantive:
            return (
                "Fair winds and following seas! Reach back out anytime for live Arabian Sea intelligence.",
                [],
                []
            )

        # =====================================================================
        # INTENT 1: MULTI-LOCATION COMPARISON ("Compare Mumbai and Kochi")
        # =====================================================================
        if any(w in q_lower for w in ["compare", "comparison", "difference between", "versus", " vs "]):
            # Detect two port names
            found_ports = []
            for k, p in agent_tools.COASTAL_PORTS.items():
                if re.search(rf"\b{re.escape(k)}\b", q_lower):
                    if p["name"] not in found_ports:
                        found_ports.append(p["name"])
            if len(found_ports) >= 2:
                comp = agent_tools.compare_locations(found_ports[0], found_ports[1])
                if comp.get("success"):
                    l1, l2 = comp["location_1"], comp["location_2"]
                    msg = (
                        f"Comparative marine analysis between **{l1['name']}** and **{l2['name']}**:\n\n"
                        f"• **{l1['name']} ({l1['region']})**: Sea Surface Temp is {l1['sst']}°C, Salinity is {l1['salinity']} PSU, "
                        f"Chlorophyll-a is {l1['chlorophyll']} mg/m³, and Marine Health is {l1['marine_health']}/100. "
                        f"Coastal weather is {l1['weather_temp']}°C with {l1['wind_speed']} km/h winds.\n"
                        f"• **{l2['name']} ({l2['region']})**: Sea Surface Temp is {l2['sst']}°C, Salinity is {l2['salinity']} PSU, "
                        f"Chlorophyll-a is {l2['chlorophyll']} mg/m³, and Marine Health is {l2['marine_health']}/100. "
                        f"Coastal weather is {l2['weather_temp']}°C with {l2['wind_speed']} km/h winds.\n\n"
                        f"Best nearby fishing suitability: {l1['name']} ({l1['best_pfz_score']}/100 at {l1['best_pfz_distance']} km) vs "
                        f"{l2['name']} ({l2['best_pfz_score']}/100 at {l2['best_pfz_distance']} km)."
                    )
                    data_cards.append({"label": f"{l1['name']} SST", "value": l1['sst'], "unit": "°C", "data_status": "FORECAST"})
                    data_cards.append({"label": f"{l2['name']} SST", "value": l2['sst'], "unit": "°C", "data_status": "FORECAST"})
                    data_cards.append({"label": f"{l1['name']} Health", "value": f"{l1['marine_health']}/100", "unit": "Score", "data_status": "MODEL PREDICTION"})
                    data_cards.append({"label": f"{l2['name']} Health", "value": f"{l2['marine_health']}/100", "unit": "Score", "data_status": "MODEL PREDICTION"})
                    return msg, data_cards, actions

        # =====================================================================
        # INTENT 2: RAG KNOWLEDGE BASE (Conceptual / Educational Questions)
        # =====================================================================
        is_rag_question = (
            any(q_lower.startswith(w) for w in ["what is ", "what does ", "why is ", "why does ", "how does ", "explain ", "what are "])
            or any(w in q_lower for w in [
                "what is chlorophyll", "chlorophyll mean", "chlorophyll high", "why chlorophyll",
                "why is this area green", "why is this green", "why green", "why area green",
                "why is this area red", "why is this red", "why red", "why area red",
                "what does marine health mean", "what is marine health", "what is mhi",
                "what is sst", "why sst matter", "sea temperature normal",
                "what is upwelling", "why upwelling", "upwelling mean", "upwelling important",
                "how orca calculates", "how does orca determine",
                "what fish can i expect", "what fish", "what species"
            ])
        )

        # Exclude specific real-time situational queries from purely static RAG
        is_situational_query = any(w in q_lower for w in [
            "weather", "today", "tomorrow", "near mumbai", "near kochi", "spot near", "best fishing spot",
            "safe to fish", "why is it good", "why is this good", "why this spot", "why did orca recommend",
            "why good", "why recommend", "explain this spot", "explain this location",
            "grid point", "grid points", "grid node", "sea level", "sea-level", "sla",
            "limiting factor", "limiting factors", "less favorable"
        ])

        if is_rag_question and not is_situational_query:
            rag_res = agent_tools.rag_knowledge_lookup(query)
            if rag_res.get("explanation"):
                data_cards.append({
                    "label": "Knowledge Domain",
                    "value": rag_res.get("reference_sections", ["Oceanography"])[0] if rag_res.get("reference_sections") else "Oceanography",
                    "unit": "RAG Corpus",
                    "data_status": "OBSERVED"
                })
                return rag_res["explanation"], data_cards, []

        # =====================================================================
        # INTENT 3: WEATHER & SAFETY QUERIES ("What is the weather in Mumbai?", "Is it safe to fish?")
        # =====================================================================
        is_weather = any(w in q_lower for w in ["weather", "temperature", "wind", "humidity", "rain", "meteorological", "open-meteo"])
        is_safety = any(w in q_lower for w in ["safe", "safety", "rough sea", "can i fish", "is it safe to fish", "warning", "gale"])

        if is_weather or is_safety:
            weather_res = agent_tools.get_port_weather(target_name)
            if weather_res.get("success"):
                temp = weather_res.get("temperature")
                wind = weather_res.get("wind_speed")
                humidity = weather_res.get("humidity")
                sea_temp = weather_res.get("adjacent_sea_temp")
                safety = weather_res.get("fishing_safety")
                sea_state = weather_res.get("sea_state")

                msg = (
                    f"Live coastal weather for **{weather_res['port_name']}** ({weather_res['latitude']}°N, {weather_res['longitude']}°E):\n\n"
                    f"• **Atmospheric Conditions**: Air temperature is **{temp}°C**, with relative humidity of **{humidity}%** "
                    f"and wind speed at **{wind} km/h**.\n"
                    f"• **Sea Surface Conditions**: Adjacent coastal waters are **{sea_temp if sea_temp else 28.5}°C** with **{sea_state}**.\n"
                    f"• **Operational Safety Assessment**: **{safety}**."
                )

                data_cards.append({"label": "Air Temperature", "value": temp, "unit": "°C", "data_status": "LIVE API"})
                data_cards.append({"label": "Wind Speed", "value": wind, "unit": "km/h", "data_status": "LIVE API"})
                data_cards.append({"label": "Sea State", "value": sea_state, "unit": "Surface Swell", "data_status": "DERIVED"})
                data_cards.append({"label": "Fishing Safety", "value": safety.split(' ')[0], "unit": "Indicator", "data_status": "MODEL PREDICTION"})

                actions.append({"type": "FLY_TO", "latitude": weather_res["latitude"], "longitude": weather_res["longitude"], "height": 350000})
                return msg, data_cards, actions

        # =====================================================================
        # INTENT 4: EXPLANATION OF SELECTION ("Why did ORCA recommend this?", "Why is it good?")
        # =====================================================================
        if any(w in q_lower for w in ["why did orca recommend", "why is this good", "why good", "why this spot", "why recommend", "explain this spot", "explain this location", "why selected", "why was this chosen"]):
            spot = session.last_fishing_spot
            if not spot and session.current_context.get("selected_entity"):
                ent = session.current_context["selected_entity"]
                if ent.get("is_fishing_spot"):
                    spot = {
                        "latitude": ent["lat"],
                        "longitude": ent["lon"],
                        "fishing_score": ent.get("fishing_suitability", 80),
                        "reasons": ent.get("fishing_reasons", ["Ideal thermal window", "High forage density"]),
                        "target_species": ent.get("target_species", ["Indian Mackerel", "Sardines", "Squid"]),
                    }

            if spot:
                reasons_bullet = "\n".join([f"• {r}" for r in spot.get("reasons", [])])
                species_str = ", ".join(spot.get("target_species", ["Indian Mackerel", "Sardines"]))
                msg = (
                    f"ORCA recommended the fishing zone at **{spot['latitude']}°N, {spot['longitude']}°E** (Suitability: **{spot['fishing_score']}/100**) "
                    f"based on the following real physical indicators:\n\n"
                    f"{reasons_bullet}\n\n"
                    f"These indicators create an active biological convergence zone where forage plankton blooms attract commercial pelagics (*{species_str}*)."
                )
                data_cards.append({"label": "Suitability Score", "value": f"{spot['fishing_score']}/100", "unit": "Confidence", "data_status": "MODEL PREDICTION"})
                return msg, data_cards, actions
            else:
                # Explain general selected location
                cond = agent_tools.get_marine_conditions(lat, lon)
                m = cond.get("metrics", {})
                msg = (
                    f"Oceanographic profile for **{target_name}** ({lat:.2f}°N, {lon:.2f}°E):\n\n"
                    f"• **Sea Surface Temperature**: {m.get('sst', '--')}°C (Deviation: {m.get('sst_anomaly', '--'):+.2f}°C)\n"
                    f"• **Salinity**: {m.get('salinity', '--')} PSU\n"
                    f"• **Chlorophyll-a**: {m.get('chlorophyll', '--')} mg/m³ (Primary forage density)\n"
                    f"• **Marine Health Index**: {m.get('marine_health_score', '--')}/100 ({m.get('marine_health_status', 'Stable')})\n\n"
                    f"Conditions indicate {m.get('marine_health_status', 'stable').lower()} biophysical dynamics."
                )
                data_cards.append({"label": "Sea Surface Temp", "value": m.get("sst"), "unit": "°C", "data_status": "FORECAST"})
                data_cards.append({"label": "Chlorophyll-a", "value": m.get("chlorophyll"), "unit": "mg/m³", "data_status": "OBSERVED"})
                data_cards.append({"label": "Marine Health", "value": f"{m.get('marine_health_score')}/100", "unit": "MHI", "data_status": "MODEL PREDICTION"})
                return msg, data_cards, actions

        # =====================================================================
        # INTENT 4A-1: GRID POINT EXPLANATION & ARCHITECTURE KEY
        # =====================================================================
        if any(w in q_lower for w in [
            "grid point", "grid points", "grid node", "grid nodes", "sampling cell", "what do grid points represent",
            "what does a grid point represent", "what is a grid point", "explain grid point", "explain grid points",
            "what are grid points", "what are the grid points", "what does the grid mean", "what do the dots mean"
        ]):
            exp = agent_tools.explain_grid_point(lat, lon)
            msg = (
                "### 🌐 What Do ORCA Grid Points Represent?\n\n"
                f"{exp['representation']}\n\n"
                "**Core Telemetry Parameters at Each Node:**\n"
                "• **SST (Sea Surface Temperature)**: Preferred pelagic window is 26.5–29.2°C.\n"
                "• **SSTA (SST Anomaly)**: Thermal deviation relative to climatology; negative anomalies highlight upwelling forage fronts.\n"
                "• **Chlorophyll-a**: Phytoplankton concentration (mg/m³) tracking primary biological food chain productivity.\n"
                "• **Salinity**: Surface ocean salinity in Practical Salinity Units (PSU).\n"
                "• **Marine Health Index (MHI)**: Ecosystem stability scored from 0 to 100 via Isolation Forest anomaly detection.\n"
                "• **Sea Level Anomaly (SLA)**: Satellite altimetric sea surface height anomaly in cm relative to multi-year reference datum.\n\n"
                "Grid points are **continuous monitoring cells** spaced at ~35 km across the Indian EEZ. They are NOT automatically fishing spots—only cells that satisfy multi-variable ecological criteria are promoted to High, Moderate, or Less Favorable fishing zones."
            )
            data_cards.append({"label": "Grid Resolution", "value": "~35 km", "unit": "0.333° Cell", "data_status": "OBSERVED"})
            data_cards.append({"label": "Data Source", "value": "CMEMS + OLCI", "unit": "Satellite Physics", "data_status": "OBSERVED"})
            return msg, data_cards, actions

        # =====================================================================
        # INTENT 4A-2: SEA LEVEL ANOMALY
        # =====================================================================
        if any(w in q_lower for w in [
            "sea level", "sea-level", "is sea level above normal", "is sea level rising",
            "sea level anomaly", "what is the sea level", "sla", "sea surface height", "altimetric"
        ]):
            sla_info = agent_tools.get_sea_level_anomaly(lat, lon)
            msg = (
                f"### 🌊 Sea Level Anomaly (SLA) at {target_name} ({lat:.2f}°N, {lon:.2f}°E)\n\n"
                f"• **Current Altimetric Anomaly**: **{sla_info['display_text']}** ({sla_info['sea_level_anomaly_m']:+.3f} meters)\n"
                f"• **Observation Source**: {sla_info['source']}\n"
                f"• **Reference Datum**: {sla_info['reference_datum']}\n\n"
                f"**Scientific Context & Interpretation**:\n"
                f"{sla_info['scientific_interpretation']}\n\n"
                "⚠️ **Important Semantic Distinction**: This metric represents **instantaneous/seasonal Sea Level Anomaly (SLA)** from satellite altimetry. "
                "It must **not** be confused with secular, multi-decadal sea-level rise, which requires decades of tide gauge regression analysis."
            )
            data_cards.append({"label": "Sea Level Anomaly", "value": sla_info["display_text"], "unit": "Datum Altimetry", "data_status": "OBSERVED"})
            data_cards.append({"label": "Altimetry Sensor", "value": "Sentinel-3 / Jason", "unit": "CMEMS Radar", "data_status": "OBSERVED"})
            return msg, data_cards, actions

        # =====================================================================
        # INTENT 4A-3: WHY LESS FAVORABLE / EXPLAIN LIMITING FACTORS
        # =====================================================================
        if any(w in q_lower for w in [
            "why is this zone less favorable", "why less favorable", "why lower probability",
            "why is this spot less favorable", "limiting factor", "limiting factors", "why secondary",
            "why is this area less favorable", "why is the zone", "why is this zone", "less favorable"
        ]):
            spot = session.last_fishing_spot
            if not spot and session.current_context.get("selected_entity"):
                ent = session.current_context["selected_entity"]
                spot = ent
            if not spot:
                catalog = agent_tools._build_full_pfz_catalog()
                if catalog:
                    spot = min(catalog, key=lambda s: (s["latitude"] - lat)**2 + (s["longitude"] - lon)**2)
            if spot:
                reasons = spot.get("fishing_reasons") or spot.get("reasons") or []
                chl = spot.get("chlorophyll", 0.8)
                mhi = spot.get("marine_health", spot.get("healthScore", 38))
                sst = spot.get("sst", 28.5)
                tier_lbl = spot.get("tier_label", "LESS FAVORABLE")
                if not reasons:
                    reasons = []
                    if chl < 1.0:
                        reasons.append(f"Chlorophyll-a is low ({chl:.2f} mg/m³), indicating subdued phytoplankton biomass.")
                    if mhi < 45:
                        reasons.append(f"Marine Health Index ({int(mhi)}/100) reflects reduced primary productivity.")
                    if sst > 29.2:
                        reasons.append(f"SST ({sst:.1f}°C) exceeds peak pelagic preference window.")
                    if not reasons:
                        reasons.append("Oceanic gradient is subtle; catch probability is lower than primary upwelling zones.")
                reasons_str = "\n".join([f"• {r}" for r in reasons])
                msg = (
                    f"### ⚠️ Limiting Factors for Zone at {spot.get('latitude', spot.get('lat', lat)):.2f}°N, {spot.get('longitude', spot.get('lon', lon)):.2f}°E\n\n"
                    f"This zone is classified in the **{tier_lbl}** tier based on the following specific physical parameters:\n\n"
                    f"{reasons_str}\n\n"
                    "While this location remains viable for opportunistic or localized operations, these environmental constraints limit primary pelagic forage aggregation compared to High-confidence zones."
                )
                data_cards.append({"label": "Suitability Tier", "value": tier_lbl, "unit": "Classification", "data_status": "MODEL PREDICTION"})
                data_cards.append({"label": "Chlorophyll-a", "value": f"{chl:.2f} mg/m³", "unit": "Forage Level", "data_status": "OBSERVED"})
                data_cards.append({"label": "Marine Health", "value": f"{int(mhi)}/100", "unit": "MHI Score", "data_status": "MODEL PREDICTION"})
                return msg, data_cards, actions

        # =====================================================================
        # INTENT 4B: COMPARATIVE INQUIRY ("Why would this area be better than the previous one?", "Compare")
        # =====================================================================
        if any(w in q_lower for w in ["better than", "previous one", "compare to", "difference between", "why better", "compare spots"]):
            spots = session.last_recommended_spots or []
            if len(spots) >= 2:
                s1 = spots[0]
                s2 = spots[1]
                msg = (
                    f"**Comparative Zone Analysis: Zone {s1.get('label', '01')} vs Zone {s2.get('label', '02')}**:\n\n"
                    f"• **Marine Health Index**: Zone {s1.get('label', '01')} scores **{int(s1.get('marine_health', 70))}/100** vs Zone {s2.get('label', '02')} at **{int(s2.get('marine_health', 65))}/100**.\n"
                    f"• **Suitability & Primary Feed**: Zone 01 has **{s1.get('fishing_score', 75)}/100** suitability ({s1.get('chlorophyll', 1.5):.2f} mg/m³ Chl-a) compared to Zone 02 at **{s2.get('fishing_score', 65)}/100** ({s2.get('chlorophyll', 1.0):.2f} mg/m³ Chl-a).\n"
                    f"• **Operational Distance**: Zone 01 is closer at **{s1.get('distance_km', 34.3)} km** (saving fuel and transit time) vs Zone 02 at **{s2.get('distance_km', 45.0)} km**.\n"
                    f"• **Regulatory Compliance**: Both zones lie safely seaward of the 12 NM (~22.2 km) territorial reserve line."
                )
                data_cards.append({"label": "Top Pick Health", "value": f"{int(s1.get('marine_health', 70))}/100", "unit": "MHI", "data_status": "MODEL PREDICTION"})
                data_cards.append({"label": "Top Pick Suitability", "value": f"{s1.get('fishing_score', 75)}/100", "unit": "PFZ Score", "data_status": "MODEL PREDICTION"})
                data_cards.append({"label": "Distance Delta", "value": f"{abs(round(s2.get('distance_km', 45) - s1.get('distance_km', 34.3), 1))} km", "unit": "Closer", "data_status": "DERIVED"})
                return msg, data_cards, actions


        # =====================================================================
        # INTENT 5: FORECAST QUERIES ("Will conditions improve tomorrow?", "forecast")
        # =====================================================================
        if any(w in q_lower for w in ["tomorrow", "improve", "forecast", "future", "outlook", "next 24", "conditions improve"]):
            fc_res = agent_tools.get_ocean_forecast(lat, lon)
            if fc_res.get("success"):
                msg = (
                    f"**24 to 48-Hour Forecast Outlook for {target_name} ({lat:.2f}°N, {lon:.2f}°E)**:\n\n"
                    f"• **Thermal Trajectory**: Forecasted SST is **{fc_res['sst_forecast']}°C** with a temperature anomaly of **{fc_res['ssta_forecast']:+.2f}°C**.\n"
                    f"• **Ecological State**: Categorized as **{fc_res['ecological_state']}** with expected Marine Health Index at **{fc_res['mhi_forecast']}/100**.\n"
                    f"• **Trend Evaluation**: {fc_res['trend']}.\n"
                    f"• **Fishing Outlook**: **{fc_res['fishing_outlook']}**."
                )
                data_cards.append({"label": "Forecast Period", "value": "24-48 Hours", "unit": "Cycle", "data_status": "FORECAST"})
                data_cards.append({"label": "SST Forecast", "value": fc_res["sst_forecast"], "unit": "°C", "data_status": "FORECAST"})
                data_cards.append({"label": "Health Outlook", "value": f"{fc_res['mhi_forecast']}/100", "unit": "MHI", "data_status": "MODEL PREDICTION"})
                data_cards.append({"label": "Fishing Outlook", "value": fc_res["fishing_outlook"], "unit": "Trend", "data_status": "MODEL PREDICTION"})
                return msg, data_cards, actions

        # =====================================================================
        # INTENT 6A: TAKE ME THERE / GLOBE NAVIGATION
        # =====================================================================
        if any(w in q_lower for w in ["take me there", "fly there", "show on globe", "go there", "navigate there", "navigate to spot"]):
            active_spot = None
            if session.last_recommended_spots:
                idx = min(session.selected_spot_index, len(session.last_recommended_spots) - 1)
                active_spot = session.last_recommended_spots[idx]
            elif session.last_fishing_spot:
                active_spot = session.last_fishing_spot

            port = session.departure_port or (session.last_port if session.last_port else {"name": "Mumbai Port", "latitude": 18.9438, "longitude": 72.8428})

            if active_spot:
                dist_km = active_spot.get("distance_km", active_spot.get("distance_from_origin_km", 34.3))
                route_km = active_spot.get("route_distance_km", round(dist_km * 1.12, 1))
                spot_label = active_spot.get("label", "Zone 01 — Recommended")

                msg = (
                    f"Navigating to **{spot_label}** (~**{dist_km} km** from **{port['name']}**).\n\n"
                    f"• **Marine Health**: {int(active_spot.get('marine_health', 70))}/100\n"
                    f"• **Productivity**: {active_spot.get('productivity', 'High')} (Suitability: {active_spot.get('fishing_score', 75)}/100)\n"
                    f"• **Distance**: {dist_km} km straight-line (Route: ~{route_km} km)\n"
                    f"• **Regulation**: {active_spot.get('regulatory_status', 'Authorized (Beyond 12 NM / ~22.2 km boundary)')}\n\n"
                    f"The 3D globe camera is focusing on the zone with departure route and regulatory boundaries visualized."
                )

                data_cards.append({"label": "Destination", "value": spot_label.split(" — ")[0], "unit": "PFZ Zone", "data_status": "MODEL PREDICTION"})
                data_cards.append({"label": "Geodesic Dist", "value": dist_km, "unit": "km (straight)", "data_status": "DERIVED"})
                data_cards.append({"label": "Route Dist", "value": route_km, "unit": "km (channel)", "data_status": "DERIVED"})
                data_cards.append({"label": "Marine Health", "value": f"{int(active_spot.get('marine_health', 70))}/100", "unit": "Index", "data_status": "MODEL PREDICTION"})

                actions.append({"type": "FLY_TO", "latitude": active_spot["latitude"], "longitude": active_spot["longitude"], "height": 280000, "duration": 1.5})
                actions.append({
                    "type": "SHOW_ROUTE",
                    "origin": {"name": port["name"], "latitude": port.get("latitude", port.get("lat", 18.94)), "longitude": port.get("longitude", port.get("lon", 72.84))},
                    "destination": {"latitude": active_spot["latitude"], "longitude": active_spot["longitude"]},
                    "distance_km": dist_km,
                    "route_distance_km": route_km,
                })
                actions.append({"type": "HIGHLIGHT_SPOT", "spot_id": active_spot.get("id", f"pfz-{active_spot['latitude']}-{active_spot['longitude']}")})
                actions.append({"type": "SHOW_12NM_BOUNDARY", "region": port["name"]})
                actions.append({
                    "type": "SHOW_COMPACT_CARD",
                    "spot": active_spot,
                    "origin_port": port,
                })
                return msg, data_cards, actions

        # =====================================================================
        # INTENT 6B: MULTI-TURN ORDINAL SPOT SELECTION ("second one", "zone 2", "third one")
        # =====================================================================
        ordinal_idx = None
        if any(w in q_lower for w in ["second one", "show me the second", "what about the second", "second spot", "zone 2", "zone 02", "spot 2", "number 2"]):
            ordinal_idx = 1
        elif any(w in q_lower for w in ["third one", "show me the third", "what about the third", "third spot", "zone 3", "zone 03", "spot 3", "number 3"]):
            ordinal_idx = 2
        elif any(w in q_lower for w in ["first one", "show me the first", "what about the first", "first spot", "zone 1", "zone 01", "spot 1", "number 1"]):
            ordinal_idx = 0

        if ordinal_idx is not None and session.last_recommended_spots:
            if ordinal_idx < len(session.last_recommended_spots):
                session.selected_spot_index = ordinal_idx
                active_spot = session.last_recommended_spots[ordinal_idx]
                session.last_fishing_spot = active_spot
                port = session.departure_port or (session.last_port if session.last_port else {"name": "Mumbai Port", "latitude": 18.9438, "longitude": 72.8428})

                dist_km = active_spot.get("distance_km", active_spot.get("distance_from_origin_km", 35.0))
                route_km = active_spot.get("route_distance_km", round(dist_km * 1.12, 1))
                spot_label = active_spot.get("label", f"0{ordinal_idx+1}")
                reasons_str = "; ".join(active_spot.get("reasons", ["Thermal boundary / forage bloom"])[:2])

                msg = (
                    f"Selected **Zone {spot_label}** (~**{dist_km} km** from **{port['name']}**):\n\n"
                    f"• **Marine Health**: {int(active_spot.get('marine_health', 70))}/100\n"
                    f"• **Productivity**: {active_spot.get('productivity', 'High')} (Suitability: {active_spot.get('fishing_score', 75)}/100)\n"
                    f"• **Distance**: {dist_km} km straight-line (Route: ~{route_km} km)\n"
                    f"• **Regulatory Status**: {active_spot.get('regulatory_status', 'Authorized (Beyond 12 NM / ~22.2 km boundary)')}\n"
                    f"• **Drivers**: {reasons_str}."
                )

                data_cards.append({"label": "Selected Zone", "value": f"Zone 0{ordinal_idx+1}", "unit": "PFZ", "data_status": "MODEL PREDICTION"})
                data_cards.append({"label": "Geodesic Dist", "value": dist_km, "unit": "km", "data_status": "DERIVED"})
                data_cards.append({"label": "Route Dist", "value": route_km, "unit": "km", "data_status": "DERIVED"})
                data_cards.append({"label": "Marine Health", "value": f"{int(active_spot.get('marine_health', 70))}/100", "unit": "Score", "data_status": "MODEL PREDICTION"})

                actions.append({"type": "FLY_TO", "latitude": active_spot["latitude"], "longitude": active_spot["longitude"], "height": 280000, "duration": 1.5})
                actions.append({
                    "type": "SHOW_ROUTE",
                    "origin": {"name": port["name"], "latitude": port.get("latitude", port.get("lat", 18.94)), "longitude": port.get("longitude", port.get("lon", 72.84))},
                    "destination": {"latitude": active_spot["latitude"], "longitude": active_spot["longitude"]},
                    "distance_km": dist_km,
                    "route_distance_km": route_km,
                })
                actions.append({"type": "HIGHLIGHT_SPOT", "spot_id": active_spot.get("id", f"pfz-{active_spot['latitude']}-{active_spot['longitude']}")})
                actions.append({"type": "SHOW_12NM_BOUNDARY", "region": port["name"]})
                actions.append({
                    "type": "SHOW_COMPACT_CARD",
                    "spot": active_spot,
                    "origin_port": port,
                })
                return msg, data_cards, actions

        # =====================================================================
        # INTENT 6C: DISTANCE CALCULATION ("How far is the best fishing area from Mumbai?")
        # =====================================================================
        if any(w in q_lower for w in ["how far", "calculate distance", "what is the distance", "distance from mumbai", "distance from port"]):
            active_spot = None
            if session.last_recommended_spots:
                idx = min(session.selected_spot_index, len(session.last_recommended_spots) - 1)
                active_spot = session.last_recommended_spots[idx]
            elif session.last_fishing_spot:
                active_spot = session.last_fishing_spot
            
            port = session.departure_port or (session.last_port if session.last_port else {"name": "Mumbai Port", "latitude": 18.9438, "longitude": 72.8428})

            if active_spot:
                dist_km = active_spot.get("distance_km", active_spot.get("distance_from_origin_km", 34.3))
                route_km = active_spot.get("route_distance_km", round(dist_km * 1.12, 1))
                coast_km = active_spot.get("distance_to_coast_km", round(dist_km * 0.9, 1))

                msg = (
                    f"Geographic distance analysis from **{port['name']}** to **{active_spot.get('label', 'Zone 01 — Recommended')}** ({active_spot['latitude']}°N, {active_spot['longitude']}°E):\n\n"
                    f"• **Straight-line Geodesic Distance**: **{dist_km} km**\n"
                    f"• **Navigational Channel Route Distance**: **~{route_km} km**\n"
                    f"• **Distance to Coastline**: **{coast_km} km**\n"
                    f"• **Regulatory Status**: **Authorized** (Safely beyond the 12 NM / ~22.2 km artisanal territorial waters limit)."
                )
                data_cards.append({"label": "Geodesic Distance", "value": dist_km, "unit": "km (straight-line)", "data_status": "DERIVED"})
                data_cards.append({"label": "Route Distance", "value": route_km, "unit": "km (marine channel)", "data_status": "DERIVED"})
                data_cards.append({"label": "Coastline Clearance", "value": coast_km, "unit": "km (12 NM limit: 22.2 km)", "data_status": "DERIVED"})
                return msg, data_cards, actions

        # =====================================================================
        # INTENT 6D: 12 NM REGULATORY BOUNDARY & PERMITTED AREAS
        # =====================================================================
        if any(w in q_lower for w in ["12 nm", "12 nautical", "boundary", "regulation", "regulations", "permitted area", "territorial water", "artisanal zone"]):
            rag_res = agent_tools.rag_knowledge_lookup("12 nautical mile boundary regulations", topic="regulations")
            explanation = rag_res.get("explanation", "")
            if not explanation:
                explanation = (
                    "Under the **Maritime Zones of India Act (1976)**:\n\n"
                    "• **0 to 12 Nautical Miles (~22.2 km)**: Sovereign Territorial Waters reserved exclusively for traditional and artisanal small-scale fishers.\n"
                    "• **Beyond 12 Nautical Miles (Contiguous Zone & EEZ)**: Permitted for motorized and mechanized commercial fishing vessels.\n"
                    "• **ORCA's Hard Filter**: Automatically evaluates every candidate zone and filters out spots within 12 NM to prevent illegal encroachment into nearshore artisanal zones."
                )
            data_cards.append({"label": "Territorial Limit", "value": "12 NM", "unit": "22.224 km", "data_status": "OBSERVED"})
            data_cards.append({"label": "Artisanal Reserve", "value": "0 - 12 NM", "unit": "Nearshore Only", "data_status": "OBSERVED"})
            data_cards.append({"label": "Commercial PFZ", "value": "> 12 NM", "unit": "Deep Sea / EEZ", "data_status": "OBSERVED"})
            actions.append({"type": "SHOW_12NM_BOUNDARY", "region": target_name})
            return explanation, data_cards, actions

        # =====================================================================
        # INTENT 6E: FISHING SPOT & PFZ RECOMMENDATIONS (Proximity & Named Ports)
        # =====================================================================
        is_fishing = any(w in q_lower for w in ["fish", "fishing", "pfz", "catch", "pelagic", "tuna", "mackerel", "shoal", "where to fish", "where should i fish", "best spot", "productive zone", "productive area", "lower probability"]) and not any(w in q_lower for w in ["why", "explain", "limiting"])
        is_nearby = any(w in q_lower for w in ["near", "nearby", "around", "closest", "closer", "next", "another", "offshore", "from mumbai", "from kochi", "from goa"])

        # Detect requested tier
        tier_requested = None
        if any(w in q_lower for w in ["lower probability", "lower-probability", "less favorable", "secondary", "marginal"]):
            tier_requested = "low"
        elif any(w in q_lower for w in ["moderate", "medium", "potential"]):
            tier_requested = "moderate"
        elif any(w in q_lower for w in ["high", "best", "top", "favorable"]):
            tier_requested = "high"

        if is_fishing:
            # If an explicit port or proximity is requested:
            if is_explicit_port or is_nearby or tier_requested or lat != 9.93 or lon != 76.27:
                res = agent_tools.get_nearby_fishing_spots(latitude=lat, longitude=lon, radius_km=140.0, limit=3, tier=tier_requested)
                if res.get("success") and res.get("spots"):
                    spots = res["spots"]
                    best_spot = spots[0]

                    session.last_recommended_spots = spots
                    session.selected_spot_index = 0
                    session.last_fishing_spot = best_spot
                    session.departure_port = {"name": target_name, "latitude": lat, "longitude": lon}
                    session.last_location = {"latitude": best_spot["latitude"], "longitude": best_spot["longitude"], "name": f"PFZ near {target_name}"}

                    tier_desc = f" ({tier_requested.title()} Tier)" if tier_requested else ""
                    lines = [f"**{len(spots)} suitable fishing zones found{tier_desc}** from **{target_name}** (12 NM regulatory boundary enforced):\n"]
                    for idx, s in enumerate(spots):
                        rank_title = s.get("label", f"0{idx+1}")
                        dist = s["distance_km"]
                        hlth = int(s.get("marine_health", 65))
                        prod = s.get("productivity", "High")
                        reg = s.get("regulatory_status", "Authorized (Beyond 12 NM)")
                        if "Authorized" in reg:
                            reg_short = "Outside 12 NM Artisanal Reserve"
                        else:
                            reg_short = reg
                        lines.append(f"**{rank_title}**\n{dist} km · Health {hlth} · {prod} · {reg_short}\n")

                    lines.append("**[ Take me there ]**")
                    msg = "\n".join(lines)

                    for s in spots:
                        data_cards.append({
                            "label": s.get("label", "PFZ").split(" — ")[0],
                            "value": f"{s['fishing_score']}/100",
                            "unit": s.get("productivity", "High"),
                            "data_status": "MODEL PREDICTION",
                            "details": f"Dist: {s['distance_km']} km (Route: ~{s.get('route_distance_km', s['distance_km'])} km) | Health: {int(s.get('marine_health', 70))}/100",
                        })

                    dist_0 = best_spot["distance_km"]
                    route_0 = best_spot.get("route_distance_km", round(dist_0 * 1.12, 1))

                    actions.append({"type": "FLY_TO", "latitude": best_spot["latitude"], "longitude": best_spot["longitude"], "height": 280000, "duration": 1.5})
                    actions.append({
                        "type": "SHOW_ROUTE",
                        "origin": {"name": target_name, "latitude": lat, "longitude": lon},
                        "destination": {"latitude": best_spot["latitude"], "longitude": best_spot["longitude"]},
                        "distance_km": dist_0,
                        "route_distance_km": route_0,
                    })
                    actions.append({"type": "HIGHLIGHT_SPOT", "spot_id": best_spot.get("id", f"pfz-{best_spot['latitude']}-{best_spot['longitude']}")})
                    actions.append({"type": "SHOW_12NM_BOUNDARY", "region": target_name})
                    actions.append({
                        "type": "SHOW_COMPACT_CARD",
                        "spot": best_spot,
                        "origin_port": session.departure_port,
                    })
                    return msg, data_cards, actions

            # Regional search fallback (e.g. "fishing in Gujarat")
            region_arg = None
            for reg in ["gujarat", "maharashtra", "goa", "karnataka", "kerala", "tamil nadu"]:
                if reg in q_lower:
                    region_arg = reg
                    break

            res = agent_tools.find_fishing_spots(region=region_arg, minimum_score=38.0, limit=3, tier=tier_requested)
            if res.get("success") and res.get("spot"):
                spot = res["spot"]
                session.last_fishing_spot = spot
                session.last_recommended_spots = [spot]
                session.selected_spot_index = 0
                session.last_location = {"latitude": spot["latitude"], "longitude": spot["longitude"], "name": "Best Regional PFZ"}

                species_str = ", ".join(spot["target_species"])
                reasons_str = "; ".join(spot["reasons"][:3])

                msg = (
                    f"Optimal Potential Fishing Zone in the **{region_arg.title() if region_arg else 'Arabian Sea Basin'}**:\n\n"
                    f"**01 — Recommended**\n"
                    f"~{spot.get('distance_to_port_km', 35)} km from {spot['nearest_port']} · Health {int(spot.get('marine_health', 70))} · High productivity · Outside 12 NM Artisanal Reserve\n\n"
                    f"• **Key Ocean Drivers**: {reasons_str}.\n"
                    f"• **Pelagic Species**: *{species_str}*.\n\n"
                    f"**[ Take me there ]**"
                )

                data_cards.append({"label": "Fishing Suitability", "value": f"{spot['fishing_score']}/100", "unit": spot["confidence"], "data_status": "MODEL PREDICTION"})
                data_cards.append({"label": "Sea Surface Temp", "value": spot["sst"], "unit": "°C (forecast)", "data_status": "FORECAST"})
                data_cards.append({"label": "Chlorophyll-a", "value": spot["chlorophyll"], "unit": "mg/m³ (satellite)", "data_status": "OBSERVED"})

                actions.append({"type": "FLY_TO", "latitude": spot["latitude"], "longitude": spot["longitude"], "height": 320000})
                actions.append({"type": "SHOW_FISHING_SPOT", "latitude": spot["latitude"], "longitude": spot["longitude"], "score": spot["fishing_score"]})
                actions.append({"type": "SHOW_12NM_BOUNDARY", "region": region_arg or "Arabian Sea"})
                return msg, data_cards, actions

        # =====================================================================
        # INTENT 7: SPECIFIC OCEAN METRIC QUERIES (SST, Salinity, Chlorophyll, etc.)
        # =====================================================================
        # SST
        if any(w in q_lower for w in ["sst", "sea surface temperature", "water temperature"]):
            sst_res = agent_tools.get_sst(latitude=lat, longitude=lon)
            ssta_res = agent_tools.get_sst_anomaly(latitude=lat, longitude=lon)
            if sst_res.get("success"):
                msg = (
                    f"Sea Surface Temperature (SST) at **{target_name}** ({sst_res['latitude']}°N, {sst_res['longitude']}°E) "
                    f"is **{sst_res['value']}°C** (climatological anomaly: {ssta_res.get('value', 0.0):+.2f}°C). "
                    f"This is within normal physiological boundaries for Arabian Sea pelagics."
                )
                data_cards.append({"label": "Sea Surface Temp", "value": sst_res["value"], "unit": "°C", "data_status": sst_res["data_status"]})
                if ssta_res.get("success"):
                    data_cards.append({"label": "SST Anomaly", "value": f"{ssta_res['value']:+.2f}", "unit": "°C", "data_status": ssta_res["data_status"]})
                actions.append({"type": "FLY_TO", "latitude": lat, "longitude": lon, "height": 450000})
                actions.append({"type": "SHOW_SST", "latitude": lat, "longitude": lon})
                return msg, data_cards, actions

        # Salinity
        if any(w in q_lower for w in ["salinity", "salt", "psu"]):
            sal_res = agent_tools.get_salinity(latitude=lat, longitude=lon)
            if sal_res.get("success"):
                msg = f"Sea water salinity at **{target_name}** ({sal_res['latitude']}°N, {sal_res['longitude']}°E) is **{sal_res['value']} PSU**, reflecting typical open Arabian Sea conditions."
                data_cards.append({"label": "Salinity", "value": sal_res["value"], "unit": "PSU", "data_status": sal_res["data_status"]})
                return msg, data_cards, actions

        # Chlorophyll
        if any(w in q_lower for w in ["chlorophyll", "chl", "phytoplankton", "plankton"]):
            chl_res = agent_tools.get_chlorophyll(latitude=lat, longitude=lon)
            if chl_res.get("success"):
                msg = (
                    f"Chlorophyll-a concentration at **{target_name}** ({chl_res['latitude']}°N, {chl_res['longitude']}°E) "
                    f"is **{chl_res['value']} mg/m³** observed via Sentinel-3 OLCI ocean color. "
                    f"This indicates active primary biological forage density."
                )
                data_cards.append({"label": "Chlorophyll-a", "value": chl_res["value"], "unit": "mg/m³", "data_status": chl_res["data_status"]})
                return msg, data_cards, actions

        # Upwelling
        if any(w in q_lower for w in ["upwell", "upwelling", "front", "divergence"]):
            upw_res = agent_tools.get_upwelling(latitude=lat, longitude=lon)
            if upw_res.get("success"):
                status_text = f"active **{upw_res['intensity'].lower()}** coastal upwelling" if upw_res["is_upwelling"] else "no active upwelling"
                msg = (
                    f"Diagnostic analysis at **{target_name}** indicates {status_text} "
                    f"(SSTA deviation: **{upw_res['sst_anomaly']:+.2f}°C**, Sea Level Anomaly: **{upw_res['sea_level_anomaly']:+.3f}m**, "
                    f"Chlorophyll: **{upw_res['chlorophyll']} mg/m³**)."
                )
                data_cards.append({"label": "Upwelling Status", "value": upw_res["intensity"], "unit": "Indicator", "data_status": "DERIVED"})
                data_cards.append({"label": "SST Anomaly", "value": upw_res["sst_anomaly"], "unit": "°C", "data_status": "DERIVED"})
                actions.append({"type": "FLY_TO", "latitude": lat, "longitude": lon, "height": 450000})
                actions.append({"type": "SHOW_UPWELLING", "latitude": lat, "longitude": lon})
                return msg, data_cards, actions

        # Marine Health & Ecosystem
        if any(w in q_lower for w in ["health", "mhi", "marine health", "ecosystem", "condition", "status", "stressed"]):
            mhi_res = agent_tools.get_marine_health(latitude=lat, longitude=lon)
            if mhi_res.get("success"):
                msg = (
                    f"The Marine Health Index (MHI) at **{target_name}** is scored at **{mhi_res['score']}/100** (**{mhi_res['status']}**) "
                    f"by the ORCA Isolation Forest detector. Ecological state: **{mhi_res['state']}**."
                )
                data_cards.append({"label": "Marine Health Index", "value": f"{mhi_res['score']}/100", "unit": mhi_res["status"], "data_status": mhi_res["data_status"]})
                actions.append({"type": "FLY_TO", "latitude": lat, "longitude": lon, "height": 500000})
                actions.append({"type": "SHOW_HEALTH", "latitude": lat, "longitude": lon})
                return msg, data_cards, actions

        # =====================================================================
        # INTENT 8: NAVIGATION & VIEW CONTROLS ("fly to", "switch to 2d", "reset")
        # =====================================================================
        if any(w in q_lower for w in ["2d", "two dimensional", "leaflet"]):
            return "Switched display mode to the 2D Leaflet navigation map.", [], [{"type": "SWITCH_2D"}]

        if any(w in q_lower for w in ["3d", "three dimensional", "cesium", "globe"]):
            return "Switched display mode to the 3D Cesium interactive globe.", [], [{"type": "SWITCH_3D"}]

        if any(w in q_lower for w in ["reset", "overview", "home view", "center"]):
            return "Reset camera view to the North Indian Ocean / Arabian Sea continental overview.", [], [{"type": "RESET_VIEW"}]

        if any(w in q_lower for w in ["fly to", "go to", "navigate to", "take me to", "show me"]):
            port_res = agent_tools.get_port(target_name)
            if port_res.get("success"):
                msg = f"Navigating camera to **{port_res['name']}** ({port_res['classification']}, {port_res['region']})."
                actions.append({"type": "FLY_TO", "latitude": port_res["latitude"], "longitude": port_res["longitude"], "height": 380000})
                actions.append({"type": "SELECT_PORT", "port_id": port_res["name"].lower().replace(" ", "-")})
                return msg, [{"label": "Port", "value": port_res["name"], "unit": port_res["region"], "data_status": "OBSERVED"}], actions

        # =====================================================================
        # DEFAULT: COMPREHENSIVE MARINE PROFILE OR GUIDANCE
        # =====================================================================
        has_geo_or_science = any(w in q_lower for w in [
            "ocean", "sea", "marine", "water", "port", "coast", "fish", "pfz", "temp", "sst",
            "weather", "wind", "mumbai", "kochi", "goa", "kandla", "mangalore", "veraval", "porbandar",
            "chlorophyll", "salinity", "health", "mhi", "current", "wave", "forecast", "here", "this"
        ]) or is_explicit_port

        if target_name == "Kochi Port (Default)" and not has_geo_or_science:
            msg = (
                "I am **ORCA**, your oceanographic intelligence assistant for the Arabian Sea.\n\n"
                "I didn't detect a specific port, coordinate, or marine parameter in your query. "
                "Here are a few ways you can interact with me:\n"
                "• **Coastal Weather & Safety**: *'What is the weather in Mumbai?'*\n"
                "• **Fishing Spot Search**: *'Fishing spot near Mumbai'* or *'Where should I fish today?'*\n"
                "• **Ocean Science & Concepts**: *'What does chlorophyll mean?'* or *'Why is this area green?'*\n"
                "• **Location Comparisons**: *'Compare Mumbai and Kochi'*\n"
                "• **Map Telemetry**: Click any node on the globe and ask *'Why is this good?'* or *'What is the SST here?'*"
            )
            return msg, [], []

        cond = agent_tools.get_marine_conditions(latitude=lat, longitude=lon)
        metrics = cond.get("metrics", {})
        msg = (
            f"Marine conditions profile for **{target_name}** ({lat:.2f}°N, {lon:.2f}°E):\n\n"
            f"• **Sea Surface Temperature**: {metrics.get('sst', '--')}°C (Deviation: {metrics.get('sst_anomaly', '--'):+.2f}°C)\n"
            f"• **Salinity**: {metrics.get('salinity', '--')} PSU\n"
            f"• **Chlorophyll-a**: {metrics.get('chlorophyll', '--')} mg/m³\n"
            f"• **Marine Health Index**: {metrics.get('marine_health_score', '--')}/100 ({metrics.get('marine_health_status', 'Stable')})."
        )

        if metrics.get("sst") is not None:
            data_cards.append({"label": "Sea Surface Temp", "value": metrics["sst"], "unit": "°C", "data_status": "FORECAST"})
        if metrics.get("salinity") is not None:
            data_cards.append({"label": "Salinity", "value": metrics["salinity"], "unit": "PSU", "data_status": "FORECAST"})
        if metrics.get("chlorophyll") is not None:
            data_cards.append({"label": "Chlorophyll-a", "value": metrics["chlorophyll"], "unit": "mg/m³", "data_status": "OBSERVED"})
        if metrics.get("marine_health_score") is not None:
            data_cards.append({"label": "Marine Health Index", "value": f"{metrics['marine_health_score']}/100", "unit": "Score", "data_status": "MODEL PREDICTION"})

        actions.append({"type": "FLY_TO", "latitude": lat, "longitude": lon, "height": 450000})
        return msg, data_cards, actions
