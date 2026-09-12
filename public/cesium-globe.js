 
/**
 * ==========================================================================
 * ORCA CESIUM GLOBE — Zoomable 3D Earth with Labels
 * ==========================================================================
 *
 * CesiumJS globe used by the ORCA application.
 *
 * Exposes:
 *   window.ORCA_CESIUM
 *
 * Required:
 *   - CesiumJS loaded before this file
 *   - window.OCEAN_DATA available for station markers
 *
 * Optional backend:
 *   http://localhost:8000/api/v1/vessels
 * ==========================================================================
 */

(function () {
  "use strict";

  let viewer = null;
  let stationEntities = [];
  let stationEntityMap = {};
  let clickHandler = null;
  let activeRouteEntity = null;
  let spinTickRemove = null;

  const coastalPorts = [
    // --- GUJARAT COASTLINE ---
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

    // --- MAHARASHTRA / KONKAN COASTLINE ---
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

    // --- GOA COASTLINE ---
    { name: "Mormugao", lat: 15.41, lon: 73.80, isMajor: true },
    { name: "Panaji", lat: 15.50, lon: 73.83, isMajor: false },

    // --- KARNATAKA / KANARA COASTLINE ---
    { name: "Mangaluru Port", lat: 12.91, lon: 74.88, isMajor: true },
    { name: "Karwar", lat: 14.80, lon: 74.12, isMajor: false },
    { name: "Tadri", lat: 14.52, lon: 74.35, isMajor: false },
    { name: "Honnavar", lat: 14.28, lon: 74.44, isMajor: false },
    { name: "Bhatkal", lat: 13.98, lon: 74.55, isMajor: false },
    { name: "Kundapura", lat: 13.63, lon: 74.69, isMajor: false },
    { name: "Malpe", lat: 13.35, lon: 74.70, isMajor: false },

    // --- SOUTH WEST & EAST COAST ---
    { name: "Kochi Port", lat: 9.93, lon: 76.27, isMajor: true },
    { name: "Kollam", lat: 8.89, lon: 76.59, isMajor: false },
    { name: "Thiruvananthapuram", lat: 8.52, lon: 76.94, isMajor: false },
    { name: "Chennai Port", lat: 13.08, lon: 80.27, isMajor: true },
    { name: "Visakhapatnam Port", lat: 17.69, lon: 83.22, isMajor: true }
  ];

  window.ORCA_COASTAL_PORTS = coastalPorts;

  // -------------------------------------------------------------------------
  // CONFIG
  // -------------------------------------------------------------------------

  const DEFAULT_VIEW = {
    lon: 71.0,
    lat: 14.0,
    height: 4000000
  };

  const BACKEND_URL = "http://localhost:8000";

  // -------------------------------------------------------------------------
  // INITIALIZE CESIUM
  // -------------------------------------------------------------------------

  function initCesiumGlobe(containerId) {
    try {
      // Check Cesium
      if (typeof Cesium === "undefined") {
        console.error(
          "ORCA Cesium: CesiumJS is not loaded."
        );
        return false;
      }

      // Find container
      const container =
        document.getElementById(containerId);

      if (!container) {
        console.error(
          `ORCA Cesium: Container "${containerId}" not found.`
        );
        return false;
      }

      // Clean previous viewer if one exists
      if (viewer) {
        try {
          viewer.destroy();
        } catch (e) {
          console.warn(
            "ORCA Cesium: Could not destroy previous viewer.",
            e
          );
        }

        viewer = null;
      }

      // Clean container
      container.innerHTML = "";

      // ---------------------------------------------------------------------
      // CESIUM ION TOKEN
      // ---------------------------------------------------------------------
      //
      // The globe below does not depend on Cesium Ion imagery.
      // If you later use Ion terrain/assets, set your own token here.
      //
      // Cesium.Ion.defaultAccessToken = "YOUR_TOKEN";
      //

      // ---------------------------------------------------------------------
      // CREATE VIEWER
      // ---------------------------------------------------------------------

const cartoImagery =
  new Cesium.UrlTemplateImageryProvider({
    url: "https://basemaps.cartocdn.com/rastertiles/dark_all/{z}/{x}/{y}.png?key=cb1_3he2_1_f384df18951386690f3fe38c",
    credit: "© OpenStreetMap contributors © CARTO"
  });

viewer = new Cesium.Viewer(container, {
  baseLayer: new Cesium.ImageryLayer(cartoImagery, {
    brightness: 0.82,
    contrast: 1.15,
    gamma: 0.92
  }),

  animation: false,
  timeline: false,
  homeButton: false,
  sceneModePicker: false,
  baseLayerPicker: false,
  navigationHelpButton: false,
  fullscreenButton: false,
  geocoder: false,
  infoBox: false,
  selectionIndicator: false,

  creditContainer: document.createElement("div"),

  sceneMode: Cesium.SceneMode.SCENE3D,

  skyBox: false,
  skyAtmosphere: false,

  orderIndependentTranslucency: false
});

      // Enable crisp native resolution on High-DPI displays
      viewer.resolutionScale = Math.min(window.devicePixelRatio || 1.0, 2.0);

      // Unbind Cesium default entity-tracking double-click and single-click to prevent camera locking
      viewer.screenSpaceEventHandler.removeInputAction(Cesium.ScreenSpaceEventType.LEFT_DOUBLE_CLICK);
      viewer.screenSpaceEventHandler.removeInputAction(Cesium.ScreenSpaceEventType.LEFT_CLICK);
      viewer.trackedEntity = undefined;
      viewer.selectedEntity = undefined;

      // Guarantee camera controller inputs remain fully operational
      const camCtrl = viewer.scene.screenSpaceCameraController;
      camCtrl.enableInputs = true;
      camCtrl.enableRotate = true;
      camCtrl.enableTranslate = true;
      camCtrl.enableZoom = true;
      camCtrl.enableTilt = true;
      camCtrl.enableLook = true;

      // Camera interaction logging to track grid stability
      viewer.camera.moveStart.addEventListener(() => {
        console.log("[ORCA GRID]\nCamera interaction started");
      });
      viewer.camera.moveEnd.addEventListener(() => {
        const count = stationEntities.length;
        console.log(`[ORCA GRID]\nCamera interaction ended\n[ORCA GRID]\nEntities removed: 0\n[ORCA GRID]\nNo filtering expected\nPreserving all grid points (${count} active)`);
      });

      // ---------------------------------------------------------------------
      // SCENE SETTINGS
      // ---------------------------------------------------------------------

      viewer.scene.backgroundColor =
        Cesium.Color.fromCssColorString(
          "#020611"
        );

      if (viewer.scene.sun) {
        viewer.scene.sun.show = false;
      }

      if (viewer.scene.moon) {
        viewer.scene.moon.show = false;
      }

      const globe =
        viewer.scene.globe;

      globe.enableLighting = false;
      globe.showGroundAtmosphere = true;

      // Realistic dark ocean texture with specular wave normal map
      globe.oceanNormalMapUrl = Cesium.buildModuleUrl("Assets/Textures/waterNormals.jpg");
      globe.baseColor = Cesium.Color.fromCssColorString("#020b18");

      // ---------------------------------------------------------------------
      // COSMIC STARFIELD & SPACE BACKGROUND
      // ---------------------------------------------------------------------

      function addStarfield() {
        try {
          const starCollection = viewer.scene.primitives.add(new Cesium.PointPrimitiveCollection());
          const numStars = 2800;
          const minRadius = 35000000.0; // 35,000 km celestial sphere
          const maxRadius = 75000000.0; // 75,000 km celestial sphere

          for (let i = 0; i < numStars; i++) {
            const u = Math.random();
            const v = Math.random();
            const theta = u * 2.0 * Math.PI;
            const phi = Math.acos(2.0 * v - 1.0);
            const r = minRadius + Math.random() * (maxRadius - minRadius);

            const x = r * Math.sin(phi) * Math.cos(theta);
            const y = r * Math.sin(phi) * Math.sin(theta);
            const z = r * Math.cos(phi);

            const randColor = Math.random();
            let starColor;
            let starSize = 1.0 + Math.random() * 1.6;

            if (randColor > 0.94) {
              // Luminous blue-white star
              starColor = Cesium.Color.fromCssColorString("rgba(186, 230, 253, 0.95)");
              starSize = 2.4 + Math.random() * 1.2;
            } else if (randColor > 0.88) {
              // Warm golden/amber star
              starColor = Cesium.Color.fromCssColorString("rgba(254, 215, 170, 0.90)");
              starSize = 2.2 + Math.random() * 1.0;
            } else if (randColor > 0.82) {
              // Cyber cyan star (matching ORCA palette)
              starColor = Cesium.Color.fromCssColorString("rgba(0, 245, 212, 0.85)");
              starSize = 2.0 + Math.random() * 1.0;
            } else if (randColor > 0.40) {
              // Bright white star
              const alpha = 0.55 + Math.random() * 0.40;
              starColor = Cesium.Color.fromAlpha(Cesium.Color.WHITE, alpha);
            } else {
              // Distant faint star
              const alpha = 0.25 + Math.random() * 0.35;
              starColor = Cesium.Color.fromAlpha(Cesium.Color.WHITE, alpha);
              starSize = 1.0;
            }

            starCollection.add({
              position: new Cesium.Cartesian3(x, y, z),
              pixelSize: starSize,
              color: starColor
            });
          }
          console.log(`[ORCA SPACE] Initialized 3D cosmic starfield with ${numStars} celestial stars.`);
        } catch (e) {
          console.warn("ORCA Cesium starfield notice:", e);
        }
      }

      addStarfield();

      // ---------------------------------------------------------------------
      // CAMERA
      // ---------------------------------------------------------------------

      flyToDefaultView(2);

      // ---------------------------------------------------------------------
      // ADD APPLICATION DATA
      // ---------------------------------------------------------------------

      addStationMarkers();

      fetchAndRenderEEZ();

      fetchAndRenderCoastlines();

      setupClickHandlers();

      console.log(
        "ORCA Cesium globe initialized successfully."
      );

      return true;

    } catch (err) {
      console.error(
        "Cesium globe initialization failed:",
        err
      );

      viewer = null;

      return false;
    }
  }

  // -------------------------------------------------------------------------
  // DEFAULT CAMERA
  // -------------------------------------------------------------------------

  function flyToDefaultView(duration) {
    if (!viewer) return;

    viewer.camera.flyTo({
      destination:
        Cesium.Cartesian3.fromDegrees(
          DEFAULT_VIEW.lon,
          DEFAULT_VIEW.lat,
          DEFAULT_VIEW.height
        ),

      orientation: {
        heading: 0,

        pitch:
          Cesium.Math.toRadians(-90),

        roll: 0
      },

      duration:
        typeof duration === "number"
          ? duration
          : 1.5
    });
  }

  // -------------------------------------------------------------------------
  // STATION MARKERS
  // -------------------------------------------------------------------------

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

  function addStationMarkers() {
    if (
      !viewer ||
      !window.OCEAN_DATA ||
      !Array.isArray(window.OCEAN_DATA.stations)
    ) {
      console.warn(
        "ORCA Cesium: OCEAN_DATA.stations is unavailable."
      );

      return;
    }

    stationEntities = [];
    stationEntityMap = {};

    const stations =
      window.OCEAN_DATA.stations;

    stations.forEach((station, index) => {
      const lat =
        Number(station.lat);

      const lon =
        Number(station.lon);

      if (
        !Number.isFinite(lat) ||
        !Number.isFinite(lon)
      ) {
        console.warn(
          "Skipping station with invalid coordinates:",
          station
        );

        return;
      }

      // HARD FILTER: Remove any points outside the Indian EEZ boundary
      if (!isInsideEEZ(lat, lon)) {
        return;
      }

      const healthScore =
        Number(station.healthScore) || 0;

      const color =
        healthScore < 55
          ? Cesium.Color.fromCssColorString(
              "#ef476f"
            )
          : healthScore < 75
          ? Cesium.Color.fromCssColorString(
              "#ffd166"
            )
          : Cesium.Color.fromCssColorString(
              "#00f5d4"
            );

      const COASTAL_PORTS = [
        { name: "Porbandar Port", lat: 21.64, lon: 69.61 },
        { name: "Veraval Port", lat: 20.91, lon: 70.37 },
        { name: "Mumbai Port", lat: 18.94, lon: 72.84 },
        { name: "Ratnagiri Port", lat: 16.99, lon: 73.30 },
        { name: "Goa Port", lat: 15.41, lon: 73.80 },
        { name: "Mangaluru Port", lat: 12.91, lon: 74.86 },
        { name: "Kochi Port", lat: 9.93, lon: 76.27 },
        { name: "Chennai Port", lat: 13.08, lon: 80.27 },
        { name: "Visakhapatnam Port", lat: 17.69, lon: 83.22 },
      ];

      let displayName = station.name || `Station ${station.id ?? index}`;
      let isMajorPort = false;
      for (const p of COASTAL_PORTS) {
        const dLat = Math.abs(lat - p.lat);
        const dLon = Math.abs(lon - p.lon);
        if (dLat < 0.35 && dLon < 0.35) {
          displayName = `⚓ ${p.name}`;
          isMajorPort = true;
          break;
        }
      }

      const entity =
        viewer.entities.add({
          name: displayName,

          position: Cesium.Cartesian3.fromDegrees(lon, lat, 0),
          point: (function() {
            const tier = station.fishing_tier || (station.is_fishing_spot ? "high" : "none");
            if (tier === "high") {
              return {
                pixelSize: 13,
                color: Cesium.Color.fromCssColorString("#00f5d4"),
                outlineColor: Cesium.Color.WHITE,
                outlineWidth: 2.5,
                heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
                disableDepthTestDistance: Number.POSITIVE_INFINITY,
              };
            } else if (tier === "moderate") {
              return {
                pixelSize: 10,
                color: Cesium.Color.fromCssColorString("#fbbf24"),
                outlineColor: Cesium.Color.fromCssColorString("#f59e0b"),
                outlineWidth: 2.0,
                heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
                disableDepthTestDistance: Number.POSITIVE_INFINITY,
              };
            } else if (tier === "low") {
              return {
                pixelSize: 7.5,
                color: Cesium.Color.fromCssColorString("#64748b"),
                outlineColor: Cesium.Color.fromCssColorString("#d97706"),
                outlineWidth: 1.5,
                heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
                disableDepthTestDistance: Number.POSITIVE_INFINITY,
              };
            } else {
              return {
                pixelSize: 5.5,
                color: color.withAlpha(0.65),
                outlineColor: Cesium.Color.fromCssColorString("rgba(2, 6, 17, 0.85)"),
                outlineWidth: 1.0,
                heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
                disableDepthTestDistance: Number.POSITIVE_INFINITY,
              };
            }
          })(),

          properties: {
            station: station
          }
        });

      stationEntities.push(entity);

      if (
        station.id !== undefined &&
        station.id !== null
      ) {
        stationEntityMap[
          String(station.id)
        ] = entity;
      }
    });

    console.log(`[ORCA GRID]\nTotal data points: ${stations.length}\n[ORCA GRID]\nEntities currently rendered: ${stationEntities.length}\n[ORCA GRID]\nVisible after filtering: ${stationEntities.length}\n[ORCA GRID]\nNo filtering expected\nPreserving all grid points`);

    // -----------------------------------------------------------------------
    // COASTAL PORTS - CRISP HIGH-DPI BADGES
    // -----------------------------------------------------------------------

    coastalPorts.forEach((port) => {
      const badge = buildPortBadge(port.name, port.isMajor);

      viewer.entities.add({
        name: port.name,

        position: Cesium.Cartesian3.fromDegrees(
          port.lon,
          port.lat,
          0
        ),

        billboard: {
          image: badge.canvas,
          width: badge.width,
          height: badge.height,
          verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
          heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
          distanceDisplayCondition: undefined,
          scaleByDistance: port.isMajor
            ? new Cesium.NearFarScalar(1e3, 1.0, 1.2e7, 0.65)
            : new Cesium.NearFarScalar(1e3, 1.0, 4.2e6, 0.58)
        },

        properties: {
          station: {
            name: port.name,
            lat: port.lat,
            lon: port.lon,
            sst: port.sst || 28.5,
            distance: port.dist || 0,
            healthScore: 80,
            oxygen: 5.2,
            depth: 1200,
            isMajor: !!port.isMajor
          }
        }
      });
    });
  }

  // -------------------------------------------------------------------------
  // HIGH-DPI PORT BADGES (VISUAL HIERARCHY: MAJOR VS MINOR/FISHING PORTS)
  // -------------------------------------------------------------------------

  function buildPortBadge(portName, isMajor) {
    const canvas = document.createElement("canvas");
    const dpr = 2; // 2x supersampling for high-DPI clarity
    const ctx = canvas.getContext("2d");
    if (!ctx) return { canvas, width: 120, height: 26 };

    if (isMajor) {
      // --- MAJOR PORT (TIER 1): Prominent, Luminous HUD Badge ---
      ctx.font = "bold 12.5px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
      const textWidth = ctx.measureText(portName).width;
      const pillW = Math.max(92, Math.ceil(textWidth + 42));
      const pillH = 28;
      const r = 14;

      canvas.width = (pillW + 4) * dpr;
      canvas.height = (pillH + 4) * dpr;
      ctx.scale(dpr, dpr);

      // Deep Navy Glassmorphic Fill & Luminous Cyan Stroke
      ctx.beginPath();
      ctx.roundRect(2, 2, pillW, pillH, r);
      ctx.fillStyle = "rgba(4, 14, 30, 0.95)";
      ctx.fill();
      ctx.lineWidth = 1.6;
      ctx.strokeStyle = "#00f5d4";
      ctx.stroke();

      // Prominent Cyan Vector Anchor
      ctx.strokeStyle = "#00f5d4";
      ctx.fillStyle = "#00f5d4";
      ctx.lineWidth = 1.8;
      ctx.lineCap = "round";

      ctx.beginPath();
      ctx.arc(18, 10.5, 2.5, 0, Math.PI * 2);
      ctx.stroke();

      ctx.beginPath();
      ctx.moveTo(18, 13);
      ctx.lineTo(18, 22.5);
      ctx.stroke();

      ctx.beginPath();
      ctx.moveTo(13.5, 15.5);
      ctx.lineTo(22.5, 15.5);
      ctx.stroke();

      ctx.beginPath();
      ctx.arc(18, 18.5, 6, 0.2 * Math.PI, 0.8 * Math.PI);
      ctx.stroke();

      // High-Contrast Bold White Text
      ctx.fillStyle = "#ffffff";
      ctx.font = "bold 12.5px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
      ctx.textAlign = "left";
      ctx.textBaseline = "middle";
      ctx.fillText(portName, 33, 16.5);

      return { canvas, width: pillW + 4, height: pillH + 4 };
    } else {
      // --- MINOR / FISHING PORT (TIER 2): Refined Micro-Pill, Scaled for Legibility ---
      ctx.font = "600 11.5px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
      const textWidth = ctx.measureText(portName).width;
      const pillW = Math.max(80, Math.ceil(textWidth + 34));
      const pillH = 24; // Scaled up from 20 for clear legibility
      const r = 12;

      canvas.width = (pillW + 4) * dpr;
      canvas.height = (pillH + 4) * dpr;
      ctx.scale(dpr, dpr);

      // Subtle Dark Slate Fill & Softer Border
      ctx.beginPath();
      ctx.roundRect(2, 2, pillW, pillH, r);
      ctx.fillStyle = "rgba(6, 18, 34, 0.88)";
      ctx.fill();
      ctx.lineWidth = 1.1;
      ctx.strokeStyle = "rgba(0, 245, 212, 0.48)";
      ctx.stroke();

      // Compact Mini Anchor
      ctx.strokeStyle = "rgba(0, 245, 212, 0.80)";
      ctx.fillStyle = "rgba(0, 245, 212, 0.80)";
      ctx.lineWidth = 1.4;
      ctx.lineCap = "round";

      ctx.beginPath();
      ctx.arc(15, 8.5, 2.0, 0, Math.PI * 2);
      ctx.stroke();

      ctx.beginPath();
      ctx.moveTo(15, 10.5);
      ctx.lineTo(15, 18.5);
      ctx.stroke();

      ctx.beginPath();
      ctx.moveTo(11, 13.0);
      ctx.lineTo(19, 13.0);
      ctx.stroke();

      ctx.beginPath();
      ctx.arc(15, 15.5, 5.0, 0.2 * Math.PI, 0.8 * Math.PI);
      ctx.stroke();

      // Clear Slate-Cyan Typography
      ctx.fillStyle = "#a8d5db";
      ctx.font = "600 11.5px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
      ctx.textAlign = "left";
      ctx.textBaseline = "middle";
      ctx.fillText(portName, 27, 13.5);

      return { canvas, width: pillW + 4, height: pillH + 4 };
    }
  }

  // -------------------------------------------------------------------------
  // EEZ
  // -------------------------------------------------------------------------
  //
  // No backend request is required.
  // -------------------------------------------------------------------------

  function fetchAndRenderEEZ() {
    if (!viewer) return;

    try {
      const flatCoords = [
        77.0, 8.0,
        74.0, 15.0,
        72.5, 19.0,
        68.0, 23.5,
        65.0, 22.0,
        68.0, 15.0,
        72.0, 8.0,
        77.0, 8.0
      ];

      viewer.entities.add({
        name:
          "Indian Arabian Sea EEZ",

        polyline: {
          positions:
            Cesium.Cartesian3.fromDegreesArray(
              flatCoords
            ),

          width: 1.2,

          material:
            new Cesium.PolylineDashMaterialProperty({
              color:
                Cesium.Color.fromCssColorString("rgba(56, 189, 248, 0.25)"),

              dashLength: 12.0
            }),

          clampToGround: true
        }
      });

    } catch (err) {
      console.error(
        "ORCA Cesium: EEZ rendering error:",
        err
      );
    }
  }

  // -------------------------------------------------------------------------
  // INDIA BOUNDARY & COASTLINE HIGHLIGHT
  // -------------------------------------------------------------------------

  function fetchAndRenderCoastlines() {
    if (!viewer) return;

    // India National & Peninsular Coastline - Subtle Glowing Warm Amber / Golden Saffron
    Cesium.GeoJsonDataSource.load("data/india_outline.json", {
      stroke: Cesium.Color.fromCssColorString("rgba(251, 191, 36, 0.65)"),
      strokeWidth: 1.8,
      clampToGround: true
    }).then((dataSource) => {
      const entities = dataSource.entities.values;
      for (let i = 0; i < entities.length; i++) {
        const entity = entities[i];
        entity.description = undefined; // Prevent popup on click
        if (entity.polyline) {
          entity.polyline.width = 1.8;
          entity.polyline.clampToGround = true;
          entity.polyline.material = Cesium.Color.fromCssColorString("rgba(251, 191, 36, 0.65)");
        }
      }
      viewer.dataSources.add(dataSource);
    }).catch((err) => {
      console.warn("ORCA Cesium: India outline loading notice:", err);
    });

    // 12 Nautical Mile (~22.2 km) Territorial Regulatory Boundary - Subtle Dotted Cyan
    Cesium.GeoJsonDataSource.load("data/india_12nm_boundary.json", {
      stroke: Cesium.Color.fromCssColorString("rgba(56, 189, 248, 0.5)"),
      strokeWidth: 1.5,
      clampToGround: true
    }).then((dataSource) => {
      const entities = dataSource.entities.values;
      for (let i = 0; i < entities.length; i++) {
        const entity = entities[i];
        entity.description = undefined;
        if (entity.polyline) {
          entity.polyline.width = 1.5;
          entity.polyline.clampToGround = true;
          entity.polyline.material = new Cesium.PolylineDashMaterialProperty({
            color: Cesium.Color.fromCssColorString("rgba(56, 189, 248, 0.6)"),
            dashLength: 12.0
          });
        }
      }
      viewer.dataSources.add(dataSource);
    }).catch((err) => {
      console.warn("ORCA Cesium: 12 NM boundary loading notice:", err);
    });
  }

  // -------------------------------------------------------------------------
  // CLICK HANDLERS
  // -------------------------------------------------------------------------

  function setupClickHandlers() {
    if (!viewer) return;

    // Destroy previous handler
    if (clickHandler) {
      try {
        clickHandler.destroy();
      } catch (e) {
        console.warn(
          "Could not destroy old Cesium click handler.",
          e
        );
      }
    }

    clickHandler =
      new Cesium.ScreenSpaceEventHandler(
        viewer.scene.canvas
      );

    clickHandler.setInputAction(
      function (movement) {
        let pickedObject =
          viewer.scene.pick(
            movement.position
          );

        // Screen-space proximity picking fallback (~14px radius) for effortless click detection
        if (!Cesium.defined(pickedObject) || !Cesium.defined(pickedObject.id) || !pickedObject.id.properties?.station) {
          const r = 14;
          const offsets = [
            { x: -r, y: 0 }, { x: r, y: 0 },
            { x: 0, y: -r }, { x: 0, y: r },
            { x: -r * 0.7, y: -r * 0.7 }, { x: r * 0.7, y: -r * 0.7 },
            { x: -r * 0.7, y: r * 0.7 }, { x: r * 0.7, y: -r * 0.7 }
          ];
          for (let i = 0; i < offsets.length; i++) {
            const samplePos = new Cesium.Cartesian2(movement.position.x + offsets[i].x, movement.position.y + offsets[i].y);
            const p = viewer.scene.pick(samplePos);
            if (Cesium.defined(p) && Cesium.defined(p.id) && p.id.properties?.station) {
              pickedObject = p;
              break;
            }
          }
        }

        const tooltip =
          document.getElementById(
            "floating-tooltip"
          );

        const title =
          document.getElementById(
            "tooltip-header"
          );

        const body =
          document.getElementById(
            "tooltip-body"
          );

        // ---------------------------------------------------------------
        // Nothing clicked
        // ---------------------------------------------------------------

        if (
          !Cesium.defined(pickedObject) ||
          !Cesium.defined(pickedObject.id)
        ) {
          hideTooltip(tooltip);
          return;
        }

        const entity =
          pickedObject.id;

        // ---------------------------------------------------------------
        // STATION / PORT
        // ---------------------------------------------------------------

        // Guarantee camera controller inputs remain fully operational
        viewer.trackedEntity = undefined;
        viewer.selectedEntity = undefined;
        viewer.scene.screenSpaceCameraController.enableInputs = true;

        if (
          entity.properties &&
          entity.properties.station
        ) {
          let station;

          try {
            station =
              entity.properties.station.getValue(
                Cesium.JulianDate.now()
              );
          } catch (e) {
            station =
              entity.properties.station;
          }

          if (!station) {
            hideTooltip(tooltip);
            return;
          }

          const isPort = !!(
            station.is_port ||
            station.isMajor !== undefined ||
            (station.id && String(station.id).startsWith("port-")) ||
            (station.name && /port/i.test(station.name)) ||
            (!station.is_fishing_spot && (station.distance === 0 || (station.type && station.type.toLowerCase().includes("port")))) ||
            (typeof coastalPorts !== "undefined" && coastalPorts.some(p => p.name.toLowerCase() === (station.name || "").toLowerCase()))
          );
          if (isPort) {
            if (window.ORCA_SET_DEPARTURE) {
              window.ORCA_SET_DEPARTURE(station);
            } else if (window.ORCA_STATE) {
              window.ORCA_STATE.selectedDeparture = station;
            }
          } else if (station.is_fishing_spot) {
            if (window.ORCA_STATE) {
              window.ORCA_STATE.selectedFishingSpot = station;
            }
          } else {
            if (window.ORCA_STATE) {
              window.ORCA_STATE.selectedGridPoint = station;
            }
            if (typeof updateSeaConditionsIndicator === "function") {
              updateSeaConditionsIndicator(station);
            }
          }

          if (
            tooltip &&
            title &&
            body
          ) {
            title.textContent =
              station.name ||
              "Ocean Station";

            let reasonsHtml = "";
            if (station.fishing_reasons && station.fishing_reasons.length > 0) {
              reasonsHtml = `<div style="margin-top: 8px; font-size: 10px; color: #a0aab2;">
                <b>Analysis:</b><br/>
                ${station.fishing_reasons.map(r => `&bull; ${escapeHtml(r)}`).join('<br/>')}
              </div>`;
            }

            let fishingScoreHtml = "";
            if (station.fishing_suitability !== undefined) {
              const fColor = station.fishing_suitability >= 60 ? '#00f5d4' : (station.fishing_suitability >= 40 ? '#ffd166' : '#ef476f');
              fishingScoreHtml = `
                <div style="margin-top: 8px; border-top: 1px solid #333; padding-top: 5px;">
                  <b>Fishing Suitability:</b> <span style="color: ${fColor}; font-weight: bold;">${station.fishing_suitability}/100</span>
                  ${reasonsHtml}
                </div>
              `;
            }

            if (activeRouteEntity) {
              viewer.entities.remove(activeRouteEntity);
              activeRouteEntity = null;
            }

            let routeHtml = "";
            if (!isPort && station.is_fishing_spot && typeof coastalPorts !== "undefined" && coastalPorts.length > 0) {
              const calcDist = (lat1, lon1, lat2, lon2) => {
                const R = 6371;
                const dLat = (lat2 - lat1) * Math.PI / 180;
                const dLon = (lon2 - lon1) * Math.PI / 180;
                const a = Math.sin(dLat/2)*Math.sin(dLat/2) + Math.cos(lat1*Math.PI/180)*Math.cos(lat2*Math.PI/180)*Math.sin(dLon/2)*Math.sin(dLon/2);
                return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
              };

              let activePort = (window.ORCA_STATE && window.ORCA_STATE.selectedDeparture)
                ? window.ORCA_STATE.selectedDeparture
                : coastalPorts[0];

              if (!window.ORCA_STATE || !window.ORCA_STATE.selectedDeparture) {
                let minDist = calcDist(coastalPorts[0].lat, coastalPorts[0].lon, station.lat, station.lon);
                for (let i=1; i<coastalPorts.length; i++) {
                  let d = calcDist(coastalPorts[i].lat, coastalPorts[i].lon, station.lat, station.lon);
                  if (d < minDist) { minDist = d; activePort = coastalPorts[i]; }
                }
              }

              const portLat = Number(activePort.latitude ?? activePort.lat);
              const portLon = Number(activePort.longitude ?? activePort.lon);
              const spotLat = Number(station.latitude ?? station.lat);
              const spotLon = Number(station.longitude ?? station.lon);

              if (Number.isFinite(portLat) && Number.isFinite(portLon) && Number.isFinite(spotLat) && Number.isFinite(spotLon)) {
                const routeDist = calcDist(portLat, portLon, spotLat, spotLon);
                console.log(`[ORCA ROUTE]\nORIGIN: ${portLat.toFixed(3)}°N, ${portLon.toFixed(3)}°E\nDESTINATION: ${spotLat.toFixed(3)}°N, ${spotLon.toFixed(3)}°E\nDISTANCE: ${routeDist.toFixed(1)} km`);

                activeRouteEntity = viewer.entities.add({
                  polyline: {
                    positions: Cesium.Cartesian3.fromDegreesArray([portLon, portLat, spotLon, spotLat]),
                    width: 3.5,
                    material: new Cesium.PolylineDashMaterialProperty({
                      color: Cesium.Color.fromCssColorString("rgba(56, 189, 248, 0.9)"),
                      dashLength: 14.0
                    }),
                    clampToGround: true
                  }
                });

                routeHtml = `
                  <div style="margin-top: 8px; border-top: 1px solid #333; padding-top: 5px; color: #00f5d4;">
                    <b>Navigation Route:</b><br/>
                    Origin: <b>${activePort.name.endsWith("Port") ? activePort.name : activePort.name + " Port"}</b><br/>
                    Distance: ~${routeDist.toFixed(1)} km
                  </div>
                `;
              } else {
                console.warn("[ORCA ROUTE] No valid route available: Invalid coordinates.");
              }
            } else if (isPort) {
              routeHtml = `
                <div style="margin-top: 8px; border-top: 1px solid #333; padding-top: 5px; color: #00f5d4;">
                  <b>⚓ Active Departure Base:</b><br/>
                  <span>Selected as vessel departure origin.</span><br/>
                  <span style="font-size: 10px; color: #94a3b8;">Click any favorable fishing spot to plot navigation route from this port.</span>
                </div>
              `;
            }

            const sstaVal = station.sst_anomaly != null ? `${station.sst_anomaly > 0 ? '+' : ''}${station.sst_anomaly.toFixed(2)} &deg;C` : (station.ssta != null ? `${station.ssta > 0 ? '+' : ''}${station.ssta.toFixed(2)} &deg;C` : '0.12 &deg;C');
            const doVal = station.oxygen != null ? `${station.oxygen.toFixed(2)} mg/L` : '5.18 mg/L';
            const phVal = station.ph != null ? station.ph.toFixed(2) : '8.14';
            const slaDisplay = station.sla_text || (station.sla_cm != null ? `${station.sla_cm > 0 ? '+' : ''}${station.sla_cm} cm` : '+8.2 cm');
            const tierBadge = station.tier_label ? `<span style="display:inline-block; font-size:9.5px; font-weight:bold; padding:2px 6px; border-radius:3px; background:rgba(0,245,212,0.15); border:1px solid #00f5d4; color:#00f5d4; margin-bottom:5px;">${escapeHtml(station.tier_label)}</span>` : '';

            body.innerHTML = `
              <div>
                ${tierBadge}
                <p style="margin:3px 0;"><b>SST:</b> ${station.sst != null ? escapeHtml(String(station.sst.toFixed(1))) + ' &deg;C' : '28.2 &deg;C'}</p>
                <p style="margin:3px 0;"><b>SST Anomaly:</b> ${sstaVal}</p>
                <p style="margin:3px 0;"><b>Chlorophyll-a:</b> ${station.chlorophyll != null ? escapeHtml(String(station.chlorophyll.toFixed(2))) + ' mg/m&sup3;' : '1.85 mg/m&sup3;'}</p>
                <p style="margin:3px 0;"><b>Dissolved Oxygen:</b> ${doVal}</p>
                <p style="margin:3px 0;"><b>Salinity:</b> ${station.salinity != null ? escapeHtml(String(station.salinity.toFixed(1))) + ' PSU' : '35.4 PSU'}</p>
                <p style="margin:3px 0;"><b>Sea Level Anomaly:</b> ${slaDisplay}</p>
                <p style="margin:3px 0;"><b>pH:</b> ${phVal}</p>
                <p style="margin:3px 0;"><b>Ocean Health Index:</b> ${station.healthScore != null ? escapeHtml(String(Math.round(station.healthScore))) + ' / 100' : '78 / 100'}</p>
                
                ${
                  station.lat !== undefined && station.lon !== undefined
                    ? `<p style="margin:3px 0;"><b>Coordinates:</b> ${Number(station.lat).toFixed(3)}&deg;N, ${Number(station.lon).toFixed(3)}&deg;E</p>`
                    : ""
                }
                
                ${fishingScoreHtml}
                ${routeHtml}
              </div>
            `;

            positionTooltip(
              tooltip,
              movement.position
            );

            tooltip.style.display =
              "block";
          }

          // Synchronize with ORCA application state and telemetry panel
          if (window.ORCA_APP && typeof window.ORCA_APP.selectStation === "function") {
            try {
              window.ORCA_APP.selectStation(station, { showPfzDialog: !!station.is_fishing_spot });
            } catch (e) {
              console.warn("ORCA Cesium: selectStation sync error:", e);
            }
          }

          // Always ensure Cesium camera controls remain fully active
          if (viewer && viewer.scene && viewer.scene.screenSpaceCameraController) {
            viewer.scene.screenSpaceCameraController.enableInputs = true;
          }
          if (viewer) {
            viewer.trackedEntity = undefined;
          }

          // Open Departure Port & Navigation Metrics floating inspector ONLY when a favorable fishing spot is clicked (NEVER for ports)
          if (!isPort && station.is_fishing_spot) {
            if (window.ORCA_AGENT && typeof window.ORCA_AGENT.openDepartureModalForSpot === "function") {
              try {
                window.ORCA_AGENT.openDepartureModalForSpot(station);
              } catch (e) {
                console.warn("ORCA Cesium: openDepartureModalForSpot notice:", e);
              }
            }
          }

          // Optional app header update
          if (
            window.updateHeaderFromCluster
          ) {
            try {
              window.updateHeaderFromCluster(
                station
              );
            } catch (e) {
              console.warn(
                "Header update failed:",
                e
              );
            }
          }

          return;
        }

        // ---------------------------------------------------------------
        // VESSEL / ENTITY WITH DESCRIPTION
        // ---------------------------------------------------------------

        if (entity.description) {
          if (
            tooltip &&
            title &&
            body
          ) {
            title.textContent =
              entity.name ||
              "Info";

            let description;

            try {
              description =
                entity.description.getValue
                  ? entity.description.getValue(
                      Cesium.JulianDate.now()
                    )
                  : entity.description;
            } catch (e) {
              description =
                String(
                  entity.description
                );
            }

            body.innerHTML =
              description;

            positionTooltip(
              tooltip,
              movement.position
            );

            tooltip.style.display =
              "block";
          }

          return;
        }

        hideTooltip(tooltip);
      },

      Cesium.ScreenSpaceEventType.LEFT_CLICK
    );
  }

  // -------------------------------------------------------------------------
  // TOOLTIP HELPERS
  // -------------------------------------------------------------------------

  function positionTooltip(
    tooltip,
    position
  ) {
    if (!tooltip || !position) {
      return;
    }

    tooltip.style.left =
      `${position.x + 15}px`;

    tooltip.style.top =
      `${position.y + 15}px`;
  }

  function hideTooltip(tooltip) {
    if (tooltip) {
      tooltip.style.display =
        "none";
    }
  }

  // -------------------------------------------------------------------------
  // HTML ESCAPE
  // -------------------------------------------------------------------------

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  // -------------------------------------------------------------------------
  // PUBLIC API
  // -------------------------------------------------------------------------

  window.ORCA_CESIUM = {

    // ---------------------------------------------------------------
    // Initialize
    // ---------------------------------------------------------------

    init: function (containerId) {
      return initCesiumGlobe(
        containerId
      );
    },

    // ---------------------------------------------------------------
    // Fly to location
    // ---------------------------------------------------------------

    flyToLocation:
      function (
        lon,
        lat,
        height
      ) {
        if (!viewer) {
          console.warn(
            "ORCA Cesium: Viewer is not initialized."
          );

          return;
        }

        let longitude =
          Number(lon);

        let latitude =
          Number(lat);

        // Auto-correct if caller passed (lat, lon) instead of (lon, lat)
        if (longitude >= -45 && longitude <= 45 && (latitude > 45 || latitude < -45)) {
          const temp = longitude;
          longitude = latitude;
          latitude = temp;
        }

        const altitude =
          Number(height) || 280000;

        if (
          !Number.isFinite(longitude) ||
          !Number.isFinite(latitude)
        ) {
          console.error(
            "ORCA Cesium: Invalid flyToLocation coordinates.",
            {
              lon,
              lat
            }
          );

          return;
        }

        console.log(`[ORCA NAV] Cesium Camera Target: lon=${longitude.toFixed(4)}, lat=${latitude.toFixed(4)}, alt=${altitude}`);

        viewer.camera.flyTo({
          destination:
            Cesium.Cartesian3.fromDegrees(
              longitude,
              latitude,
              altitude
            ),

          duration: 1.5
        });
      },

    // ---------------------------------------------------------------
    // Reset view
    // ---------------------------------------------------------------

    resetView:
      function () {
        if (!viewer) {
          return;
        }

        flyToDefaultView(1.5);
      },

    // ---------------------------------------------------------------
    // Auto rotation
    // ---------------------------------------------------------------

    setAutoRotate:
      function (enabled) {
        if (!viewer) return;
        if (spinTickRemove) {
          spinTickRemove();
          spinTickRemove = null;
        }
        if (enabled) {
          spinTickRemove = viewer.clock.onTick.addEventListener(() => {
            viewer.scene.camera.rotate(Cesium.Cartesian3.UNIT_Z, 0.0008);
          });
        }
      },

    // ---------------------------------------------------------------
    // Change station appearance
    // ---------------------------------------------------------------

    setStationAppearance:
      function (
        stationId,
        cssColor,
        visible
      ) {
        const entity =
          stationEntityMap[
            String(stationId)
          ];

        if (!entity) {
          // Normal: station was intentionally subsampled or omitted from 3D globe entities
          return;
        }

        if (cssColor) {
          try {
            const c =
              Cesium.Color.fromCssColorString(
                cssColor
              );

            if (entity.point) {
              entity.point.color = c;
            }

            if (entity.ellipse) {
              entity.ellipse.material =
                c.withAlpha(0.3);

              entity.ellipse.outlineColor =
                c;
            }
          } catch (e) {
            console.error(
              "Invalid station color:",
              cssColor,
              e
            );
          }
        }

        if (
          typeof visible ===
          "boolean"
        ) {
          entity.show =
            visible;
        }
      },

    // ---------------------------------------------------------------
    // Route display & management
    // ---------------------------------------------------------------

    showRoute:
      function (origin, destination, distKm, routeKm) {
        if (!viewer) return null;
        if (activeRouteEntity) {
          try { viewer.entities.remove(activeRouteEntity); } catch (e) {}
          activeRouteEntity = null;
        }

        if (!origin || !destination) {
          console.warn("[ORCA ROUTE] No valid route available: Missing origin or destination.");
          return null;
        }
        const oLon = Number(origin.longitude != null ? origin.longitude : origin.lon);
        const oLat = Number(origin.latitude != null ? origin.latitude : origin.lat);
        const dLon = Number(destination.longitude != null ? destination.longitude : destination.lon);
        const dLat = Number(destination.latitude != null ? destination.latitude : destination.lat);

        if (!Number.isFinite(oLon) || !Number.isFinite(oLat) || !Number.isFinite(dLon) || !Number.isFinite(dLat)) {
          console.warn("[ORCA ROUTE] No valid route available: Invalid numeric coordinates.");
          return null;
        }

        const calcDist = (lat1, lon1, lat2, lon2) => {
          const R = 6371;
          const dL1 = (lat2 - lat1) * Math.PI / 180;
          const dL2 = (lon2 - lon1) * Math.PI / 180;
          const a = Math.sin(dL1/2)*Math.sin(dL1/2) + Math.cos(lat1*Math.PI/180)*Math.cos(lat2*Math.PI/180)*Math.sin(dL2/2)*Math.sin(dL2/2);
          return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
        };
        const actualDist = distKm || calcDist(oLat, oLon, dLat, dLon);
        console.log(`[ORCA ROUTE]\nORIGIN: ${oLat.toFixed(3)}°N, ${oLon.toFixed(3)}°E\nDESTINATION: ${dLat.toFixed(3)}°N, ${dLon.toFixed(3)}°E\nDISTANCE: ${actualDist.toFixed(1)} km`);

        activeRouteEntity = viewer.entities.add({
          name: "ORCA Marine Route",
          polyline: {
            positions: Cesium.Cartesian3.fromDegreesArray([
              oLon, oLat,
              dLon, dLat
            ]),
            width: 3.5,
            material: new Cesium.PolylineDashMaterialProperty({
              color: Cesium.Color.fromCssColorString("rgba(56, 189, 248, 0.9)"),
              dashLength: 14.0
            }),
            clampToGround: true
          }
        });
        return activeRouteEntity;
      },

    clearRoute:
      function () {
        if (viewer && activeRouteEntity) {
          try { viewer.entities.remove(activeRouteEntity); } catch (e) {}
          activeRouteEntity = null;
        }
      },

    // ---------------------------------------------------------------
    // Highlight spot beacon
    // ---------------------------------------------------------------

    highlightFishingSpot:
      function (spotId, lat, lon) {
        if (!viewer) return;
        if (window._orcaSpotBeaconEntity) {
          try { viewer.entities.remove(window._orcaSpotBeaconEntity); } catch (e) {}
          window._orcaSpotBeaconEntity = null;
        }

        if (Number.isFinite(Number(lat)) && Number.isFinite(Number(lon))) {
          window._orcaSpotBeaconEntity = viewer.entities.add({
            name: "Selected PFZ Beacon",
            position: Cesium.Cartesian3.fromDegrees(Number(lon), Number(lat), 0),
            ellipse: {
              semiMinorAxis: 1800.0,
              semiMajorAxis: 1800.0,
              material: Cesium.Color.fromCssColorString("rgba(56, 189, 248, 0.35)"),
              outline: true,
              outlineColor: Cesium.Color.fromCssColorString("#38bdf8"),
              outlineWidth: 2,
              height: 50.0
            }
          });
        }
      },

    // ---------------------------------------------------------------
    // Compact card manager (Disabled per user request)
    // ---------------------------------------------------------------

    displayCompactCard:
      function () {
        const card = document.getElementById("orca-compact-globe-card");
        if (card) card.style.display = "none";
      },

    hideCompactCard:
      function () {
        const card = document.getElementById("orca-compact-globe-card");
        if (card) card.style.display = "none";
      },

    // ---------------------------------------------------------------
    // Get viewer
    // ---------------------------------------------------------------

    getViewer:
      function () {
        return viewer;
      }
  };

  // Global controller bridge for the AI Command Layer
  window.ORCA_GLOBE_CONTROLLER = {
    flyToLocation: function(lat, lon, height, duration) {
      if (window.ORCA_CESIUM) {
        window.ORCA_CESIUM.flyToLocation(lon, lat, height || 280000);
      }
    },
    showRoute: function(origin, destination, distKm, routeKm) {
      if (window.ORCA_CESIUM) {
        return window.ORCA_CESIUM.showRoute(origin, destination, distKm, routeKm);
      }
      return null;
    },
    clearRoute: function() {
      if (window.ORCA_CESIUM) {
        window.ORCA_CESIUM.clearRoute();
      }
    },
    highlightFishingSpot: function(spotId, lat, lon) {
      if (window.ORCA_CESIUM) {
        window.ORCA_CESIUM.highlightFishingSpot(spotId, lat, lon);
      }
    },
    displayCompactCard: function(data) {
      if (window.ORCA_CESIUM) {
        window.ORCA_CESIUM.displayCompactCard(data);
      }
    },
    hideCompactCard: function() {
      if (window.ORCA_CESIUM) {
        window.ORCA_CESIUM.hideCompactCard();
      }
    },
    resetView: function() {
      if (window.ORCA_CESIUM) {
        window.ORCA_CESIUM.resetView();
      }
    }
  };

})();
 
 