/* Adds the ORCA forecast feed to the new top header interface. */
(() => {
  "use strict";
  const roots = window.ORCA_API_BASE ? [window.ORCA_API_BASE] : ["http://localhost:8000"];
  let station = "Kochi";
  let payload;
  const telemetryCache = new Map();
  const CACHE_TTL_MS = 60000;

  async function requestTelemetry(targetStation) {
    const s = targetStation || station;
    const now = Date.now();
    const cached = telemetryCache.get(s);
    if (cached && (now - cached.timestamp < CACHE_TTL_MS)) {
      return cached.data;
    }

    let lastError;
    for (const root of roots) {
      try {
        const response = await fetch(`${root}/dashboard/telemetry?station=${encodeURIComponent(s)}`);
        const body = await response.json();
        if (!response.ok) throw new Error(body.detail || `HTTP ${response.status}`);
        telemetryCache.set(s, { data: body, timestamp: now });
        return body;
      } catch (error) { lastError = error; }
    }
    if (cached) return cached.data;
    throw lastError || new Error("ORCA API unavailable");
  }

  function updateHeaderNav() {
    const stationSelect = document.getElementById("station-select");
    if (stationSelect && station) {
      stationSelect.value = station;
    }

    document.querySelectorAll(".station-tab").forEach(btn => {
      if (btn.dataset.station === station) {
        btn.classList.add("active");
      } else {
        btn.classList.remove("active");
      }
    });
    
    const headerName = document.getElementById("header-station-name");
    if (headerName && payload) {
      headerName.textContent = `${payload.station.name} (${payload.station.region})`;
    }
  }

  function updateHeaderMetrics(props) {
    if (!props) return;
    
    // MHI
    const elMhi = document.getElementById("head-mhi");
    if (elMhi) elMhi.textContent = props.mhi !== undefined ? `${props.mhi} / 100` : "-- / 100";
    
    // SST Anomaly
    const elSst = document.getElementById("head-sst-anom");
    if (elSst) {
        if (props.sst_anom !== undefined) {
            elSst.textContent = `${props.sst_anom > 0 ? '+' : ''}${props.sst_anom} \u00b0C`;
            elSst.style.color = props.sst_anom > 0 ? "var(--accent-danger)" : "var(--accent-cyan)";
        } else {
            elSst.textContent = "-- \u00b0C";
            elSst.style.color = "var(--text-main)";
        }
    }
    
    // Current
    const elCurrent = document.getElementById("head-current");
    if (elCurrent) elCurrent.textContent = props.current !== undefined ? `${props.current} m/s` : "-- m/s";
    
    // Chlorophyll
    const elChl = document.getElementById("head-chl");
    if (elChl) elChl.textContent = props.chl !== undefined ? props.chl : "--";
  }

  async function load() {
    try {
      payload = await requestTelemetry();
      if (!window.ORCA_GLOBE) throw new Error("Original globe did not initialize.");
      window.ORCA_GLOBE.applyLiveTelemetry(payload);
      
      updateHeaderNav();
      
      updateHeaderMetrics({
        mhi: payload.health.index,
        sst_anom: payload.station_telemetry.thetao_anom,
        current: payload.station_telemetry.current_speed,
        chl: payload.station_telemetry.chlorophyll != null ? `${payload.station_telemetry.chlorophyll} mg/m³` : "--"
      });
      
    } catch (error) {
      console.error("ORCA live feed:", error);
    }
  }

  // Expose an update function so the globe can inject cluster data on click
  window.updateHeaderFromCluster = function(props) {
    // Un-highlight all station tabs since a custom cluster is selected
    document.querySelectorAll(".station-tab").forEach(btn => btn.classList.remove("active"));
    const headerName = document.getElementById("header-station-name");
    if (headerName) headerName.textContent = `Cluster: ${props.event_type} (${props.zone})`;
    
    updateHeaderMetrics({
        mhi: props.mean_MHI,
        sst_anom: props.thetao_daily_anomaly !== undefined ? props.thetao_daily_anomaly : undefined,
        current: props.current_speed !== undefined ? props.current_speed : undefined,
        chl: props.log_chl !== undefined ? props.log_chl : undefined
    });
  };

  document.addEventListener("DOMContentLoaded", () => {
    const stationSelect = document.getElementById("station-select");
    if (stationSelect) {
      stationSelect.addEventListener("change", (e) => {
        station = e.target.value;
        load();
      });
    }

    document.querySelectorAll(".station-tab").forEach(btn => {
        btn.addEventListener("click", (e) => {
            station = e.target.dataset.station;
            load();
        });
    });
    load();
  });
})();
