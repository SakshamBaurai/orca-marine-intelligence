/* Adds the ORCA forecast feed to the new top header interface. */
(() => {
  "use strict";
  const roots = window.ORCA_API_BASE ? [window.ORCA_API_BASE] : ["http://localhost:8000"];
  let station = "Kochi";
  let payload;
  const telemetryCache = new Map();
  const CACHE_TTL_MS = 60000;

  const PORT_DATA_MAP = {
    "Kandla": { name: "Kandla Port", lat: 23.01, lon: 70.22, isMajor: true, healthScore: 82, sla: "+6 cm" },
    "Mundra": { name: "Mundra Port", lat: 22.74, lon: 69.71, isMajor: true, healthScore: 80, sla: "+7 cm" },
    "Porbandar": { name: "Porbandar Port", lat: 21.64, lon: 69.61, isMajor: true, healthScore: 85, sla: "+5 cm" },
    "Veraval": { name: "Veraval Port", lat: 20.91, lon: 70.37, isMajor: true, healthScore: 84, sla: "+8 cm" },
    "Pipavav": { name: "Pipavav Port", lat: 20.91, lon: 71.50, isMajor: true, healthScore: 79, sla: "+9 cm" },
    "Hazira": { name: "Hazira Port", lat: 21.10, lon: 72.64, isMajor: true, healthScore: 76, sla: "+10 cm" },
    "Mumbai": { name: "Mumbai Port", lat: 18.94, lon: 72.84, isMajor: true, healthScore: 78, sla: "+8 cm" },
    "JNPT": { name: "JNPT (Nhava Sheva)", lat: 18.95, lon: 72.95, isMajor: true, healthScore: 77, sla: "+8 cm" },
    "Mormugao": { name: "Mormugao Port", lat: 15.41, lon: 73.80, isMajor: true, healthScore: 86, sla: "+4 cm" },
    "Mangaluru": { name: "New Mangalore Port", lat: 12.91, lon: 74.88, isMajor: true, healthScore: 83, sla: "+5 cm" },
    "Kochi": { name: "Kochi Port", lat: 9.93, lon: 76.27, isMajor: true, healthScore: 88, sla: "+6 cm" },
    "Jakhau": { name: "Jakhau Port", lat: 23.24, lon: 68.71, isMajor: false, healthScore: 81, sla: "+5 cm" },
    "Mandvi": { name: "Mandvi Port", lat: 22.83, lon: 69.36, isMajor: false, healthScore: 82, sla: "+6 cm" },
    "Navlakhi": { name: "Navlakhi", lat: 22.96, lon: 70.45, isMajor: false, healthScore: 78, sla: "+7 cm" },
    "Bedi": { name: "Bedi Port", lat: 22.50, lon: 70.04, isMajor: false, healthScore: 80, sla: "+6 cm" },
    "Sikka": { name: "Sikka Terminal", lat: 22.43, lon: 69.84, isMajor: false, healthScore: 79, sla: "+6 cm" },
    "Salaya": { name: "Salaya Port", lat: 22.31, lon: 69.60, isMajor: false, healthScore: 81, sla: "+5 cm" },
    "Okha": { name: "Okha Port", lat: 22.47, lon: 69.07, isMajor: false, healthScore: 83, sla: "+5 cm" },
    "Mangrol": { name: "Mangrol Port", lat: 21.12, lon: 70.11, isMajor: false, healthScore: 82, sla: "+7 cm" },
    "Jafrabad": { name: "Jafrabad Port", lat: 20.87, lon: 71.37, isMajor: false, healthScore: 80, sla: "+8 cm" },
    "Alang": { name: "Alang", lat: 21.41, lon: 72.20, isMajor: false, healthScore: 75, sla: "+11 cm" },
    "Bhavnagar": { name: "Bhavnagar Port", lat: 21.78, lon: 72.18, isMajor: false, healthScore: 76, sla: "+10 cm" },
    "Dahej": { name: "Dahej Port", lat: 21.70, lon: 72.53, isMajor: false, healthScore: 77, sla: "+9 cm" },
    "Daman": { name: "Daman Coast", lat: 20.40, lon: 72.83, isMajor: false, healthScore: 78, sla: "+8 cm" },
    "Alibaug": { name: "Alibaug (Mandwa)", lat: 18.73, lon: 72.88, isMajor: false, healthScore: 82, sla: "+8 cm" },
    "Dighi": { name: "Dighi Port", lat: 18.28, lon: 72.98, isMajor: false, healthScore: 83, sla: "+7 cm" },
    "Dabhol": { name: "Dabhol Port", lat: 17.59, lon: 73.18, isMajor: false, healthScore: 84, sla: "+6 cm" },
    "Jaigad": { name: "Jaigad Port", lat: 17.30, lon: 73.21, isMajor: false, healthScore: 85, sla: "+6 cm" },
    "Ratnagiri": { name: "Ratnagiri Port", lat: 16.99, lon: 73.30, isMajor: false, healthScore: 86, sla: "+5 cm" },
    "Vijaydurg": { name: "Vijaydurg Port", lat: 16.56, lon: 73.33, isMajor: false, healthScore: 87, sla: "+5 cm" },
    "Devgad": { name: "Devgad Port", lat: 16.38, lon: 73.38, isMajor: false, healthScore: 88, sla: "+4 cm" },
    "Malvan": { name: "Malvan Fish Harbour", lat: 16.05, lon: 73.47, isMajor: false, healthScore: 89, sla: "+4 cm" },
    "Panaji": { name: "Panaji Port", lat: 15.50, lon: 73.83, isMajor: false, healthScore: 87, sla: "+4 cm" },
    "Karwar": { name: "Karwar Port", lat: 14.80, lon: 74.12, isMajor: false, healthScore: 86, sla: "+5 cm" },
    "Tadri": { name: "Tadri Port", lat: 14.52, lon: 74.35, isMajor: false, healthScore: 85, sla: "+5 cm" },
    "Honnavar": { name: "Honnavar Port", lat: 14.28, lon: 74.44, isMajor: false, healthScore: 84, sla: "+5 cm" },
    "Bhatkal": { name: "Bhatkal Fish Harbour", lat: 13.98, lon: 74.55, isMajor: false, healthScore: 85, sla: "+5 cm" },
    "Kundapura": { name: "Kundapura Port", lat: 13.63, lon: 74.69, isMajor: false, healthScore: 84, sla: "+5 cm" },
    "Malpe": { name: "Malpe Deep-Sea Port", lat: 13.35, lon: 74.70, isMajor: false, healthScore: 86, sla: "+5 cm" },
    "Kollam": { name: "Kollam Port", lat: 8.89, lon: 76.59, isMajor: false, healthScore: 87, sla: "+4 cm" },
    "Thiruvananthapuram": { name: "Vizhinjam Port", lat: 8.52, lon: 76.94, isMajor: false, healthScore: 89, sla: "+4 cm" },
    "Thoothukudi": { name: "Thoothukudi (VOC Port)", lat: 8.76, lon: 78.13, isMajor: false, healthScore: 84, sla: "+3 cm" },
    "Chennai": { name: "Chennai Port", lat: 13.08, lon: 80.27, isMajor: true, healthScore: 82, sla: "+4 cm" },
    "Kakinada": { name: "Kakinada Port", lat: 16.99, lon: 82.25, isMajor: false, healthScore: 81, sla: "+5 cm" },
    "Visakhapatnam": { name: "Visakhapatnam Port", lat: 17.69, lon: 83.22, isMajor: true, healthScore: 83, sla: "+6 cm" },
    "Paradip": { name: "Paradip Port", lat: 20.27, lon: 86.67, isMajor: false, healthScore: 80, sla: "+7 cm" }
  };

  window.ORCA_PORT_MAP = PORT_DATA_MAP;

  function updateSelectedPortSafety(st) {
    const portInfo = PORT_DATA_MAP[st] || { name: `${st} Port`, lat: 9.93, lon: 76.27, isMajor: true, healthScore: 85, sla: "+6 cm" };
    
    if (window.ORCA_STATE) {
      window.ORCA_STATE.selectedDeparture = {
        name: portInfo.name,
        lat: portInfo.lat,
        lon: portInfo.lon,
        latitude: portInfo.lat,
        longitude: portInfo.lon,
        isMajor: portInfo.isMajor
      };
    }

    if (typeof window.updateSeaConditionsIndicator === "function") {
      window.updateSeaConditionsIndicator(portInfo);
    }

    if (typeof window.updateCoastalPortWeather === "function") {
      window.updateCoastalPortWeather(portInfo);
    }

    if (window.ORCA_NAVIGATION && typeof window.ORCA_NAVIGATION.recalculateActiveRoute === "function") {
      window.ORCA_NAVIGATION.recalculateActiveRoute();
    }
  }

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
    if (headerName) {
      const portInfo = PORT_DATA_MAP[station];
      const pName = portInfo ? portInfo.name : (payload && payload.station ? `${payload.station.name} (${payload.station.region})` : station);
      headerName.textContent = pName;
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
    updateSelectedPortSafety(station);
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
        updateSelectedPortSafety(station);
      });
    }

    document.querySelectorAll(".station-tab").forEach(btn => {
        btn.addEventListener("click", (e) => {
            station = e.target.dataset.station;
            load();
            updateSelectedPortSafety(station);
        });
    });
    load();
    updateSelectedPortSafety(station);
  });
})();
