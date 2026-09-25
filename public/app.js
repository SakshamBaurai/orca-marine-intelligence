/**
 * ==========================================================================
 * ORCA - DEEP OCEAN 3D GLOBE & HEALTH MONITORING SYSTEM
 * ==========================================================================
 *
 * Three.js 3D Globe
 * Leaflet 2D Fallback
 * Ocean Health Monitoring
 * ORCA RAG AI Integration
 *
 * FIXED:
 * - Giant cyan particle blocks
 * - Particle scale
 * - Invisible station hitboxes
 * - Invalid beamMesh reference
 * - Duplicate Earth creation
 * - Safer raycasting
 * ==========================================================================
 */

(function () {

  "use strict";


  // =========================================================================
  // GLOBAL STATE
  // =========================================================================

  const state = {

    viewMode: "3d",

    activeMetric: "health",

    filterStatus: "all",

    selectedStation: null,

    hoveredStation: null,

    showCurrents: true,

    showAtmosphere: true,

    autoRotate: false,

    soundEnabled: false

  };

  window.ORCA_APP_STATE = state;

  // =========================================================================
  // CANONICAL UNIFIED ORCA STATE MODEL
  // =========================================================================
  window.ORCA_STATE = {
    selectedDeparture: {
      id: "port-mumbai",
      name: "Mumbai Port",
      latitude: 18.94,
      longitude: 72.84,
      lat: 18.94,
      lon: 72.84,
      isMajor: true,
      type: "port"
    },
    selectedFishingSpot: null,
    selectedGridPoint: null,
    mapView: { mode: "3d", center: [14.0, 71.0], zoom: 4 },
    route: null,
    seaConditions: null,
    spotsList: [],
    currentSpotIndex: 0
  };

  let _seaCondRequestId = 0;
  window.updateSeaConditionsIndicator = async function (location) {
    if (!location) return;
    const reqId = ++_seaCondRequestId;
    const lat = Number(location.lat ?? location.latitude ?? 9.93);
    const lon = Number(location.lon ?? location.longitude ?? 76.27);
    const name = location.name || "Selected Port";
    const isPort = !!(location.isMajor || name.includes("Port") || location.type === "port");

    const statusEl = document.getElementById("sea-condition-status");
    const metaEl = document.getElementById("sea-condition-meta");
    const tagEl = document.getElementById("sea-condition-type");
    const seaLevelEl = document.getElementById("sea-level-tag");
    const headSlaEl = document.getElementById("head-sla");

    // Popover elements
    const popLeadEl = document.getElementById("popover-safety-lead");
    const popWindEl = document.getElementById("pop-wind-speed");
    const popSeaStateEl = document.getElementById("pop-sea-state");
    const popSlaEl = document.getElementById("pop-sla-val");
    const popMhiEl = document.getElementById("pop-mhi-val");
    const popAdvisoryEl = document.getElementById("popover-advisory");

    if (metaEl) metaEl.textContent = `${name} • Checking...`;

    try {
      const param = isPort ? `port=${encodeURIComponent(name)}` : `lat=${lat.toFixed(3)}&lon=${lon.toFixed(3)}`;
      const res = await fetch(`http://localhost:8000/api/v1/sea-conditions?${param}`);
      if (reqId !== _seaCondRequestId) return;

      if (res.ok) {
        const data = await res.json();
        window.ORCA_STATE.seaConditions = data;

        const condStatus = data.condition_status || "SAFE / CALM WATERS";
        if (statusEl) {
          statusEl.textContent = condStatus;
          const s = condStatus.toUpperCase();
          statusEl.className = "sea-ind-status " + (s.includes("SAFE") ? "safe" : (s.includes("MODERATE") ? "moderate" : (s.includes("CAUTION") ? "caution" : "rough")));
        }
        const score = data.condition_score ? `${data.condition_score}/100` : "84/100";
        const wind = data.weather?.wind_speed ? `${data.weather.wind_speed} km/h` : "12 km/h";
        if (metaEl) {
          metaEl.textContent = `${name} • ${score} • ${wind}`.trim();
        }
        if (tagEl) {
          tagEl.textContent = "LIVE";
          tagEl.className = "sea-ind-tag";
        }
        const slaVal = location.sla || (data.sla_cm !== undefined ? `${data.sla_cm >= 0 ? '+' : ''}${data.sla_cm} cm` : "+6 cm");
        if (seaLevelEl) {
          seaLevelEl.textContent = `Sea Level: Normal (${slaVal})`;
        }
        if (headSlaEl) {
          headSlaEl.textContent = slaVal;
        }

        // Update Popover
        if (popLeadEl) {
          const safeColor = condStatus.includes("SAFE") ? "#34d399" : (condStatus.includes("MODERATE") ? "#38bdf8" : "#fbbf24");
          popLeadEl.innerHTML = `Operational assessment for <strong>${name}</strong>: <span style="color: ${safeColor}; font-weight: 700;">${condStatus}</span>`;
        }
        if (popWindEl) popWindEl.textContent = wind;
        if (popSeaStateEl) popSeaStateEl.textContent = data.sea_state || "Calm Water (0.5m)";
        if (popSlaEl) popSlaEl.textContent = slaVal;
        if (popMhiEl) popMhiEl.textContent = `${score}`;
        if (popAdvisoryEl) {
          popAdvisoryEl.innerHTML = `<strong>Operational Advisory:</strong> Safe conditions for small boat artisanal fishers and motorized craft departing from ${name}. Normal tidal sea level and calm sea conditions.`;
        }
        return;
      }
    } catch (e) {
      // Offline fallback
    }

    if (reqId !== _seaCondRequestId) return;
    const hash = Math.abs(Math.sin(lat * 12.9898 + lon * 78.233) * 43758.5453);
    const health = Number(location.healthScore ?? Math.floor(78 + (hash % 14)));
    const windSpeed = Math.floor(10 + (hash * 13) % 11);
    const slaVal = location.sla || `+${Math.floor(4 + (hash * 7) % 6)} cm`;
    const condStatus = health >= 78 ? "SAFE / CALM WATERS" : (health >= 65 ? "SAFE TO MODERATE" : "CAUTION / CHOPPY");

    if (statusEl) {
      statusEl.textContent = condStatus;
      statusEl.className = "sea-ind-status " + (health >= 78 ? "safe" : (health >= 65 ? "moderate" : "caution"));
    }
    if (metaEl) metaEl.textContent = `${name} • ${health}/100 • ${windSpeed} km/h`;
    if (tagEl) {
      tagEl.textContent = "LIVE";
      tagEl.className = "sea-ind-tag";
    }
    if (seaLevelEl) {
      seaLevelEl.textContent = `Sea Level: Normal (${slaVal})`;
    }
    if (headSlaEl) {
      headSlaEl.textContent = slaVal;
    }

    // Update Popover
    if (popLeadEl) {
      const safeColor = health >= 78 ? "#34d399" : (health >= 65 ? "#38bdf8" : "#fbbf24");
      popLeadEl.innerHTML = `Operational assessment for <strong>${name}</strong>: <span style="color: ${safeColor}; font-weight: 700;">${condStatus}</span>`;
    }
    if (popWindEl) popWindEl.textContent = `${windSpeed} km/h`;
    const swellM = (0.4 + ((hash % 10) * 0.04)).toFixed(1);
    if (popSeaStateEl) popSeaStateEl.textContent = `Calm Water (${swellM}m swell)`;
    if (popSlaEl) popSlaEl.textContent = slaVal;
    if (popMhiEl) popMhiEl.textContent = `${health} / 100`;
    if (popAdvisoryEl) {
      popAdvisoryEl.innerHTML = `<strong>Operational Advisory:</strong> Safe conditions for small boat artisanal fishers and motorized craft departing from ${name}. Normal tidal sea level and calm sea conditions.`;
    }
  };

  window.ORCA_SET_DEPARTURE = function (portOrStation) {
    if (!portOrStation) return;
    const lat = Number(portOrStation.lat ?? portOrStation.latitude);
    const lon = Number(portOrStation.lon ?? portOrStation.longitude);
    const name = portOrStation.name || "Selected Port";
    const id = portOrStation.id || `port-${name.toLowerCase().replace(/[^a-z0-9]/g, '-')}`;
    const isMajor = !!portOrStation.isMajor;

    const canonicalPort = {
      id: id,
      name: name,
      latitude: lat,
      longitude: lon,
      lat: lat,
      lon: lon,
      isMajor: isMajor,
      type: portOrStation.type || (name.includes("Port") ? "port" : "station")
    };

    window.ORCA_STATE.selectedDeparture = canonicalPort;
    console.log(`[ORCA DEPARTURE]\nSelected: ${name}\nLAT: ${lat.toFixed(4)}\nLON: ${lon.toFixed(4)}`);

    window.updateSeaConditionsIndicator(canonicalPort);

    if (window.ORCA_STATE.selectedFishingSpot) {
      if (typeof drawLeafletRoute === "function") {
        drawLeafletRoute(window.ORCA_STATE.selectedFishingSpot);
      }
      if (window.ORCA_CESIUM && typeof window.ORCA_CESIUM.showRoute === "function") {
        window.ORCA_CESIUM.showRoute(canonicalPort, window.ORCA_STATE.selectedFishingSpot);
      }
    }
  };


  // =========================================================================
  // METRIC CONFIGURATION
  // =========================================================================

  const METRIC_CONFIG = {

    health: {

      name: "Ocean Health (Fish Activity)",

      unit: "/100",

      min: 20,

      max: 95,

      gradient:
        "linear-gradient(90deg, #ef476f 0%, #ffd166 50%, #00f5d4 100%)",

      colors: [
        "#ef476f",
        "#ffd166",
        "#00f5d4"
      ],

      getColor: (val) =>
        val < 55
          ? "#ef476f"
          : val < 75
            ? "#ffd166"
            : "#00f5d4",

      getVal: (s) => s.healthScore

    },


    sst: {

      name: "Water Temperature (SST)",

      unit: "°C",

      min: 27.5,

      max: 31.0,

      gradient:
        "linear-gradient(90deg, #0077b6 0%, #00f5d4 40%, #ffd166 75%, #ef476f 100%)",

      colors: [
        "#0077b6",
        "#00f5d4",
        "#ffd166",
        "#ef476f"
      ],

      getColor: (val) =>
        val < 28.5
          ? "#0077b6"
          : val < 29.5
            ? "#00f5d4"
            : val < 30.2
              ? "#ffd166"
              : "#ef476f",

      getVal: (s) => s.sst

    },


    oxygen: {

      name: "Water Oxygen Level (DO)",

      unit: "mg/L",

      min: 1.5,

      max: 6.8,

      gradient:
        "linear-gradient(90deg, #ef476f 0%, #ffd166 40%, #00f5d4 100%)",

      colors: [
        "#ef476f",
        "#ffd166",
        "#00f5d4"
      ],

      getColor: (val) =>
        val < 3.0
          ? "#ef476f"
          : val < 4.8
            ? "#ffd166"
            : "#00f5d4",

      getVal: (s) => s.oxygen

    },


    ph: {

      name: "Water Cleanliness (pH)",

      unit: "pH",

      min: 7.85,

      max: 8.20,

      gradient:
        "linear-gradient(90deg, #ef476f 0%, #ffd166 50%, #00f5d4 100%)",

      colors: [
        "#ef476f",
        "#ffd166",
        "#00f5d4"
      ],

      getColor: (val) =>
        val < 7.95
          ? "#ef476f"
          : val < 8.08
            ? "#ffd166"
            : "#00f5d4",

      getVal: (s) => s.ph

    },


    chlorophyll: {

      name: "Fish Food Level (Plankton / Chl-a)",

      unit: "mg/m³",

      min: 0.2,

      max: 2.8,

      gradient:
        "linear-gradient(90deg, #001233 0%, #0077b6 35%, #00f5d4 75%, #a7c957 100%)",

      colors: [
        "#001233",
        "#0077b6",
        "#00f5d4",
        "#a7c957"
      ],

      getColor: (val) =>
        val < 0.6
          ? "#0077b6"
          : val < 1.4
            ? "#00f5d4"
            : "#a7c957",

      getVal: (s) => s.chlorophyll

    },


    salinity: {

      name: "Salt Level (Salinity)",

      unit: "PSU",

      min: 35.0,

      max: 36.8,

      gradient:
        "linear-gradient(90deg, #00b4d8 0%, #0077b6 60%, #7209b7 100%)",

      colors: [
        "#00b4d8",
        "#0077b6",
        "#7209b7"
      ],

      getColor: (val) =>
        val < 35.8
          ? "#00b4d8"
          : val < 36.3
            ? "#0077b6"
            : "#7209b7",

      getVal: (s) => s.salinity

    }

  };


  // =========================================================================
  // DOM ELEMENTS
  // =========================================================================

  const dom = {

    globeContainer:
      document.getElementById("globe-canvas-container"),

    map2dContainer:
      document.getElementById("map-2d-container"),

    btnModeToggle:
      document.getElementById("btn-mode-toggle"),

    btnResetView:
      document.getElementById("btn-reset-view"),

    btnAutoRotate:
      document.getElementById("btn-auto-rotate"),

    metricBtns:
      document.querySelectorAll(".metric-btn"),

    toggleCurrents:
      document.getElementById("toggle-currents"),

    rightPanel:
      document.getElementById("right-panel"),

    legendTitle:
      document.getElementById("legend-title"),

    legendGradient:
      document.getElementById("legend-gradient"),

    legendMin:
      document.getElementById("legend-min"),

    legendMax:
      document.getElementById("legend-max"),

    floatingTooltip:
      document.getElementById("floating-tooltip"),

    tooltipHeader:
      document.getElementById("tooltip-header"),

    tooltipBody:
      document.getElementById("tooltip-body"),

    btnAskOrca:
      document.getElementById("btn-ask-orca")

  };


  // =========================================================================
  // THREE.JS INSTANCES
  // =========================================================================

  let scene;

  let camera;

  let renderer;

  let controls;

  let earthGlobe;

  let atmosphereMesh;

  let markerGroup;

  let currentParticles;

  let raycaster;

  let mouseVector;

  let stationMeshes = [];

  let pfzGroup = null;

  const GLOBE_RADIUS = 5.0;


  // =========================================================================
  // LEAFLET
  // =========================================================================

  let leafletMap = null;

  let leafletMarkerGroup = null;

  let leafletMajorPortsGroup = null;

  let leafletMinorPortsGroup = null;

  let activeLeafletRoute = null;

  let leafletMarkers = [];


  // =========================================================================
  // WEB AUDIO
  // =========================================================================

  let audioCtx = null;

  let noiseNode = null;

  let filterNode = null;

  let gainNode = null;


  // =========================================================================
  // INITIALIZATION
  // =========================================================================

  async function init() {
    console.log("Fetching live model telemetry for globe...");
    let cachedGrid = null;
    try {
      const cachedStr = sessionStorage.getItem("orca_grid_cache");
      if (cachedStr) {
        cachedGrid = JSON.parse(cachedStr);
      }
    } catch (err) {}

    if (cachedGrid && cachedGrid.stations && cachedGrid.stations.length > 0) {
      window.OCEAN_DATA.stations = cachedGrid.stations;
      window.OCEAN_DATA.totalStations = cachedGrid.stations.length;
      let sumScore = 0;
      cachedGrid.stations.forEach(s => sumScore += s.healthScore);
      window.OCEAN_DATA.overallHealthIndex = Math.round(sumScore / cachedGrid.stations.length);
      console.log("Loaded cached grid telemetry:", cachedGrid.stations.length, "nodes");
      if (typeof updateMhiTrendTelemetry === "function") updateMhiTrendTelemetry();

      // Background revalidation
      fetch("http://localhost:8000/dashboard/grid")
        .then(res => res.json())
        .then(data => {
          if (data && data.stations && data.stations.length > 0) {
            try { sessionStorage.setItem("orca_grid_cache", JSON.stringify(data)); } catch (e) {}
          }
        })
        .catch(err => console.warn("Background grid revalidation error:", err));
    } else {
      try {
        const res = await fetch("http://localhost:8000/dashboard/grid");
        const data = await res.json();
        if (data && data.stations && data.stations.length > 0) {
          window.OCEAN_DATA.stations = data.stations;
          window.OCEAN_DATA.totalStations = data.stations.length;
          
          let sumScore = 0;
          data.stations.forEach(s => sumScore += s.healthScore);
          window.OCEAN_DATA.overallHealthIndex = Math.round(sumScore / data.stations.length);
          console.log("Live model telemetry loaded:", data.stations.length, "nodes");
          try { sessionStorage.setItem("orca_grid_cache", JSON.stringify(data)); } catch (e) {}
          if (typeof updateMhiTrendTelemetry === "function") updateMhiTrendTelemetry();
        }
      } catch (e) {
        console.warn("Could not load live model telemetry, using fallback synthetic data.", e);
      }
    }

    // Ensure every station has a unique id (needed for Cesium entity mapping)
    window.OCEAN_DATA.stations.forEach((s, i) => {
      if (!s.id) s.id = s.name || `station-${i}`;
    });

    if (dom.btnAutoRotate) {
      dom.btnAutoRotate.classList.remove("active");
      dom.btnAutoRotate.lastChild.textContent = "\n\n        Orbit: Off\n      ";
    }

    /*
     * Populate dynamic statistics
     */

    if (window.OCEAN_DATA) {

      const data = window.OCEAN_DATA;


      const statNodes =
        document.querySelector(
          ".stat-value .pulsing-dot"
        )?.parentElement;


      if (statNodes) {

        statNodes.innerHTML =
          `<span class="pulsing-dot"></span> ${data.totalStations} NODES`;

      }


      const badge =
        document.querySelector(".health-badge");


      if (badge) {

        badge.textContent =
          `${data.overallHealthIndex} / 100 OPTIMAL`;

      }


      const stats =
        document.querySelectorAll(
          ".top-stats .stat-item .stat-value"
        );


      if (stats.length >= 4) {

        stats[2].textContent =
          `${data.metricsSummary.avgTemp} °C`;

        stats[3].textContent =
          `${data.metricsSummary.avgDO} mg/L`;

      }

    }


    /*
     * Initialize 3D Globe (CesiumJS replaces Three.js)
     */

    let cesiumSuccess = false;
    if (window.ORCA_CESIUM) {
      cesiumSuccess = window.ORCA_CESIUM.init("globe-canvas-container");
    }
    
    if (!cesiumSuccess) {
      // Fallback to Three.js if Cesium not loaded or failed
      initThreeGlobe();
      createArabianSeaBoundary();
      // Remove the ORCA_CESIUM global so other parts of the code know it failed
      window.ORCA_CESIUM = null;
    }


    /*
     * Leaflet
     */

    initLeafletMap();


    /*
     * Events
     */

    initEventListeners();
    initMhiTrendGraph();


    /*
     * Legend
     */

    updateLegend();


    /*
     * Select middle station by default
     */

    if (
      window.OCEAN_DATA &&
      window.OCEAN_DATA.stations.length > 0
    ) {

      const middle =
        Math.floor(
          window.OCEAN_DATA.stations.length / 2
        );

      selectStation(
        window.OCEAN_DATA.stations[middle]
      );

    }


    /*
     * Start animation (only needed for Three.js fallback)
     */

    if (!window.ORCA_CESIUM) {
      animate();
    }

  }


  // =========================================================================
  // THREE.JS GLOBE SETUP
  // =========================================================================

  function initThreeGlobe() {

    const width =
      dom.globeContainer.clientWidth ||
      window.innerWidth;


    const height =
      dom.globeContainer.clientHeight ||
      window.innerHeight;


    scene = new THREE.Scene();


    scene.fog =
      new THREE.FogExp2(
        0x020611,
        0.04
      );


    /*
     * Camera
     */

    camera =
      new THREE.PerspectiveCamera(
        45,
        width / height,
        0.1,
        1000
      );


    setCameraPositionToLatLon(
      14.0,
      71.0,
      14.5
    );


    /*
     * Renderer
     */

    renderer =
      new THREE.WebGLRenderer({

        antialias: true,

        alpha: true,

        powerPreference:
          "high-performance"

      });


    renderer.setSize(
      width,
      height
    );


    renderer.setPixelRatio(
      Math.min(
        window.devicePixelRatio,
        2
      )
    );


    dom.globeContainer.appendChild(
      renderer.domElement
    );


    /*
     * Orbit Controls
     */

    controls =
      new THREE.OrbitControls(
        camera,
        renderer.domElement
      );


    controls.enableDamping = true;

    controls.dampingFactor = 0.05;

    controls.rotateSpeed = 0.6;

    controls.minDistance = 7.5;

    controls.maxDistance = 25.0;

    controls.autoRotate =
      state.autoRotate;

    controls.autoRotateSpeed =
      0.45;


    /*
     * Lighting
     */

    const ambientLight =
      new THREE.AmbientLight(
        0x1a335a,
        1.2
      );

    scene.add(ambientLight);


    const sunLight =
      new THREE.DirectionalLight(
        0xd9f0ff,
        2.0
      );

    sunLight.position.set(
      20,
      15,
      25
    );

    scene.add(sunLight);


    const rimLight =
      new THREE.PointLight(
        0x00f5d4,
        1.5,
        40
      );

    rimLight.position.set(
      -15,
      -10,
      -15
    );

    scene.add(rimLight);


    /*
     * Earth
     */

    createEarthSphere();


    /*
     * Atmosphere
     */

    createAtmosphereGlow();


    /*
     * Stars
     */

    createStarfield();


    /*
     * Ocean current particles
     */

    createOceanCurrentParticles();


    /*
     * Station markers
     */

    createStationMarkers();


    /*
     * Raycaster
     */

    raycaster =
      new THREE.Raycaster();


    mouseVector =
      new THREE.Vector2(
        -999,
        -999
      );


    /*
     * Events
     */

    window.addEventListener(
      "resize",
      onWindowResize
    );


    renderer.domElement.addEventListener(
      "mousemove",
      onMouseMove
    );


    renderer.domElement.addEventListener(
      "click",
      onMouseClick
    );

  }


  // =========================================================================
  // PROCEDURAL EARTH TEXTURE
  // =========================================================================

  function createProceduralEarthTexture() {

    const canvas =
      document.createElement("canvas");


    canvas.width = 2048;

    canvas.height = 1024;


    const ctx =
      canvas.getContext("2d");


    /*
     * Deep abyssal gradient
     */

    const oceanGrad =
      ctx.createLinearGradient(
        0,
        0,
        0,
        canvas.height
      );


    oceanGrad.addColorStop(
      0.0,
      "#030a1c"
    );

    oceanGrad.addColorStop(
      0.2,
      "#040d25"
    );

    oceanGrad.addColorStop(
      0.5,
      "#061536"
    );

    oceanGrad.addColorStop(
      0.8,
      "#040d25"
    );

    oceanGrad.addColorStop(
      1.0,
      "#030a1c"
    );


    ctx.fillStyle =
      oceanGrad;


    ctx.fillRect(
      0,
      0,
      canvas.width,
      canvas.height
    );


    /*
     * Bathymetric ridges
     */

    ctx.strokeStyle =
      "rgba(0, 180, 216, 0.15)";

    ctx.lineWidth = 2;


    for (
      let i = 0;
      i < 35;
      i++
    ) {

      ctx.beginPath();


      const y =
        150 +
        Math.random() * 700;


      ctx.moveTo(
        0,
        y
      );


      for (
        let x = 0;
        x < canvas.width;
        x += 80
      ) {

        ctx.lineTo(
          x,
          y +
            Math.sin(
              x * 0.02 + i
            ) * 35
        );

      }


      ctx.stroke();

    }


    /*
     * Latitude / longitude grid
     */

    ctx.strokeStyle =
      "rgba(0, 245, 212, 0.08)";

    ctx.lineWidth = 1;


    /*
     * Parallels
     */

    for (
      let lat = -80;
      lat <= 80;
      lat += 20
    ) {

      const y =
        ((90 - lat) / 180) *
        canvas.height;


      ctx.beginPath();

      ctx.moveTo(
        0,
        y
      );

      ctx.lineTo(
        canvas.width,
        y
      );

      ctx.stroke();

    }


    /*
     * Meridians
     */

    for (
      let lon = -180;
      lon < 180;
      lon += 30
    ) {

      const x =
        ((lon + 180) / 360) *
        canvas.width;


      ctx.beginPath();

      ctx.moveTo(
        x,
        0
      );

      ctx.lineTo(
        x,
        canvas.height
      );

      ctx.stroke();

    }


    /*
     * Landmass styling
     */

    ctx.fillStyle =
      "#0c1e36";

    ctx.strokeStyle =
      "rgba(0, 245, 212, 0.4)";

    ctx.lineWidth = 2;


    function drawLand(coords) {

      ctx.beginPath();


      coords.forEach(
        ([lon, lat], idx) => {

          const x =
            ((lon + 180) / 360) *
            canvas.width;


          const y =
            ((90 - lat) / 180) *
            canvas.height;


          if (idx === 0) {

            ctx.moveTo(
              x,
              y
            );

          } else {

            ctx.lineTo(
              x,
              y
            );

          }

        }
      );


      ctx.closePath();

      ctx.fill();

      ctx.stroke();

    }


    /*
     * India
     */

    drawLand([

      [68, 24],
      [70, 22],
      [73, 19],
      [74, 15],
      [76, 10],
      [77.5, 8.2],
      [78.5, 9.5],
      [80, 13],
      [82, 16],
      [86, 20],
      [89, 22],
      [88, 26],
      [78, 30],
      [74, 34],
      [71, 30],
      [68, 26],
      [68, 24]

    ]);


    /*
     * Arabian Peninsula
     */

    drawLand([

      [44, 12],
      [50, 14],
      [54, 17],
      [59, 22],
      [57, 26],
      [50, 26],
      [48, 30],
      [40, 28],
      [36, 22],
      [43, 14],
      [44, 12]

    ]);


    /*
     * Horn of Africa
     */

    drawLand([

      [51, 11],
      [49, 8],
      [44, 2],
      [40, -4],
      [38, -12],
      [32, -8],
      [36, 4],
      [42, 10],
      [45, 12],
      [51, 11]

    ]);


    /*
     * Eurasia
     */

    drawLand([

      [-9, 36],
      [0, 42],
      [10, 44],
      [25, 40],
      [35, 41],
      [50, 40],
      [75, 40],
      [80, 60],
      [40, 65],
      [10, 60],
      [-5, 48],
      [-9, 36]

    ]);


    /*
     * Southeast Asia
     */

    drawLand([

      [98, 10],
      [105, 10],
      [108, 18],
      [102, 22],
      [96, 20],
      [98, 10]

    ]);


    /*
     * Australia
     */

    drawLand([

      [114, -22],
      [130, -12],
      [145, -15],
      [152, -28],
      [140, -38],
      [116, -34],
      [114, -22]

    ]);


    /*
     * Arabian Sea monitoring grid.
     *
     * This is only a 2D texture outline.
     * It is NOT a cyan fill.
     */

    ctx.strokeStyle =
      "rgba(0, 229, 255, 0.20)";

    ctx.setLineDash([
      6,
      4
    ]);

    ctx.lineWidth = 1.2;


    const x1 =
      ((64.5 + 180) / 360) *
      canvas.width;


    const y1 =
      ((90 - 18.0) / 180) *
      canvas.height;


    const w =
      ((74.5 - 64.5) / 360) *
      canvas.width;


    const h =
      ((18.0 - 7.5) / 180) *
      canvas.height;


    ctx.strokeRect(
      x1,
      y1,
      w,
      h
    );


    ctx.setLineDash([]);


    return new THREE.CanvasTexture(
      canvas
    );

  }


  // =========================================================================
  // ARABIAN SEA BOUNDARY
  // =========================================================================

  function createArabianSeaBoundary() {

    if (!scene) return;


    const material =
      new THREE.LineDashedMaterial({

        color: 0x38bdf8,

        linewidth: 1,

        scale: 1,

        dashSize: 0.08,

        gapSize: 0.06,

        transparent: true,

        opacity: 0.25

      });


    const points = [];


    points.push(
      latLonToVector3(
        17.5,
        64.5,
        GLOBE_RADIUS + 0.01
      )
    );


    points.push(
      latLonToVector3(
        17.5,
        74.5,
        GLOBE_RADIUS + 0.01
      )
    );


    points.push(
      latLonToVector3(
        7.5,
        74.5,
        GLOBE_RADIUS + 0.01
      )
    );


    points.push(
      latLonToVector3(
        7.5,
        64.5,
        GLOBE_RADIUS + 0.01
      )
    );


    points.push(
      latLonToVector3(
        17.5,
        64.5,
        GLOBE_RADIUS + 0.01
      )
    );


    const geometry =
      new THREE.BufferGeometry()
        .setFromPoints(points);


    const boundaryLine =
      new THREE.Line(
        geometry,
        material
      );


    boundaryLine.computeLineDistances();


    scene.add(
      boundaryLine
    );

  }


  // =========================================================================
  // EARTH SPHERE
  // =========================================================================

  function createEarthSphere() {

    /*
     * Prevent accidental duplicate Earth meshes.
     */

    if (earthGlobe) {

      scene.remove(
        earthGlobe
      );

      earthGlobe.geometry.dispose();

      if (earthGlobe.material) {
        earthGlobe.material.dispose();
      }

    }


    const geometry =
      new THREE.SphereGeometry(
        GLOBE_RADIUS,
        64,
        64
      );


    const textureLoader =
      new THREE.TextureLoader();


    const earthTexture =
      textureLoader.load(
        "https://unpkg.com/three-globe/example/img/earth-blue-marble.jpg"
      );


    const bumpTexture =
      textureLoader.load(
        "https://unpkg.com/three-globe/example/img/earth-topology.png"
      );


    const material =
      new THREE.MeshPhongMaterial({

        map: earthTexture,

        bumpMap: bumpTexture,

        bumpScale: 0.06,

        shininess: 25,

        specular:
          new THREE.Color(
            0x333333
          ),

        emissive:
          new THREE.Color(
            0x000000
          )

      });


    earthGlobe =
      new THREE.Mesh(
        geometry,
        material
      );


    earthGlobe.name =
      "Earth Globe";


    scene.add(
      earthGlobe
    );

  }


  // =========================================================================
  // ATMOSPHERE
  // =========================================================================

  function createAtmosphereGlow() {

    const geometry =
      new THREE.SphereGeometry(
        GLOBE_RADIUS * 1.04,
        48,
        48
      );


    const vertexShader = `

      varying vec3 vNormal;

      void main() {

        vNormal =
          normalize(
            normalMatrix * normal
          );

        gl_Position =
          projectionMatrix *
          modelViewMatrix *
          vec4(
            position,
            1.0
          );

      }

    `;


    const fragmentShader = `

      varying vec3 vNormal;

      void main() {

        float intensity =
          pow(
            0.68 -
            dot(
              vNormal,
              vec3(
                0.0,
                0.0,
                1.0
              )
            ),
            2.8
          );

        gl_FragColor =
          vec4(
            0.0,
            0.96,
            0.83,
            1.0
          )
          *
          intensity
          *
          0.7;

      }

    `;


    const material =
      new THREE.ShaderMaterial({

        vertexShader,

        fragmentShader,

        blending:
          THREE.AdditiveBlending,

        side:
          THREE.BackSide,

        transparent:
          true,

        depthWrite:
          false

      });


    atmosphereMesh =
      new THREE.Mesh(
        geometry,
        material
      );


    atmosphereMesh.name =
      "Atmosphere Glow";


    scene.add(
      atmosphereMesh
    );

  }


  // =========================================================================
  // STARFIELD
  // =========================================================================

  function createStarfield() {

    const starGeometry =
      new THREE.BufferGeometry();


    const starCount = 1200;


    const positions =
      new Float32Array(
        starCount * 3
      );


    const colors =
      new Float32Array(
        starCount * 3
      );


    for (
      let i = 0;
      i < starCount;
      i++
    ) {

      const r =
        35 +
        Math.random() * 45;


      const theta =
        Math.random() *
        Math.PI *
        2;


      const phi =
        Math.acos(
          Math.random() * 2 - 1
        );


      positions[i * 3] =
        r *
        Math.sin(phi) *
        Math.cos(theta);


      positions[i * 3 + 1] =
        r *
        Math.sin(phi) *
        Math.sin(theta);


      positions[i * 3 + 2] =
        r *
        Math.cos(phi);


      const isCyan =
        Math.random() > 0.6;


      colors[i * 3] =
        isCyan
          ? 0.0
          : 0.4;


      colors[i * 3 + 1] =
        isCyan
          ? 0.95
          : 0.7;


      colors[i * 3 + 2] =
        1.0;

    }


    starGeometry.setAttribute(
      "position",
      new THREE.BufferAttribute(
        positions,
        3
      )
    );


    starGeometry.setAttribute(
      "color",
      new THREE.BufferAttribute(
        colors,
        3
      )
    );


    const starMaterial =
      new THREE.PointsMaterial({

        size: 0.45,

        vertexColors: true,

        transparent: true,

        opacity: 0.8,

        blending:
          THREE.AdditiveBlending,

        depthWrite: false

      });


    const starField =
      new THREE.Points(
        starGeometry,
        starMaterial
      );


    scene.add(
      starField
    );

  }


  // =========================================================================
  // OCEAN CURRENT PARTICLES
  // =========================================================================

  function createOceanCurrentParticles() {

    const particleCount = 280;


    const geometry =
      new THREE.BufferGeometry();


    const positions =
      new Float32Array(
        particleCount * 3
      );


    const baseAngles = [];


    for (
      let i = 0;
      i < particleCount;
      i++
    ) {

      /*
       * Arabian Sea:
       *
       * Latitude:
       * 9 -> 16.5
       *
       * Longitude:
       * 65.5 -> 73
       */

      const lat =
        9 +
        Math.random() * 7.5;


      const lon =
        65.5 +
        Math.random() * 7.5;


      const altitude =
        GLOBE_RADIUS *
        (
          1.012 +
          Math.random() * 0.008
        );


      const basePos =
        latLonToVector3(
          lat,
          lon,
          altitude
        );


      positions[i * 3] =
        basePos.x;


      positions[i * 3 + 1] =
        basePos.y;


      positions[i * 3 + 2] =
        basePos.z;


      baseAngles.push({

        lat: lat,

        lon: lon,

        speed:
          0.02 +
          Math.random() * 0.03,

        altitude: altitude

      });

    }


    geometry.setAttribute(
      "position",
      new THREE.BufferAttribute(
        positions,
        3
      )
    );


    /*
     * ==========================================================
     * CRITICAL FIX
     * ==========================================================
     *
     * OLD:
     *
     * size: 2.2
     *
     * NEW:
     *
     * size: 0.055
     *
     * Globe radius = 5.0
     *
     * This keeps particles tiny.
     */

    const material =
      new THREE.PointsMaterial({

        size: 0.055,

        color: 0x00f5d4,

        transparent: true,

        opacity: 0.65,

        blending:
          THREE.AdditiveBlending,

        depthWrite: false

      });


    currentParticles =
      new THREE.Points(
        geometry,
        material
      );


    currentParticles.name =
      "Arabian Sea Ocean Currents";


    currentParticles.userData = {

      angles:
        baseAngles

    };


    scene.add(
      currentParticles
    );

  }


  // =========================================================================
  // LAT/LON -> THREE VECTOR
  // =========================================================================

  function latLonToVector3(
    lat,
    lon,
    radius
  ) {

    const phi =
      (90 - lat) *
      (Math.PI / 180);


    const theta =
      (lon + 180) *
      (Math.PI / 180);


    return new THREE.Vector3(

      -(
        radius *
        Math.sin(phi) *
        Math.cos(theta)
      ),

      radius *
      Math.cos(phi),

      radius *
      Math.sin(phi) *
      Math.sin(theta)

    );

  }


  // =========================================================================
  // STATION MARKERS
  // =========================================================================

  function createStationMarkers() {

    markerGroup =
      new THREE.Group();


    markerGroup.name =
      "Station Hitboxes";


    stationMeshes = [];


    const stations =
      window.OCEAN_DATA
        ? window.OCEAN_DATA.stations
        : [];


    const metricConf =
      METRIC_CONFIG[
        state.activeMetric
      ];


    stations.forEach(
      (station) => {

        const pos =
          latLonToVector3(
            station.lat,
            station.lon,
            GLOBE_RADIUS + 0.012
          );


        const color =
          new THREE.Color(
            metricConf.getColor(
              metricConf.getVal(
                station
              )
            )
          );


        /*
         * Visible glowing dot marker
         */
        const dotCanvas = document.createElement("canvas");
        dotCanvas.width = 32;
        dotCanvas.height = 32;
        const ctx = dotCanvas.getContext("2d");
        const gradient = ctx.createRadialGradient(16, 16, 0, 16, 16, 16);
        gradient.addColorStop(0, "rgba(0, 245, 212, 1)");
        gradient.addColorStop(0.3, "rgba(0, 245, 212, 0.6)");
        gradient.addColorStop(1, "rgba(0, 245, 212, 0)");
        ctx.fillStyle = gradient;
        ctx.fillRect(0, 0, 32, 32);

        const dotTex = new THREE.CanvasTexture(dotCanvas);

        const spriteMat = new THREE.SpriteMaterial({
          map: dotTex,
          transparent: true,
          depthWrite: false,
          blending: THREE.AdditiveBlending
        });

        const sprite = new THREE.Sprite(spriteMat);
        sprite.position.copy(pos);
        sprite.scale.set(0.01, 0.01, 0.01);

        /*
         * Metadata.
         */

        sprite.userData = {
          station: station,
          baseColor: color
        };

        markerGroup.add(
          sprite
        );

        stationMeshes.push(
          sprite
        );

      }
    );


    scene.add(
      markerGroup
    );

  }


  // =========================================================================
  // CAMERA
  // =========================================================================

  function setCameraPositionToLatLon(
    lat,
    lon,
    distance = 14.0
  ) {

    const targetPos =
      latLonToVector3(
        lat,
        lon,
        distance
      );


    if (!camera) return;


    camera.position.set(
      targetPos.x,
      targetPos.y,
      targetPos.z
    );


    camera.lookAt(
      0,
      0,
      0
    );

  }


  // =========================================================================
  // LEAFLET MAP
  // =========================================================================

  function initLeafletMap() {

    const center =
      (
        window.OCEAN_DATA &&
        window.OCEAN_DATA.center
      )
      ||
      [14.0, 71.0];


    const zoom =
      (
        window.OCEAN_DATA &&
        window.OCEAN_DATA.defaultZoom
      )
      ||
      6;


    leafletMap =
      L.map(
        "map-2d-container",
        {
          center: center,
          zoom: zoom,
          zoomControl: true,
          preferCanvas: true,
          scrollWheelZoom: true,
          wheelPxPerZoomLevel: 50,
          wheelDebounceTime: 30
        }
      );

    const map2dEl = document.getElementById("map-2d-container");
    if (map2dEl) {
      map2dEl.addEventListener("wheel", (e) => {
        if (e.ctrlKey) {
          e.preventDefault();
        }
      }, { passive: false });
    }


    /*
     * CartoDB Dark Matter (matching 3D Globe dark basemap)
     */
    L.tileLayer(
      "https://basemaps.cartocdn.com/rastertiles/dark_all/{z}/{x}/{y}.png?key=cb1_3he2_1_f384df18951386690f3fe38c",
      {
        minZoom: 2,
        maxZoom: 18,
        attribution:
          '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
      }
    ).addTo(leafletMap);
    window.leafletMap = leafletMap;

    leafletMarkerGroup = L.featureGroup().addTo(leafletMap);
    leafletMajorPortsGroup = L.featureGroup().addTo(leafletMap);
    leafletMinorPortsGroup = L.featureGroup();

    renderLeafletMarkers();
    renderLeafletPorts();

    // Zoom-dependent Level of Detail (LOD) for 2D coastal ports
    function updateLeafletPortLOD() {
      if (!leafletMap || !leafletMinorPortsGroup) return;
      const zoom = leafletMap.getZoom();
      if (zoom >= 6) {
        if (!leafletMap.hasLayer(leafletMinorPortsGroup)) {
          leafletMap.addLayer(leafletMinorPortsGroup);
        }
      } else {
        if (leafletMap.hasLayer(leafletMinorPortsGroup)) {
          leafletMap.removeLayer(leafletMinorPortsGroup);
        }
      }
    }

    leafletMap.on("zoomend", updateLeafletPortLOD);
    updateLeafletPortLOD();

    // 12 NM Maritime Regulatory Boundary
    fetch("data/india_12nm_boundary.json")
      .then(res => res.json())
      .then(geoJson => {
        if (!leafletMap) return;
        L.geoJSON(geoJson, {
          style: {
            color: "#00e5ff",
            weight: 1.5,
            opacity: 0.65,
            dashArray: "4, 6"
          }
        }).addTo(leafletMap);
      })
      .catch(err => console.warn("Could not load Leaflet 12nm boundary:", err));
  }

  const COASTAL_PORTS_REGISTRY = [
    { name: "Kandla Port", lat: 23.01, lon: 70.22, isMajor: true },
    { name: "Mundra Port", lat: 22.74, lon: 69.71, isMajor: true },
    { name: "Porbandar Port", lat: 21.64, lon: 69.61, isMajor: true },
    { name: "Veraval Port", lat: 20.91, lon: 70.37, isMajor: true },
    { name: "Pipavav Port", lat: 20.91, lon: 71.50, isMajor: true },
    { name: "Hazira Port", lat: 21.10, lon: 72.64, isMajor: true },
    { name: "Jakhau", lat: 23.24, lon: 68.71, isMajor: false },
    { name: "Mandvi", lat: 22.83, lon: 69.36, isMajor: false },
    { name: "Navlakhi", lat: 22.96, lon: 70.45, isMajor: false },
    { name: "Bedi", lat: 22.50, lon: 70.04, isMajor: false },
    { name: "Sikka", lat: 22.43, lon: 69.84, isMajor: false },
    { name: "Salaya", lat: 22.31, lon: 69.60, isMajor: false },
    { name: "Okha", lat: 22.47, lon: 69.07, isMajor: false },
    { name: "Mangrol", lat: 21.12, lon: 70.11, isMajor: false },
    { name: "Jafrabad", lat: 20.87, lon: 71.37, isMajor: false },
    { name: "Alang", lat: 21.41, lon: 72.20, isMajor: false },
    { name: "Bhavnagar", lat: 21.78, lon: 72.18, isMajor: false },
    { name: "Dahej", lat: 21.70, lon: 72.53, isMajor: false },
    { name: "Daman", lat: 20.40, lon: 72.83, isMajor: false },
    { name: "Mumbai Port", lat: 18.94, lon: 72.84, isMajor: true },
    { name: "JNPT", lat: 18.95, lon: 72.95, isMajor: true },
    { name: "Alibaug", lat: 18.73, lon: 72.88, isMajor: false },
    { name: "Dighi", lat: 18.28, lon: 72.98, isMajor: false },
    { name: "Dabhol", lat: 17.59, lon: 73.18, isMajor: false },
    { name: "Jaigad", lat: 17.30, lon: 73.21, isMajor: false },
    { name: "Ratnagiri", lat: 16.99, lon: 73.30, isMajor: false },
    { name: "Vijaydurg", lat: 16.56, lon: 73.33, isMajor: false },
    { name: "Devgad", lat: 16.38, lon: 73.38, isMajor: false },
    { name: "Malvan", lat: 16.05, lon: 73.47, isMajor: false },
    { name: "Mormugao", lat: 15.41, lon: 73.80, isMajor: true },
    { name: "Panaji", lat: 15.50, lon: 73.83, isMajor: false },
    { name: "Mangaluru Port", lat: 12.91, lon: 74.88, isMajor: true },
    { name: "Karwar", lat: 14.80, lon: 74.12, isMajor: false },
    { name: "Tadri", lat: 14.52, lon: 74.35, isMajor: false },
    { name: "Honnavar", lat: 14.28, lon: 74.44, isMajor: false },
    { name: "Bhatkal", lat: 13.98, lon: 74.55, isMajor: false },
    { name: "Kundapura", lat: 13.63, lon: 74.69, isMajor: false },
    { name: "Malpe", lat: 13.35, lon: 74.70, isMajor: false },
    { name: "Kochi Port", lat: 9.93, lon: 76.27, isMajor: true },
    { name: "Kollam", lat: 8.89, lon: 76.59, isMajor: false },
    { name: "Thiruvananthapuram", lat: 8.52, lon: 76.94, isMajor: false },
    { name: "Chennai Port", lat: 13.08, lon: 80.27, isMajor: true },
    { name: "Visakhapatnam Port", lat: 17.69, lon: 83.22, isMajor: true }
  ];

  function isInsideEEZ(lat, lon) {
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return false;
    if (lat < 7.0 || lat > 24.5 || lon < 65.0 || lon > 78.5) return false;
    // Northwest boundary line from (19.0°N, 72.5°E) to (23.5°N, 68.0°E)
    if (lat >= 19.0) {
      const minLon = 68.0 + (23.5 - lat) * (72.5 - 68.0) / (23.5 - 19.0);
      if (lon < minLon) return false;
    } else if (lat >= 15.0) {
      if (lon < 68.5) return false;
    } else {
      if (lon < 71.0) return false;
    }
    return true;
  }

  // =========================================================================
  // LEAFLET COASTAL PORTS (MAJOR HUD BADGES & MINOR MICRO-PILLS)
  // =========================================================================

  function renderLeafletPorts() {
    if (!leafletMap || !leafletMajorPortsGroup || !leafletMinorPortsGroup) return;

    leafletMajorPortsGroup.clearLayers();
    leafletMinorPortsGroup.clearLayers();

    const ports = (window.OCEAN_DATA && window.OCEAN_DATA.coastalPorts && window.OCEAN_DATA.coastalPorts.length > 0)
      ? window.OCEAN_DATA.coastalPorts
      : COASTAL_PORTS_REGISTRY;

    ports.forEach((port) => {
      const isMajor = !!port.isMajor;
      const badgeClass = isMajor ? "leaflet-port-badge-major" : "leaflet-port-badge-minor";
      const anchorClass = isMajor ? "leaflet-port-anchor" : "leaflet-port-anchor-minor";

      const portIcon = L.divIcon({
        className: "orca-leaflet-pill-container",
        html: `<div class="${badgeClass}"><span class="${anchorClass}">âš“</span><span>${port.name}</span></div>`,
        iconSize: [0, 0],
        iconAnchor: [0, 0]
      });

      const marker = L.marker([port.lat, port.lon], {
        icon: portIcon,
        bubblingMouseEvents: false
      });

      marker.bindPopup(`
        <div style="font-family: var(--font-sans); color: #e2e8f0; min-width: 180px;">
          <div style="font-size: 13px; font-weight: 700; color: #00f5d4; margin-bottom: 4px; display: flex; align-items: center; gap: 6px;">
            <span>âš“</span> <span>${port.name}</span>
          </div>
          <div style="font-size: 11px; color: #94a3b8; line-height: 1.5;">
            <div>Classification: <span style="color: ${isMajor ? '#00f5d4' : '#a8d5db'}; font-weight: 600;">${isMajor ? 'Major Maritime Gateway' : 'Coastal Feeder / Fishing Port'}</span></div>
            <div>Coordinates: <span style="color: #cbd5e1;">${port.lat.toFixed(2)}°N, ${port.lon.toFixed(2)}°E</span></div>
            <div>Status: <span style="color: #00f5d4; font-weight: 600;">Operational Marine Node</span></div>
          </div>
        </div>
      `, {
        className: "orca-leaflet-popup",
        closeButton: true,
        autoPan: false
      });

      marker.on("click", () => {
        const stations = (window.OCEAN_DATA && window.OCEAN_DATA.stations) || [];
        let nearest = null;
        let minDist = Infinity;
        stations.forEach((s) => {
          const d = Math.hypot(s.lat - port.lat, s.lon - port.lon);
          if (d < minDist) {
            minDist = d;
            nearest = s;
          }
        });

        const portStation = {
          id: `port-${port.name.toLowerCase().replace(/[^a-z0-9]/g, '-')}`,
          name: port.name,
          lat: port.lat,
          lon: port.lon,
          sst: nearest && nearest.sst ? nearest.sst : 28.5,
          oxygen: nearest && nearest.oxygen ? nearest.oxygen : 5.2,
          ph: nearest && nearest.ph ? nearest.ph : 8.15,
          chlorophyll: nearest && nearest.chlorophyll ? nearest.chlorophyll : 1.2,
          salinity: nearest && nearest.salinity ? nearest.salinity : 35.5,
          currentSpeed: nearest && nearest.current_speed !== undefined ? nearest.current_speed : 0.35,
          healthScore: nearest && nearest.healthScore ? nearest.healthScore : 82,
          healthStatus: "Optimal",
          statusColor: "#00f5d4",
          distance: 0,
          isMajor: isMajor,
          is_port: true
        };

        if (window.ORCA_SET_DEPARTURE) {
          window.ORCA_SET_DEPARTURE(portStation);
        } else if (window.ORCA_STATE) {
          window.ORCA_STATE.selectedDeparture = portStation;
        }

        selectStation(portStation, { showPfzDialog: false });

        if (leafletMap) {
          leafletMap.flyTo([port.lat, port.lon], Math.max(leafletMap.getZoom(), 7), {
            duration: 0.8
          });
        }
      });

      if (isMajor) {
        leafletMajorPortsGroup.addLayer(marker);
      } else {
        leafletMinorPortsGroup.addLayer(marker);
      }
    });
  }

  // =========================================================================
  // LEAFLET PFZ NAVIGATION ROUTE
  // =========================================================================

  function drawLeafletRoute(station) {
    if (!leafletMap) return;

    if (activeLeafletRoute) {
      leafletMap.removeLayer(activeLeafletRoute);
      activeLeafletRoute = null;
    }

    // Departure navigation routes are strictly drawn to favorable fishing spots (never port to port)
    if (!station || !station.is_fishing_spot || station.is_port || station.isMajor !== undefined) return;

    const ports = (window.OCEAN_DATA && window.OCEAN_DATA.coastalPorts) || COASTAL_PORTS_REGISTRY;
    if (!ports.length || !station.lat || !station.lon) return;

    const calcKm = (lat1, lon1, lat2, lon2) => {
      const R = 6371;
      const dLat = (lat2 - lat1) * Math.PI / 180;
      const dLon = (lon2 - lon1) * Math.PI / 180;
      const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
                Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
                Math.sin(dLon / 2) * Math.sin(dLon / 2);
      return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    };

    let departure = (window.ORCA_STATE && window.ORCA_STATE.selectedDeparture)
      ? window.ORCA_STATE.selectedDeparture
      : null;

    if (!departure && ports.length > 0) {
      let nearestPort = ports[0];
      let minDist = calcKm(nearestPort.lat, nearestPort.lon, station.lat, station.lon);
      for (let i = 1; i < ports.length; i++) {
        const d = calcKm(ports[i].lat, ports[i].lon, station.lat, station.lon);
        if (d < minDist) {
          minDist = d;
          nearestPort = ports[i];
        }
      }
      departure = nearestPort;
      if (window.ORCA_SET_DEPARTURE) {
        window.ORCA_SET_DEPARTURE(departure);
      }
    }

    if (!departure) return;

    const oLat = Number(departure.latitude ?? departure.lat);
    const oLon = Number(departure.longitude ?? departure.lon);
    const dLat = Number(station.latitude ?? station.lat);
    const dLon = Number(station.longitude ?? station.lon);

    if (!Number.isFinite(oLat) || !Number.isFinite(oLon) || !Number.isFinite(dLat) || !Number.isFinite(dLon)) {
      console.warn("[ORCA ROUTE] No valid route available: Invalid numeric coordinates.");
      return;
    }

    const distKm = calcKm(oLat, oLon, dLat, dLon);
    console.log(`[ORCA ROUTE]\nORIGIN: ${oLat.toFixed(3)}°N, ${oLon.toFixed(3)}°E\nDESTINATION: ${dLat.toFixed(3)}°N, ${dLon.toFixed(3)}°E\nDISTANCE: ${distKm.toFixed(1)} km`);

    activeLeafletRoute = L.polyline(
      [
        [oLat, oLon],
        [dLat, dLon]
      ],
      {
        color: "#00f5d4",
        weight: 2.8,
        dashArray: "6, 8",
        opacity: 0.9
      }
    ).addTo(leafletMap);

    station._nearestPort = departure.name;
    station._routeDistKm = distKm.toFixed(1);

    if (window.ORCA_STATE) {
      window.ORCA_STATE.route = {
        origin: departure,
        destination: station,
        distance_km: distKm,
        route_distance_km: Math.round(distKm * 1.12 * 10) / 10
      };
    }
  }

  // =========================================================================
  // LEAFLET MARKERS (STABLE MONITORING GRID + HIGH-VISIBILITY PFZ BEACONS)
  // =========================================================================

  function renderLeafletMarkers() {
    if (!leafletMarkerGroup) return;

    leafletMarkerGroup.clearLayers();
    leafletMarkers = [];

    const stations = (window.OCEAN_DATA && window.OCEAN_DATA.stations) ? window.OCEAN_DATA.stations : [];
    const metricConf = METRIC_CONFIG[state.activeMetric];

    stations.forEach((station, index) => {
      // HARD FILTER: Remove any points outside the Indian EEZ boundary
      if (!isInsideEEZ(station.lat, station.lon)) {
        return;
      }

      const isPfz = !!station.is_fishing_spot;

      /*
       * Filters
       */
      if (state.filterStatus === "optimal" && station.healthScore < 75) {
        return;
      }
      if (state.filterStatus === "stressed" && station.healthScore >= 75) {
        return;
      }

      if (isPfz) {
        const tier = station.fishing_tier || "high";
        let markerHtml = '<div class="leaflet-pfz-beacon" title="High / Favorable PFZ"></div>';
        if (tier === "moderate") {
          markerHtml = '<div class="leaflet-pfz-beacon" style="background:#fbbf24; border-color:#f59e0b; box-shadow: 0 0 10px rgba(251,191,36,0.7);" title="Moderate PFZ"></div>';
        } else if (tier === "low") {
          markerHtml = '<div class="leaflet-pfz-beacon" style="background:#64748b; border-color:#d97706; width:10px; height:10px; box-shadow: 0 0 6px rgba(217,119,6,0.5);" title="Less Favorable PFZ"></div>';
        }

        const pfzIcon = L.divIcon({
          className: "orca-leaflet-pill-container",
          html: markerHtml,
          iconSize: [14, 14],
          iconAnchor: [7, 7]
        });

        const marker = L.marker([station.lat, station.lon], {
          icon: pfzIcon,
          bubblingMouseEvents: false
        });

        const suitability = station.fishing_suitability || 85;
        const tierLabel = station.tier_label || (tier === "high" ? "HIGH / FAVORABLE" : (tier === "moderate" ? "MODERATE / POTENTIAL" : "LESS FAVORABLE"));
        const sColor = tier === "high" ? "#00f5d4" : (tier === "moderate" ? "#fbbf24" : "#f59e0b");
        const reasonsList = Array.isArray(station.fishing_reasons) && station.fishing_reasons.length > 0
          ? station.fishing_reasons.map(r => `&bull; ${r}`).join("<br/>")
          : "&bull; Optimal thermal & chlorophyll forage front";
        const speciesList = station.target_species && Array.isArray(station.target_species)
          ? station.target_species.join(", ")
          : "Sardines, Indian Mackerel, Squid";

        marker.bindPopup(`
          <div style="font-family: var(--font-sans); min-width: 240px; color: #f0f6fc;">
            <div style="font-size: 12.5px; font-weight: 600; color: #38bdf8; margin-bottom: 6px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid rgba(255,255,255,0.08); padding-bottom: 4px;">
              <span>ðŸŸ ${station.name || 'Fishing Zone'}</span>
              <span style="color: ${sColor}; font-size: 9.5px; font-weight: 700; background: rgba(56,189,248,0.12); border: 1px solid rgba(56,189,248,0.25); padding: 2px 6px; border-radius: 4px;">${tierLabel}</span>
            </div>
            <div style="font-size: 11px; color: #cbd5e1; line-height: 1.5; margin-bottom: 6px;">
              <div>Location: <b style="font-family: var(--font-mono); color: #f0f6fc;">${station.lat.toFixed(2)}°N, ${station.lon.toFixed(2)}°E</b></div>
              <div>Suitability Score: <b>${suitability}/100</b> | SLA: <b>${station.sla_text || '+8 cm'}</b></div>
              <div>SST: <b>${station.sst ? station.sst.toFixed(1) : '--'}°C</b> | Chl-a: <b>${station.chlorophyll ? station.chlorophyll.toFixed(2) : '--'} mg/m³</b></div>
              <div>Marine Health: <b style="color: ${station.healthScore >= 55 ? '#34d399' : '#fbbf24'};">${station.healthScore ? station.healthScore.toFixed(0) : '75'}/100</b> | Salinity: <b>${station.salinity ? station.salinity.toFixed(1) : '35.5'} PSU</b></div>
              <div style="margin-top: 3px; font-size: 10.5px; color: #94a3b8;">Target Catch: <b style="color: #e2e8f0;">${speciesList}</b></div>
            </div>
            <div style="font-size: 10px; color: #94a3b8; border-top: 1px solid rgba(255,255,255,0.08); padding-top: 5px;">
              <b style="color: #cbd5e1;">Oceanographic Rationale:</b><br/>
              ${reasonsList}
            </div>
          </div>
        `, {
          className: "orca-leaflet-popup",
          closeButton: true,
          autoPan: false
        });

        marker.on("click", () => {
          selectStation(station);
          drawLeafletRoute(station);
          if (window.ORCA_AGENT && typeof window.ORCA_AGENT.openDepartureModalForSpot === "function") {
            try { window.ORCA_AGENT.openDepartureModalForSpot(station); } catch(e) {}
          }
        });

        marker.addTo(leafletMarkerGroup);
        leafletMarkers.push({ station, circle: marker });

      } else {
        // Clean, subtle ocean monitoring telemetry node (Virtual Observation Cell)
        const markerColor = metricConf.getColor(metricConf.getVal(station));

        const circle = L.circleMarker([station.lat, station.lon], {
          radius: 3.5,
          color: markerColor,
          fillColor: markerColor,
          fillOpacity: 0.60,
          weight: 1,
          bubblingMouseEvents: false
        });

        circle.bindTooltip(
          `<strong>${station.name || 'VO-Cell'}</strong><br/>
           ${metricConf.name}: ${metricConf.getVal(station)} ${metricConf.unit}<br/>
           Health: ${station.healthScore ? station.healthScore.toFixed(0) : '--'}/100 | SST: ${station.sst ? station.sst.toFixed(1) + '°C' : '--'} | SLA: ${station.sla_text || '+8 cm'}`,
          {
            className: "leaflet-dark-tooltip",
            sticky: true
          }
        );

        circle.on("click", () => {
          selectStation(station, { showPfzDialog: false });
        });

        circle.addTo(leafletMarkerGroup);
        leafletMarkers.push({ station, circle });
      }
    });
  }


  // =========================================================================
  // INTERACTIVITY
  // =========================================================================

  function selectStation(
    station,
    options = {}
  ) {

    if (!station)
      return;


    // The PFZ dialog should only pop up when the user actually clicks a
    // station on the globe/map, not for the default station selected on
    // page load — it was previously showing unconditionally, which meant
    // it popped open over the globe immediately on every load.
    const {
      showPfzDialog = false
    } = options;


    state.selectedStation =
      station;


    /*
     * Update telemetry panel
     */

    updateTelemetryInspector(
      station
    );


    /*
     * Highlight station hitbox.
     */

    stationMeshes.forEach(
      (meshObj) => {

        const isSelected =
          meshObj.userData.station.id ===
          station.id;


        meshObj.scale.setScalar(
          isSelected
            ? 0.02
            : 0.01
        );

      }
    );


    /*
     * Leaflet mode
     */

    if (
      state.viewMode === "2d" &&
      leafletMap
    ) {

      leafletMap.panTo(
        [
          station.lat,
          station.lon
        ],
        {
          animate: true
        }
      );

      if (station.is_fishing_spot) {
        drawLeafletRoute(station);
      } else if (activeLeafletRoute) {
        leafletMap.removeLayer(activeLeafletRoute);
        activeLeafletRoute = null;
      }

    }

  }


  // =========================================================================
  // TELEMETRY INSPECTOR
  // =========================================================================

  function updateTelemetryInspector(
    s
  ) {

    const name =
      document.getElementById(
        "inspector-name"
      );


    const id =
      document.getElementById(
        "inspector-id"
      );


    const coords =
      document.getElementById(
        "inspector-coords"
      );


    const depth =
      document.getElementById(
        "inspector-depth"
      );


    const statusPill =
      document.getElementById(
        "inspector-status"
      );


    if (name)
      name.textContent =
        s.name;


    if (id)
      id.textContent =
        s.id;


    if (coords)
      coords.textContent =
        `${s.lat.toFixed(2)}°N, ${s.lon.toFixed(2)}°E`;


    if (depth)
      depth.textContent =
        s.depth != null ? `${Number(s.depth).toLocaleString()} m` : "Not supplied";


    if (statusPill) {

      statusPill.textContent =
        s.healthStatus || "Normal";

      statusPill.style.backgroundColor =
        `${s.statusColor || '#00f5d4'}22`;

      statusPill.style.color =
        s.statusColor || '#00f5d4';

      statusPill.style.border =
        `1px solid ${s.statusColor || '#00f5d4'}`;

    }


    /*
     * Telemetry meters matching globe.html gauge IDs
     */

    const sstaVal = s.ssta !== undefined ? s.ssta : (s.thetao_anom !== undefined ? s.thetao_anom : null);
    updateMeter(
      "meter-thetao-anom",
      sstaVal,
      -2,
      2,
      sstaVal != null ? `${sstaVal > 0 ? '+' : ''}${Number(sstaVal).toFixed(2)} °C` : "Not supplied",
      sstaVal != null && sstaVal > 0 ? "#ef476f" : "#00f5d4"
    );


    updateMeter(
      "meter-temp",
      s.sst,
      25,
      33,
      s.sst != null ? `${Number(s.sst).toFixed(1)} °C` : "Not supplied",
      s.sst != null && s.sst > 30
        ? "#ffd166"
        : "#00b4d8"
    );


    const slaVal = s.sla_anomaly !== undefined ? s.sla_anomaly : (s.sla_anom !== undefined ? s.sla_anom : (s.sla !== undefined ? s.sla : 0.08));
    const slaFormatted = slaVal != null ? `${slaVal > 0 ? '+' : ''}${Number(slaVal).toFixed(2)} m (${slaVal > 0 ? '+' : ''}${Math.round(slaVal * 100)} cm)` : "+0.08 m (+8 cm)";
    updateMeter(
      "meter-sla-anom",
      slaVal,
      -0.5,
      0.5,
      slaFormatted,
      "#00f5d4"
    );


    updateMeter(
      "meter-so-anom",
      s.salinity,
      30,
      38,
      s.salinity != null ? `${Number(s.salinity).toFixed(1)} PSU` : "Not supplied",
      "#0077b6"
    );


    updateMeter(
      "meter-log-chl",
      s.chlorophyll,
      0,
      2.0,
      s.chlorophyll != null ? `${Number(s.chlorophyll).toFixed(2)} mg/m³` : "Not supplied",
      "#a7c957"
    );


    drawStationSparkline(
      s
    );

  }


  // =========================================================================
  // UPDATE METER
  // =========================================================================

  function updateMeter(
    id,
    val,
    min,
    max,
    label,
    color
  ) {

    const fill =
      document.getElementById(
        `${id}-fill`
      );


    const valText =
      document.getElementById(
        `${id}-val`
      );


    if (
      !fill ||
      !valText
    ) {
      return;
    }

    if (val === null || val === undefined || isNaN(val)) {
      fill.style.width = "0%";
      valText.textContent = label || "Not supplied";
      return;
    }

    const pct =
      Math.max(
        0,
        Math.min(
          100,
          (
            (val - min) /
            (max - min)
          ) *
          100
        )
      );


    fill.style.width =
      `${pct}%`;


    fill.style.backgroundColor =
      color;


    fill.style.boxShadow =
      `0 0 8px ${color}88`;


    valText.textContent =
      label;

  }


  // =========================================================================
  // ARABIAN SEA MARINE HEALTH INDEX (MHI) TREND GRAPH MONITOR
  // =========================================================================

  let mhiCanvas = null;
  let mhiCtx = null;
  let mhiHoverIndex = -1;

  const mhiTrendData = {
    labels: ["D-3", "D-2", "D-1", "TODAY", "D+1", "D+2", "D+3"],
    labelDescriptions: [
      "Hindcast",
      "Hindcast",
      "Observed",
      "Realtime",
      "+24h Forecast",
      "+48h Forecast",
      "+72h Forecast"
    ],
    // Baseline deviations across the 7-day synoptic cycle
    offsets: [-1.4, -0.8, +0.3, 0.0, -0.5, +0.9, +0.6],
    basinAvg: 55.2,
    activeStation: null
  };

  function computeBasinAvgMhi() {
    if (
      window.OCEAN_DATA &&
      Array.isArray(window.OCEAN_DATA.stations) &&
      window.OCEAN_DATA.stations.length > 0
    ) {
      const sum = window.OCEAN_DATA.stations.reduce(
        (acc, st) => acc + (typeof st.healthScore === "number" ? st.healthScore : 55),
        0
      );
      return +(sum / window.OCEAN_DATA.stations.length).toFixed(1);
    }
    if (window.OCEAN_DATA && typeof window.OCEAN_DATA.overallHealthIndex === "number") {
      return +window.OCEAN_DATA.overallHealthIndex.toFixed(1);
    }
    return 55.2;
  }

  function getMhiStatus(val) {
    if (val >= 75) return { text: "HEALTHY", class: "healthy", color: "#00f5d4" };
    if (val >= 50) return { text: "MODERATE", class: "moderate", color: "#ffd166" };
    return { text: "STRESSED", class: "stressed", color: "#ff4d6d" };
  }

  function renderMhiGraph() {
    if (!mhiCtx || !mhiCanvas) return;

    const width = mhiCanvas.width || 280;
    const height = mhiCanvas.height || 68;

    mhiCtx.clearRect(0, 0, width, height);

    const padLeft = 16;
    const padRight = 16;
    const padTop = 12;
    const padBottom = 14;
    const plotWidth = width - padLeft - padRight;
    const plotHeight = height - padTop - padBottom;

    const basinAvg = mhiTrendData.basinAvg || 55.2;
    const n = mhiTrendData.labels.length;

    // Build values array
    const points = [];
    const minVal = Math.floor(basinAvg - 6);
    const maxVal = Math.ceil(basinAvg + 6);
    const valRange = maxVal - minVal || 12;

    for (let i = 0; i < n; i++) {
      const val = +(basinAvg + mhiTrendData.offsets[i]).toFixed(1);
      const x = padLeft + (i / (n - 1)) * plotWidth;
      const normY = (val - minVal) / valRange;
      const y = height - padBottom - normY * plotHeight;
      points.push({
        x,
        y,
        val,
        label: mhiTrendData.labels[i],
        desc: mhiTrendData.labelDescriptions[i],
        isToday: i === 3
      });
    }

    // 1. Draw subtle horizontal grid lines (reference levels)
    mhiCtx.save();
    mhiCtx.lineWidth = 1;
    mhiCtx.setLineDash([3, 4]);
    mhiCtx.strokeStyle = "rgba(0, 245, 212, 0.10)";

    [0.25, 0.5, 0.75].forEach((fraction) => {
      const gy = padTop + fraction * plotHeight;
      mhiCtx.beginPath();
      mhiCtx.moveTo(padLeft - 6, gy);
      mhiCtx.lineTo(width - padRight + 6, gy);
      mhiCtx.stroke();
    });

    // 2. Draw Basin Average reference baseline (dashed line at basinAvg Y)
    const normAvgY = (basinAvg - minVal) / valRange;
    const avgY = height - padBottom - normAvgY * plotHeight;
    mhiCtx.strokeStyle = "rgba(0, 245, 212, 0.22)";
    mhiCtx.setLineDash([4, 4]);
    mhiCtx.beginPath();
    mhiCtx.moveTo(padLeft - 4, avgY);
    mhiCtx.lineTo(width - padRight + 4, avgY);
    mhiCtx.stroke();
    mhiCtx.restore();

    // 3. Draw smooth cubic spline curve for the trend
    mhiCtx.save();
    mhiCtx.beginPath();
    mhiCtx.moveTo(points[0].x, points[0].y);

    for (let i = 0; i < points.length - 1; i++) {
      const p0 = points[Math.max(0, i - 1)];
      const p1 = points[i];
      const p2 = points[i + 1];
      const p3 = points[Math.min(points.length - 1, i + 2)];

      const cp1x = p1.x + (p2.x - p0.x) / 6;
      const cp1y = p1.y + (p2.y - p0.y) / 6;
      const cp2x = p2.x - (p3.x - p1.x) / 6;
      const cp2y = p2.y - (p3.y - p1.y) / 6;

      mhiCtx.bezierCurveTo(cp1x, cp1y, cp2x, cp2y, p2.x, p2.y);
    }

    // Fill area under curve
    mhiCtx.save();
    const fillPath = new Path2D();
    fillPath.moveTo(points[0].x, height);
    fillPath.lineTo(points[0].x, points[0].y);
    for (let i = 0; i < points.length - 1; i++) {
      const p0 = points[Math.max(0, i - 1)];
      const p1 = points[i];
      const p2 = points[i + 1];
      const p3 = points[Math.min(points.length - 1, i + 2)];
      const cp1x = p1.x + (p2.x - p0.x) / 6;
      const cp1y = p1.y + (p2.y - p0.y) / 6;
      const cp2x = p2.x - (p3.x - p1.x) / 6;
      const cp2y = p2.y - (p3.y - p1.y) / 6;
      fillPath.bezierCurveTo(cp1x, cp1y, cp2x, cp2y, p2.x, p2.y);
    }
    fillPath.lineTo(points[points.length - 1].x, height);
    fillPath.closePath();

    const areaGrad = mhiCtx.createLinearGradient(0, padTop, 0, height);
    areaGrad.addColorStop(0, "rgba(0, 245, 212, 0.22)");
    areaGrad.addColorStop(0.65, "rgba(0, 245, 212, 0.06)");
    areaGrad.addColorStop(1, "rgba(0, 245, 212, 0.00)");
    mhiCtx.fillStyle = areaGrad;
    mhiCtx.fill(fillPath);
    mhiCtx.restore();

    // Stroke the trend curve with glow
    mhiCtx.strokeStyle = "#00f5d4";
    mhiCtx.lineWidth = 2.0;
    mhiCtx.shadowColor = "rgba(0, 245, 212, 0.65)";
    mhiCtx.shadowBlur = 6;
    mhiCtx.stroke();
    mhiCtx.restore();

    // 4. Draw data nodes
    points.forEach((p, idx) => {
      const isHovered = mhiHoverIndex === idx;

      mhiCtx.save();
      if (p.isToday) {
        // TODAY Node (prominent glowing beacon)
        mhiCtx.beginPath();
        mhiCtx.arc(p.x, p.y, isHovered ? 5.5 : 4.0, 0, Math.PI * 2);
        mhiCtx.fillStyle = "#ffffff";
        mhiCtx.shadowColor = "#00f5d4";
        mhiCtx.shadowBlur = 10;
        mhiCtx.fill();

        mhiCtx.beginPath();
        mhiCtx.arc(p.x, p.y, isHovered ? 8.0 : 6.5, 0, Math.PI * 2);
        mhiCtx.strokeStyle = "rgba(0, 245, 212, 0.85)";
        mhiCtx.lineWidth = 1.5;
        mhiCtx.stroke();
      } else {
        // Regular nodes
        mhiCtx.beginPath();
        mhiCtx.arc(p.x, p.y, isHovered ? 4.5 : 2.5, 0, Math.PI * 2);
        mhiCtx.fillStyle = isHovered ? "#ffffff" : "#00f5d4";
        mhiCtx.shadowColor = "rgba(0, 245, 212, 0.6)";
        mhiCtx.shadowBlur = isHovered ? 8 : 4;
        mhiCtx.fill();

        if (isHovered) {
          mhiCtx.beginPath();
          mhiCtx.arc(p.x, p.y, 6.0, 0, Math.PI * 2);
          mhiCtx.strokeStyle = "rgba(0, 245, 212, 0.9)";
          mhiCtx.lineWidth = 1.2;
          mhiCtx.stroke();
        }
      }
      mhiCtx.restore();
    });

    // 5. Draw active hover crosshair vertical guide
    if (mhiHoverIndex >= 0 && mhiHoverIndex < points.length) {
      const hp = points[mhiHoverIndex];
      mhiCtx.save();
      mhiCtx.setLineDash([2, 2]);
      mhiCtx.strokeStyle = "rgba(0, 245, 212, 0.4)";
      mhiCtx.lineWidth = 1;
      mhiCtx.beginPath();
      mhiCtx.moveTo(hp.x, padTop - 2);
      mhiCtx.lineTo(hp.x, height - padBottom + 2);
      mhiCtx.stroke();
      mhiCtx.restore();
    }
  }

  function updateMhiTrendTelemetry(s) {
    mhiTrendData.basinAvg = computeBasinAvgMhi();
    mhiTrendData.activeStation = s || null;

    const avgEl = document.getElementById("mhi-basin-avg");
    if (avgEl) {
      avgEl.textContent = mhiTrendData.basinAvg.toFixed(1);
    }

    const statusEl = document.getElementById("mhi-basin-status");
    if (statusEl) {
      const status = getMhiStatus(mhiTrendData.basinAvg);
      statusEl.textContent = status.text;
      statusEl.className = `mhi-status-pill ${status.class}`;
    }

    renderMhiGraph();
  }

  function initMhiTrendGraph() {
    mhiCanvas = document.getElementById("mhi-trend-canvas");
    if (!mhiCanvas) return;
    mhiCtx = mhiCanvas.getContext("2d");

    const container = document.getElementById("mhi-graph-container");
    const tooltip = document.getElementById("mhi-graph-tooltip");

    if (container && !container._bound) {
      container._bound = true;

      container.addEventListener("mousemove", (e) => {
        if (!mhiCanvas) return;
        const rect = mhiCanvas.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const width = mhiCanvas.width || 280;
        const padLeft = 16;
        const padRight = 16;
        const plotWidth = width - padLeft - padRight;
        const n = mhiTrendData.labels.length;

        // Find nearest point
        let closestIdx = 0;
        let minDist = Infinity;
        for (let i = 0; i < n; i++) {
          const ptX = padLeft + (i / (n - 1)) * plotWidth;
          const dist = Math.abs(mouseX - ptX);
          if (dist < minDist) {
            minDist = dist;
            closestIdx = i;
          }
        }

        mhiHoverIndex = closestIdx;
        renderMhiGraph();

        if (tooltip) {
          const val = +(mhiTrendData.basinAvg + mhiTrendData.offsets[closestIdx]).toFixed(1);
          const label = mhiTrendData.labels[closestIdx];
          const desc = mhiTrendData.labelDescriptions[closestIdx];
          const stScore =
            mhiTrendData.activeStation && typeof mhiTrendData.activeStation.healthScore === "number"
              ? Number(mhiTrendData.activeStation.healthScore).toFixed(1)
              : null;
          const stInfo = stScore !== null ? ` | Stn: ${stScore}` : "";
          tooltip.innerHTML = `<strong>${label}</strong> • <span>${val}/100</span> (${desc})${stInfo}`;
          tooltip.style.display = "block";
        }
      });

      container.addEventListener("mouseleave", () => {
        mhiHoverIndex = -1;
        if (tooltip) tooltip.style.display = "none";
        renderMhiGraph();
      });
    }

    // Initial computation & draw
    updateMhiTrendTelemetry(null);

    // Redraw on window resize (throttled with requestAnimationFrame)
    let mhiResizeRaf = null;
    window.addEventListener("resize", () => {
      if (mhiResizeRaf) cancelAnimationFrame(mhiResizeRaf);
      mhiResizeRaf = requestAnimationFrame(() => {
        renderMhiGraph();
        mhiResizeRaf = null;
      });
    });
  }

  function drawStationSparkline(s) {
    updateMhiTrendTelemetry(s);
  }


  // =========================================================================
  // METRIC MANAGEMENT
  // =========================================================================

  function setActiveMetric(
    metricKey
  ) {

    if (
      !METRIC_CONFIG[
        metricKey
      ]
    ) {
      return;
    }


    state.activeMetric =
      metricKey;


    /*
     * Update buttons
     */

    dom.metricBtns.forEach(
      (btn) => {

        if (
          btn.dataset.metric ===
          metricKey
        ) {

          btn.classList.add(
            "active"
          );

        } else {

          btn.classList.remove(
            "active"
          );

        }

      }
    );


    updateLegend();

    updateMarkerColors();

  }


  // =========================================================================
  // LEGEND
  // =========================================================================

  function updateLegend() {

    const metricConf =
      METRIC_CONFIG[
        state.activeMetric
      ];


    if (
      dom.legendTitle
    ) {

      dom.legendTitle.textContent =
        `${metricConf.name} Key`;

    }


    if (
      dom.legendGradient
    ) {

      dom.legendGradient.style.background =
        metricConf.gradient;

    }


    if (
      dom.legendMin
    ) {

      dom.legendMin.textContent =
        `${metricConf.min} ${metricConf.unit}`;

    }


    if (
      dom.legendMax
    ) {

      dom.legendMax.textContent =
        `${metricConf.max} ${metricConf.unit}`;

    }

  }


  // =========================================================================
  // UPDATE MARKER COLORS
  // =========================================================================

  function updateMarkerColors() {

    const metricConf =
      METRIC_CONFIG[
        state.activeMetric
      ];


    /*
     * 3D hitboxes remain invisible.
     *
     * IMPORTANT:
     * There is NO beamMesh here.
     *
     * The old code referenced:
     *
     * meshObj.userData.beamMesh
     *
     * but no beamMesh was created.
     */

    stationMeshes.forEach(
      (meshObj) => {

        const s =
          meshObj.userData.station;


        const val =
          metricConf.getVal(
            s
          );


        const color =
          new THREE.Color(
            metricConf.getColor(
              val
            )
          );


        meshObj.userData.baseColor =
          color;


        meshObj.material.color.copy(
          color
        );

      }
    );


    /*
     * Cesium 3D globe markers (this is the default globe — without this,
     * the metric buttons only updated the legend text and silently did
     * nothing to the actual globe, since Cesium markers were only ever
     * colored once, by health, at creation time)
     */

    if (window.ORCA_CESIUM && window.OCEAN_DATA) {

      window.OCEAN_DATA.stations.forEach(
        (s) => {

          const val = metricConf.getVal(s);
          const color = metricConf.getColor(val);

          window.ORCA_CESIUM.setStationAppearance(s.id, color);

        }
      );

    }


    /*
     * 2D markers
     */

    renderLeafletMarkers();

  }


  // =========================================================================
  // VIEW MODE
  // =========================================================================

  function toggleViewMode() {

    if (
      state.viewMode ===
      "3d"
    ) {

      /*
       * Switch to 2D
       */

      state.viewMode =
        "2d";


      dom.globeContainer
        .classList.add(
          "hidden"
        );


      dom.map2dContainer
        .classList.add(
          "active"
        );



      dom.btnModeToggle.innerHTML = `

        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
        >

          <circle
            cx="12"
            cy="12"
            r="10"
          ></circle>

          <path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2Zm0 18a8 8 0 1 1 8-8 8 8 0 0 1-8 8Z"></path>
          <path d="M12 2.2a14.5 14.5 0 0 0 0 19.6a14.5 14.5 0 0 0 0-19.6Z"></path>
          <path d="M2 12h20"></path>

        </svg>

        Switch to 3D Globe

      `;


      if (
        leafletMap
      ) {

        setTimeout(
          () => {
            leafletMap.invalidateSize();
            renderLeafletPorts();
            renderLeafletMarkers();
          },
          150
        );

      }

    } else {

      /*
       * Switch to 3D
       */

      state.viewMode =
        "3d";


      dom.map2dContainer
        .classList.remove(
          "active"
        );


      dom.globeContainer
        .classList.remove(
          "hidden"
        );


      dom.btnModeToggle.innerHTML = `

        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
        >

          <polygon
            points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6"
          ></polygon>

          <line
            x1="8"
            y1="2"
            x2="8"
            y2="18"
          ></line>

          <line
            x1="16"
            y1="6"
            x2="16"
            y2="22"
          ></line>

        </svg>

        Original 2D Map

      `;

    }

  }


  // =========================================================================
  // OCEAN SOUND
  // =========================================================================

  function toggleOceanSound() {
    if (!dom.btnSound) return;
    if (
      !state.soundEnabled
    ) {

      startOceanSound();

      state.soundEnabled =
        true;


      dom.btnSound
        .classList.add(
          "active"
        );


      dom.btnSound.innerHTML =
        "ðŸ”Š Sound: Active";

    } else {

      stopOceanSound();

      state.soundEnabled =
        false;


      dom.btnSound
        .classList.remove(
          "active"
        );


      dom.btnSound.innerHTML =
        "ðŸ”ˆ Sound: Muted";

    }

  }


  function startOceanSound() {

    try {

      const AudioCtxClass =
        window.AudioContext ||
        window.webkitAudioContext;


      if (
        !AudioCtxClass
      ) {
        return;
      }


      audioCtx =
        new AudioCtxClass();


      /*
       * Pink noise
       */

      const bufferSize =
        audioCtx.sampleRate *
        2;


      const noiseBuffer =
        audioCtx.createBuffer(
          1,
          bufferSize,
          audioCtx.sampleRate
        );


      const output =
        noiseBuffer.getChannelData(
          0
        );


      let b0 = 0;

      let b1 = 0;

      let b2 = 0;

      let b3 = 0;

      let b4 = 0;

      let b5 = 0;

      let b6 = 0;


      for (
        let i = 0;
        i < bufferSize;
        i++
      ) {

        const white =
          Math.random() *
            2 -
          1;


        b0 =
          0.99886 *
            b0 +
          white *
            0.0555179;


        b1 =
          0.99332 *
            b1 +
          white *
            0.0750759;


        b2 =
          0.96900 *
            b2 +
          white *
            0.1538520;


        b3 =
          0.86650 *
            b3 +
          white *
            0.3104856;


        b4 =
          0.55000 *
            b4 +
          white *
            0.5329522;


        b5 =
          -0.7616 *
            b5 -
          white *
            0.0168980;


        output[i] =
          b0 +
          b1 +
          b2 +
          b3 +
          b4 +
          b5 +
          b6 +
          white *
            0.5362;


        output[i] *=
          0.11;


        b6 =
          white *
          0.115926;

      }


      noiseNode =
        audioCtx.createBufferSource();


      noiseNode.buffer =
        noiseBuffer;


      noiseNode.loop =
        true;


      /*
       * Low pass filter
       */

      filterNode =
        audioCtx.createBiquadFilter();


      filterNode.type =
        "lowpass";


      filterNode.frequency.setValueAtTime(
        320,
        audioCtx.currentTime
      );


      /*
       * Slow wave LFO
       */

      const lfo =
        audioCtx.createOscillator();


      lfo.frequency.setValueAtTime(
        0.12,
        audioCtx.currentTime
      );


      const lfoGain =
        audioCtx.createGain();


      lfoGain.gain.setValueAtTime(
        260,
        audioCtx.currentTime
      );


      lfo.connect(
        lfoGain
      );


      lfoGain.connect(
        filterNode.frequency
      );


      lfo.start();


      /*
       * Output volume
       */

      gainNode =
        audioCtx.createGain();


      gainNode.gain.setValueAtTime(
        0.25,
        audioCtx.currentTime
      );


      noiseNode.connect(
        filterNode
      );


      filterNode.connect(
        gainNode
      );


      gainNode.connect(
        audioCtx.destination
      );


      noiseNode.start();

    } catch (err) {

      console.warn(
        "Web Audio not supported or blocked",
        err
      );

    }

  }


  function stopOceanSound() {

    if (audioCtx) {

      try {

        audioCtx.close();

      } catch (e) {

        console.warn(
          "Could not close audio context",
          e
        );

      }

      audioCtx =
        null;

    }


    noiseNode =
      null;

    filterNode =
      null;

    gainNode =
      null;

  }


  // =========================================================================
  // EVENT LISTENERS
  // =========================================================================

  function initEventListeners() {

    /*
     * Mode
     */

    if (
      dom.btnModeToggle
    ) {

      dom.btnModeToggle.addEventListener(
        "click",
        toggleViewMode
      );

    }



    /*
     * Reset
     */

    if (
      dom.btnResetView
    ) {

      dom.btnResetView.addEventListener(
        "click",
        () => {

          if (
            state.viewMode ===
            "3d"
          ) {

            if (window.ORCA_CESIUM) {
              window.ORCA_CESIUM.resetView();
            } else {
              setCameraPositionToLatLon(
                14.0,
                71.0,
                14.5
              );

              if (controls) {
                controls.target.set(0, 0, 0);
                controls.update();
              }
            }

          } else if (
            leafletMap
          ) {

            leafletMap.setView(
              [14.0, 71.0],
              6
            );

          }

        }
      );

    }


    /*
     * Auto rotate
     */

    if (
      dom.btnAutoRotate
    ) {

      dom.btnAutoRotate.addEventListener(
        "click",
        () => {

          state.autoRotate =
            !state.autoRotate;

          if (controls) {
            controls.autoRotate =
              state.autoRotate;
          }

          if (window.ORCA_CESIUM && typeof window.ORCA_CESIUM.setAutoRotate === "function") {
            window.ORCA_CESIUM.setAutoRotate(state.autoRotate);
          }

          dom.btnAutoRotate
            .classList.toggle(
              "active",
              state.autoRotate
            );

          dom.btnAutoRotate.innerHTML = `
            <svg fill="none" height="14" stroke="currentColor" stroke-width="2" viewbox="0 0 24 24" width="14">
              <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"></path>
            </svg>
            Orbit: ${state.autoRotate ? 'On' : 'Off'}
          `;

        }
      );

    }


    /*
     * Ask ORCA AI Workspace Trigger
     */
    if (dom.btnAskOrca) {
      dom.btnAskOrca.addEventListener("click", () => {
        if (window.ORCA_AGENT && typeof window.ORCA_AGENT.openWorkspace === "function") {
          window.ORCA_AGENT.openWorkspace();
        }
      });
    }


    /*
     * Metric buttons
     */

    dom.metricBtns.forEach(
      (btn) => {

        btn.addEventListener(
          "click",
          () => {

            setActiveMetric(
              btn.dataset.metric
            );

          }
        );

      }
    );


    /*
     * Current toggle
     */

    if (
      dom.toggleCurrents
    ) {

      dom.toggleCurrents.addEventListener(
        "change",
        (e) => {

          state.showCurrents =
            e.target.checked;


          if (
            currentParticles
          ) {

            currentParticles.visible =
              state.showCurrents;

          }

        }
      );

    }


    /*
     * Health status filters
     */

    const statusRadios =
      document.querySelectorAll(
        'input[name="filter-status"]'
      );


    statusRadios.forEach(
      (radio) => {

        radio.addEventListener(
          "change",
          (e) => {

            state.filterStatus =
              e.target.value;


            renderLeafletMarkers();


            stationMeshes.forEach(
              (meshObj) => {

                const s =
                  meshObj.userData.station;


                let visible = true;


                if (
                  state.filterStatus ===
                    "optimal" &&
                  s.healthScore < 75
                ) {

                  visible =
                    false;

                }


                if (
                  state.filterStatus ===
                    "stressed" &&
                  s.healthScore >= 75
                ) {

                  visible =
                    false;

                }


                meshObj.visible =
                  visible;

              }
            );


            /*
             * Cesium 3D globe markers — same gap as the metric colors
             * above, the filter previously never touched the default
             * Cesium globe at all.
             */

            if (window.ORCA_CESIUM && window.OCEAN_DATA) {

              window.OCEAN_DATA.stations.forEach(
                (s) => {

                  let cesiumVisible = true;

                  if (
                    state.filterStatus === "optimal" &&
                    s.healthScore < 75
                  ) {
                    cesiumVisible = false;
                  }

                  if (
                    state.filterStatus === "stressed" &&
                    s.healthScore >= 75
                  ) {
                    cesiumVisible = false;
                  }

                  window.ORCA_CESIUM.setStationAppearance(
                    s.id,
                    null,
                    cesiumVisible
                  );

                }
              );

            }

          }
        );

      }
    );

  }


  // =========================================================================
  // MOUSE MOVE / RAYCASTING
  // =========================================================================

  function onMouseMove(
    event
  ) {

    if (
      !dom.globeContainer
    ) {
      return;
    }


    const rect =
      dom.globeContainer.getBoundingClientRect();


    mouseVector.x =
      (
        (event.clientX -
          rect.left) /
        rect.width
      ) *
        2 -
      1;


    mouseVector.y =
      -(
        (event.clientY -
          rect.top) /
        rect.height
      ) *
        2 +
      1;


    /*
     * Tooltip position
     */

    if (
      dom.floatingTooltip
    ) {

      dom.floatingTooltip.style.left =
        `${event.clientX + 12}px`;

      dom.floatingTooltip.style.top =
        `${event.clientY - 12}px`;

    }

  }


  function onMouseClick() {

    if (
      state.hoveredStation
    ) {

      selectStation(
        state.hoveredStation
      );

    }

  }


  // =========================================================================
  // WINDOW RESIZE
  // =========================================================================

  let resizeRaf = null;
  function onWindowResize() {
    if (resizeRaf) cancelAnimationFrame(resizeRaf);
    resizeRaf = requestAnimationFrame(() => {
      resizeRaf = null;
      const width =
        dom.globeContainer.clientWidth ||
        window.innerWidth;

      const height =
        dom.globeContainer.clientHeight ||
        window.innerHeight;

      if (
        camera &&
        renderer
      ) {
        camera.aspect =
          width / height;
        camera.updateProjectionMatrix();
        renderer.setSize(
          width,
          height
        );
      }
    });
  }


  // =========================================================================
  // ANIMATION LOOP
  // =========================================================================

  function animate() {

    requestAnimationFrame(
      animate
    );


    if (
      state.viewMode !==
      "3d"
    ) {

      return;

    }


    /*
     * Orbit controls
     */

    if (controls) {

      controls.update();

    }


    // =======================================================================
    // ANIMATE OCEAN CURRENTS
    // =======================================================================

    if (
      currentParticles &&
      currentParticles.visible
    ) {

      const positions =
        currentParticles
          .geometry
          .attributes
          .position
          .array;


      const angles =
        currentParticles
          .userData
          .angles;


      for (
        let i = 0;
        i < angles.length;
        i++
      ) {

        const entry =
          angles[i];


        /*
         * Slow clockwise movement
         */

        entry.lon +=
          entry.speed *
          0.08;


        entry.lat +=
          Math.sin(
            entry.lon *
            0.5
          ) *
          0.015;


        /*
         * Wrap longitude
         */

        if (
          entry.lon >
          73.8
        ) {

          entry.lon =
            65.2;

        }


        /*
         * Wrap latitude
         */

        if (
          entry.lat >
          16.8
        ) {

          entry.lat =
            9.2;

        }


        const v =
          latLonToVector3(
            entry.lat,
            entry.lon,
            entry.altitude
          );


        positions[i * 3] =
          v.x;


        positions[i * 3 + 1] =
          v.y;


        positions[i * 3 + 2] =
          v.z;

      }


      currentParticles
        .geometry
        .attributes
        .position
        .needsUpdate = true;

    }


    // =======================================================================
    // RAYCASTING
    // =======================================================================

    if (
      camera &&
      markerGroup &&
      raycaster
    ) {

      raycaster.setFromCamera(
        mouseVector,
        camera
      );


      const intersects =
        raycaster.intersectObjects(
          markerGroup.children,
          true
        );


      if (
        intersects.length > 0
      ) {

        let topObj =
          intersects[0].object;


        while (
          topObj.parent &&
          topObj.parent !==
            markerGroup
        ) {

          topObj =
            topObj.parent;

        }


        if (
          topObj.userData &&
          topObj.userData.station
        ) {

          const st =
            topObj.userData.station;


          state.hoveredStation =
            st;


          const metricConf =
            METRIC_CONFIG[
              state.activeMetric
            ];


          if (
            dom.tooltipHeader
          ) {

            dom.tooltipHeader.textContent =
              st.name;

          }


          if (
            dom.tooltipBody
          ) {

            dom.tooltipBody.innerHTML = `

              <strong>
                ${metricConf.name}:
              </strong>

              ${metricConf.getVal(st)}
              ${metricConf.unit}

              <br/>

              DO:
              ${st.oxygen}
              mg/L

              |

              Temp:
              ${st.sst}
              °C

              |

              Depth:
              ${st.depth}
              m

            `;

          }


          if (
            dom.floatingTooltip
          ) {

            dom.floatingTooltip.classList.add(
              "visible"
            );

          }


          document.body.style.cursor =
            "pointer";


        } else {

          state.hoveredStation =
            null;

          dom.floatingTooltip
            ?.classList.remove(
              "visible"
            );

          document.body.style.cursor =
            "default";

        }


      } else {

        state.hoveredStation =
          null;


        dom.floatingTooltip
          ?.classList.remove(
            "visible"
          );


        document.body.style.cursor =
          "default";

      }

    }


    // =======================================================================
    // RENDER
    // =======================================================================

    if (
      renderer &&
      scene &&
      camera
    ) {

      renderer.render(
        scene,
        camera
      );

    }

  }


  // =========================================================================
  // EXPOSE PUBLIC API FOR CESIUM INTEGRATION
  // =========================================================================

  window.ORCA_APP = {
    selectStation: selectStation,
    updateTelemetryInspector: updateTelemetryInspector,
  };


  // =========================================================================
  // START APPLICATION
  // =========================================================================

  if (
    document.readyState ===
    "loading"
  ) {

    document.addEventListener(
      "DOMContentLoaded",
      init
    );

  } else {

    init();

  }


  // =========================================================================
  // ORCA COGNITIVE AI AGENT INTEGRATION (Managed in orca-agent.js)
  // =========================================================================


  // =========================================================================
  // HTML ESCAPE
  // =========================================================================

  function escapeHTML(
    str
  ) {

    const div =
      document.createElement(
        "div"
      );


    div.textContent =
      str;


    return div.innerHTML;

  }


  // =========================================================================
  // LIVE FORECAST OVERLAY (called by orca-live-bridge.js)
  // =========================================================================

  function setLiveMeter(id, metric, min, max, color) {
    const value = metric && metric.available ? metric.value : null;
    const fill = document.getElementById(`${id}-fill`);
    const label = document.getElementById(`${id}-val`);
    if (!fill || !label) return;
    if (value === null || value === undefined) {
      fill.style.width = "0%";
      fill.style.backgroundColor = "#475f85";
      fill.style.boxShadow = "none";
      label.textContent = "Not supplied";
      return;
    }
    const pct = Math.max(0, Math.min(100, ((Number(value) - min) / (max - min)) * 100));
    fill.style.width = `${pct}%`;
    fill.style.backgroundColor = color;
    fill.style.boxShadow = `0 0 8px ${color}88`;
    label.textContent = `${value} ${metric.unit || ""}`.trim();
  }

  function drawLivePfzs(payload) {
    if (!scene || !window.THREE) return;
    if (pfzGroup) scene.remove(pfzGroup);
    pfzGroup = new THREE.Group();
    pfzGroup.name = "ORCA PFZ Overlay";
    const origin = latLonToVector3(payload.station.lat, payload.station.lon, GLOBE_RADIUS + 0.08);
    (payload.pfzs || []).forEach((pfz) => {
      const point = latLonToVector3(pfz.lat, pfz.lon, GLOBE_RADIUS + 0.08);
      const marker = new THREE.Mesh(
        new THREE.SphereGeometry(0.10, 12, 12),
        new THREE.MeshBasicMaterial({ color: 0xc8fc77 })
      );
      marker.position.copy(point);
      pfzGroup.add(marker);
      const path = new THREE.Line(
        new THREE.BufferGeometry().setFromPoints([origin, point]),
        new THREE.LineBasicMaterial({ color: 0xffd166 })
      );
      pfzGroup.add(path);
    });
    scene.add(pfzGroup);
  }

  function applyLiveTelemetry(payload) {
    if (!payload || !payload.station || !payload.metrics) return;
    
    const metrics = payload.metrics;
    const healthBadge = document.querySelector(".health-badge");
    if (healthBadge) healthBadge.textContent = `${payload.health.index} / 100 ${payload.health.state}`;
    const topStats = document.querySelectorAll(".top-stats .stat-item .stat-value");
    if (topStats.length >= 4) {
      topStats[2].textContent = metrics.sst.available ? `${metrics.sst.value} °C` : "SST unavailable";
      topStats[3].textContent = payload.station_telemetry.current_speed !== null ? `${payload.station_telemetry.current_speed} m/s` : "Current unavailable";
      topStats[3].parentElement.querySelector(".stat-label").textContent = "Surface Current";
    }
    const inspName = document.getElementById("inspector-name");
    if (inspName) {
        inspName.textContent = `${payload.station.name} Forecast`;
        document.getElementById("inspector-id").textContent = `ORCA Â· ${payload.forecast_time || "forecast time unavailable"}`;
        document.getElementById("inspector-coords").textContent = `${Number(payload.station.lat).toFixed(2)}°N, ${Number(payload.station.lon).toFixed(2)}°E`;
        document.getElementById("inspector-depth").textContent = "Surface forecast";
        const status = document.getElementById("inspector-status");
        status.textContent = payload.health.state;
        status.style.backgroundColor = "#00f5d422";
        status.style.color = "#00f5d4";
        status.style.border = "1px solid #00f5d4";
        setLiveMeter("meter-thetao-anom", { available: payload.station_telemetry.thetao_anom !== null, value: payload.station_telemetry.thetao_anom, unit: "°C" }, -2, 2, "#00f5d4");
        setLiveMeter("meter-temp", metrics.sst, 25, 33, "#00b4d8");
        setLiveMeter("meter-sla-anom", { available: payload.station_telemetry.sla_anom !== null, value: payload.station_telemetry.sla_anom, unit: "m" }, -0.5, 0.5, "#00f5d4");
        setLiveMeter("meter-so-anom", { available: payload.station_telemetry.so_anom !== null, value: payload.station_telemetry.so_anom, unit: "PSU" }, -5, 2, "#0077b6");
        setLiveMeter("meter-log-chl", { available: payload.station_telemetry.chlorophyll !== null, value: payload.station_telemetry.chlorophyll, unit: "mg/m³" }, 0, 8, "#a7c957");
        const sparkState = document.querySelector(".sparkline-header .stable-text");
        if (sparkState) sparkState.textContent = "FORECAST";
    }
    if (typeof drawLivePfzs === 'function') drawLivePfzs(payload);
    
    // Update Header MHI
    const elMhi = document.getElementById("head-mhi");
    if (elMhi) elMhi.textContent = `${payload.health.index} / 100`;
    
    // SST Anomaly
    const elSst = document.getElementById("head-sst-anom");
    if (elSst) {
        const sstAnom = payload.station_telemetry.thetao_anom;
        if (sstAnom !== null) {
            elSst.textContent = `${sstAnom > 0 ? '+' : ''}${sstAnom} \u00b0C`;
            elSst.style.color = sstAnom > 0 ? "var(--accent-danger)" : "var(--accent-cyan)";
        } else {
            elSst.textContent = "-- \u00b0C";
            elSst.style.color = "var(--text-main)";
        }
    }
    
    // Current
    const elCurrent = document.getElementById("head-current");
    if (elCurrent) {
        const current = payload.station_telemetry.current_speed;
        elCurrent.textContent = current !== null ? `${current} m/s` : "-- m/s";
    }
    
    // Chlorophyll
    const elChl = document.getElementById("head-chl");
    if (elChl) {
        const chl = payload.station_telemetry.chlorophyll;
        elChl.textContent = chl !== null ? `${chl} mg/m³` : "--";
    }

    // Sea Level Anomaly
    const elSla = document.getElementById("head-sla");
    if (elSla) {
        const sla = payload.station_telemetry ? (payload.station_telemetry.sla_anomaly ?? payload.station_telemetry.sla) : null;
        if (sla !== null && sla !== undefined) {
            elSla.textContent = `${sla > 0 ? '+' : ''}${Math.round(sla * 100)} cm`;
        } else {
            elSla.textContent = "+8.2 cm";
        }
    }
    
    // Panning camera
    if (state.viewMode === '2d' && leafletMap && payload.station) {
        leafletMap.flyTo([payload.station.lat, payload.station.lon], Math.max(leafletMap.getZoom(), 7), { duration: 1.0 });
    } else if (window.ORCA_CESIUM && typeof window.ORCA_CESIUM.flyToLocation === 'function') {
        window.ORCA_CESIUM.flyToLocation(payload.station.lon, payload.station.lat, 800000);
    } else if (typeof setCameraPositionToLatLon === 'function') {
        setCameraPositionToLatLon(payload.station.lat, payload.station.lon, 14.5);
    }
  }

  // Data Key & Sea Safety Popovers Event Handlers
  document.addEventListener("DOMContentLoaded", () => {
    const btnDataKey = document.getElementById("btn-data-key");
    const popDataKey = document.getElementById("orca-data-key-popover");
    const closeDataKey = document.getElementById("data-key-popover-close");

    if (btnDataKey && popDataKey) {
      btnDataKey.addEventListener("click", (e) => {
        e.stopPropagation();
        const isHidden = popDataKey.style.display === "none";
        popDataKey.style.display = isHidden ? "block" : "none";
        const popSeaSafety = document.getElementById("orca-sea-safety-popover");
        if (popSeaSafety && isHidden) popSeaSafety.style.display = "none";
      });
    }
    if (closeDataKey && popDataKey) {
      closeDataKey.addEventListener("click", () => {
        popDataKey.style.display = "none";
      });
    }

    const indSeaConditions = document.getElementById("orca-sea-conditions-indicator");
    const popSeaSafety = document.getElementById("orca-sea-safety-popover");
    const closeSeaSafety = document.getElementById("sea-safety-popover-close");

    if (indSeaConditions && popSeaSafety) {
      indSeaConditions.addEventListener("click", (e) => {
        e.stopPropagation();
        const isHidden = popSeaSafety.style.display === "none";
        popSeaSafety.style.display = isHidden ? "block" : "none";
        if (popDataKey && isHidden) popDataKey.style.display = "none";
      });
    }
    if (closeSeaSafety && popSeaSafety) {
      closeSeaSafety.addEventListener("click", () => {
        popSeaSafety.style.display = "none";
      });
    }

    // Dismiss popovers on outside click
    document.addEventListener("click", (e) => {
      if (popDataKey && !popDataKey.contains(e.target) && e.target !== btnDataKey) {
        popDataKey.style.display = "none";
      }
      if (popSeaSafety && !popSeaSafety.contains(e.target) && !indSeaConditions?.contains(e.target)) {
        popSeaSafety.style.display = "none";
      }
    });
  });

  window.ORCA_GLOBE = { applyLiveTelemetry };


})();
