/* ORCA dashboard client.  The API is the source of truth; no synthetic telemetry. */
(() => {
  "use strict";
  // Deployments can set window.ORCA_API_BASE before this script; local frontend
  // servers use the ORCA FastAPI default port automatically.
  const apiRoots = window.ORCA_API_BASE ? [window.ORCA_API_BASE] :
    ((location.hostname === "localhost" && /^(3000|3001)$/.test(location.port)) ? ["http://localhost:8000"] : [""]);
  const state = { station: "Kochi", data: null, view: "standard", globe: null };
  const byId = (id) => document.getElementById(id);
  const niceTime = (iso) => iso ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" }).format(new Date(iso)) + " UTC" : "Forecast time unavailable";

  function setText(id, text) { byId(id).textContent = text; }
  function value(metric) { return metric?.available ? metric.value : "—"; }

  async function loadTelemetry() {
    setText("updated", "SYNCING");
    try {
      let data, lastError;
      for (const apiRoot of apiRoots) {
        try {
          const response = await fetch(`${apiRoot}/dashboard/telemetry?station=${encodeURIComponent(state.station)}`, { headers: { Accept: "application/json" } });
          const body = await response.json();
          if (!response.ok) throw new Error(body.detail || `Telemetry API returned ${response.status}.`);
          data = body;
          break;
        } catch (error) { lastError = error; }
      }
      if (!data) throw lastError || new Error("No ORCA telemetry API is available.");
      state.data = data;
      render();
    } catch (error) {
      setText("updated", "OFFLINE");
      setText("safety-message", "Forecast telemetry unavailable — check the ORCA service.");
      setText("data-note", error.message);
      drawGlobe(); // Keep the operational reference map usable during reconnects.
      console.error("ORCA telemetry:", error);
    }
  }

  function renderStations() {
    const rail = byId("station-rail");
    rail.replaceChildren(...state.data.stations.map((station) => {
      const button = document.createElement("button");
      button.textContent = station.name;
      button.className = station.name === state.station ? "active" : "";
      button.onclick = () => { state.station = station.name; loadTelemetry(); };
      return button;
    }));
  }

  function renderMetrics() {
    const host = byId("metrics"), template = byId("metric-template");
    host.replaceChildren(...Object.values(state.data.metrics).map((metric) => {
      const card = template.content.firstElementChild.cloneNode(true);
      card.querySelector("p").textContent = metric.label;
      card.querySelector("strong").textContent = value(metric);
      card.querySelector("span").textContent = metric.available ? metric.unit : "";
      card.querySelector("small").textContent = metric.available ? "Forecast feed" : "Not supplied by current feed";
      card.dataset.status = metric.available ? "available" : "unavailable";
      return card;
    }));
  }

  function render() {
    const d = state.data, s = d.station, health = d.health;
    renderStations(); renderMetrics();
    setText("station-subhead", `${s.name} (${s.region})`);
    setText("updated", `UPDATED ${niceTime(d.updated_at)}`);
    setText("safety-message", d.safety.message);
    setText("safety-state", d.safety.status.toUpperCase());
    setText("pfz-message", d.pfzs.length ? `${d.pfzs.length} high-chlorophyll / thermal-front candidates identified` : "No PFZ candidates meet the current model criteria");
    setText("pfz-state", d.pfzs.length ? "CANDIDATES" : "CLEAR");
    setText("health-index", health.index.toFixed(health.index % 1 ? 1 : 0));
    setText("health-state", `${health.state} · ${health.source}`);
    setText("station-coords", `${Number(s.lat).toFixed(2)}°N, ${Number(s.lon).toFixed(2)}°E`);
    setText("forecast-time", niceTime(d.forecast_time));
    setText("alert-count", `${health.local_alerts} / ${health.sample_cells}`);
    byId("route-list").replaceChildren(...(d.routes.length ? d.routes.map((route, i) => {
      const chip = document.createElement("span"); chip.className = "route-chip";
      chip.textContent = `PFZ ${i + 1} → ${route.to.lat.toFixed(2)}°N, ${route.to.lon.toFixed(2)}°E`;
      return chip;
    }) : [Object.assign(document.createElement("span"), { textContent: "No thermal-front PFZ planning lines" })]));
    byId("species").replaceChildren(...d.catch_species.map((name) => Object.assign(document.createElement("b"), { textContent: name })));
    setText("data-note", d.disclaimer);
    drawGlobe();
  }

  function xyz(lat, lon, radius = 1) {
    const phi = (90 - lat) * Math.PI / 180, theta = (lon + 180) * Math.PI / 180;
    return new THREE.Vector3(-radius * Math.sin(phi) * Math.cos(theta), radius * Math.cos(phi), radius * Math.sin(phi) * Math.sin(theta));
  }
  function line(points, color, opacity = 1) {
    const material = new THREE.LineBasicMaterial({ color, transparent: opacity < 1, opacity });
    return new THREE.Line(new THREE.BufferGeometry().setFromPoints(points), material);
  }
  function ringAtLatitude(lat, color) {
    const points = []; for (let lon = -180; lon <= 180; lon += 3) points.push(xyz(lat, lon, 1.008)); return line(points, color, .25);
  }
  function meridian(lon, color) {
    const points = []; for (let lat = -90; lat <= 90; lat += 3) points.push(xyz(lat, lon, 1.008)); return line(points, color, .25);
  }

  function initGlobe() {
    const container = byId("globe"), scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(34, container.clientWidth / container.clientHeight, .1, 100);
    camera.position.set(0, .15, 3.1);
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2)); renderer.setSize(container.clientWidth, container.clientHeight);
    container.replaceChildren(renderer.domElement);
    const group = new THREE.Group(); group.rotation.set(-.05, -1.42, 0); scene.add(group);
    scene.add(new THREE.AmbientLight(0x8fdde0, .75)); const key = new THREE.DirectionalLight(0xc7fff2, 1.2); key.position.set(3, 2, 4); scene.add(key);
    let dragging = false, lastX = 0, lastY = 0;
    renderer.domElement.addEventListener("pointerdown", e => { dragging = true; lastX = e.clientX; lastY = e.clientY; renderer.domElement.setPointerCapture(e.pointerId); });
    renderer.domElement.addEventListener("pointermove", e => { if (!dragging) return; group.rotation.y += (e.clientX - lastX) * .007; group.rotation.x += (e.clientY - lastY) * .007; lastX=e.clientX;lastY=e.clientY; });
    renderer.domElement.addEventListener("pointerup", () => dragging = false);
    renderer.domElement.addEventListener("wheel", e => { camera.position.z = THREE.MathUtils.clamp(camera.position.z + e.deltaY * .002, 1.7, 5); }, { passive: true });
    const resize = () => { camera.aspect = container.clientWidth / container.clientHeight; camera.updateProjectionMatrix(); renderer.setSize(container.clientWidth, container.clientHeight); };
    new ResizeObserver(resize).observe(container);
    state.globe = { scene, camera, renderer, group, dragging: () => dragging };
    (function animate() { requestAnimationFrame(animate); if (!dragging) group.rotation.y += .0007; renderer.render(scene, camera); })();
  }

  function dot(lat, lon, color, size = .025) {
    const mesh = new THREE.Mesh(new THREE.SphereGeometry(size, 12, 12), new THREE.MeshBasicMaterial({ color }));
    mesh.position.copy(xyz(lat, lon, 1.03)); return mesh;
  }
  function stationLabel(name, lat, lon, selected) {
    const canvas = document.createElement("canvas"), context = canvas.getContext("2d");
    canvas.width = 240; canvas.height = 38;
    context.font = "600 16px ui-monospace, monospace";
    context.fillStyle = selected ? "#dfffb6" : "#d4ffff";
    context.fillText(name, 4, 22);
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(canvas), transparent: true, depthTest: false }));
    sprite.position.copy(xyz(lat, lon, 1.07)); sprite.scale.set(.36, .057, 1);
    return sprite;
  }
  function drawGlobe() {
    if (!window.THREE) return;
    if (!state.globe) initGlobe();
    const { group } = state.globe; group.clear();
    const view = state.view;
    const d = state.data || {
      station: { name: "Kochi", lat: 9.93, lon: 76.27 },
      stations: [{ name: "Kochi", lat: 9.93, lon: 76.27 }], pfzs: [], routes: [],
    };
    const surfaceColors = { standard: 0x0b4e68, weather: 0x213e72, ocean: 0x0c5961 };
    const globe = new THREE.Mesh(new THREE.SphereGeometry(1, 72, 72), new THREE.MeshPhongMaterial({ color: surfaceColors[view], emissive: 0x06151f, specular: 0x74e8e6, shininess: 12, transparent: true, opacity: .94 }));
    group.add(globe);
    // Detailed ten-degree reference grid makes all operational coordinates traceable.
    for (let lat = -80; lat <= 80; lat += 10) group.add(ringAtLatitude(lat, 0x97e5dc));
    for (let lon = -180; lon < 180; lon += 10) group.add(meridian(lon, 0x97e5dc));
    d.stations.forEach((s) => {
      const selected = s.name === d.station.name;
      group.add(dot(s.lat, s.lon, selected ? 0xc8fc77 : 0x77dfef, selected ? .035 : .018));
      if (view === "standard") group.add(stationLabel(s.name, s.lat, s.lon, selected));
    });
    if (view === "weather") {
      d.stations.forEach((s, i) => { const halo = new THREE.Mesh(new THREE.SphereGeometry(.055 + (i % 3) * .012, 16, 16), new THREE.MeshBasicMaterial({ color: i % 2 ? 0x73b8ff : 0xffbd5d, transparent:true, opacity:.5 })); halo.position.copy(xyz(s.lat,s.lon,1.018)); group.add(halo); });
    }
    if (view === "ocean") {
      d.pfzs.forEach(p => group.add(dot(p.lat, p.lon, 0xc8fc77, .04)));
      d.routes.forEach(route => group.add(line([xyz(d.station.lat, d.station.lon, 1.035), xyz(route.to.lat, route.to.lon, 1.035)], 0xffbd5d)));
    }
    setText("map-note", !state.data ? "Reference globe available · Telemetry API reconnecting…" : view === "ocean" ? "Lime = PFZ candidate · Orange = planning line · Not safe-navigation clearance" : view === "weather" ? "Atmospheric layer displays forecast feed stations; unavailable variables remain blank" : "Named coastal stations · 10° latitude / longitude reference grid · Drag to rotate");
  }

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-view]").forEach(button => button.addEventListener("click", () => { state.view = button.dataset.view; document.querySelectorAll("[data-view]").forEach(b => b.classList.toggle("selected", b === button)); drawGlobe(); }));
    drawGlobe();
    loadTelemetry();
  });
})();
