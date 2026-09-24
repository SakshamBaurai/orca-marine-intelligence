/**
 * ==========================================================================
 * ORCA NAVIGATION & ROUTE INTELLIGENCE ENGINE (Compatibility Layer)
 * ==========================================================================
 * Automatically calculates route distances, travel time (10 kts),
 * compass bearings, and renders active route results on 3D Globe & 2D Map.
 * ==========================================================================
 */

(function () {
  "use strict";

  let currentTargetSpot = null;
  let activeRouteData = null;

  function calculateHaversineKm(lat1, lon1, lat2, lon2) {
    const p1Lat = Number(lat1);
    const p1Lon = Number(lon1);
    const p2Lat = Number(lat2);
    const p2Lon = Number(lon2);
    if (!Number.isFinite(p1Lat) || !Number.isFinite(p1Lon) || !Number.isFinite(p2Lat) || !Number.isFinite(p2Lon)) {
      return null;
    }
    const R = 6371;
    const dLat = (p2Lat - p1Lat) * Math.PI / 180;
    const dLon = (p2Lon - p1Lon) * Math.PI / 180;
    const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
              Math.cos(p1Lat * Math.PI / 180) * Math.cos(p2Lat * Math.PI / 180) *
              Math.sin(dLon / 2) * Math.sin(dLon / 2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return R * c;
  }

  function formatDistance(distKm) {
    if (distKm == null || !Number.isFinite(distKm)) {
      return "Distance unavailable";
    }
    if (distKm < 1.0) {
      const meters = Math.round(distKm * 1000);
      return `${meters} m`;
    }
    return `${distKm.toFixed(1)} km`;
  }

  function formatTravelTime(distKm) {
    if (distKm == null || !Number.isFinite(distKm)) {
      return "Travel time unavailable";
    }
    const speedKmH = 18.52; // 10 knots default cruising speed
    const totalHours = distKm / speedKmH;
    const totalMinutes = Math.round(totalHours * 60);

    if (totalMinutes < 1) return "~1 min";
    if (totalMinutes < 60) return `~${totalMinutes} min`;

    const hrs = Math.floor(totalMinutes / 60);
    const mins = totalMinutes % 60;
    if (mins === 0) return `~${hrs} hr`;
    return `~${hrs} hr ${mins} min`;
  }

  function calculateHeading(lat1, lon1, lat2, lon2) {
    const p1Lat = Number(lat1);
    const p1Lon = Number(lon1);
    const p2Lat = Number(lat2);
    const p2Lon = Number(lon2);
    if (!Number.isFinite(p1Lat) || !Number.isFinite(p1Lon) || !Number.isFinite(p2Lat) || !Number.isFinite(p2Lon)) {
      return "Heading unavailable";
    }
    const dLon = (p2Lon - p1Lon) * Math.PI / 180;
    const y = Math.sin(dLon) * Math.cos(p2Lat * Math.PI / 180);
    const x = Math.cos(p1Lat * Math.PI / 180) * Math.sin(p2Lat * Math.PI / 180) -
              Math.sin(p1Lat * Math.PI / 180) * Math.cos(p2Lat * Math.PI / 180) * Math.cos(dLon);
    let brng = Math.atan2(y, x) * 180 / Math.PI;
    const deg = (Math.round(brng) + 360) % 360;
    return `${deg}°`;
  }

  function getSelectedDeparturePort() {
    if (window.ORCA_STATE && window.ORCA_STATE.selectedDeparture) {
      return window.ORCA_STATE.selectedDeparture;
    }
    const select = document.getElementById("station-select");
    const stName = select ? select.value : "Kochi";
    if (window.ORCA_PORT_MAP && window.ORCA_PORT_MAP[stName]) {
      return window.ORCA_PORT_MAP[stName];
    }
    return { name: `${stName} Port`, lat: 9.93, lon: 76.27, isMajor: true };
  }

  function openDepartureModalForSpot(spot) {
    if (!spot) return;
    currentTargetSpot = spot;

    const modal = document.getElementById("orca-departure-modal");
    if (!modal) return;

    const originPort = getSelectedDeparturePort();

    const spotLat = Number(spot.lat ?? spot.latitude ?? 19.5);
    const spotLon = Number(spot.lon ?? spot.longitude ?? 71.8);
    spot.lat = spotLat;
    spot.lon = spotLon;

    const spotName = spot.label || spot.name || `Fishing Zone #${spot.id || '12'}`;
    const depSpotName = document.getElementById("dep-spot-name");
    const depSpotCoords = document.getElementById("dep-spot-coords");
    const depSpotHealth = document.getElementById("dep-spot-health");
    const depSpotSst = document.getElementById("dep-spot-sst");
    const depSpotChl = document.getElementById("dep-spot-chl");
    const depSpotSal = document.getElementById("dep-spot-sal");
    const depSpotSla = document.getElementById("dep-spot-sla");

    if (depSpotName) depSpotName.textContent = spotName;
    if (depSpotCoords) depSpotCoords.textContent = `${spotLat.toFixed(2)}°N, ${spotLon.toFixed(2)}°E`;

    const healthVal = spot.healthScore != null ? Math.round(spot.healthScore) : (spot.mhi != null ? Math.round(spot.mhi) : 85);
    if (depSpotHealth) depSpotHealth.textContent = `Ocean Health: ${healthVal}/100`;
    if (depSpotSst) depSpotSst.textContent = `Water Temp: ${spot.sst != null ? spot.sst.toFixed(1) : '27.5'}°C`;
    const chlVal = spot.chlorophyll != null ? spot.chlorophyll : (spot.chl != null ? spot.chl : 2.10);
    if (depSpotChl) depSpotChl.textContent = `Fish Food: ${Number(chlVal).toFixed(2)} mg/m³`;
    const salVal = spot.salinity != null ? spot.salinity : (spot.sal != null ? spot.sal : 35.4);
    if (depSpotSal) depSpotSal.textContent = `Salt Level: ${Number(salVal).toFixed(1)} PSU`;

    const slaCm = spot.sla_cm != null ? (spot.sla_cm > 0 ? `+${spot.sla_cm}` : `${spot.sla_cm}`) : (spot.sla != null ? ((spot.sla > 0 ? '+' : '') + Math.round(spot.sla * 100)) : '+6');
    if (depSpotSla) depSpotSla.textContent = `Sea Level: Normal (${slaCm} cm)`;

    const depPortTitle = document.getElementById("dep-port-title");
    if (depPortTitle) depPortTitle.textContent = originPort.name || "Selected Port";

    const distKm = calculateHaversineKm(originPort.lat, originPort.lon, spotLat, spotLon);
    const distStr = formatDistance(distKm);
    const travelStr = formatTravelTime(distKm);
    const headingStr = calculateHeading(originPort.lat, originPort.lon, spotLat, spotLon);

    const depGeodesicDist = document.getElementById("dep-geodesic-dist");
    const depGeodesicKm = document.getElementById("dep-geodesic-km");
    const depChannelDist = document.getElementById("dep-channel-dist");
    const depChannelKm = document.getElementById("dep-channel-km");
    const depTransitTime = document.getElementById("dep-transit-time");
    const depBearing = document.getElementById("dep-bearing");

    if (distKm != null) {
      const dNm = (distKm * 0.539957).toFixed(1);
      if (depGeodesicDist) depGeodesicDist.textContent = `${dNm} NM`;
      if (depGeodesicKm) depGeodesicKm.textContent = `(${distStr})`;
      if (depChannelDist) depChannelDist.textContent = `${(distKm * 1.12 * 0.539957).toFixed(1)} NM`;
      if (depChannelKm) depChannelKm.textContent = `(${formatDistance(distKm * 1.12)})`;
    } else {
      if (depGeodesicDist) depGeodesicDist.textContent = "-- NM";
      if (depGeodesicKm) depGeodesicKm.textContent = `(${distStr})`;
      if (depChannelDist) depChannelDist.textContent = "-- NM";
      if (depChannelKm) depChannelKm.textContent = `(${distStr})`;
    }

    if (depTransitTime) depTransitTime.textContent = travelStr;
    if (depBearing) depBearing.textContent = headingStr;

    modal.style.display = "flex";
  }

  function hideDepartureModal() {
    const modal = document.getElementById("orca-departure-modal");
    if (modal) modal.style.display = "none";
  }

  function executeTakeMeThere(spot) {
    const target = spot || currentTargetSpot;
    if (!target) return;
    hideDepartureModal();

    const originPort = getSelectedDeparturePort();
    const spotLat = Number(target.lat ?? target.latitude);
    const spotLon = Number(target.lon ?? target.longitude);
    const spotName = target.label || target.name || `Fishing Zone #${target.id || '12'}`;

    if (window.ORCA_STATE) {
      window.ORCA_STATE.selectedFishingSpot = target;
      if (window.ORCA_SET_DEPARTURE && originPort) {
        window.ORCA_SET_DEPARTURE(originPort);
      }
    }

    const distKm = calculateHaversineKm(originPort.lat, originPort.lon, spotLat, spotLon);
    const routeKm = distKm != null ? distKm * 1.12 : null;
    const distStr = formatDistance(distKm);
    const travelStr = formatTravelTime(distKm);
    const headingStr = calculateHeading(originPort.lat, originPort.lon, spotLat, spotLon);

    activeRouteData = {
      originPort,
      spot: target,
      distKm,
      routeKm,
      distStr,
      travelStr,
      headingStr
    };

    console.log(`[ORCA ROUTE] Route generated: ${originPort.name} -> ${spotName}: dist=${distStr}, travel=${travelStr}, heading=${headingStr}`);

    updateActiveRouteUI(activeRouteData);

    if (window.ORCA_GLOBE_CONTROLLER && typeof window.ORCA_GLOBE_CONTROLLER.showRoute === "function") {
      window.ORCA_GLOBE_CONTROLLER.showRoute(originPort, target, distKm, routeKm);
    }

    if (window.ORCA_GLOBE_CONTROLLER && typeof window.ORCA_GLOBE_CONTROLLER.highlightFishingSpot === "function") {
      window.ORCA_GLOBE_CONTROLLER.highlightFishingSpot(target.id, spotLat, spotLon);
    }

    if (window.ORCA_GLOBE_CONTROLLER && typeof window.ORCA_GLOBE_CONTROLLER.flyToLocation === "function") {
      window.ORCA_GLOBE_CONTROLLER.flyToLocation(spotLat, spotLon, 280000, 2.0);
    }

    if (typeof window.drawLeafletRoute === "function") {
      window.drawLeafletRoute(target);
    }
  }

  function updateActiveRouteUI(routeData) {
    const card = document.getElementById("orca-active-route-card");
    if (!card) return;

    if (!routeData) {
      card.style.display = "none";
      return;
    }

    const elDep = document.getElementById("route-card-departure");
    const elDest = document.getElementById("route-card-destination");
    const elDist = document.getElementById("route-card-distance");
    const elTravel = document.getElementById("route-card-travel-time");
    const elHeading = document.getElementById("route-card-heading");

    const spotName = routeData.spot.label || routeData.spot.name || `Fishing Zone #${routeData.spot.id || '12'}`;

    if (elDep) elDep.textContent = routeData.originPort.name || "Departure Port";
    if (elDest) elDest.textContent = spotName;
    if (elDist) elDist.textContent = routeData.distStr;
    if (elTravel) elTravel.textContent = routeData.travelStr;
    if (elHeading) elHeading.textContent = routeData.headingStr;

    card.style.display = "block";
  }

  function clearActiveRoute() {
    activeRouteData = null;
    const card = document.getElementById("orca-active-route-card");
    if (card) card.style.display = "none";

    if (window.ORCA_GLOBE_CONTROLLER && typeof window.ORCA_GLOBE_CONTROLLER.clearRoute === "function") {
      window.ORCA_GLOBE_CONTROLLER.clearRoute();
    }
    if (window.ORCA_STATE) {
      window.ORCA_STATE.selectedFishingSpot = null;
    }
  }

  function recalculateActiveRoute() {
    if (activeRouteData && activeRouteData.spot) {
      executeTakeMeThere(activeRouteData.spot);
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const closeBtn = document.getElementById("orca-departure-modal-close");
    const cancelBtn = document.getElementById("orca-departure-cancel-btn");
    const confirmBtn = document.getElementById("orca-departure-confirm-btn");
    const clearRouteBtn = document.getElementById("btn-clear-active-route");

    if (closeBtn) closeBtn.addEventListener("click", hideDepartureModal);
    if (cancelBtn) cancelBtn.addEventListener("click", hideDepartureModal);
    if (confirmBtn) {
      confirmBtn.addEventListener("click", () => {
        executeTakeMeThere(currentTargetSpot);
      });
    }
    if (clearRouteBtn) {
      clearRouteBtn.addEventListener("click", clearActiveRoute);
    }
  });

  window.ORCA_NAVIGATION = {
    openDepartureModalForSpot,
    executeTakeMeThere,
    recalculateActiveRoute,
    clearActiveRoute,
    calculateHaversineKm,
    formatDistance,
    formatTravelTime,
    calculateHeading
  };

  window.ORCA_AGENT = {
    openDepartureModalForSpot: openDepartureModalForSpot
  };
})();
