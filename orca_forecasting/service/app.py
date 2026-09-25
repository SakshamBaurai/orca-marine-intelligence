"""FastAPI microservice exposing the ORCA detector as a stateless HTTP API.

The trained bundle is loaded **once** at process start (ONNX runtime preferred,
joblib fallback) and then every request is scored through the same pure
``build_features`` -> detector path used in training, so there is no train/serve
skew and no per-request fitting or global aggregation.

Endpoints
---------
    GET  /health          liveness + whether a model is loaded
    GET  /metadata        feature order, threshold, params, data extent, provenance
    POST /predict         score one observation
    POST /predict/batch   score many observations

Configuration (environment variables)
--------------------------------------
    ORCA_ARTIFACT_DIR   directory of a trained bundle (default: "artifacts")
    ORCA_CONFIG         optional path to the YAML config used at train time
    ORCA_PREFER_ONNX    "1" (default) to prefer the ONNX runtime, "0" for joblib
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date
from typing import List, Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from orca.analytics import annotate
from orca.config import Config
from orca.inference import InferenceEngine
from orca.live import LiveIngestionError, fetch_and_score_daily

from .models import (
    AgentChatRequest,
    AgentChatResponse,
    BatchPredictRequest,
    BatchPredictResponse,
    HealthResponse,
    LivePredictRequest,
    LivePredictResponse,
    MetadataResponse,
    Prediction,
    PredictRequest,
    PredictResponse,
)
from .dashboard import STATIONS, build_dashboard_payload
from .agent import ORCAAgent


@dataclass
class ServiceState:
    engine: InferenceEngine
    cfg: Config


_STATE: Optional[ServiceState] = None


def configure(engine: InferenceEngine, cfg: Config) -> None:
    """Inject a ready engine (used by tests to avoid disk/env dependencies)."""
    global _STATE
    _STATE = ServiceState(engine=engine, cfg=cfg)


def _load_from_env() -> ServiceState:
    artifact_dir = os.environ.get("ORCA_ARTIFACT_DIR", "artifacts")
    config_path = os.environ.get("ORCA_CONFIG")
    prefer_onnx = os.environ.get("ORCA_PREFER_ONNX", "1") != "0"
    cfg = Config.load(config_path) if config_path else Config()
    engine = InferenceEngine.from_dir(artifact_dir, prefer_onnx=prefer_onnx, data_cfg=cfg.data)
    return ServiceState(engine=engine, cfg=cfg)


def get_state() -> ServiceState:
    global _STATE
    if _STATE is None:
        _STATE = _load_from_env()
    return _STATE


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Best-effort warm load; a failure here should not stop /health from serving.
    global _STATE
    if _STATE is None:
        try:
            _STATE = _load_from_env()
        except Exception:  # pragma: no cover - allows /health to report not-loaded
            _STATE = None
    yield


app = FastAPI(title="ORCA Anomaly Detection Service", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)


# --------------------------------------------------------------------------- #
# Scoring helpers
# --------------------------------------------------------------------------- #
def _score_dataframe(state: ServiceState, df: pd.DataFrame) -> pd.DataFrame:
    engine = state.engine
    with_feats = state.cfg.analytics.enable
    scored = engine.score_frame(df, with_features=with_feats)
    if with_feats:
        feats = scored[engine.feature_names]
        ann = annotate(feats, state.cfg.analytics)
        scored["ecological_state"] = ann["ecological_state"].to_numpy()
        scored["marine_health_index"] = ann["marine_health_index"].to_numpy()
    return scored


def _require_in_configured_bounds(state: ServiceState, df: pd.DataFrame) -> None:
    """Keep direct API scoring in the same region as its fitted baseline."""
    d = state.cfg.data
    bounds = (d.lat_min, d.lat_max, d.lon_min, d.lon_max)
    if all(v is None for v in bounds):
        return
    if any(v is None for v in bounds):
        raise HTTPException(status_code=500, detail="Incomplete geographic bounds in service configuration.")
    inside = (
        df[d.lat_column].between(d.lat_min, d.lat_max)
        & df[d.lon_column].between(d.lon_min, d.lon_max)
    )
    if not bool(inside.all()):
        raise HTTPException(status_code=422, detail="Observation lies outside this deployment's configured geographic bounds.")


def _to_prediction(row: dict) -> Prediction:
    return Prediction(
        raw_score=float(row["raw_score"]),
        anomaly_score=float(row["anomaly_score"]),
        is_anomaly=bool(row["is_anomaly"]),
        ecological_state=row.get("ecological_state"),
        marine_health_index=(float(row["marine_health_index"]) if row.get("marine_health_index") is not None else None),
    )


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    loaded = _STATE is not None
    return HealthResponse(
        status="ok",
        model_loaded=loaded,
        backend=_STATE.engine.backend if loaded else None,
        version=(_STATE.cfg.version if loaded else None),
    )


@app.get("/dashboard/telemetry")
def dashboard_telemetry(station: str = Query("Kochi", description="Named ORCA coastal station.")) -> dict:
    """Return a display-ready, station-local view of the latest forecast output."""
    try:
        return build_dashboard_payload(station)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown station '{station}'. Valid stations: {', '.join(STATIONS)}") from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=500, detail=f"Could not prepare forecast telemetry: {exc}") from exc


_HISTORICAL_SLA_CACHE = None

def _get_sla_lookup():
    global _HISTORICAL_SLA_CACHE
    if _HISTORICAL_SLA_CACHE is not None:
        return _HISTORICAL_SLA_CACHE
    try:
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent.parent
        candidates = [
            root / "orca_processed_ocean_data.parquet",
            root / "orca_forecasting" / "orca_processed_ocean_data.parquet"
        ]
        p = next((c for c in candidates if c.exists()), None)
        if p:
            df_hist = pd.read_parquet(p, columns=["latitude", "longitude", "sla", "sla_anomaly", "time"])
            latest_date = df_hist["time"].max()
            slice_df = df_hist[df_hist["time"] == latest_date][["latitude", "longitude", "sla", "sla_anomaly"]].drop_duplicates()
            lookup = {}
            for _, r in slice_df.iterrows():
                key = (round(float(r["latitude"]) * 4) / 4, round(float(r["longitude"]) * 4) / 4)
                lookup[key] = (float(r["sla"]), float(r["sla_anomaly"]))
            _HISTORICAL_SLA_CACHE = lookup
            return lookup
    except Exception as e:
        print("SLA lookup notice:", e)
    _HISTORICAL_SLA_CACHE = {}
    return _HISTORICAL_SLA_CACHE


@app.get("/dashboard/grid")
def dashboard_grid() -> dict:
    import pandas as pd
    import numpy as np

    try:
        try:
            from .dashboard import _read_forecast, _forecast_path
            source = _forecast_path()
            df = _read_forecast(source)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"stations": [], "error": str(e)}
        
        if df.empty:
            return {"stations": []}
            
        df = df.copy()
        # Balanced ~0.33 degree sampling (~35 km) gives ~525 authentic coastal & shelf nodes
        df['lat_bin'] = (df['latitude'] * 3).round() / 3
        df['lon_bin'] = (df['longitude'] * 3).round() / 3
        
        agg_funcs = {
            'latitude': 'mean',
            'longitude': 'mean',
        }
        for col in ['thetao', 'chl', 'so', 'depth', 'MHI', 'is_anomaly', 'SSTA', 'current_speed', 'sla_anomaly']:
            if col in df.columns:
                if col == 'is_anomaly':
                    agg_funcs[col] = 'max'
                else:
                    agg_funcs[col] = 'mean'
                    
        grouped = df.groupby(['lat_bin', 'lon_bin']).agg(agg_funcs).reset_index()
        sla_lookup = _get_sla_lookup()
        
        stations = []
        has_thetao = 'thetao' in grouped.columns
        has_chl = 'chl' in grouped.columns
        has_so = 'so' in grouped.columns
        has_depth = 'depth' in grouped.columns
        has_mhi = 'MHI' in grouped.columns
        has_anomaly = 'is_anomaly' in grouped.columns
        has_ssta = 'SSTA' in grouped.columns
        has_current = 'current_speed' in grouped.columns
        has_sla = 'sla_anomaly' in grouped.columns

        import math
        def _clean(val, default=0.0):
            try:
                f = float(val)
                if math.isnan(f) or math.isinf(f): return default
                return f
            except:
                return default

        def _is_inside_eez(lat_v: float, lon_v: float) -> bool:
            if not (7.0 <= lat_v <= 24.5 and 65.0 <= lon_v <= 78.5):
                return False
            # Gujarat/Maharashtra northwest boundary line from (19.0°N, 72.5°E) to (23.5°N, 68.0°E)
            if lat_v >= 19.0:
                min_lon = 68.0 + (23.5 - lat_v) * (72.5 - 68.0) / (23.5 - 19.0)
                if lon_v < min_lon:
                    return False
            elif lat_v >= 15.0:
                if lon_v < 68.5:
                    return False
            else:
                if lon_v < 71.0:
                    return False
            return True

        for _, row in grouped.iterrows():
            lat_val = _clean(row["latitude"])
            lon_val = _clean(row["longitude"])
            if not _is_inside_eez(lat_val, lon_val):
                continue
            
            healthScore = 100
            if has_mhi and pd.notna(row["MHI"]):
                healthScore = _clean(row["MHI"], 100.0)
            elif has_anomaly and row["is_anomaly"]:
                healthScore = 40
                
            sst = _clean(row["thetao"], None) if has_thetao else None
            chl = _clean(row["chl"], None) if has_chl else None
            sal = _clean(row["so"], None) if has_so else None
            depth = _clean(row["depth"], None) if has_depth else None
            
            ssta = _clean(row["SSTA"], None) if has_ssta else None
            current_speed = _clean(row["current_speed"], None) if has_current else None
            
            # Sea level anomaly lookup (m and cm above reference datum)
            sla_key = (round(lat_val * 4) / 4, round(lon_val * 4) / 4)
            sla_tuple = sla_lookup.get(sla_key, (0.08, 0.0))
            sla_val = round(sla_tuple[0], 3)
            sla_anom_val = round(sla_tuple[1], 3)
            sla_cm = round(sla_val * 100, 1)
            sla_text = f"{'+' if sla_cm >= 0 else ''}{sla_cm:.0f} cm above reference"
            
            # =========================================================================
            # MULTI-TIER DATA-DRIVEN FISHING SUITABILITY CALCULATION (PFZ MODEL)
            # =========================================================================
            suitability_score = 0
            reasons = []
            
            # 1. Sea Surface Temperature Thermal Sweet Spot (Max 25 pts)
            if sst is not None:
                if 26.5 <= sst <= 29.2:
                    suitability_score += 25
                    reasons.append(f"Ideal thermal window for pelagics ({sst:.1f}°C)")
                elif (25.0 <= sst < 26.5) or (29.2 < sst <= 30.2):
                    suitability_score += 15
                    reasons.append(f"Moderate surface temperature ({sst:.1f}°C)")
                else:
                    suitability_score += 5
                    reasons.append(f"Suboptimal SST ({sst:.1f}°C)")
            else:
                suitability_score += 10
                
            # 2. Thermal Front & Coastal Upwelling Dynamics (SSTA) (Max 25 pts)
            if ssta is not None:
                if -1.5 <= ssta <= -0.2:
                    suitability_score += 25
                    reasons.append(f"Active thermal front / upwelling boundary ({ssta:+.2f}°C)")
                elif -0.2 < ssta <= 0.4:
                    suitability_score += 16
                    reasons.append(f"Stable thermal equilibrium ({ssta:+.2f}°C)")
                elif ssta < -1.5:
                    suitability_score += 12
                    reasons.append(f"Strong deep upwelling plume ({ssta:+.2f}°C)")
                else:
                    reasons.append(f"Warm surface layer / heat stress ({ssta:+.2f}°C)")
            else:
                suitability_score += 10
                
            # 3. Primary Productivity & Forage Feeding Signal (Chlorophyll-a) (Max 25 pts)
            if chl is not None:
                if 0.5 <= chl <= 3.5:
                    suitability_score += 25
                    reasons.append(f"High phytoplankton forage zone ({chl:.2f} mg/m³)")
                elif 0.25 <= chl < 0.5:
                    suitability_score += 18
                    reasons.append(f"Moderate chlorophyll feed ({chl:.2f} mg/m³)")
                elif chl > 3.5:
                    suitability_score += 14
                    reasons.append(f"Dense algal concentration ({chl:.2f} mg/m³)")
                else:
                    suitability_score += 5
                    reasons.append(f"Low primary productivity ({chl:.2f} mg/m³)")
            else:
                suitability_score += 10
                
            # 4. Current Velocity, Convergence & Eddy Upwelling (Max 15 pts)
            if current_speed is not None:
                if 0.15 <= current_speed <= 0.60:
                    suitability_score += 10
                    reasons.append(f"Favorable schooling current shear ({current_speed:.2f} m/s)")
                elif current_speed < 0.15:
                    suitability_score += 5
                    reasons.append(f"Sluggish current flow ({current_speed:.2f} m/s)")
                else:
                    suitability_score += 3
                    reasons.append(f"High velocity surface shear ({current_speed:.2f} m/s)")
            else:
                suitability_score += 5
                
            if sla_val < -0.01:
                suitability_score += 5
                reasons.append(f"Cyclonic eddy divergence upwelling (SLA {sla_val:+.2f}m)")
                
            # 5. Ecosystem Health / Habitat Viability (Max 10 pts)
            if healthScore >= 70:
                suitability_score += 10
                reasons.append(f"Healthy marine ecosystem index ({healthScore:.0f}/100)")
            elif healthScore >= 50:
                suitability_score += 5
                reasons.append(f"Moderate marine health ({healthScore:.0f}/100)")
            else:
                reasons.append(f"Stressed habitat conditions ({healthScore:.0f}/100)")
                
            suitability_score = min(100, max(0, suitability_score))
            
            # Multi-tier classification (High, Moderate, Less Favorable)
            if suitability_score >= 68 and healthScore >= 42:
                fishing_tier = "high"
                tier_label = "HIGH / FAVORABLE"
                is_fishing_spot = True
                confidence = "High Confidence"
            elif suitability_score >= 50 and healthScore >= 32:
                fishing_tier = "moderate"
                tier_label = "MODERATE / POTENTIAL"
                is_fishing_spot = True
                confidence = "Moderate Potential"
            elif suitability_score >= 38:
                fishing_tier = "low"
                tier_label = "LESS FAVORABLE"
                is_fishing_spot = True
                confidence = "Less Favorable"
                
                # Construct clear, metric-grounded explanation for less favorable tier
                tier_reasons = []
                if chl is not None and chl >= 0.35:
                    tier_reasons.append(f"Chlorophyll-a ({chl:.2f} mg/m³) provides forage signal")
                elif chl is not None:
                    tier_reasons.append(f"Low chlorophyll-a ({chl:.2f} mg/m³) indicates sparse forage")
                if ssta is not None and ssta > 0.4:
                    tier_reasons.append(f"Elevated SST anomaly (+{ssta:.2f}°C) limits thermal front upwelling")
                elif sst is not None and (sst < 26.0 or sst > 29.5):
                    tier_reasons.append(f"SST ({sst:.1f}°C) deviates from preferred 26.5-29.2°C window")
                if healthScore < 50:
                    tier_reasons.append(f"Marine ecological health index is stressed ({healthScore:.0f}/100)")
                if tier_reasons:
                    reasons = tier_reasons
            else:
                fishing_tier = "none"
                tier_label = "MONITORING NODE"
                is_fishing_spot = False
                confidence = "Monitoring Cell"
            
            health_status = "Optimal" if healthScore >= 75 else ("Moderate" if healthScore >= 55 else "Stressed")
            status_color = "#00f5d4" if healthScore >= 75 else ("#ffd166" if healthScore >= 55 else "#ef476f")

            stations.append({
                "id": f"grid-{lat_val:.2f}-{lon_val:.2f}",
                "lat": lat_val,
                "lon": lon_val,
                "sst": sst,
                "ssta": ssta,
                "current_speed": current_speed,
                "sla": sla_val,
                "sla_anomaly": sla_anom_val,
                "sla_cm": sla_cm,
                "sla_text": sla_text,
                "oxygen": None, 
                "ph": None,
                "chlorophyll": chl,
                "salinity": sal,
                "depth": depth,
                "healthScore": healthScore,
                "healthStatus": health_status,
                "statusColor": status_color,
                "is_fishing_spot": is_fishing_spot,
                "fishing_tier": fishing_tier,
                "tier_label": tier_label,
                "confidence": confidence,
                "fishing_suitability": suitability_score,
                "fishing_reasons": reasons,
                "name": f"Grid Point ({lat_val:.1f}°N, {lon_val:.1f}°E)"
            })

        return {"stations": stations}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/dashboard/events")
def dashboard_events() -> dict:
    import pandas as pd
    import os
    import math
    from shapely.geometry import Point, shape, mapping
    from geopy.distance import geodesic
    import json

    ports = {
        "Mumbai": (18.94, 72.83),
        "Kochi": (9.96, 76.23),
        "Mangaluru": (12.87, 74.84),
        "Porbandar": (21.64, 69.60)
    }

    eez_poly = None
    eez_path = r"C:\Users\neonm\OneDrive\Desktop\ORCA_Master_Backup\orca_forecasting\artifacts\arabian_sea_eez.geojson"
    if os.path.exists(eez_path):
        with open(eez_path, "r") as f:
            eez_data = json.load(f)
            if eez_data.get("features"):
                eez_poly = shape(eez_data["features"][0]["geometry"])

    csv_path = r"C:\Users\neonm\OneDrive\Desktop\ORCA_Master_Backup\latest_forecast_events.csv"
    if not os.path.exists(csv_path):
        return {"type": "FeatureCollection", "features": []}
        
    try:
        df = pd.read_csv(csv_path)
    except Exception:
        return {"type": "FeatureCollection", "features": []}
        
    features = []
    for _, row in df.iterrows():
        etype = str(row.get("event_type", ""))
        
        if "Productive Upwelling" in etype:
            zone = "Green Zone (Better Fishing)"
            color = "#00f5d4"
        elif "Thermal Stress" in etype:
            zone = "Red Zone (Avoid)"
            color = "#ef476f"
        elif "Eutrophication" in etype or "Dynamic" in etype:
            zone = "Yellow Zone (Caution)"
            color = "#ffd166"
        else:
            zone = "Unknown"
            color = "#ffffff"
            
        lon, lat = float(row["centroid_lon"]), float(row["centroid_lat"])
        area = float(row.get("estimated_area_km2", 10000))
        radius_km = math.sqrt(area / math.pi)
        radius_deg = radius_km / 111.0  # Approx degree conversion
        
        poly = Point(lon, lat).buffer(radius_deg)
        if eez_poly is not None:
            poly = poly.intersection(eez_poly)
            
        # Find nearest port
        min_dist = float("inf")
        nearest_port = ""
        for port_name, (port_lat, port_lon) in ports.items():
            d = geodesic((lat, lon), (port_lat, port_lon)).nautical
            if d < min_dist:
                min_dist = d
                nearest_port = port_name
                
        feat = {
            "type": "Feature",
            "geometry": mapping(poly) if not poly.is_empty else {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "event_id": str(row.get("event_id", "")),
                "event_type": etype,
                "zone": zone,
                "color": color,
                "estimated_area_km2": area,
                "mean_MHI": float(row.get("mean_MHI", 0)),
                "centroid_lat": lat,
                "centroid_lon": lon,
                "nearest_port": nearest_port,
                "distance_to_port_nmi": round(min_dist, 1),
                # Add model feature values for frontend display (with fallbacks)
                "thetao_daily_anomaly": float(row.get("thetao_daily_anomaly", row.get("min_SSTA", 0))),
                "current_speed": float(row.get("current_speed", 0)),
                "log_chl": float(row.get("log_chl", 0))
            }
        }
        features.append(feat)
        
    return {"type": "FeatureCollection", "features": features}


@app.get("/metadata", response_model=MetadataResponse)
def metadata() -> MetadataResponse:
    state = get_state()
    md = state.engine.a.metadata or {}
    return MetadataResponse(
        version=str(md.get("version", state.cfg.version)),
        backend=state.engine.backend,
        threshold=state.engine.threshold,
        feature_names=state.engine.feature_names,
        required_input_columns=state.engine.required_input_columns(),
        model=md.get("model", {}),
        climatology=md.get("climatology", {}),
        data_extent=md.get("data_extent", {}),
        boundaries=md.get("boundaries", {}),
    )


@app.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest) -> PredictResponse:
    state = get_state()
    record = _observation_to_dict(req.observation)
    df = pd.DataFrame.from_records([record])
    state.engine._coerce_types(df)
    _require_in_configured_bounds(state, df)
    try:
        scored = _score_dataframe(state, df)
    except Exception as exc:  # feature engineering / scoring failure -> 422
        raise HTTPException(status_code=422, detail=f"Could not score observation: {exc}")
    row = scored.iloc[0].to_dict()
    return PredictResponse(
        prediction=_to_prediction(row),
        threshold=state.engine.threshold,
        backend=state.engine.backend,
    )


@app.post("/predict/batch", response_model=BatchPredictResponse)
def predict_batch(req: BatchPredictRequest) -> BatchPredictResponse:
    state = get_state()
    records = [_observation_to_dict(o) for o in req.observations]
    df = pd.DataFrame.from_records(records)
    state.engine._coerce_types(df)
    _require_in_configured_bounds(state, df)
    try:
        scored = _score_dataframe(state, df)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not score batch: {exc}")
    preds: List[Prediction] = [_to_prediction(r) for r in scored.to_dict(orient="records")]
    return BatchPredictResponse(
        predictions=preds,
        n=len(preds),
        n_alerts=int(scored["is_anomaly"].sum()),
        threshold=state.engine.threshold,
        backend=state.engine.backend,
    )


@app.post("/predict/live", response_model=LivePredictResponse)
def predict_live(req: LivePredictRequest) -> LivePredictResponse:
    """Fetch today's (or a requested day's) configured observations and score them.

    This is deliberately a fetch-and-score path, not model retraining: every
    current record is compared to the frozen, leak-free historical climatology
    persisted in the loaded artifact bundle.
    """
    state = get_state()
    requested_date = req.observation_date or date.today()
    try:
        scored, report = fetch_and_score_daily(state.cfg, state.engine, requested_date)
    except LiveIngestionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if len(scored) > req.max_records:
        raise HTTPException(
            status_code=413,
            detail=f"Live fetch produced {len(scored)} rows, above max_records={req.max_records}. Narrow the configured grid or request a larger limit.",
        )
    if state.cfg.analytics.enable:
        ann = annotate(scored[state.engine.feature_names], state.cfg.analytics)
        scored["ecological_state"] = ann["ecological_state"].to_numpy()
        scored["marine_health_index"] = ann["marine_health_index"].to_numpy()
    predictions = [_to_prediction(row) for row in scored.to_dict(orient="records")]
    return LivePredictResponse(
        predictions=predictions,
        n=len(predictions),
        n_alerts=int(scored["is_anomaly"].sum()),
        threshold=state.engine.threshold,
        backend=state.engine.backend,
        ingestion=report,
    )


def _observation_to_dict(obs) -> dict:
    """Support both Pydantic v1 (.dict) and v2 (.model_dump)."""
    if hasattr(obs, "model_dump"):
        return obs.model_dump()
    return obs.dict()


_AGENT: Optional[ORCAAgent] = None


def get_agent() -> ORCAAgent:
    global _AGENT
    if _AGENT is None:
        _AGENT = ORCAAgent()
    return _AGENT


@app.post("/api/v1/agent/chat", response_model=AgentChatResponse)
@app.post("/agent/chat", response_model=AgentChatResponse)
def agent_chat(req: AgentChatRequest) -> AgentChatResponse:
    from . import i18n_service

    agent = get_agent()
    ctx_dict = (
        req.context.model_dump()
        if (req.context and hasattr(req.context, "model_dump"))
        else (req.context.dict() if req.context else None)
    )

    # 1. Translate/normalize query from selected or detected language into canonical English
    english_query, effective_lang = i18n_service.translate_query_to_english(
        req.message, requested_lang=req.language or "en"
    )

    # 2. Run existing ORCA intelligence & RAG pipeline untouched
    result = agent.process_query(
        query=english_query,
        context=ctx_dict,
        session_id=req.session_id or "default",
    )

    # 3. Translate response message & cards back into effective language if non-English
    if effective_lang and effective_lang != "en":
        result = i18n_service.translate_agent_response(
            result, target_lang=effective_lang, user_query=req.message
        )

    return AgentChatResponse(
        session_id=result["session_id"],
        message=result["message"],
        reply=result["message"],
        language=effective_lang or "en",
        data=result.get("data", []),
        actions=result.get("actions", []),
        tool_calls=[],
        spots=result.get("spots", []),
        selected_spot_index=result.get("selected_spot_index", 0),
        origin_port=result.get("origin_port"),
    )


@app.post("/api/v1/agent/stt")
@app.post("/agent/stt")
async def agent_stt(
    request: Request,
    lang: str = Query("en", description="Language code (en, hi, hinglish, mr, gu, ml, ta, te, kn, bn, pa, or)"),
    partial: bool = Query(False, description="True when streaming live partial chunks while speaking"),
) -> dict:
    import asyncio
    from . import i18n_service

    wav_bytes = await request.body()
    if not wav_bytes or len(wav_bytes) < 100:
        raise HTTPException(status_code=400, detail="Empty audio payload.")
    try:
        transcript = await asyncio.to_thread(
            i18n_service.transcribe_wav_bytes, wav_bytes, lang, partial
        )
        return {"success": True, "transcript": transcript, "language": lang, "partial": partial}
    except ValueError as exc:
        return {"success": False, "transcript": "", "detail": str(exc), "language": lang, "partial": partial}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Speech recognition error: {exc}")


@app.get("/api/v1/agent/tts")
@app.get("/agent/tts")
def agent_tts(
    text: str = Query(..., description="Text to synthesize into speech"),
    lang: str = Query("en", description="Language code (en, hi, hinglish, mr, gu, ml, ta, te, kn, bn, pa, or)"),
):
    from fastapi.responses import Response
    from . import i18n_service

    mp3_bytes = i18n_service.synthesize_speech_mp3(text=text, lang=lang)
    if not mp3_bytes:
        raise HTTPException(status_code=503, detail="Text-to-speech synthesis unavailable for the requested text/language.")
    return Response(content=mp3_bytes, media_type="audio/mpeg")


@app.post("/api/v1/i18n/translate")
def translate_batch_endpoint(payload: dict) -> dict:
    from . import i18n_service

    target_lang = str(payload.get("target_lang", "en")).strip().lower()
    texts = payload.get("texts", [])
    if not isinstance(texts, list):
        raise HTTPException(status_code=422, detail="'texts' must be a list of strings.")
    translated = [i18n_service.translate_text(str(t), target_lang) for t in texts]
    return {"target_lang": target_lang, "translations": translated}


@app.get("/api/v1/sea-conditions")
@app.get("/sea-conditions")
def get_sea_conditions_endpoint(
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    port: Optional[str] = None
):
    from orca_forecasting.service import agent_tools
    return agent_tools.get_sea_conditions(lat=lat, lon=lon, port_name=port)


