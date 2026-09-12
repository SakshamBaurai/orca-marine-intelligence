/**
 * ==========================================================================
 * ORCA OCEAN HEALTH MONITORING GRID DATASET
 * ==========================================================================
 *
 * Arabian Sea / North Indian Ocean
 *
 * Latitude:
 * 8°N - 18°N
 *
 * Longitude:
 * 65°E - 74°E
 *
 * This file generates the local station dataset used by:
 *
 * - Three.js globe
 * - Leaflet map
 * - Telemetry inspector
 * - Metric selector
 * - Health filters
 * ==========================================================================
 */

(function (global) {

  "use strict";


  // =========================================================================
  // COORDINATE GRID
  // =========================================================================

  const lats = [

    8.25,
    8.5,
    8.75,
    9.0,
    9.25,
    9.5,
    9.75,

    10.0,
    10.25,
    10.5,
    10.75,
    11.0,
    11.25,
    11.5,
    11.75,

    12.0,
    12.25,
    12.5,
    12.75,
    13.0,
    13.25,
    13.5,
    13.75,

    14.0,
    14.25,
    14.5,
    14.75,
    15.0,
    15.25,
    15.5,
    15.75,

    16.0,
    16.25,
    16.5,
    16.75,
    17.0,
    17.25,
    17.5,
    17.75,

    18.0,
    18.25,
    18.5,
    18.75,
    19.0,
    19.25,
    19.5,
    19.75,

    20.0,
    20.25,
    20.5,
    20.75,
    21.0,
    21.25,
    21.5,
    21.75,

    22.0,
    22.25,
    22.5,
    22.75,
    23.0

  ];


  // =========================================================================
  // WATER MASK
  // =========================================================================

  function isWater(
    lat,
    lon
  ) {

    /*
     * Rough coastline approximation.
     *
     * This prevents stations from appearing
     * on the Indian coastline / landmass.
     */

    if (
      lat <= 9.0 &&
      lon > 76.5
    ) {

      return false;

    }


    if (
      lat > 9.0 &&
      lat <= 11.0 &&
      lon > 75.8
    ) {

      return false;

    }


    if (
      lat > 11.0 &&
      lat <= 13.0 &&
      lon > 74.8
    ) {

      return false;

    }


    if (
      lat > 13.0 &&
      lat <= 15.5 &&
      lon > 74.2
    ) {

      return false;

    }


    if (
      lat > 15.5 &&
      lat <= 17.5 &&
      lon > 73.3
    ) {

      return false;

    }

    if (
      lat > 17.5 &&
      lat <= 19.8 &&
      lon > 72.85
    ) {

      return false;

    }

    if (
      lat > 19.8 &&
      lat <= 20.8 &&
      lon > 72.9
    ) {

      return false;

    }

    if (
      lat > 20.8 &&
      lat <= 22.5
    ) {
      if (lon > 70.0 && lon < 72.2 && lat > 21.2) return false;
      if (lon > 72.6) return false;
    }

    if (
      lat > 22.5 &&
      lon > 70.5
    ) {
      return false;
    }


    return true;

  }


  function isInsideEEZ(lat, lon) {
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
  // STATION GENERATION
  // =========================================================================

  const stations = [];


  let stationCounter = 1;


  lats.forEach(
    (lat) => {

      for (
        let lon = 65.25;
        lon <= 73.75;
        lon += 0.75
      ) {

        /*
         * Offset alternate rows so the grid
         * doesn't look completely mechanical.
         */

        const isAltRow =
          Math.round(
            lat * 4
          ) % 2 === 1;


        const actualLon =
          isAltRow
            ? lon
            : lon + 0.25;


        /*
         * Make sure station is inside region, inside EEZ,
         * and in water.
         */

        if (
          actualLon >= 65.0 &&
          actualLon <= 73.75 &&
          isInsideEEZ(lat, actualLon) &&
          isWater(
            lat,
            actualLon
          )
        ) {


          // ===============================================================
          // DEPTH
          // ===============================================================

          const distFromCoast =
            74.5 -
            actualLon;


          const depth =
            Math.round(
              800 +
              distFromCoast *
                420 +
              Math.sin(
                lat * 0.5
              ) *
                300
            );


          // ===============================================================
          // SEA SURFACE TEMPERATURE
          // ===============================================================

          const sst =
            +(
              28.2 +
              Math.sin(
                lat * 0.4
              ) *
                1.4 -
              distFromCoast *
                0.15 +
              (
                Math.random() *
                0.4 -
                0.2
              )
            ).toFixed(2);


          // ===============================================================
          // DISSOLVED OXYGEN
          // ===============================================================

          /*
           * Hypoxic pocket:
           *
           * Lat:
           * 12°N - 15°N
           *
           * Lon:
           * 68°E - 71°E
           */

          const isHypoxicPocket =
            (
              lat >= 12.0 &&
              lat <= 15.0 &&
              actualLon >= 68.0 &&
              actualLon <= 71.0
            );


          const baseDO =
            isHypoxicPocket
              ? 2.4
              : 5.4;


          const dissolvedOxygen =
            +(
              baseDO +
              Math.cos(
                actualLon *
                0.8
              ) *
                0.9 +
              (
                Math.random() *
                0.6 -
                0.3
              )
            ).toFixed(2);


          // ===============================================================
          // pH
          // ===============================================================

          const ph =
            +(
              8.14 -
              (
                30 -
                sst
              ) *
                0.03 -
              (
                distFromCoast < 2
                  ? 0.08
                  : 0
              ) +
              (
                Math.random() *
                0.04 -
                0.02
              )
            ).toFixed(2);


          // ===============================================================
          // CHLOROPHYLL-A
          // ===============================================================

          const chlorophyll =
            +(
              0.3 +
              (
                distFromCoast < 3
                  ? 1.4
                  : 0.2
              ) +
              Math.sin(
                lat * 0.7
              ) *
                0.3 +
              Math.random() *
                0.2
            ).toFixed(2);


          // ===============================================================
          // SALINITY
          // ===============================================================

          const salinity =
            +(
              35.4 +
              (
                lat /
                18.0
              ) *
                1.1 +
              (
                Math.random() *
                0.3 -
                0.15
              )
            ).toFixed(2);


          // ===============================================================
          // OCEAN HEALTH SCORE
          // ===============================================================

          let healthScore =
            85;


          /*
           * Dissolved oxygen
           */

          if (
            dissolvedOxygen <
            3.0
          ) {

            healthScore -=
              30;

          } else if (
            dissolvedOxygen <
            4.5
          ) {

            healthScore -=
              12;

          }


          /*
           * pH
           */

          if (
            ph < 7.95
          ) {

            healthScore -=
              15;

          }


          /*
           * SST
           */

          if (
            sst > 30.0
          ) {

            healthScore -=
              10;

          }


          /*
           * Add small random variation
           */

          healthScore =
            Math.max(
              10,
              Math.min(
                98,
                Math.round(
                  healthScore +
                  (
                    Math.random() *
                    8 -
                    4
                  )
                )
              )
            );


          // ===============================================================
          // HEALTH STATUS
          // ===============================================================

          let healthStatus =
            "Optimal";


          let statusColor =
            "#00f5d4";


          if (
            healthScore < 50
          ) {

            healthStatus =
              "Hypoxic / Stressed";


            statusColor =
              "#ef476f";

          } else if (
            healthScore < 75
          ) {

            healthStatus =
              "Moderate / Monitored";


            statusColor =
              "#ffd166";

          }


          // ===============================================================
          // STATION OBJECT
          // ===============================================================

            const suitabilityScore = Math.min(100, (sst >= 26.5 && sst <= 29.2 ? 35 : 15) + (chlorophyll >= 0.4 ? 35 : 10) + (dissolvedOxygen >= 5.0 ? 20 : 10) + (healthScore >= 70 ? 10 : 5));
            let fTier = "none";
            let tLabel = "MONITORING NODE";
            let isPfz = false;
            let conf = "Monitoring Cell";
            let fReasons = [
              sst >= 26.5 && sst <= 29.2 ? `Optimal thermal window (${sst}°C)` : `Suboptimal SST (${sst}°C)`,
              chlorophyll >= 0.4 ? `Plankton forage bloom (${chlorophyll} mg/m³)` : `Low forage density`,
              dissolvedOxygen >= 5.0 ? `High dissolved oxygen (${dissolvedOxygen} mg/L)` : `Marginal oxygen`
            ];

            if (suitabilityScore >= 68 && healthScore >= 42) {
              fTier = "high";
              tLabel = "HIGH / FAVORABLE";
              isPfz = true;
              conf = "High Confidence";
            } else if (suitabilityScore >= 50 && healthScore >= 32) {
              fTier = "moderate";
              tLabel = "MODERATE / POTENTIAL";
              isPfz = true;
              conf = "Moderate Potential";
            } else if (suitabilityScore >= 38) {
              fTier = "low";
              tLabel = "LESS FAVORABLE";
              isPfz = true;
              conf = "Less Favorable";
              const limiters = [];
              if (chlorophyll < 0.4) limiters.push(`Low chlorophyll forage (${chlorophyll} mg/m³)`);
              if (sst < 26.5 || sst > 29.2) limiters.push(`SST (${sst}°C) outside preferred 26.5-29.2°C window`);
              if (healthScore < 50) limiters.push(`Marine health under ecological stress (${healthScore}/100)`);
              if (limiters.length > 0) fReasons = limiters;
            }

            stations.push({
              id: `AS-NODE-${String(stationCounter++).padStart(3, "0")}`,
              name: `Arabian Sea Station ${stationCounter - 1}`,
              lat: +lat.toFixed(2),
              lon: +actualLon.toFixed(2),
              depth: depth,
              sst: sst,
              ssta: +((sst - 28.1).toFixed(2)),
              oxygen: dissolvedOxygen,
              ph: ph,
              chlorophyll: chlorophyll,
              salinity: salinity,
              healthScore: healthScore,
              healthStatus: healthStatus,
              statusColor: statusColor,
              currentSpeed: +(0.4 + Math.sin(lat + actualLon) * 0.5 + Math.random() * 0.3).toFixed(2),
              waveHeight: +(1.2 + Math.cos(lat * 0.6) * 0.8 + Math.random() * 0.4).toFixed(1),
              sla: 0.08,
              sla_cm: 8,
              sla_text: "+8 cm",
              is_fishing_spot: isPfz,
              fishing_tier: fTier,
              tier_label: tLabel,
              confidence: conf,
              fishing_suitability: suitabilityScore,
              fishing_reasons: fReasons
            });


        }

      }

    }
  );


  // =========================================================================
  // SUMMARY METRICS
  // =========================================================================

  const avgTemp =
    +(
      stations.reduce(
        (acc, s) =>
          acc + s.sst,
        0
      ) /
      stations.length
    ).toFixed(1);


  const avgDO =
    +(
      stations.reduce(
        (acc, s) =>
          acc + s.oxygen,
        0
      ) /
      stations.length
    ).toFixed(2);


  const avgPH =
    +(
      stations.reduce(
        (acc, s) =>
          acc + s.ph,
        0
      ) /
      stations.length
    ).toFixed(2);


  const avgSalinity =
    +(
      stations.reduce(
        (acc, s) =>
          acc + s.salinity,
        0
      ) /
      stations.length
    ).toFixed(1);


  const overallHealthIndex =
    Math.round(
      stations.reduce(
        (acc, s) =>
          acc +
          s.healthScore,
        0
      ) /
      stations.length
    );


  // =========================================================================
  // EXPOSE DATA GLOBALLY
  // =========================================================================

  global.OCEAN_DATA = {

    regionName:
      "Arabian Sea - North Indian Ocean Basin",


    center:
      [
        14.0,
        71.0
      ],


    defaultZoom:
      6,


    totalStations:
      stations.length,


    overallHealthIndex:
      overallHealthIndex,


    metricsSummary: {

      avgTemp:
        avgTemp,

      avgDO:
        avgDO,

      avgPH:
        avgPH,

      avgSalinity:
        avgSalinity

    },


    stations:
      stations,

    coastalPorts: [
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
    ]

  };


})(

  typeof window !==
  "undefined"

    ? window

    : global

);