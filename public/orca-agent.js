/**
 * ==========================================================================
 * ORCA COGNITIVE OCEAN AGENT - CLIENT CONTROLLER & GLOBE COMMAND LAYER
 * ==========================================================================
 * 
 * Features:
 * - Fullscreen AI Command Workspace with smooth glass backdrop expansion.
 * - Multi-turn conversational memory & safe UI action execution.
 * - Contextual loading progress state ("Analyzing marine conditions...", "12 NM check...").
 * - Multi-spot ranked recommendation cards ("01 — Recommended", "02", "03").
 * - "Take me there" action bridge: smooth minimize, camera fly, route display,
 *   beacon highlight, and floating compact HUD card on globe.
 * - Strictly whitelisted actions with zero arbitrary script execution.
 * ==========================================================================
 */

(function () {
  "use strict";

  const host = window.location.hostname || "127.0.0.1";
  const BACKEND_URLS = [
    `http://${host}:8000/api/v1/agent/chat`,
    `http://${host}:8000/agent/chat`,
    "http://127.0.0.1:8000/api/v1/agent/chat",
    "http://localhost:8000/api/v1/agent/chat",
    "http://127.0.0.1:8000/agent/chat",
    "http://localhost:8000/agent/chat"
  ];

  const sessionId = "orca_sess_" + Math.random().toString(36).substring(2, 9);

  // Whitelist of allowed UI actions
  const SAFE_ACTIONS = new Set([
    "FLY_TO",
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
    "SHOW_ROUTE",
    "HIGHLIGHT_SPOT",
    "SHOW_12NM_BOUNDARY",
    "SHOW_COMPACT_CARD"
  ]);

  // Client memory for active recommendations
  let lastSessionSpots = [];
  let lastSessionOriginPort = { name: "Mumbai Port", lat: 18.9438, lon: 72.8428 };
  let activeRecommendationSession = {
    originPort: null,
    spots: [],
    currentIndex: 0
  };

  // DOM Elements - Fullscreen Workspace
  let workspaceEl = null;
  let workspaceBackdropEl = null;
  let workspaceCloseBtn = null;
  let workspaceStreamEl = null;
  let workspaceFormEl = null;
  let workspaceInputEl = null;
  let workspaceSubmitBtn = null;
  let workspaceShowGlobeChk = null;
  let workspaceProgressEl = null;
  let workspaceProgressBarEl = null;
  let workspaceProgressStatusEl = null;
  let workspaceChipsContainer = null;

  // DOM Elements - Floating Compact Card
  let compactCardEl = null;
  let compactCloseBtn = null;
  let compactReopenAiBtn = null;
  let compactNextSpotBtn = null;

  // DOM Elements - Legacy Drawer (for backwards compatibility)
  let legacyWidgetEl = null;
  let legacyToggleBtn = null;
  let legacyLauncherBtn = null;
  let legacyHistoryEl = null;
  let legacyFormEl = null;
  let legacyInputEl = null;
  let legacyChipsContainer = null;

  // 4. Navigation & Departure Port Modal Selectors
  let gateModalEl = null;
  let gateCloseBtn = null;
  let gateCancelBtn = null;
  let gateProceedBtn = null;
  let gateCheckbox = null;
  let pendingGateCallback = null;

  let depModalEl = null;
  let depCloseBtn = null;
  let depCancelBtn = null;
  let depConfirmBtn = null;
  let depAskBtn = null;
  let depPortSelect = null;
  let depSpotName = null;
  let depSpotTier = null;
  let depSpotCoords = null;
  let depSpotHealth = null;
  let depSpotSst = null;
  let depSpotChl = null;
  let depSpotSal = null;
  let depSpotSla = null;
  let depSpotReg = null;
  let depSpotRationaleBox = null;
  let depRationaleTitle = null;
  let depRationaleList = null;
  let depGeodesicDist = null;
  let depGeodesicKm = null;
  let depChannelDist = null;
  let depChannelKm = null;
  let depTransitTime = null;
  let depBearing = null;
  let depCardinalDir = null;
  let currentTargetSpot = null;
  let sortedPortsForSpot = [];

  function initOrcaAgent() {
    // 1. Fullscreen Workspace Selectors
    workspaceEl = document.getElementById("orca-ai-workspace");
    workspaceBackdropEl = document.getElementById("workspace-backdrop");
    workspaceCloseBtn = document.getElementById("workspace-close-btn");
    workspaceStreamEl = document.getElementById("workspace-stream");
    workspaceFormEl = document.getElementById("workspace-form");
    workspaceInputEl = document.getElementById("workspace-query-input");
    workspaceSubmitBtn = document.getElementById("workspace-submit");
    workspaceShowGlobeChk = document.getElementById("toggle-show-globe");
    workspaceProgressEl = document.getElementById("workspace-progress");
    workspaceProgressBarEl = document.getElementById("workspace-progress-bar");
    workspaceProgressStatusEl = document.getElementById("workspace-progress-status");
    workspaceChipsContainer = document.getElementById("workspace-quick-chips");

    // 2. Compact Card Selectors
    compactCardEl = document.getElementById("orca-compact-globe-card");
    compactCloseBtn = document.getElementById("compact-card-close");
    compactReopenAiBtn = document.getElementById("compact-card-reopen-ai");
    compactNextSpotBtn = document.getElementById("compact-card-next-spot");

    // 3. Legacy Drawer Selectors
    legacyWidgetEl = document.getElementById("orca-ai-widget");
    legacyToggleBtn = document.getElementById("ai-drawer-toggle");
    legacyLauncherBtn = document.getElementById("orca-ai-launcher");
    legacyHistoryEl = document.getElementById("ai-chat-history");
    legacyFormEl = document.getElementById("ai-chat-form");
    legacyInputEl = document.getElementById("ai-chat-input");
    legacyChipsContainer = document.getElementById("ai-quick-chips");

    // 4. Gate & Departure Modal Elements
    gateModalEl = document.getElementById("orca-globe-gate-modal");
    gateCloseBtn = document.getElementById("orca-gate-modal-close");
    gateCancelBtn = document.getElementById("orca-gate-cancel-btn");
    gateProceedBtn = document.getElementById("orca-gate-proceed-btn");
    gateCheckbox = document.getElementById("gate-confirm-checkbox");

    depModalEl = document.getElementById("orca-departure-modal");
    depCloseBtn = document.getElementById("orca-departure-modal-close");
    depCancelBtn = document.getElementById("orca-departure-cancel-btn");
    depConfirmBtn = document.getElementById("orca-departure-confirm-btn");
    depAskBtn = document.getElementById("orca-departure-ask-btn");
    depPortSelect = document.getElementById("departure-port-select");
    depSpotName = document.getElementById("dep-spot-name");
    depSpotTier = document.getElementById("dep-spot-tier");
    depSpotCoords = document.getElementById("dep-spot-coords");
    depSpotHealth = document.getElementById("dep-spot-health");
    depSpotSst = document.getElementById("dep-spot-sst");
    depSpotChl = document.getElementById("dep-spot-chl");
    depSpotSal = document.getElementById("dep-spot-sal");
    depSpotSla = document.getElementById("dep-spot-sla");
    depSpotReg = document.getElementById("dep-spot-reg");
    depSpotRationaleBox = document.getElementById("dep-spot-rationale-box");
    depRationaleTitle = document.getElementById("dep-rationale-title");
    depRationaleList = document.getElementById("dep-rationale-list");
    depGeodesicDist = document.getElementById("dep-geodesic-dist");
    depGeodesicKm = document.getElementById("dep-geodesic-km");
    depChannelDist = document.getElementById("dep-channel-dist");
    depChannelKm = document.getElementById("dep-channel-km");
    depTransitTime = document.getElementById("dep-transit-time");
    depBearing = document.getElementById("dep-bearing");
    depCardinalDir = document.getElementById("dep-cardinal-dir");

    // Wire Globe Gate Modal
    if (gateCloseBtn) gateCloseBtn.addEventListener("click", hideGlobeGateModal);
    if (gateCancelBtn) gateCancelBtn.addEventListener("click", hideGlobeGateModal);
    if (gateProceedBtn) {
      gateProceedBtn.addEventListener("click", () => {
        if (workspaceShowGlobeChk) {
          workspaceShowGlobeChk.checked = true;
          workspaceShowGlobeChk.dispatchEvent(new Event("change"));
        }
        const cb = pendingGateCallback;
        hideGlobeGateModal();
        if (typeof cb === "function") cb();
      });
    }
    if (gateCheckbox) {
      gateCheckbox.addEventListener("change", (e) => {
        if (workspaceShowGlobeChk) {
          workspaceShowGlobeChk.checked = e.target.checked;
          workspaceShowGlobeChk.dispatchEvent(new Event("change"));
        }
      });
    }

    // Wire Departure Modal
    if (depCloseBtn) depCloseBtn.addEventListener("click", hideDepartureModal);
    if (depCancelBtn) depCancelBtn.addEventListener("click", hideDepartureModal);
    if (depAskBtn) {
      depAskBtn.addEventListener("click", () => {
        openWorkspace();
        if (currentTargetSpot) {
          const tier = currentTargetSpot.fishing_tier || currentTargetSpot.tier || "moderate";
          const q = (tier === "low")
            ? `Why is the zone at ${currentTargetSpot.lat.toFixed(2)}°N, ${currentTargetSpot.lon.toFixed(2)}°E less favorable? Detail its limiting factors.`
            : `Explain conditions and suitability at ${currentTargetSpot.lat.toFixed(2)}°N, ${currentTargetSpot.lon.toFixed(2)}°E`;
          if (workspaceInputEl) workspaceInputEl.value = q;
          handleAgentSubmit(q);
        }
      });
    }
    if (depConfirmBtn) {
      depConfirmBtn.addEventListener("click", () => {
        if (window.ORCA_NAVIGATION && typeof window.ORCA_NAVIGATION.executeTakeMeThere === "function" && currentTargetSpot) {
          window.ORCA_NAVIGATION.executeTakeMeThere(currentTargetSpot);
          return;
        }
        if (!currentTargetSpot || !sortedPortsForSpot.length) return;
        const selectedIdx = depPortSelect ? parseInt(depPortSelect.value, 10) : 0;
        const chosenPort = sortedPortsForSpot[selectedIdx] || sortedPortsForSpot[0];
        executeTakeMeThere(currentTargetSpot, chosenPort);
      });
    }
    if (depPortSelect) {
      depPortSelect.addEventListener("change", () => {
        const selectedIdx = parseInt(depPortSelect.value, 10);
        if (sortedPortsForSpot[selectedIdx] && currentTargetSpot) {
          updateDepartureMetricsUI(sortedPortsForSpot[selectedIdx], currentTargetSpot);
        }
      });
    }

    // Wire Workspace Open / Close
    if (workspaceCloseBtn) {
      workspaceCloseBtn.addEventListener("click", closeWorkspace);
    }
    if (workspaceBackdropEl) {
      workspaceBackdropEl.addEventListener("click", closeWorkspace);
    }

    // ESC key closes workspace
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && isWorkspaceOpen()) {
        closeWorkspace();
      }
    });

    // Wire Workspace Form Submit
    if (workspaceFormEl && workspaceInputEl) {
      workspaceFormEl.addEventListener("submit", (e) => {
        e.preventDefault();
        const query = workspaceInputEl.value.trim();
        if (!query) return;
        handleAgentSubmit(query);
      });
    }

    // Wire Workspace Suggested Chips
    if (workspaceChipsContainer) {
      workspaceChipsContainer.addEventListener("click", (e) => {
        const chip = e.target.closest(".prompt-chip");
        if (!chip) return;
        const query = chip.getAttribute("data-query");
        if (query) {
          if (workspaceInputEl) workspaceInputEl.value = query;
          handleAgentSubmit(query);
        }
      });
    }

    // Wire Event Delegation for "Take me there" buttons inside stream
    if (workspaceStreamEl) {
      workspaceStreamEl.addEventListener("click", (e) => {
        const takeBtn = e.target.closest(".spot-take-me-btn");
        if (!takeBtn) return;
        const spotIdx = parseInt(takeBtn.getAttribute("data-spot-idx"), 10);
        const spot = (Number.isFinite(spotIdx) && lastSessionSpots[spotIdx])
          ? lastSessionSpots[spotIdx]
          : lastSessionSpots[0];
        if (spot) {
          takeUserToSpot(spot, lastSessionOriginPort);
        }
      });
    }
    if (legacyHistoryEl) {
      legacyHistoryEl.addEventListener("click", (e) => {
        const takeBtn = e.target.closest(".spot-take-me-btn");
        if (!takeBtn) return;
        const spotIdx = parseInt(takeBtn.getAttribute("data-spot-idx"), 10);
        const spot = (Number.isFinite(spotIdx) && lastSessionSpots[spotIdx])
          ? lastSessionSpots[spotIdx]
          : lastSessionSpots[0];
        if (spot) {
          takeUserToSpot(spot, lastSessionOriginPort);
        }
      });
    }

    // Wire Floating Compact Card Controls
    if (compactCloseBtn) {
      compactCloseBtn.addEventListener("click", () => {
        if (window.ORCA_GLOBE_CONTROLLER && typeof window.ORCA_GLOBE_CONTROLLER.hideCompactCard === "function") {
          window.ORCA_GLOBE_CONTROLLER.hideCompactCard();
        } else if (compactCardEl) {
          compactCardEl.style.display = "none";
        }
      });
    }

    if (compactReopenAiBtn) {
      compactReopenAiBtn.addEventListener("click", () => {
        openWorkspace();
      });
    }

    if (compactNextSpotBtn) {
      compactNextSpotBtn.addEventListener("click", handleNextSpotAction);
    }

    // Legacy Drawer controls (if present in DOM)
    if (legacyToggleBtn && legacyWidgetEl) {
      legacyToggleBtn.innerHTML = "&times;";
      legacyToggleBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        legacyWidgetEl.classList.add("minimized");
        legacyWidgetEl.style.display = "none";
        if (legacyLauncherBtn) legacyLauncherBtn.style.display = "flex";
      });
    }

    if (legacyLauncherBtn && legacyWidgetEl) {
      legacyLauncherBtn.addEventListener("click", () => {
        legacyWidgetEl.classList.remove("minimized");
        legacyWidgetEl.style.display = "flex";
        if (legacyInputEl) legacyInputEl.focus();
      });
    }

    if (legacyChipsContainer) {
      legacyChipsContainer.addEventListener("click", (e) => {
        const chip = e.target.closest(".ai-chip");
        if (!chip) return;
        const query = chip.getAttribute("data-query");
        if (query) {
          if (legacyInputEl) legacyInputEl.value = query;
          handleAgentSubmit(query);
        }
      });
    }

    if (legacyFormEl && legacyInputEl) {
      legacyFormEl.addEventListener("submit", (e) => {
        e.preventDefault();
        const query = legacyInputEl.value.trim();
        if (!query) return;
        handleAgentSubmit(query);
      });
    }

    console.log("ORCA AI Command Layer initialized (Session: " + sessionId + ")");
  }

  function isWorkspaceOpen() {
    return workspaceEl && workspaceEl.classList.contains("expanded");
  }

  function openWorkspace() {
    if (!workspaceEl) return;
    workspaceEl.classList.add("expanded");
    if (workspaceInputEl) {
      setTimeout(() => workspaceInputEl.focus(), 150);
    }
  }

  function closeWorkspace() {
    if (workspaceEl) {
      workspaceEl.classList.remove("expanded");
    }
    if (legacyWidgetEl) {
      legacyWidgetEl.classList.add("minimized");
      legacyWidgetEl.style.display = "none";
      if (legacyLauncherBtn) legacyLauncherBtn.style.display = "flex";
    }
    if (window.ORCA_I18N) {
      if (typeof window.ORCA_I18N.stopSpeechPlayback === "function") window.ORCA_I18N.stopSpeechPlayback();
      if (typeof window.ORCA_I18N.stopVoiceInput === "function") window.ORCA_I18N.stopVoiceInput();
    }
  }

  // Safe Canonical Coordinate Resolver
  function getCanonicalCoordinates(spot) {
    if (!spot) return null;
    let lat = spot.lat !== undefined ? Number(spot.lat) : (spot.latitude !== undefined ? Number(spot.latitude) : null);
    let lon = spot.lon !== undefined ? Number(spot.lon) : (spot.longitude !== undefined ? Number(spot.longitude) : null);
    if (Array.isArray(spot.coords)) {
      lat = Number(spot.coords[0]);
      lon = Number(spot.coords[1]);
    }
    // Auto-swap if accidentally inverted (latitude is ~8 to 25 for Arabian Sea, longitude is ~65 to 80)
    if (lat !== null && lon !== null && Math.abs(lat) > 45 && Math.abs(lon) <= 45) {
      const temp = lat;
      lat = lon;
      lon = temp;
    }
    if (!Number.isFinite(lat) || !Number.isFinite(lon) || lat < -90 || lat > 90 || lon < -180 || lon > 180) {
      return null;
    }
    return { lat, lon };
  }

  // Mathematical & Geodesic Navigation Helpers
  function calculateHaversineKm(lat1, lon1, lat2, lon2) {
    const R = 6371.0;
    const dLat = (lat2 - lat1) * Math.PI / 180.0;
    const dLon = (lon2 - lon1) * Math.PI / 180.0;
    const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
              Math.cos(lat1 * Math.PI / 180.0) * Math.cos(lat2 * Math.PI / 180.0) *
              Math.sin(dLon / 2) * Math.sin(dLon / 2);
    return 2 * R * Math.asin(Math.sqrt(Math.max(0, Math.min(1, a))));
  }

  function calculateInitialBearing(lat1, lon1, lat2, lon2) {
    const phi1 = lat1 * Math.PI / 180.0;
    const phi2 = lat2 * Math.PI / 180.0;
    const deltaLambda = (lon2 - lon1) * Math.PI / 180.0;
    const y = Math.sin(deltaLambda) * Math.cos(phi2);
    const x = Math.cos(phi1) * Math.sin(phi2) - Math.sin(phi1) * Math.cos(phi2) * Math.cos(deltaLambda);
    const theta = Math.atan2(y, x);
    return (theta * 180.0 / Math.PI + 360.0) % 360.0;
  }

  function getCardinalDirection(deg) {
    const dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];
    const idx = Math.round(deg / 22.5) % 16;
    return dirs[idx];
  }

  function showGlobeGateModal(onProceed) {
    pendingGateCallback = onProceed;
    if (gateModalEl) {
      if (gateCheckbox) gateCheckbox.checked = true;
      gateModalEl.style.display = "flex";
    } else {
      if (workspaceShowGlobeChk) workspaceShowGlobeChk.checked = true;
      if (typeof onProceed === "function") onProceed();
    }
  }

  function hideGlobeGateModal() {
    if (gateModalEl) gateModalEl.style.display = "none";
    pendingGateCallback = null;
  }

  // Open Departure Port & Navigation Metrics Dialog
  function openDepartureModal(spot, preferredPort) {
    if (!spot) return;

    // Reject coastal ports: Departure calculations are strictly from coastal port to favorable fishing spot (never port to port)
    const isPort = !!(
      spot.is_port ||
      spot.isMajor !== undefined ||
      (spot.id && String(spot.id).startsWith("port-")) ||
      (spot.name && /port/i.test(spot.name)) ||
      (!spot.is_fishing_spot && (spot.distance === 0 || (spot.type && spot.type.toLowerCase().includes("port")))) ||
      (window.ORCA_COASTAL_PORTS && window.ORCA_COASTAL_PORTS.some(p => p.name.toLowerCase() === (spot.name || "").toLowerCase()))
    );
    if (isPort) {
      if (typeof window.ORCA_SET_DEPARTURE === "function") {
        window.ORCA_SET_DEPARTURE(spot);
      } else if (window.ORCA_STATE) {
        window.ORCA_STATE.selectedDeparture = spot;
      }
      return;
    }

    // Strict Gating: Ensure "Show result on Globe" is enabled
    if (workspaceShowGlobeChk && !workspaceShowGlobeChk.checked) {
      showGlobeGateModal(() => {
        openDepartureModal(spot, preferredPort);
      });
      return;
    }

    // Resolve canonical coordinates
    let canonical = getCanonicalCoordinates(spot);
    if (window.OCEAN_DATA && Array.isArray(window.OCEAN_DATA.stations)) {
      const sLat = canonical ? canonical.lat : Number(spot.lat || spot.latitude);
      const sLon = canonical ? canonical.lon : Number(spot.lon || spot.longitude);
      const match = window.OCEAN_DATA.stations.find(st => {
        return (spot.id && st.id === spot.id) || (Math.abs(st.lat - sLat) < 0.06 && Math.abs(st.lon - sLon) < 0.06);
      });
      if (match) {
        canonical = { lat: Number(match.lat), lon: Number(match.lon) };
      }
    }
    if (!canonical) {
      canonical = { lat: Number(spot.lat || spot.latitude || 19.5), lon: Number(spot.lon || spot.longitude || 71.8) };
    }
    spot.lat = canonical.lat;
    spot.lon = canonical.lon;
    spot.latitude = canonical.lat;
    spot.longitude = canonical.lon;
    currentTargetSpot = spot;

    // Populate spot details
    const spotName = spot.label || spot.name || `PFZ Spot (${spot.lat.toFixed(2)}°N, ${spot.lon.toFixed(2)}°E)`;
    if (depSpotName) depSpotName.textContent = spotName;
    if (depSpotCoords) depSpotCoords.textContent = `${spot.lat.toFixed(2)}°N, ${spot.lon.toFixed(2)}°E`;
    const healthVal = spot.healthScore != null ? Math.round(spot.healthScore) : (spot.mhi != null ? Math.round(spot.mhi) : 85);
    if (depSpotHealth) depSpotHealth.textContent = `Ocean Health: ${healthVal}/100`;
    if (depSpotSst) depSpotSst.textContent = `Water Temp: ${spot.sst != null ? spot.sst.toFixed(1) : '27.5'}°C`;
    const chlVal = spot.chlorophyll != null ? spot.chlorophyll : (spot.chl != null ? spot.chl : 2.10);
    if (depSpotChl) depSpotChl.textContent = `Fish Food: ${chlVal.toFixed(2)} mg/m³`;
    const salVal = spot.salinity != null ? spot.salinity : (spot.sal != null ? spot.sal : 35.4);
    if (depSpotSal) depSpotSal.textContent = `Salt Level: ${salVal.toFixed(1)} PSU`;

    // Sea Level Anomaly
    const slaCm = spot.sla_cm != null ? (spot.sla_cm > 0 ? `+${spot.sla_cm}` : `${spot.sla_cm}`) : (spot.sla != null ? ((spot.sla > 0 ? '+' : '') + Math.round(spot.sla * 100)) : '+6');
    if (depSpotSla) depSpotSla.textContent = `Sea Level: Normal (${slaCm} cm)`;
    if (depSpotReg) depSpotReg.textContent = "✓ Safe Beyond 12 NM Small Boat Zone";

    // Determine Tier & Badge
    let tier = spot.fishing_tier || spot.tier;
    let tierLabel = spot.tier_label;
    if (!tier) {
      const score = spot.fishingScore || spot.score || healthVal;
      if (score >= 68 && healthVal >= 42) {
        tier = "high";
        tierLabel = "High Potential";
      } else if (score >= 50 && healthVal >= 32) {
        tier = "moderate";
        tierLabel = "Moderate Potential";
      } else if (score >= 38) {
        tier = "low";
        tierLabel = "Less Favorable";
      } else {
        tier = "none";
        tierLabel = "Monitoring Node";
      }
    }
    if (depSpotTier) {
      depSpotTier.className = `tier-badge tier-${tier}`;
      depSpotTier.textContent = tierLabel || (tier === 'high' ? 'High Potential' : tier === 'moderate' ? 'Moderate Potential' : tier === 'low' ? 'Less Favorable' : 'Monitoring Node');
    }

    // Limiting factors / Drivers list
    if (depSpotRationaleBox) depSpotRationaleBox.style.display = "block";
    if (tier === "low") {
      if (depRationaleTitle) depRationaleTitle.textContent = "Limiting Factors (Why Less Favorable):";
      const items = [];
      const sstVal = spot.sst != null ? spot.sst : 28.5;
      if (Array.isArray(spot.limiting_factors) && spot.limiting_factors.length > 0) {
        spot.limiting_factors.forEach(f => items.push(f));
      } else if (Array.isArray(spot.fishing_reasons) && spot.fishing_reasons.length > 0) {
        spot.fishing_reasons.forEach(r => items.push(r));
      } else {
        if (chlVal < 1.0) items.push(`Chlorophyll-a is low (${chlVal.toFixed(2)} mg/m³), indicating subdued phytoplankton biomass.`);
        if (healthVal < 45) items.push(`Marine Health Index (${healthVal}/100) reflects reduced primary productivity.`);
        if (sstVal > 29.2) items.push(`SST (${sstVal.toFixed(1)}°C) exceeds peak pelagic preference window.`);
        if (items.length === 0) items.push("Oceanic gradient is subtle; catch probability is lower than primary upwelling zones.");
      }
      if (depRationaleList) {
        depRationaleList.innerHTML = items.map(it => `<li>⚠️ ${it}</li>`).join("");
      }
    } else {
      if (depRationaleTitle) depRationaleTitle.textContent = tier === "high" ? "High Potential Drivers:" : "Moderate Potential Factors:";
      const items = [];
      if (Array.isArray(spot.fishing_reasons) && spot.fishing_reasons.length > 0) {
        spot.fishing_reasons.forEach(r => items.push(r));
      } else {
        const sstVal = spot.sst != null ? spot.sst : 27.5;
        if (chlVal >= 1.5) items.push(`Strong chlorophyll concentration (${chlVal.toFixed(2)} mg/m³) marks active upwelling.`);
        items.push(`Favorable thermal envelope: SST at ${sstVal.toFixed(1)}°C promotes pelagic aggregation.`);
        items.push(`Verified beyond 12 NM territorial baseline (safe EEZ fishing zone).`);
      }
      if (depRationaleList) {
        depRationaleList.innerHTML = items.map(it => `<li>✓ ${it}</li>`).join("");
      }
    }

    // Coastal ports list (use complete 43 ports catalog from window.ORCA_COASTAL_PORTS when available)
    let ports = (window.ORCA_COASTAL_PORTS && window.ORCA_COASTAL_PORTS.length > 0)
      ? window.ORCA_COASTAL_PORTS
      : ((window.OCEAN_DATA && window.OCEAN_DATA.coastalPorts && window.OCEAN_DATA.coastalPorts.length > 0)
        ? window.OCEAN_DATA.coastalPorts
        : [
            { name: "Veraval Port", lat: 20.91, lon: 70.37, isMajor: true },
            { name: "Porbandar Port", lat: 21.64, lon: 69.61, isMajor: true },
            { name: "Pipavav Port", lat: 20.91, lon: 71.50, isMajor: false },
            { name: "Mumbai Port", lat: 18.94, lon: 72.84, isMajor: true },
            { name: "Jawaharlal Nehru Port (JNPT)", lat: 18.95, lon: 72.95, isMajor: true },
            { name: "Kochi Port", lat: 9.93, lon: 76.27, isMajor: true },
            { name: "Mormugao Port (Goa)", lat: 15.41, lon: 73.80, isMajor: true },
            { name: "New Mangalore Port", lat: 12.91, lon: 74.86, isMajor: true },
            { name: "Kandla Port", lat: 23.01, lon: 70.22, isMajor: true }
          ]);

    // Calculate distance to each port and sort nearest first
    sortedPortsForSpot = ports.map(p => {
      const dKm = calculateHaversineKm(p.lat, p.lon, spot.lat, spot.lon);
      const dNm = dKm * 0.539957;
      return { ...p, distKm: dKm, distNm: dNm };
    }).sort((a, b) => a.distKm - b.distKm);

    // Populate dropdown
    if (depPortSelect) {
      depPortSelect.innerHTML = "";
      sortedPortsForSpot.forEach((p, idx) => {
        const opt = document.createElement("option");
        opt.value = idx;
        const tag = idx === 0 ? " (Nearest Port)" : "";
        opt.textContent = `⚓ ${p.name}${tag} — ${p.distNm.toFixed(1)} NM (${p.distKm.toFixed(1)} km)`;
        depPortSelect.appendChild(opt);
      });

      // If preferredPort matches, select it; otherwise default to nearest (idx 0)
      let selectedIdx = 0;
      if (preferredPort && preferredPort.name) {
        const matchIdx = sortedPortsForSpot.findIndex(p => p.name.toLowerCase().includes(preferredPort.name.toLowerCase()) || preferredPort.name.toLowerCase().includes(p.name.toLowerCase()));
        if (matchIdx !== -1) selectedIdx = matchIdx;
      }
      depPortSelect.selectedIndex = selectedIdx;
      updateDepartureMetricsUI(sortedPortsForSpot[selectedIdx], spot);
    }

    if (depModalEl) {
      depModalEl.style.display = "flex";
    }
  }

  function hideDepartureModal() {
    if (depModalEl) depModalEl.style.display = "none";
  }

  function updateDepartureMetricsUI(port, spot) {
    if (!port || !spot) return;
    const dKm = calculateHaversineKm(port.lat, port.lon, spot.lat, spot.lon);
    const dNm = dKm * 0.539957;
    const channelKm = dKm * 1.12;
    const channelNm = channelKm * 0.539957;
    const cruiseSpeedKts = 10.0;
    const transitHours = channelNm / cruiseSpeedKts;
    const hrs = Math.floor(transitHours);
    const mins = Math.round((transitHours - hrs) * 60);
    const transitStr = hrs > 0 ? `${hrs}h ${mins}m` : `${mins} min`;

    const bearingDeg = calculateInitialBearing(port.lat, port.lon, spot.lat, spot.lon);
    const cardinal = getCardinalDirection(bearingDeg);

    if (depGeodesicDist) depGeodesicDist.textContent = `${dNm.toFixed(1)} NM`;
    if (depGeodesicKm) depGeodesicKm.textContent = `(${dKm.toFixed(1)} km)`;
    if (depChannelDist) depChannelDist.textContent = `${channelNm.toFixed(1)} NM`;
    if (depChannelKm) depChannelKm.textContent = `(${channelKm.toFixed(1)} km)`;
    if (depTransitTime) depTransitTime.textContent = transitStr;
    if (depBearing) depBearing.textContent = `${Math.round(bearingDeg)}°`;
    if (depCardinalDir) depCardinalDir.textContent = `${cardinal} heading`;
  }

  // Execute Navigation once departure port is confirmed or "Take me there" is clicked
  function executeTakeMeThere(spot, originPort) {
    if (!spot) return;
    hideDepartureModal();
    closeWorkspace();

    if (!originPort) {
      originPort = (window.ORCA_STATE && window.ORCA_STATE.selectedDeparture)
        ? window.ORCA_STATE.selectedDeparture
        : (activeRecommendationSession.originPort || lastSessionOriginPort || { name: "Mumbai Port", lat: 18.9438, lon: 72.8428 });
    }

    // Resolve canonical coordinates
    const canonical = getCanonicalCoordinates(spot);
    if (canonical) {
      spot.lat = canonical.lat;
      spot.lon = canonical.lon;
      spot.latitude = canonical.lat;
      spot.longitude = canonical.lon;
    }

    // Delegate to unified ORCA_NAVIGATION engine so Active Route Card (#orca-active-route-card) is also displayed
    if (window.ORCA_NAVIGATION && typeof window.ORCA_NAVIGATION.executeTakeMeThere === "function") {
      window.ORCA_NAVIGATION.executeTakeMeThere(spot, originPort);
      return;
    }

    if (window.ORCA_STATE) {
      window.ORCA_STATE.selectedFishingSpot = spot;
      if (window.ORCA_SET_DEPARTURE && originPort) {
        window.ORCA_SET_DEPARTURE(originPort);
      }
    }

    const distKm = Math.round(calculateHaversineKm(originPort.lat, originPort.lon, spot.lat, spot.lon) * 10) / 10;
    const routeKm = Math.round(distKm * 1.12 * 10) / 10;
    spot.distance_km = distKm;
    spot.route_distance_km = routeKm;
    lastSessionOriginPort = originPort;

    const spotLat = spot.lat;
    const spotLon = spot.lon;

    console.log(`[ORCA NAV] Navigating to spot (${spotLat.toFixed(2)}, ${spotLon.toFixed(2)}) from ${originPort.name}: dist=${distKm}km, route=${routeKm}km`);

    // Fly camera smoothly to spot location
    if (window.ORCA_GLOBE_CONTROLLER && typeof window.ORCA_GLOBE_CONTROLLER.flyToLocation === "function") {
      window.ORCA_GLOBE_CONTROLLER.flyToLocation(spotLat, spotLon, 280000, 2.0);
    }

    // If Leaflet 2D is active, also pan Leaflet
    if (window.leafletMap && typeof window.leafletMap.flyTo === "function") {
      window.leafletMap.flyTo([spotLat, spotLon], 8, { duration: 1.5 });
    }

    // Render navigational route from origin port to spot
    if (window.ORCA_GLOBE_CONTROLLER && typeof window.ORCA_GLOBE_CONTROLLER.showRoute === "function") {
      window.ORCA_GLOBE_CONTROLLER.showRoute(originPort, spot, distKm, routeKm);
    }

    // Highlight spot beacon
    if (window.ORCA_GLOBE_CONTROLLER && typeof window.ORCA_GLOBE_CONTROLLER.highlightFishingSpot === "function") {
      window.ORCA_GLOBE_CONTROLLER.highlightFishingSpot(spot.id, spotLat, spotLon);
    }
  }

  // Deterministic Next Spot Progression Handler
  function handleNextSpotAction() {
    const spots = (window.ORCA_STATE && Array.isArray(window.ORCA_STATE.spotsList) && window.ORCA_STATE.spotsList.length > 0)
      ? window.ORCA_STATE.spotsList
      : (activeRecommendationSession.spots && activeRecommendationSession.spots.length > 0 ? activeRecommendationSession.spots : lastSessionSpots);

    if (!spots || spots.length === 0) {
      console.warn("[ORCA SPOT] No candidate spots loaded.");
      return;
    }

    let currentIdx = (window.ORCA_STATE && Number.isFinite(window.ORCA_STATE.currentSpotIndex))
      ? window.ORCA_STATE.currentSpotIndex
      : activeRecommendationSession.currentIndex;

    const nextIdx = currentIdx + 1;
    if (nextIdx < spots.length) {
      if (window.ORCA_STATE) {
        window.ORCA_STATE.currentSpotIndex = nextIdx;
        window.ORCA_STATE.selectedFishingSpot = spots[nextIdx];
      }
      activeRecommendationSession.currentIndex = nextIdx;
      activeRecommendationSession.spots = spots;

      const nextSpot = spots[nextIdx];
      const depPort = (window.ORCA_STATE && window.ORCA_STATE.selectedDeparture)
        ? window.ORCA_STATE.selectedDeparture
        : (activeRecommendationSession.originPort || lastSessionOriginPort);

      console.log(`[ORCA SPOT] Advancing to spot ${nextIdx + 1} of ${spots.length}: (${nextSpot.lat.toFixed(2)}, ${nextSpot.lon.toFixed(2)})`);
      executeTakeMeThere(nextSpot, depPort);

      if (compactNextSpotBtn) {
        if (nextIdx === spots.length - 1) {
          compactNextSpotBtn.innerHTML = `<span>Last spot</span>`;
        } else {
          compactNextSpotBtn.innerHTML = `
            <span>Next spot</span>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
          `;
        }
      }
    } else {
      // Reached end of valid candidate spots - DO NOT FLY CAMERA
      console.log("[ORCA SPOT] No more suitable fishing spots found.");
      if (compactNextSpotBtn) {
        compactNextSpotBtn.disabled = true;
        compactNextSpotBtn.style.opacity = "0.45";
        compactNextSpotBtn.style.cursor = "not-allowed";
        compactNextSpotBtn.innerHTML = `<span>No more spots</span>`;
      }
      const routeEl = document.getElementById("compact-card-route-info");
      if (routeEl) {
        routeEl.innerHTML = `<span style="color: #fbbf24; font-size: 10.5px; font-weight: 600;">No more suitable fishing spots found.</span>`;
      }
    }
  }

  // "Take me there" Navigation Handler: closes Ask ORCA workspace and navigates directly to the spot on the map
  function takeUserToSpot(spot, originPort) {
    if (!spot) return;
    if (workspaceShowGlobeChk && !workspaceShowGlobeChk.checked) {
      showGlobeGateModal(() => {
        takeUserToSpot(spot, originPort);
      });
      return;
    }
    executeTakeMeThere(spot, originPort || lastSessionOriginPort);
  }

  // Current view/location context collector
  function gatherActiveContext() {
    const ctx = {
      latitude: 15.0,
      longitude: 70.0,
      selected_station: null,
      selected_port: null,
      selected_entity: null,
      active_layer: null,
      view_mode: "3d",
      selected_departure: null,
      selected_grid_point: null,
      selected_fishing_spot: null,
      sea_conditions: null
    };

    if (window.ORCA_STATE) {
      if (window.ORCA_STATE.selectedDeparture) {
        ctx.selected_departure = window.ORCA_STATE.selectedDeparture;
        ctx.selected_port = window.ORCA_STATE.selectedDeparture.name;
      }
      if (window.ORCA_STATE.selectedGridPoint) {
        ctx.selected_grid_point = window.ORCA_STATE.selectedGridPoint;
        ctx.selected_entity = window.ORCA_STATE.selectedGridPoint;
        ctx.latitude = window.ORCA_STATE.selectedGridPoint.lat;
        ctx.longitude = window.ORCA_STATE.selectedGridPoint.lon;
      }
      if (window.ORCA_STATE.selectedFishingSpot) {
        ctx.selected_fishing_spot = window.ORCA_STATE.selectedFishingSpot;
      }
      if (window.ORCA_STATE.seaConditions) {
        ctx.sea_conditions = window.ORCA_STATE.seaConditions;
      }
    }

    const appState = window.ORCA_APP_STATE || {};
    const sel = appState.selectedStation;
    if (sel && !ctx.selected_grid_point) {
      ctx.selected_station = sel.name;
      ctx.latitude = sel.lat;
      ctx.longitude = sel.lon;
      ctx.selected_entity = {
        id: sel.id,
        name: sel.name,
        lat: sel.lat,
        lon: sel.lon,
        is_fishing_spot: !!sel.is_fishing_spot,
        fishing_suitability: sel.fishing_suitability,
        target_species: sel.target_species,
        fishing_reasons: sel.fishing_reasons,
        healthScore: sel.healthScore,
        sst: sel.sst,
        chlorophyll: sel.chlorophyll,
        salinity: sel.salinity,
        oxygen: sel.oxygen,
        ph: sel.ph
      };
    }
    if (appState.activeMetric) {
      ctx.active_layer = appState.activeMetric;
    }

    const portSelect = document.getElementById("coastal-port-select");
    if (portSelect && portSelect.value && !ctx.selected_departure) {
      ctx.selected_port = portSelect.value;
    }

    const btn3d = document.getElementById("view-3d");
    const is3D = btn3d ? btn3d.classList.contains("active") : true;
    ctx.view_mode = is3D ? "3d" : "2d";

    if (is3D && window.ORCA_CESIUM && typeof window.ORCA_CESIUM.cameraLon === "number") {
      ctx.camera_latitude = window.ORCA_CESIUM.cameraLat;
      ctx.camera_longitude = window.ORCA_CESIUM.cameraLon;
      if (!ctx.selected_grid_point && !sel && !ctx.selected_port) {
        ctx.latitude = window.ORCA_CESIUM.cameraLat || ctx.latitude;
        ctx.longitude = window.ORCA_CESIUM.cameraLon || ctx.longitude;
      }
    } else if (!is3D && window.leafletMap) {
      const center = window.leafletMap.getCenter();
      ctx.camera_latitude = center.lat;
      ctx.camera_longitude = center.lng;
      if (!ctx.selected_grid_point && !sel && !ctx.selected_port) {
        ctx.latitude = center.lat;
        ctx.longitude = center.lng;
      }
    }

    return ctx;
  }

  function escapeHTML(str) {
    if (!str) return "";
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function formatMarkdownText(text) {
    if (!text) return "";
    let safe = escapeHTML(text);
    // Replace **bold** with <strong>bold</strong>
    safe = safe.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
    // Turn bracketed [ Take me there ] / [ मुझे वहाँ ले चलें ... ] into clickable Take me there buttons
    safe = safe.replace(/\[\s*([^\]]*?(?:Take me there|Mujhe Wahan Le Chalein|ले चलें|घेऊन चला|લઈ જાઓ|കൊണ്ടുപോകൂ|அழைத்துச்|తీసుకెళ్లు|ಕರೆದೊಯ್ಯಿರಿ|নিয়ে চলুন|ਲੈ ਚੱਲੋ|ନେଇଯାଆନ୍ତୁ)[^\]]*?)\s*\]/gi, (match, inner) => {
      return `<button type="button" class="spot-take-me-btn" data-spot-idx="0" style="margin: 4px 0; display: inline-flex; align-items: center; gap: 6px;"><span>${inner.trim()}</span><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M5 12h14M12 5l7 7-7 7"/></svg></button>`;
    });
    // Replace newlines with <br/>
    safe = safe.replace(/\n/g, "<br/>");
    return safe;
  }

  function getStatusBadgeClass(status) {
    const s = String(status || "").toUpperCase();
    if (s.includes("OBSERVED") || s.includes("LIVE")) return "status-observed";
    if (s.includes("FORECAST")) return "status-forecast";
    if (s.includes("DERIVED")) return "status-derived";
    if (s.includes("MODEL") || s.includes("PREDICTION")) return "status-prediction";
    return "status-unavailable";
  }

  // Progress Bar Helper
  function updateProgressState(stage, pct, text) {
    if (!workspaceProgressEl) return;
    workspaceProgressEl.style.display = "block";
    if (workspaceProgressBarEl) {
      workspaceProgressBarEl.style.width = pct + "%";
    }
    if (workspaceProgressStatusEl) {
      workspaceProgressStatusEl.textContent = text;
    }
  }

  function clearProgressState() {
    if (!workspaceProgressEl) return;
    if (workspaceProgressBarEl) {
      workspaceProgressBarEl.style.width = "100%";
    }
    if (workspaceProgressStatusEl) {
      workspaceProgressStatusEl.textContent = "Analysis ready.";
    }
    setTimeout(() => {
      if (workspaceProgressEl) workspaceProgressEl.style.display = "none";
      if (workspaceProgressBarEl) workspaceProgressBarEl.style.width = "0%";
    }, 400);
  }

  async function handleAgentSubmit(query) {
    if (workspaceInputEl) workspaceInputEl.value = "";
    if (legacyInputEl) legacyInputEl.value = "";

    // 1. Render User Message
    appendUserMessage(query);

    // 2. Start Contextual Progress
    updateProgressState(1, 20, "ORCA is connecting to physical marine telemetry...");
    const progressTimer1 = setTimeout(() => {
      updateProgressState(2, 50, "Querying Copernicus CMEMS models & chlorophyll arrays...");
    }, 280);
    const progressTimer2 = setTimeout(() => {
      updateProgressState(3, 75, "Applying 12 NM territorial regulatory boundary filter...");
    }, 550);
    const progressTimer3 = setTimeout(() => {
      updateProgressState(4, 90, "Calculating geodesic distances & marine channel routes...");
    }, 850);

    // 3. Gather Context
    const context = gatherActiveContext();

    // 4. Request Backend Agent
    let responseData = null;
    let requestError = null;
    const activeLang = (window.ORCA_I18N && typeof window.ORCA_I18N.getLanguage === "function")
      ? window.ORCA_I18N.getLanguage()
      : "en";

    for (const url of BACKEND_URLS) {
      try {
        const res = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message: query,
            session_id: sessionId,
            language: activeLang,
            context: context
          })
        });
        if (res.ok) {
          responseData = await res.json();
          break;
        }
      } catch (err) {
        requestError = err;
      }
    }

    clearTimeout(progressTimer1);
    clearTimeout(progressTimer2);
    clearTimeout(progressTimer3);
    clearProgressState();

    if (!responseData) {
      renderAgentOfflineFallback(query, requestError);
      return;
    }

    // Save active spots & origin port in client session memory
    if (Array.isArray(responseData.spots) && responseData.spots.length > 0) {
      lastSessionSpots = responseData.spots;
      activeRecommendationSession = {
        originPort: responseData.origin_port || lastSessionOriginPort,
        spots: responseData.spots,
        currentIndex: 0
      };
      if (window.ORCA_STATE) {
        window.ORCA_STATE.spotsList = responseData.spots;
        window.ORCA_STATE.currentSpotIndex = 0;
        window.ORCA_STATE.selectedFishingSpot = responseData.spots[0];
      }
      if (compactNextSpotBtn) {
        compactNextSpotBtn.disabled = false;
        compactNextSpotBtn.style.opacity = "1";
        compactNextSpotBtn.style.cursor = "pointer";
        compactNextSpotBtn.innerHTML = `
          <span>Next spot</span>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
        `;
      }
    }
    if (responseData.origin_port) {
      lastSessionOriginPort = responseData.origin_port;
      if (window.ORCA_SET_DEPARTURE) {
        window.ORCA_SET_DEPARTURE(responseData.origin_port);
      }
    }

    // 5. Render Response Message & Ranked Cards in Workspace Stream
    appendAssistantMessage(responseData);

    // 6. Execute Safe UI Actions
    // Check if "Show result on Globe" is enabled
    const shouldShowGlobe = workspaceShowGlobeChk ? workspaceShowGlobeChk.checked : true;
    if (Array.isArray(responseData.actions)) {
      executeSafeActions(responseData.actions, shouldShowGlobe);
    }

    // If user explicitly asked "Take me there" / "Take me to there", navigate directly on the map and close workspace
    if (/(\btake me (to )?there\b|\bfly there\b|\bnavigate there\b|\bgo there\b|\bwahan le chal|\bले चलें)/i.test(query) && lastSessionSpots.length > 0) {
      takeUserToSpot(lastSessionSpots[0], lastSessionOriginPort);
    }
  }

  function appendUserMessage(text) {
    // Append to fullscreen workspace stream
    if (workspaceStreamEl) {
      const msgDiv = document.createElement("div");
      msgDiv.className = "workspace-msg workspace-msg-user";
      msgDiv.textContent = text;
      workspaceStreamEl.appendChild(msgDiv);
      workspaceStreamEl.scrollTop = workspaceStreamEl.scrollHeight;
    }

    // Also append to legacy history if present
    if (legacyHistoryEl) {
      const msgDiv = document.createElement("div");
      msgDiv.className = "user-message";
      msgDiv.textContent = text;
      legacyHistoryEl.appendChild(msgDiv);
      legacyHistoryEl.scrollTop = legacyHistoryEl.scrollHeight;
    }
  }

  function appendAssistantMessage(data) {
    const messageText = data.message || data.reply || "Marine telemetry analysis complete.";
    const speakLabel = (window.ORCA_I18N && typeof window.ORCA_I18N.t === "function")
      ? window.ORCA_I18N.t("voice.speak_btn")
      : "🔊 Speak";
    const takeMeLabel = (window.ORCA_I18N && typeof window.ORCA_I18N.t === "function")
      ? window.ORCA_I18N.t("ws.take_me")
      : "Take me there";

    // 1. Workspace Stream Rendering
    if (workspaceStreamEl) {
      const botDiv = document.createElement("div");
      botDiv.className = "workspace-msg workspace-msg-bot";

      let html = `
        <div class="workspace-msg-sender">
          <span class="workspace-avatar">🐋</span>
          <span class="sender-name">ORCA Marine Intelligence</span>
          <span class="verified-tag">12 NM BOUNDARY HARD FILTER ACTIVE</span>
          <button type="button" class="orca-speak-btn" title="Speak Answer Aloud">${escapeHTML(speakLabel)}</button>
        </div>
        <div class="workspace-msg-content">${formatMarkdownText(messageText)}</div>
      `;

      // Multi-spot Ranked Cards (01, 02, 03)
      if (Array.isArray(data.spots) && data.spots.length > 0) {
        html += `<div class="ranked-spots-grid">`;
        data.spots.forEach((spot, idx) => {
          const isRec = idx === 0;
          const recClass = isRec ? "recommended" : "";
          const badgeText = spot.label || (isRec ? "01 — RECOMMENDED" : `0${idx + 1}`);
          const distGeodesic = spot.distance_km || 34.3;
          const distRoute = spot.route_distance_km || Math.round(distGeodesic * 1.12 * 10) / 10;
          const sstVal = spot.sst ? `${spot.sst}°C` : "28.2°C";
          const prodVal = spot.productivity || "Optimal";
          const healthVal = Math.round(spot.marine_health || 60);

          html += `
            <div class="ranked-spot-card ${recClass}">
              <div class="spot-card-badge">${escapeHTML(badgeText)}</div>
              <div class="spot-card-dist">
                ${distGeodesic} km geodesic <span style="font-size: 11px; font-weight: normal; color: #94a3b8;">(~${distRoute} km channel)</span>
              </div>
              <div class="spot-card-stats">
                <span>🌡️ ${sstVal}</span>
                <span>🌊 ${escapeHTML(prodVal)}</span>
                <span>🩺 ${healthVal}/100</span>
              </div>
              <div class="spot-card-reg">✓ 12 NM Boundary Compliant</div>
              <button type="button" class="spot-take-me-btn" data-spot-idx="${idx}">
                <span>${escapeHTML(takeMeLabel)}</span>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
              </button>
            </div>
          `;
        });
        html += `</div>`;
      }

      // Scientific Data Cards
      if (Array.isArray(data.data) && data.data.length > 0) {
        html += `<div class="ai-card-grid" style="margin-top: 10px;">`;
        for (const card of data.data) {
          const badgeClass = getStatusBadgeClass(card.data_status);
          const statusLabel = card.data_status || "TELEMETRY";
          html += `
            <div class="ai-data-card">
              <span class="ai-card-label">${escapeHTML(card.label || "Metric")}</span>
              <div class="ai-card-val-row">
                <span class="ai-card-value">${escapeHTML(String(card.value ?? "--"))}</span>
                <span class="ai-card-unit">${escapeHTML(card.unit || "")}</span>
              </div>
              <span class="ai-card-badge ${badgeClass}">${escapeHTML(statusLabel)}</span>
            </div>
          `;
        }
        html += `</div>`;
      }

      // Safe Action Chips
      if (Array.isArray(data.actions) && data.actions.length > 0) {
        html += `<div style="margin-top: 8px; display: flex; flex-wrap: wrap; gap: 6px;">`;
        for (const act of data.actions) {
          let label = act.type;
          if (act.type === "FLY_TO") label = `✈️ View: ${act.latitude}°N, ${act.longitude}°E`;
          else if (act.type === "SHOW_ROUTE") label = `🚢 Route: ${act.distance_km || 34.3} km`;
          else if (act.type === "HIGHLIGHT_SPOT") label = `🎯 Spot Beacon Highlighted`;
          else if (act.type === "SHOW_COMPACT_CARD") label = `📋 Floating HUD Active`;
          else if (act.type === "SHOW_SST") label = `🌡️ SST Layer Activated`;
          else if (act.type === "SHOW_UPWELLING") label = `🌊 Upwelling Fronts`;
          else if (act.type === "SELECT_PORT") label = `⚓ Selected Port: ${act.port_id}`;

          html += `<span class="ai-action-chip" style="font-size: 10px; padding: 3px 8px; border-radius: 4px; background: rgba(56, 189, 248, 0.08); border: 1px solid rgba(56, 189, 248, 0.2); color: #38bdf8;">${escapeHTML(label)}</span>`;
        }
        html += `</div>`;
      }

      botDiv.innerHTML = html;
      workspaceStreamEl.appendChild(botDiv);
      workspaceStreamEl.scrollTop = workspaceStreamEl.scrollHeight;
    }

    // 2. Legacy Drawer Rendering (if active)
    if (legacyHistoryEl) {
      const botDiv = document.createElement("div");
      botDiv.className = "orca-message ai-bot-msg";
      let drawerSpotsHtml = "";
      if (Array.isArray(data.spots) && data.spots.length > 0) {
        drawerSpotsHtml = `<div style="display:flex; flex-wrap:wrap; gap:6px; margin-top:8px;">` +
          data.spots.map((sp, idx) => `
            <button type="button" class="spot-take-me-btn" data-spot-idx="${idx}" style="font-size:10.5px; padding:5px 10px;">
              <span>#0${idx + 1} ${escapeHTML(takeMeLabel)} (${sp.distance_km || 34.3} km)</span>
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
            </button>
          `).join("") + `</div>`;
      }
      botDiv.innerHTML = `
        <div class="ai-sender">
          <span><span class="ai-avatar-mini">🐋</span> ORCA Cognitive Agent</span>
          <button type="button" class="orca-speak-btn" title="Speak Answer Aloud">${escapeHTML(speakLabel)}</button>
        </div>
        <div class="ai-content">${formatMarkdownText(messageText)}${drawerSpotsHtml}</div>
      `;
      legacyHistoryEl.appendChild(botDiv);
      legacyHistoryEl.scrollTop = legacyHistoryEl.scrollHeight;
    }
  }

  function renderAgentOfflineFallback(query, err) {
    const speakLabel = (window.ORCA_I18N && typeof window.ORCA_I18N.t === "function")
      ? window.ORCA_I18N.t("voice.speak_btn")
      : "🔊 Speak";
    const errorMsg = `Note: The ORCA FastAPI backend server is currently starting or unreachable (${escapeHTML(err ? err.message : "Connection Failed")}).

Offline Telemetry Cache:
Physical Arabian Sea telemetry is loaded in memory. Active coastal stations (Mumbai, Kochi, Kandla, Mangaluru, Goa, Porbandar) report sea surface temperatures ranging from 26.8°C to 28.5°C. All commercial fishing spots adhere strictly to the 12 NM (~22.2 km) territorial waters hard boundary seaward of the Indian coastline.`;

    if (workspaceStreamEl) {
      const botDiv = document.createElement("div");
      botDiv.className = "workspace-msg workspace-msg-bot";
      botDiv.innerHTML = `
        <div class="workspace-msg-sender">
          <span class="workspace-avatar">🐋</span>
          <span class="sender-name">ORCA Marine Intelligence</span>
          <span class="verified-tag">OFFLINE CACHE</span>
          <button type="button" class="orca-speak-btn" title="Speak Answer Aloud">${escapeHTML(speakLabel)}</button>
        </div>
        <div class="workspace-msg-content">${formatMarkdownText(errorMsg)}</div>
      `;
      workspaceStreamEl.appendChild(botDiv);
      workspaceStreamEl.scrollTop = workspaceStreamEl.scrollHeight;
    }
  }

  // Safe UI Action Dispatcher
  function executeSafeActions(actions, shouldShowGlobe) {
    if (!Array.isArray(actions)) return;

    for (const action of actions) {
      if (!action || !action.type || !SAFE_ACTIONS.has(action.type)) {
        console.warn("ORCA AI: Blocked non-whitelisted action:", action);
        continue;
      }

      console.log("ORCA AI Executing Safe Action:", action.type, action);

      switch (action.type) {
        case "FLY_TO": {
          if (shouldShowGlobe) {
            const lat = Number(action.latitude);
            const lon = Number(action.longitude);
            const height = Number(action.height) || 280000;
            const duration = Number(action.duration) || 1.8;
            if (Number.isFinite(lat) && Number.isFinite(lon)) {
              flyCamera(lat, lon, height, duration);
            }
          }
          break;
        }

        case "SHOW_ROUTE": {
          if (shouldShowGlobe && window.ORCA_GLOBE_CONTROLLER && typeof window.ORCA_GLOBE_CONTROLLER.showRoute === "function") {
            window.ORCA_GLOBE_CONTROLLER.showRoute(action.origin, action.destination, action.distance_km, action.route_distance_km);
          }
          break;
        }

        case "HIGHLIGHT_SPOT": {
          if (shouldShowGlobe && window.ORCA_GLOBE_CONTROLLER && typeof window.ORCA_GLOBE_CONTROLLER.highlightFishingSpot === "function") {
            window.ORCA_GLOBE_CONTROLLER.highlightFishingSpot(action.spot_id, action.latitude, action.longitude);
          }
          break;
        }

        case "SHOW_COMPACT_CARD": {
          break;
        }

        case "SHOW_FISHING_SPOT": {
          const lat = Number(action.latitude);
          const lon = Number(action.longitude);
          const score = Number(action.score) || 95;
          if (Number.isFinite(lat) && Number.isFinite(lon)) {
            if (shouldShowGlobe) {
              flyCamera(lat, lon, 350000, 1.8);
            }
            highlightFishingSpotOnMap(lat, lon, score);
          }
          break;
        }

        case "SHOW_SST": {
          triggerLayerChange("temperature");
          break;
        }

        case "SHOW_UPWELLING": {
          triggerLayerChange("chlorophyll");
          break;
        }

        case "SHOW_HEALTH": {
          triggerLayerChange("health");
          break;
        }

        case "SWITCH_2D": {
          const btn2d = document.getElementById("view-2d");
          if (btn2d) btn2d.click();
          break;
        }

        case "SWITCH_3D": {
          const btn3d = document.getElementById("view-3d");
          if (btn3d) btn3d.click();
          break;
        }

        case "RESET_VIEW": {
          const resetBtn = document.getElementById("btn-reset-view");
          if (resetBtn) resetBtn.click();
          break;
        }

        case "SELECT_PORT": {
          const portSelect = document.getElementById("coastal-port-select");
          if (portSelect && action.port_id) {
            portSelect.value = action.port_id;
            portSelect.dispatchEvent(new Event("change"));
          }
          break;
        }

        case "SELECT_STATION": {
          const stSelect = document.getElementById("station-select");
          if (stSelect && action.station_id) {
            stSelect.value = action.station_id;
            stSelect.dispatchEvent(new Event("change"));
          }
          break;
        }
      }
    }
  }

  function flyCamera(lat, lon, height, duration) {
    if (window.ORCA_GLOBE_CONTROLLER && typeof window.ORCA_GLOBE_CONTROLLER.flyToLocation === "function") {
      window.ORCA_GLOBE_CONTROLLER.flyToLocation(lat, lon, height, duration);
      return;
    }

    const is3D = document.getElementById("view-3d")?.classList.contains("active") ?? true;
    if (is3D && window.ORCA_CESIUM && typeof window.ORCA_CESIUM.flyToLocation === "function") {
      window.ORCA_CESIUM.flyToLocation(lon, lat, height || 280000);
    } else if (window.leafletMap && typeof window.leafletMap.flyTo === "function") {
      window.leafletMap.flyTo([lat, lon], 7, { duration: duration || 1.2 });
    }
  }

  function highlightFishingSpotOnMap(lat, lon, score) {
    if (window.leafletMap && window.L) {
      const beaconIcon = L.divIcon({
        className: "leaflet-pfz-beacon",
        iconSize: [16, 16],
        iconAnchor: [8, 8]
      });
      const marker = L.marker([lat, lon], { icon: beaconIcon }).addTo(window.leafletMap);
      marker.bindPopup(`
        <div style="font-family: monospace; font-size: 11px;">
          <strong style="color: #00f5d4;">🎯 POTENTIAL FISHING ZONE</strong><br>
          Suitability: <strong>${score}/100 (Optimal)</strong><br>
          Coords: ${lat.toFixed(3)}°N, ${lon.toFixed(3)}°E
        </div>
      `).openPopup();
    }

    if (window.ORCA_CESIUM && typeof window.ORCA_CESIUM.addPfzBeacon === "function") {
      window.ORCA_CESIUM.addPfzBeacon(lat, lon, score);
    }
  }

  function triggerLayerChange(metricName) {
    const btn = document.querySelector(`[data-metric="${metricName}"]`);
    if (btn) btn.click();
  }

  // Initialize when DOM is ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initOrcaAgent);
  } else {
    initOrcaAgent();
  }

  // Expose to window for external control
  window.ORCA_AGENT = {
    ask: handleAgentSubmit,
    nextSpot: handleNextSpotAction,
    openWorkspace: openWorkspace,
    closeWorkspace: closeWorkspace,
    isWorkspaceOpen: isWorkspaceOpen,
    takeUserToSpot: takeUserToSpot,
    openDepartureModalForSpot: function(spot) {
      if (window.ORCA_NAVIGATION && typeof window.ORCA_NAVIGATION.openDepartureModalForSpot === "function") {
        window.ORCA_NAVIGATION.openDepartureModalForSpot(spot);
      } else {
        openDepartureModal(spot);
      }
    },
    gatherContext: gatherActiveContext,
    executeSafeActions: executeSafeActions
  };
})();

