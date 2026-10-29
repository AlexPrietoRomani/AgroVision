/**
 * Script cliente de AgroVisión: navegación por pestañas, estado efímero,
 * mapa Leaflet, gráficos Chart.js, modales y llamadas al gateway.
 */
// ===== Estado EFÍMERO (solo memoria; se borra al refrescar) =====
let creds = {};
let parcels = [];
let drawnGeojson = null;
let map = null, drawnItems = null, parcelsLayer = null;
let chartResumen = null, chartSatelite = null, chartWeather = null, chartAnalysis = null;
const sessionId = "sess-" + Math.random().toString(36).slice(2);
let backendOk = false;
let appEnv = "development";

const VALID_INDICES = ["ndvi", "evi", "savi", "ndwi", "ndre"];
const INDEX_LABELS = { ndvi: "NDVI", evi: "EVI", savi: "SAVI", ndwi: "NDWI", ndre: "NDRE" };
const RECOMMENDED_INDICES_BY_CROP = {
  "Arándanos": ["ndvi", "ndwi", "ndre"],
  "Uva": ["ndvi", "savi", "ndwi"],
  "Uvas": ["ndvi", "savi", "ndwi"],
  "Paltos": ["ndvi", "evi", "ndre"],
  "Cítricos": ["ndvi", "evi", "ndre"],
  "Espárragos": ["ndvi", "savi"],
  "Otros": ["ndvi"],
};
let activeParcelIndices = [];

// Perfiles y Modos de Sesión (Fase 15)
let profileId = null;
let currentProfile = null;
let fingerprint = null;
let isSharedMode = false;

async function sha256(message) {
  const msgBuffer = new TextEncoder().encode(message);
  const hashBuffer = await crypto.subtle.digest("SHA-256", msgBuffer);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
}

const $ = (id) => document.getElementById(id);

function authHeaders() {
  const h = {};
  if (creds.groq) h["X-User-Groq-Key"] = creds.groq;
  if (creds.copId) h["X-User-Copernicus-Id"] = creds.copId;
  if (creds.copSecret) h["X-User-Copernicus-Secret"] = creds.copSecret;
  if (creds.sbUrl) h["X-User-Supabase-Url"] = creds.sbUrl;
  if (creds.sbKey) h["X-User-Supabase-Key"] = creds.sbKey;
  if (creds.dbUrl) h["X-User-Database-Url"] = creds.dbUrl;
  return h;
}

function notify(title, body) {
  $("notif-title").innerText = title; $("notif-body").innerText = body || "";
  const n = $("notif"); n.classList.remove("translate-x-[150%]");
  setTimeout(() => n.classList.add("translate-x-[150%]"), 3500);
}

function updateStatus() {
  const el = $("db-status-text");
  const dot = $("db-status").querySelector("span.relative");
  if (!backendOk) {
    el.innerText = "Backend no disponible";
    el.className = "text-red-500";
    dot.className = "relative inline-flex rounded-full h-2 w-2 bg-red-500";
    return;
  }
  fetch("./api/credentials/status", { headers: authHeaders() })
    .then((r) => r.ok ? r.json() : null)
    .then((s) => {
      if (!s) {
        el.innerText = "Backend conectado · Status desconocido";
        el.className = "text-amber-400";
        dot.className = "relative inline-flex rounded-full h-2 w-2 bg-amber-500";
        return;
      }
      const missing = [];
      if (!s.groq) missing.push("Groq");
      if (!s.copernicus) missing.push("Copernicus");
      if (!s.supabase) missing.push("Supabase");
      if (missing.length === 0) {
        el.innerText = "Backend conectado · Todo OK";
        el.className = "text-emerald-400";
        dot.className = "relative inline-flex rounded-full h-2 w-2 bg-emerald-500";
      } else {
        el.innerText = `Backend conectado · Faltan: ${missing.join(", ")}`;
        el.className = "text-amber-400";
        dot.className = "relative inline-flex rounded-full h-2 w-2 bg-amber-500";
      }
    })
    .catch(() => {
      el.innerText = "Backend conectado · Error al verificar credenciales";
      el.className = "text-amber-400";
      dot.className = "relative inline-flex rounded-full h-2 w-2 bg-amber-500";
    });
}

// ===== Telemetría (Fase 9) =====
function track(action, meta = {}) {
  try {
    fetch("./api/events", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, meta, session_id: sessionId, ts: new Date().toISOString() }),
      keepalive: true,
    }).catch(() => {});
  } catch { /* la telemetría nunca debe propagar errores */ }
}

window.addEventListener("error", (e) => track("js_error", { message: String(e.message || e), where: "window" }));
window.addEventListener("unhandledrejection", (e) => track("js_error", { message: String(e.reason || ""), where: "promise" }));

async function api(path, opts = {}) {
  try {
    const res = await fetch("./api" + path, {
      ...opts,
      headers: { ...(opts.body ? { "Content-Type": "application/json" } : {}), ...authHeaders(), ...(opts.headers || {}) },
    });
    if (!res.ok) track("api_error", { where: path, status: res.status, method: opts.method || "GET" });
    return res;
  } catch (e) {
    track("api_error", { where: path, status: "network", method: opts.method || "GET" });
    throw e;
  }
}

function getCheckedIndices(selector) {
  return Array.from(document.querySelectorAll(`${selector}:checked`)).map((checkbox) => checkbox.value);
}

function setCheckedIndices(selector, indices) {
  const selected = new Set(indices || []);
  document.querySelectorAll(selector).forEach((checkbox) => {
    checkbox.checked = selected.has(checkbox.value);
  });
}

function normalizeIndices(indices) {
  const valid = Array.isArray(indices) ? indices.filter((index) => VALID_INDICES.includes(index)) : [];
  return valid.length ? [...new Set(valid)] : ["ndvi"];
}

function formatIndices(indices) {
  return (indices || []).map((index) => INDEX_LABELS[index] || index.toUpperCase()).join(", ");
}

function getParcelIndices(fieldId) {
  const parcel = parcels.find((item) => item.id === fieldId);
  return normalizeIndices(parcel?.selected_indices);
}

function setParcelIndices(fieldId, indices) {
  const normalized = normalizeIndices(indices);
  const parcel = parcels.find((item) => item.id === fieldId);
  if (parcel) parcel.selected_indices = normalized;
  activeParcelIndices = normalized;
  return normalized;
}

function renderActiveIndexBadges(indices) {
  const container = $("parcel-active-indices");
  if (!container) return;
  const selected = new Set(indices || []);
  container.innerHTML = VALID_INDICES.map((index) => {
    const isActive = selected.has(index);
    const badgeClass = isActive
      ? "bg-emerald-100 text-emerald-800 border-emerald-200"
      : "bg-stone-100 text-stone-400 border-stone-200";
    const icon = isActive ? "fa-circle-check" : "fa-circle";
    return `<span class="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-1 rounded-full border ${badgeClass}" title="${isActive ? "Variable activa" : "Variable no activa"}"><i class="fa-solid ${icon} text-[9px]"></i>${INDEX_LABELS[index]}</span>`;
  }).join("");
}

function updateIndexSelectOptions(indices) {
  const selected = new Set(indices || []);
  document.querySelectorAll("#select-index option").forEach((option) => {
    const baseLabel = option.dataset.indexLabel || option.textContent.replace(/ · (activa|agregar)$/, "");
    option.textContent = `${baseLabel} · ${selected.has(option.value) ? "activa" : "agregar"}`;
  });
}

function syncSatelliteIndexControls(fieldId, field = null) {
  const indices = fieldId ? normalizeIndices(field?.selected_indices ?? getParcelIndices(fieldId)) : [];
  activeParcelIndices = indices;
  setCheckedIndices(".attr-index-checkbox", indices);
  setCheckedIndices(".reprocess-index-checkbox", indices);
  renderActiveIndexBadges(indices);
  updateIndexSelectOptions(indices);
}

function applyCreatorIndices(indices) {
  setCheckedIndices(".creator-index-checkbox", normalizeIndices(indices));
  $("creator-indices-error")?.classList.add("hidden");
}

// ===== Navegación =====
const TITLES = {
  "tab-resumen": ["Resumen de Campo", "Visión analítica unificada de parcelas."],
  "tab-satelite": ["Teledetección (GIS)", "NDVI 5 años + clima + heatmap (solo lectura)."],
  "tab-weather": ["Meteorología y Clima", "Historial agroclimático mensual de Open-Meteo."],
  "tab-analysis": ["Análisis Cruzado", "Correlación temporal entre índices y variables climáticas."],
  "tab-vision": ["Detección por Dron", "Conteo de plantas — EN DESARROLLO."],
  "tab-data": ["Explorador de Datos", "Consulta tus datos directamente (Fase 11)."],
  "tab-config": ["Credenciales & APIs", "Llaves efímeras (solo en esta sesión)."],
  "tab-settings": ["Ajustes de Perfil", "Gestión del modo de sesión y preferencias de usuario."],
};
function showSection2Chat() {
  const form = $("section2-form");
  const chat = $("section2-chat");
  const icon = $("branding-icon");
  const btn = $("btn-branding-toggle");
  if (form && chat) {
    form.classList.add("hidden");
    chat.classList.remove("hidden");
  }
  if (icon) icon.className = "fa-solid fa-sliders text-base";
  if (btn) btn.title = "Mostrar Ajustes de Parcela";
  loadChatHistory();
}

function switchTab(id) {
  document.querySelectorAll(".tab-content").forEach((s) => s.classList.remove("active"));
  document.querySelectorAll(".nav-btn").forEach((b) => b.classList.remove("nav-btn-active"));
  const sec = $(id); if (!sec) return;
  sec.classList.add("active");

  // Mantener seleccionada la opción correcta del menú lateral
  document.querySelector(`.nav-btn[data-tab="${id}"]`)?.classList.add("nav-btn-active");

  if (location.hash !== "#" + id) history.replaceState(null, "", "#" + id);
  track("nav", { tab: id });

  if (id === "tab-resumen") {
    setTimeout(initMap, 50);
    loadResumen();
    showSection2Chat();
  }
  if (id === "tab-satelite") {
    loadTeledeteccion();
  }
  if (id === "tab-weather") {
    loadWeather();
  }
  if (id === "tab-analysis") {
    loadAnalysis();
  }
  if (id === "tab-data") loadDataExplorer();
  if (id === "tab-chat") loadChatHistory();
}

document.querySelectorAll(".nav-btn").forEach((b) =>
  b.addEventListener("click", () => switchTab(b.dataset.tab))
);

// Botón "Volver al Mapa" para regresar al visor principal del mapa
document.querySelectorAll(".btn-volver-mapa").forEach((btn) => {
  btn.addEventListener("click", () => switchTab("tab-resumen"));
});

// ===== Sidebar colapsable manual (Sección 1) =====
$("btn-sidebar-toggle").addEventListener("click", () => {
  const isExpanded = $("sidebar").classList.toggle("expanded");
  $("toggle-icon").className = isExpanded ? "fa-solid fa-angles-left" : "fa-solid fa-bars";
  track("sidebar_toggle", { expanded: isExpanded });
  if (map) setTimeout(() => map.invalidateSize(), 300);
});

$("btn-footer").addEventListener("click", () => {
  $("footer-body").classList.toggle("hidden");
  $("footer-chevron").classList.toggle("fa-chevron-up");
  $("footer-chevron").classList.toggle("fa-chevron-down");
});

// ===== Alternador de Chat y Formulario en Sección 2 =====
$("btn-branding-toggle").addEventListener("click", () => {
  const isFormVisible = !$("section2-form").classList.contains("hidden");
  if (isFormVisible) {
    $("section2-form").classList.add("hidden");
    $("section2-chat").classList.remove("hidden");
    $("branding-icon").className = "fa-solid fa-sliders text-base";
    $("btn-branding-toggle").title = "Mostrar Ajustes de Parcela";
    loadChatHistory();
    track("chat_toggle", { state: "open" });
  } else {
    $("section2-form").classList.remove("hidden");
    $("section2-chat").classList.add("hidden");
    $("branding-icon").className = "fa-solid fa-robot text-base";
    $("btn-branding-toggle").title = "Mostrar Chat con Asistente";
    track("chat_toggle", { state: "closed" });
  }
});

// ===== Gestión de Atributos de Ajustes de Parcela (Sección 2) =====
async function loadFieldAttributes(fid) {
  if (!fid) {
    clearFieldAttributes();
    return;
  }
  try {
    const res = await api(`/fields/${fid}`);
    if (res.ok) {
      const field = await res.json();
      $("attr-crop-variety").value = field.crop_variety || "";
      $("attr-field-type").value = field.field_type || "";
      $("attr-soil-type").value = field.soil_type || "";
      $("attr-irrigation-system").value = field.irrigation_system || "";
      $("attr-pests-diseases").value = field.pests_diseases || "";
      $("attr-plantation-date").value = field.plantation_date || "";
      $("attr-num-plants").value = field.num_plants || "";
      $("attr-historical-yield").value = field.historical_yield || "";
      $("attr-target-market").value = field.target_market || "";
      $("attr-document-metadata").value = field.document_metadata || "";

      const fieldIndices = Array.isArray(field.selected_indices) ? field.selected_indices : getParcelIndices(fid);
      setParcelIndices(fid, fieldIndices);
      syncSatelliteIndexControls(fid);

      $("active-parcel-name-display").innerText = field.name;
    }
  } catch (e) {
    console.error("Error al cargar atributos de la parcela", e);
  }
}

function clearFieldAttributes() {
  $("attr-crop-variety").value = "";
  $("attr-field-type").value = "";
  $("attr-soil-type").value = "";
  $("attr-irrigation-system").value = "";
  $("attr-pests-diseases").value = "";
  $("attr-plantation-date").value = "";
  $("attr-num-plants").value = "";
  $("attr-historical-yield").value = "";
  $("attr-target-market").value = "";
  $("attr-document-metadata").value = "";
  syncSatelliteIndexControls(null);
  $("active-parcel-name-display").innerText = "—";
}

async function saveFieldAttributes(fid, isAutosave) {
  if (!fid) return;
  const previousIndices = getParcelIndices(fid);
  const selectedIndices = getCheckedIndices(".attr-index-checkbox");
  const nextIndices = selectedIndices.length ? normalizeIndices(selectedIndices) : ["ndvi"];
  const body = {
    crop_variety: $("attr-crop-variety").value.trim() || null,
    field_type: $("attr-field-type").value.trim() || null,
    soil_type: $("attr-soil-type").value.trim() || null,
    irrigation_system: $("attr-irrigation-system").value.trim() || null,
    pests_diseases: $("attr-pests-diseases").value.trim() || null,
    plantation_date: $("attr-plantation-date").value || null,
    num_plants: $("attr-num-plants").value ? parseInt($("attr-num-plants").value, 10) : null,
    historical_yield: $("attr-historical-yield").value.trim() || null,
    target_market: $("attr-target-market").value.trim() || null,
    document_metadata: $("attr-document-metadata").value.trim() || null,
    selected_indices: nextIndices
  };

  try {
    const res = await api(`/fields/${fid}`, {
      method: "PATCH",
      body: JSON.stringify(body)
    });
    if (res.ok) {
      const addedIndices = nextIndices.filter((index) => !previousIndices.includes(index));
      setParcelIndices(fid, nextIndices);
      syncSatelliteIndexControls(fid);
      if (!isAutosave) {
        if (addedIndices.length) {
          notify("Ajustes guardados", `Se agregaron ${formatIndices(addedIndices)}. El cálculo satelital continúa en segundo plano.`);
        } else {
          notify("Ajustes guardados", "Los atributos de la parcela se han guardado.");
        }
      } else if (addedIndices.length) {
        notify("Nuevas variables satelitales", `Calculando ${formatIndices(addedIndices)} en segundo plano.`);
      }
      track("field_attributes_saved", {
        field_id: fid,
        autosave: isAutosave,
        selected_indices: nextIndices,
        added_indices: addedIndices
      });
    } else {
      const e = await res.json().catch(() => ({}));
      if (!isAutosave) {
        notify("Error al guardar", e.detail || "Error desconocido");
      }
    }
  } catch (e) {
    if (!isAutosave) {
      notify("Error de red", String(e));
    }
  }
}

let autosaveTimeout = null;
function triggerAutosave() {
  const fid = $("select-parcela").value;
  if (!fid) return;
  if (autosaveTimeout) clearTimeout(autosaveTimeout);
  autosaveTimeout = setTimeout(() => {
    saveFieldAttributes(fid, true);
  }, 1200); // 1.2s debounced auto-save
}

// Conectar eventos de autosave (input change o blur)
[
  "attr-crop-variety", "attr-field-type", "attr-soil-type", "attr-irrigation-system",
  "attr-pests-diseases", "attr-plantation-date", "attr-num-plants", "attr-historical-yield",
  "attr-target-market", "attr-document-metadata"
].forEach(id => {
  $(id).addEventListener("input", triggerAutosave);
  $(id).addEventListener("blur", () => {
    const fid = $("select-parcela").value;
    if (fid) saveFieldAttributes(fid, false); // guardar inmediatamente al perder el foco
  });
});

document.querySelectorAll(".attr-index-checkbox").forEach((checkbox) => {
  checkbox.addEventListener("change", triggerAutosave);
});

$("btn-save-attributes").addEventListener("click", (e) => {
  e.preventDefault();
  const fid = $("select-parcela").value;
  if (!fid) return notify("Error", "Selecciona una parcela primero.");
  saveFieldAttributes(fid, false);
});

// ===== Gestión de Parcelas y Mapa (Sección 3) =====
function renderFloatingParcels() {
  const list = $("floating-parcelas-list");
  if (!list) return;
  const activeId = $("select-parcela").value;
  list.innerHTML = parcels.length
    ? parcels.map((p) => {
        const isActive = p.id === activeId;
        const circleIcon = isActive 
          ? '<i class="fa-solid fa-circle-dot text-emerald-500"></i>' 
          : '<i class="fa-regular fa-circle text-stone-500"></i>';
        const bgClass = isActive 
          ? 'bg-stone-900 border-emerald-800/40' 
          : 'hover:bg-stone-900/50 border-transparent';
        return `
          <div data-pid="${p.id}" class="floating-parcel-item flex items-center justify-between p-2 rounded-lg border ${bgClass} cursor-pointer transition-all">
            <div class="flex items-center gap-2 select-item-click">
              ${circleIcon}
              <span class="text-xs font-semibold text-stone-200">${p.name}</span>
            </div>
            <i class="fa-solid fa-gear text-stone-500 hover:text-stone-300 cursor-pointer btn-gear-click" title="Ajustes de Parcela"></i>
          </div>
        `;
      }).join("")
    : '<div class="text-xs text-stone-500 py-2">Sin parcelas aún.</div>';

  // Actualizar el botón principal y el estado en el widget
  const activeParcel = parcels.find(p => p.id === activeId);
  if (activeParcel) {
    $("current-farm-name").innerText = activeParcel.name;
    if ($("floating-parcel-name")) $("floating-parcel-name").innerText = activeParcel.name;
    if ($("floating-parcel-area")) $("floating-parcel-area").innerText = `${activeParcel.area_ha != null ? activeParcel.area_ha.toFixed(1) : "—"} ha`;
  } else {
    $("current-farm-name").innerText = "Seleccionar Parcela";
    if ($("floating-parcel-name")) $("floating-parcel-name").innerText = "Ninguna seleccionada";
    if ($("floating-parcel-area")) $("floating-parcel-area").innerText = "— ha";
  }
}

function selectParcel(id) {
  const sel = $("select-parcela");
  if (sel) {
    sel.value = id;
    sel.dispatchEvent(new Event("change"));
  }
}

async function refreshParcels() {
  const previousIndices = new Map(parcels.map((parcel) => [parcel.id, parcel.selected_indices]));
  try {
    const r = await api("/fields");
    parcels = r.ok ? await r.json() : [];
  } catch { parcels = []; }
  parcels = parcels.map((parcel) => {
    const backendIndices = Array.isArray(parcel.selected_indices) ? parcel.selected_indices : null;
    const fallbackIndices = previousIndices.get(parcel.id);
    const indices = backendIndices?.length ? backendIndices : fallbackIndices;
    return { ...parcel, selected_indices: normalizeIndices(indices) };
  });
  const sel = $("select-parcela");
  const previousActiveId = sel.value;
  sel.innerHTML = parcels.length
    ? parcels.map((p) => `<option value="${p.id}">${p.name}</option>`).join("")
    : '<option value="">(sin parcelas)</option>';
  if (previousActiveId && sel.querySelector(`option[value="${previousActiveId}"]`)) {
    sel.value = previousActiveId;
  }

  if ($("parcelas-list")) {
    $("parcelas-list").innerHTML = parcels.length
      ? parcels.map((p) => `<li data-pid="${p.id}" title="Ir a la parcela" class="flex items-center justify-between bg-stone-50 border border-stone-200 rounded px-2.5 py-1.5 cursor-pointer hover:bg-stone-100"><span class="font-semibold text-stone-700 text-[11px]"><i class="fa-solid fa-location-dot text-emerald-600 mr-1"></i>${p.name}</span><i class="fa-solid fa-crosshairs text-stone-400"></i></li>`).join("")
      : '<li class="text-stone-500">Sin parcelas aún.</li>';
  }

  renderFloatingParcels();
  renderParcelsOnMap();
}

// Recarga canónica de parcelas (Fase 10: delega en refreshParcels).
const loadParcels = refreshParcels;

function initMap() {
  if (map) { map.invalidateSize(); return; }
  const osm = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { attribution: "© OpenStreetMap" });
  const sat = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", { attribution: "© Esri World Imagery", maxZoom: 19 });
  const topo = L.tileLayer("https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png", { attribution: "© OpenTopoMap", maxZoom: 17 });
  map = L.map("map", { center: [-11.37, -77.37], zoom: 11, layers: [sat] }); // Lomas de Lachay
  L.control.layers({ "Satélite": sat, "Normal": osm, "Relieve": topo }).addTo(map);
  drawnItems = new L.FeatureGroup().addTo(map);
  parcelsLayer = L.geoJSON(null, {
    style: { color: "#15803d", weight: 2, fillColor: "#15803d", fillOpacity: 0.15 },
    onEachFeature: (f, layer) => layer.bindPopup(f.properties.name),
  }).addTo(map);
  renderParcelsOnMap();
  const drawControl = new L.Control.Draw({
    draw: { polygon: true, marker: false, polyline: false, circle: false, rectangle: false, circlemarker: false },
    edit: { featureGroup: drawnItems, edit: false, remove: true },
  });
  map.addControl(drawControl);
  map.on(L.Draw.Event.CREATED, (e) => {
    drawnItems.clearLayers();
    drawnItems.addLayer(e.layer);
    drawnGeojson = e.layer.toGeoJSON().geometry;

    let areaHa = 1.25;
    try {
      const latlngs = e.layer.getLatLngs()[0];
      const areaM2 = L.GeometryUtil.geodesicArea(latlngs);
      areaHa = areaM2 / 10000;
    } catch(err) {
      console.log("No L.GeometryUtil, using default estimation.");
    }
    $("creator-area-ha").innerText = `${areaHa.toFixed(2)} ha`;
    $("creator-name-input").value = `Lote_${parcels.length + 1}`;

    // Cambiar a Paso B (Detalles) en Seccion 2
    $("creator-step-drawing").classList.add("hidden");
    $("creator-step-details").classList.remove("hidden");

    // Ocultar banner de dibujo
    $("map-draw-banner").classList.add("hidden");
    if (polygonDrawer) {
      try { polygonDrawer.disable(); } catch(err){}
    }
  });

  map.on(L.Draw.Event.DRAWSTART, () => {
    $("map-draw-banner").classList.remove("hidden");
    $("map-draw-banner-text").innerText = "Haz clic en el mapa para marcar tu primer punto.";
  });

  map.on(L.Draw.Event.DRAWVERTEX, () => {
    $("map-draw-banner-text").innerText = "Completa tu lote marcando los puntos restantes en el mapa. Haz doble clic o cierra para terminar.";
  });
}

function renderParcelsOnMap() {
  if (!parcelsLayer) return;
  parcelsLayer.clearLayers();
  const feats = parcels
    .filter((p) => p.geojson)
    .map((p) => ({ type: "Feature", properties: { name: p.name, id: p.id }, geometry: p.geojson }));
  if (!feats.length) return;
  parcelsLayer.addData({ type: "FeatureCollection", features: feats });
  try { map.fitBounds(parcelsLayer.getBounds(), { maxZoom: 14, padding: [25, 25] }); } catch {}
}

function flyToParcel(id) {
  const p = parcels.find((x) => x.id === id);
  if (!p || !p.geojson || !map) return;
  try { map.flyToBounds(L.geoJSON(p.geojson).getBounds(), { maxZoom: 15, padding: [25, 25] }); } catch {}
}

// Control del selector flotante de parcelas
if ($("btn-farm-selector-toggle")) {
  $("btn-farm-selector-toggle").addEventListener("click", (e) => {
    e.stopPropagation();
    $("farm-selector-dropdown").classList.toggle("hidden");
  });
}

document.addEventListener("click", (e) => {
  const dropdown = $("farm-selector-dropdown");
  const toggle = $("btn-farm-selector-toggle");
  if (dropdown && !dropdown.classList.contains("hidden") && !dropdown.contains(e.target) && e.target !== toggle && !toggle?.contains(e.target)) {
    dropdown.classList.add("hidden");
  }
});

let polygonDrawer = null;

function enableDrawingMode() {
  // Mostrar panel de creación
  $("section2-form").classList.add("hidden");
  $("section2-chat").classList.add("hidden");
  $("section2-creator").classList.remove("hidden");

  // Poner Paso A activo (Instrucciones)
  $("creator-step-drawing").classList.remove("hidden");
  $("creator-step-details").classList.add("hidden");
  $("creator-step-loading").classList.add("hidden");

  // Activar el dibujador de polígonos de Leaflet
  if (polygonDrawer) {
    try { polygonDrawer.disable(); } catch(err){}
  }
  drawnItems.clearLayers();
  drawnGeojson = null;

  polygonDrawer = new L.Draw.Polygon(map, {
    shapeOptions: { color: "#15803d", weight: 2, fillColor: "#15803d", fillOpacity: 0.15 }
  });
  polygonDrawer.enable();
}

function disableDrawingMode() {
  if (polygonDrawer) {
    try { polygonDrawer.disable(); } catch(err){}
  }
  $("map-draw-banner").classList.add("hidden");
  drawnItems.clearLayers();
  drawnGeojson = null;

  $("section2-creator").classList.add("hidden");

  // Regresar a la vista correspondiente
  showSection2Chat();
}

if ($("btn-floating-add-parcel")) {
  $("btn-floating-add-parcel").addEventListener("click", () => {
    $("farm-selector-dropdown").classList.add("hidden");
    enableDrawingMode();
  });
}

if ($("btn-cancel-draw")) {
  $("btn-cancel-draw").addEventListener("click", () => {
    disableDrawingMode();
  });
}

if ($("btn-creator-cancel")) {
  $("btn-creator-cancel").addEventListener("click", () => {
    disableDrawingMode();
  });
}

if ($("btn-show-creator")) {
  $("btn-show-creator").addEventListener("click", () => {
    enableDrawingMode();
  });
}

if ($("btn-draw-undo")) {
  $("btn-draw-undo").addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (polygonDrawer && typeof polygonDrawer.deleteLastVertex === 'function') {
      polygonDrawer.deleteLastVertex();
    }
  });
}

if ($("creator-crop-select")) {
  $("creator-crop-select").addEventListener("change", () => {
    const crop = $("creator-crop-select").value;
    applyCreatorIndices(RECOMMENDED_INDICES_BY_CROP[crop] || ["ndvi"]);
  });
}

if ($("btn-creator-select-recommended-indices")) {
  $("btn-creator-select-recommended-indices").addEventListener("click", () => {
    const crop = $("creator-crop-select").value;
    applyCreatorIndices(RECOMMENDED_INDICES_BY_CROP[crop] || ["ndvi"]);
  });
}

if ($("btn-creator-select-all-indices")) {
  $("btn-creator-select-all-indices").addEventListener("click", () => {
    applyCreatorIndices(VALID_INDICES);
  });
}

if ($("btn-creator-save")) {
  $("btn-creator-save").addEventListener("click", async () => {
    const name = $("creator-name-input").value.trim();
    const crop = $("creator-crop-select").value;
    const selectedIndices = getCheckedIndices(".creator-index-checkbox");
    if (!drawnGeojson) return notify("Falta el polígono", "Dibuja un polígono en el mapa.");
    if (!name) return notify("Falta el nombre", "Escribe un nombre.");
    if (!selectedIndices.length) {
      $("creator-indices-error")?.classList.remove("hidden");
      return notify("Falta una variable satelital", "Marca al menos una variable satelital para calcular.");
    }
    $("creator-indices-error")?.classList.add("hidden");

    // Mostrar pantalla de carga (Paso C)
    $("creator-step-details").classList.add("hidden");
    $("creator-step-loading").classList.remove("hidden");

    try {
      track("parcel_draw_save", { name, crop, indices: selectedIndices });

      // 1. Crear la parcela en la base de datos
      const r = await api("/fields", { 
        method: "POST", 
        body: JSON.stringify({
          name,
          geojson: drawnGeojson,
          crop_variety: crop || null,
          selected_indices: selectedIndices
        })
      });

      if (r.ok) {
        const field = await r.json();
        const newFieldId = field.id;

        // 2. Si seleccionó cultivo o variables, guardarlas vía PATCH
        if (crop || selectedIndices.length) {
          await api(`/fields/${newFieldId}`, {
            method: "PATCH",
            body: JSON.stringify({ crop_variety: crop || null, selected_indices: selectedIndices })
          });
        }

        track("parcel_create_wizard_success", { name, crop, indices: selectedIndices });

        // 3. Simular procesamiento para esperar recálculo e iniciar notificaciones escalonadas
        setTimeout(async () => {
          // Limpiar cargando
          $("section2-creator").classList.add("hidden");
          showSection2Chat();

          // Notificaciones escalonadas (toasts en la esquina superior derecha)
          setTimeout(() => {
            notify("Meteorología Lista", `El clima histórico de Open-Meteo para ${name} está disponible.`, "success");
          }, 100);

          setTimeout(() => {
            notify("Teledetección Lista", `Sentinel-2 calculará ${formatIndices(selectedIndices)} en ${name}.`, "success");
          }, 800);

          setTimeout(() => {
            notify("Asistente Listo", `El agente RAG de AgroVisión ya tiene cargado el contexto completo de ${name}.`, "success");
          }, 1500);

          drawnGeojson = null;
          drawnItems.clearLayers();

          await refreshParcels();
          setParcelIndices(newFieldId, selectedIndices);
          selectParcel(newFieldId);
          flyToParcel(newFieldId);
        }, 3000);

      } else {
        const e = await r.json().catch(() => ({}));
        notify("Error " + r.status, e.detail || "");
        $("creator-step-loading").classList.add("hidden");
        $("creator-step-details").classList.remove("hidden");
      }
    } catch (e) {
      notify("Error de red", String(e));
      $("creator-step-loading").classList.add("hidden");
      $("creator-step-details").classList.remove("hidden");
    }
  });
}

if ($("floating-parcelas-list")) {
  $("floating-parcelas-list").addEventListener("click", (e) => {
    const item = e.target.closest(".floating-parcel-item");
    if (!item) return;
    const pid = item.dataset.pid;
    const gear = e.target.closest(".btn-gear-click");

    selectParcel(pid);
    flyToParcel(pid);

    if (gear) {
      // Mostrar formulario de Ajustes
      $("section2-form").classList.remove("hidden");
      $("section2-chat").classList.add("hidden");
      $("section2-creator").classList.add("hidden");
      $("branding-icon").className = "fa-solid fa-robot text-base";
      $("btn-branding-toggle").title = "Mostrar Chat con Asistente";
    }
    $("farm-selector-dropdown").classList.add("hidden");
  });
}

// ===== Resumen KPIs y Gráfico NDVI =====
async function loadResumen() {
  renderFloatingParcels();
}

// ===== Teledetección (GIS + Heatmap + Índices) =====
const INDEX_RANGES = { ndvi: [0, 1], evi: [0, 1], savi: [-0.4, 0.8], ndwi: [-0.6, 0.7], ndre: [0, 0.5] };
let currentIndex = "ndvi";

$("select-index").addEventListener("change", () => {
  currentIndex = $("select-index").value;
  loadTeledeteccion();
});

$("btn-add-satellite-var").addEventListener("click", async () => {
  const fid = $("select-parcela").value;
  if (!fid) return notify("Selecciona una parcela", "Elige una parcela antes de agregar variables satelitales.");
  const index = $("select-index").value;
  const currentIndices = getParcelIndices(fid);
  if (!currentIndices.includes(index)) {
    const nextIndices = normalizeIndices([...currentIndices, index]);
    try {
      const res = await api(`/fields/${fid}`, {
        method: "PATCH",
        body: JSON.stringify({ selected_indices: nextIndices })
      });
      if (!res.ok) {
        const error = await res.json().catch(() => ({}));
        return notify("No se pudo agregar la variable", error.detail || `Error ${res.status}`);
      }
      setParcelIndices(fid, nextIndices);
      syncSatelliteIndexControls(fid);
      track("satellite_index_added", { field_id: fid, index });
      notify("Variable satelital habilitada", `${INDEX_LABELS[index] || index.toUpperCase()} se agregó a la parcela. Puedes calcularla ahora.`);
    } catch (error) {
      return notify("Error de red", String(error));
    }
  } else {
    notify("Variable ya activa", `${INDEX_LABELS[index] || index.toUpperCase()} ya está activa en la parcela. Puedes reprocesarla.`);
  }
  showReprocessModal(index);
});

async function loadTeledeteccion() {
  const fid = $("select-parcela").value;
  if (!fid) { $("satelite-empty").classList.remove("hidden"); return; }
  $("satelite-empty").classList.add("hidden");
  const parcelIndices = getParcelIndices(fid);
  activeParcelIndices = parcelIndices;
  renderActiveIndexBadges(parcelIndices);
  updateIndexSelectOptions(parcelIndices);

  const rI = await api("/vegetation/" + currentIndex, { method: "POST", body: JSON.stringify({ field_id: fid }) });
  const series = rI.ok ? (await rI.json()).series : [];
  if (!series.length) { $("satelite-empty").classList.remove("hidden"); return; }

  const label = INDEX_LABELS[currentIndex] || currentIndex.toUpperCase();
  const range = INDEX_RANGES[currentIndex] || [0, 1];

  chartSatelite?.destroy();
  chartSatelite = new Chart($("chart-satelite"), {
    type: "line",
    data: {
      labels: series.map((p) => p.date),
      datasets: [
        { label: label, data: series.map((p) => p.mean_value), borderColor: "#15803d", tension: 0.3, fill: false }
      ],
    },
    options: { responsive: true, maintainAspectRatio: false, scales: { y: { min: range[0], max: range[1], title: { display: true, text: label } } } },
  });
  track("chart_view", { chart: "teledeteccion", index: currentIndex, points: series.length });
}

$("btn-heatmap").addEventListener("click", async () => {
  const fid = $("select-parcela").value;
  if (!fid) return notify("Selecciona una parcela", "");
  const idx = currentIndex;
  track("heatmap", { field_id: fid, index: idx });
  $("heatmap-box").innerHTML = '<span class="text-xs text-stone-500">Generando…</span>';
  try {
    const r = await api("/vegetation/" + idx + "/raster", { method: "POST", body: JSON.stringify({ field_id: fid }) });
    if (r.ok) { const url = URL.createObjectURL(await r.blob()); $("heatmap-box").innerHTML = `<img src="${url}" class="max-w-full rounded shadow" />`; }
    else { $("heatmap-box").innerHTML = '<span class="text-xs text-red-500">No se pudo generar. Verifica Copernicus.</span>'; }
  } catch (e) { $("heatmap-box").innerHTML = '<span class="text-xs text-red-500">Error de red.</span>'; }
});

// ===== Meteorología (Weather) =====
let currentGranularity = 'horario';
let currentWeatherVariable = 'temperatures';
let currentBottomChartFilter = 'water_balance';
let weatherRawData = [];
let weatherCampaignStart = "";
let activeFieldId = "";

let chartWaterBalance = null; // Store bottom chart instance globally in this block

// Helper to calculate Dew Point (Punto de Rocío) using Magnus-Tetens formula:
// Td = (b * alpha(T,RH)) / (a - alpha(T,RH)) where alpha(T,RH) = (a*T)/(b+T) + ln(RH/100)
// Standard values: a = 17.27, b = 237.7
function calculateDewPoint(temp, rh) {
  if (temp === null || temp === undefined || rh === null || rh === undefined || rh <= 0) return temp;
  const a = 17.27;
  const b = 237.7;
  const alpha = ((a * temp) / (b + temp)) + Math.log(rh / 100);
  const dewPoint = (b * alpha) / (a - alpha);
  return parseFloat(dewPoint.toFixed(1));
}

// Helper for VPD (Déficit de Presión de Vapor) in kPa:
// Es = 0.6108 * exp((17.27 * T) / (T + 237.3))
// Ea = Es * (RH / 100)
// VPD = Es - Ea
function calculateVPD(temp, rh) {
  if (temp === null || temp === undefined || rh === null || rh === undefined) return 0;
  const Es = 0.6108 * Math.exp((17.27 * temp) / (temp + 237.3));
  const Ea = Es * (rh / 100);
  return parseFloat(Math.max(0, Es - Ea).toFixed(2));
}

// Agronomic stressors definitions & note strings
const weatherNotesData = {
  gdd: {
    title: "Grados Día Acumulados (GDD)",
    icon: "fa-fire-flame-simple text-orange-600",
    bg: "bg-orange-50 border-orange-100 text-orange-950",
    text: "Los Grados Día acumulados miden el calor total que la planta ha absorbido por encima de una temperatura base (10°C). Es un indicador clave para predecir las fases de brotación, floración y maduración del cultivo."
  },
  chill_hours: {
    title: "Horas Frío (HF)",
    icon: "fa-snowflake text-blue-600",
    bg: "bg-blue-50 border-blue-100 text-blue-950",
    text: "Mide las horas acumuladas con temperaturas inferiores a 7.2°C. Es fundamental para variedades caducifolias o de bajo requerimiento frío para romper el letargo invernal de forma uniforme."
  },
  thermal_stress: {
    title: "Horas de Estrés Térmico",
    icon: "fa-triangle-exclamation text-red-650",
    bg: "bg-red-50 border-red-100 text-red-950",
    text: "Registra las horas acumuladas con temperaturas superiores a 32°C. Provoca un aumento drástico en la tasa de respiración de la planta, deshidratación foliar y posible aborto de flores o frutos tiernos."
  },
  dpv_stress: {
    title: "Horas de Estrés por DPV",
    icon: "fa-wind text-amber-600",
    bg: "bg-amber-50 border-amber-100 text-amber-950",
    text: "Suma de horas con Déficit de Presión de Vapor superior a 2.0 kPa. Bajo un aire muy seco, las plantas cierran estomas para retener agua, lo que detiene la fotosíntesis y ralentiza el crecimiento."
  },
  frost_hours: {
    title: "Horas Heladas",
    icon: "fa-temperature-arrow-down text-indigo-700",
    bg: "bg-indigo-50 border-indigo-100 text-indigo-950",
    text: "Horas acumuladas por debajo de 0°C. Representa un riesgo inminente de congelación celular y necrosis de brotes nuevos, flores expuestas y frutos en desarrollo."
  },
  et0_accum: {
    title: "Evapotranspiración (ET0) Acumulada",
    icon: "fa-droplet-slash text-emerald-600",
    bg: "bg-emerald-50 border-emerald-100 text-emerald-950",
    text: "La ET0 acumulada estima la demanda hídrica teórica del suelo y vegetación (FAO-56 Penman-Monteith). Es la referencia base para planificar los tiempos y volúmenes de riego semanales."
  },
  balance: {
    title: "Estimación de Balance Hídrico",
    icon: "fa-wand-magic-sparkles text-emerald-600",
    bg: "bg-emerald-50 border-emerald-100 text-emerald-950",
    text: "Muestra la diferencia acumulada entre precipitaciones y evapotranspiración. Un balance negativo indica déficit hídrico neto que debe compensarse mediante riego programado."
  }
};

function updateAgronomicNote(type) {
  const note = weatherNotesData[type] || weatherNotesData.balance;
  const box = $("agronomic-note-box");
  const icon = $("agronomic-note-icon");
  const title = $("agronomic-note-title");
  const text = $("agronomic-note-text");
  if (box && icon && title && text) {
    box.className = `${note.bg} border rounded-xl p-3 text-[10px] leading-relaxed flex gap-2 cursor-pointer transition-all duration-300 hover:shadow-sm`;
    icon.className = `fa-solid ${note.icon} text-xs shrink-0 mt-0.5`;
    title.textContent = note.title;
    text.textContent = note.text;
  }
}

function setupWeatherEventListeners() {
  // Toggle buttons for granularity
  const btnHorario = $("btn-gran-horario");
  const btnDiario = $("btn-gran-diario");
  const btnSemanal = $("btn-gran-semanal");

  const updateGranularityUI = (selected) => {
    currentGranularity = selected;
    [btnHorario, btnDiario, btnSemanal].forEach(btn => {
      if (btn) {
        const isSelected = btn.id === `btn-gran-${selected}`;
        btn.className = isSelected 
          ? "flex-1 text-center py-2 bg-white text-emerald-800 font-extrabold rounded-lg text-xs shadow-sm transition-all"
          : "flex-1 text-center py-2 text-stone-500 hover:text-stone-850 font-bold rounded-lg text-xs transition-all";
      }
    });
    const dateFilter = $("filter-date-container");
    const campInfo = $("campaign-info-container");
    if (selected === 'horario') {
      dateFilter?.classList.remove('hidden');
      campInfo?.classList.add('hidden');
    } else {
      dateFilter?.classList.add('hidden');
      campInfo?.classList.remove('hidden');
    }
    renderDynamicKPIs();
    drawTopWeatherChart();
  };

  if (btnHorario) btnHorario.addEventListener("click", () => updateGranularityUI("horario"));
  if (btnDiario) btnDiario.addEventListener("click", () => updateGranularityUI("diario"));
  if (btnSemanal) btnSemanal.addEventListener("click", () => updateGranularityUI("semanal"));

  // Historical Date Picker
  const datePicker = $("historical-date-picker");
  if (datePicker) {
    datePicker.addEventListener("change", () => {
      if (currentGranularity === "horario") {
        renderDynamicKPIs();
        drawTopWeatherChart();
      }
    });
  }

  // Top chart variable selector
  const varSelect = $("weather-variable-select");
  if (varSelect) {
    varSelect.addEventListener("change", (e) => {
      currentWeatherVariable = e.target.value;
      drawTopWeatherChart();
    });
  }

  // Bottom chart selector
  const bottomSelect = $("bottom-chart-filter-select");
  if (bottomSelect) {
    bottomSelect.addEventListener("change", (e) => {
      currentBottomChartFilter = e.target.value;
      drawBottomWeatherChart();
    });
  }

  // Setup Agronomic Stress Cards Clicks
  const bindCardClick = (id, type) => {
    const card = $(id);
    if (card) {
      card.addEventListener("click", () => updateAgronomicNote(type));
    }
  };
  bindCardClick("btn-indicator-gdd", "gdd");
  bindCardClick("btn-indicator-chill", "chill_hours");
  bindCardClick("btn-indicator-thermal", "thermal_stress");
  bindCardClick("btn-indicator-dpv", "dpv_stress");
  bindCardClick("btn-indicator-frost", "frost_hours");
  bindCardClick("btn-indicator-et0", "et0_accum");

  const noteBox = $("agronomic-note-box");
  if (noteBox) {
    noteBox.addEventListener("click", () => updateAgronomicNote("balance"));
  }
}

// Group records helpers
function getAggregatedData() {
  if (!weatherRawData || !weatherRawData.length) return { labels: [], datasets: [] };

  if (currentGranularity === 'horario') {
    // Filter records by historical-date-picker value (YYYY-MM-DD)
    const datePicker = $("historical-date-picker");
    let selectedDateStr = datePicker ? datePicker.value : "";
    if (!selectedDateStr) {
      // Default to latest date in raw data
      const dates = weatherRawData.map(r => r.date.split("T")[0]);
      selectedDateStr = dates.reduce((max, d) => d > max ? d : max, dates[0]);
      if (datePicker) datePicker.value = selectedDateStr;
    }

    const filtered = weatherRawData.filter(r => {
      if (!r.date) return false;
      const d = new Date(r.date);
      const y = d.getFullYear();
      const m = String(d.getMonth() + 1).padStart(2, "0");
      const dateStr = String(d.getDate()).padStart(2, "0");
      return `${y}-${m}-${dateStr}` === selectedDateStr;
    });

    // Produce 24 points (hours 0-23)
    const hoursData = Array.from({ length: 24 }, (_, hour) => {
      const match = filtered.find(r => {
        if (!r.date) return false;
        return new Date(r.date).getHours() === hour;
      });
      return match || {
        temp_c: 0,
        relative_humidity_percentage: 0,
        soil_temperature_0_to_7cm_c: 0,
        soil_moisture_0_to_7cm_m3_m3: 0,
        precip_mm: 0,
        solar_radiation_w_m2: 0,
        wind_speed_10m_km_h: 0,
        et0_fao_evapotranspiration: 0
      };
    });

    const labels = Array.from({ length: 24 }, (_, i) => `${i}:00`);
    return { labels, rawRecords: hoursData, mode: 'horario' };

  } else if (currentGranularity === 'diario') {
    // Group by day YYYY-MM-DD
    const dailyMap = new Map();
    weatherRawData.forEach(r => {
      const day = r.date.split("T")[0];
      if (!dailyMap.has(day)) dailyMap.set(day, []);
      dailyMap.get(day).push(r);
    });

    const sortedDays = Array.from(dailyMap.keys()).sort();
    const dailyRecords = sortedDays.map(day => {
      const records = dailyMap.get(day);
      const temps = records.map(r => r.temp_c).filter(v => v !== null && v !== undefined);
      const rhs = records.map(r => r.relative_humidity_percentage).filter(v => v !== null && v !== undefined);
      const winds = records.map(r => r.wind_speed_10m_km_h).filter(v => v !== null && v !== undefined);
      const rads = records.map(r => r.solar_radiation_w_m2).filter(v => v !== null && v !== undefined);
      const soils = records.map(r => r.soil_moisture_0_to_7cm_m3_m3).filter(v => v !== null && v !== undefined);

      const maxTemp = temps.length ? Math.max(...temps) : 0;
      const minTemp = temps.length ? Math.min(...temps) : 0;
      const meanTemp = temps.length ? (temps.reduce((s, v) => s + v, 0) / temps.length) : 0;

      const maxRH = rhs.length ? Math.max(...rhs) : 0;
      const minRH = rhs.length ? Math.min(...rhs) : 0;
      const meanRH = rhs.length ? (rhs.reduce((s, v) => s + v, 0) / rhs.length) : 0;

      const precip = records.reduce((s, r) => s + (r.precip_mm || 0), 0);
      const maxRad = rads.length ? Math.max(...rads) : 0;

      const maxWind = winds.length ? Math.max(...winds) : 0;
      const minWind = winds.length ? Math.min(...winds) : 0;
      const meanWind = winds.length ? (winds.reduce((s, v) => s + v, 0) / winds.length) : 0;

      const meanSoil = soils.length ? (soils.reduce((s, v) => s + v, 0) / soils.length) : 0;

      // VPD stress calculation inside daily aggregator
      const vpds = records.map(r => calculateVPD(r.temp_c, r.relative_humidity_percentage));
      const meanVPD = vpds.length ? (vpds.reduce((s, v) => s + v, 0) / vpds.length) : 0;

      return {
        day,
        maxTemp,
        minTemp,
        meanTemp,
        maxRH,
        minRH,
        meanRH,
        precip,
        maxRad,
        maxWind,
        minWind,
        meanWind,
        meanSoil,
        meanVPD
      };
    });

    return { labels: sortedDays, records: dailyRecords, mode: 'diario' };

  } else {
    // Semanal: Group raw records by 7-day calendar windows starting from the campaign start date
    const campaignStartMs = new Date(weatherCampaignStart).getTime();
    const weeklyMap = new Map();

    weatherRawData.forEach(r => {
      const recordMs = new Date(r.date).getTime();
      const diffDays = Math.floor((recordMs - campaignStartMs) / (1000 * 60 * 60 * 24));
      const weekIndex = Math.max(0, Math.floor(diffDays / 7)) + 1;
      if (!weeklyMap.has(weekIndex)) weeklyMap.set(weekIndex, []);
      weeklyMap.get(weekIndex).push(r);
    });

    const sortedWeeks = Array.from(weeklyMap.keys()).sort((a, b) => a - b);
    const weeklyRecords = sortedWeeks.map(wIdx => {
      const records = weeklyMap.get(wIdx);
      const temps = records.map(r => r.temp_c).filter(v => v !== null && v !== undefined);
      const rhs = records.map(r => r.relative_humidity_percentage).filter(v => v !== null && v !== undefined);
      const winds = records.map(r => r.wind_speed_10m_km_h).filter(v => v !== null && v !== undefined);
      const rads = records.map(r => r.solar_radiation_w_m2).filter(v => v !== null && v !== undefined);
      const soils = records.map(r => r.soil_moisture_0_to_7cm_m3_m3).filter(v => v !== null && v !== undefined);

      const maxTemp = temps.length ? Math.max(...temps) : 0;
      const minTemp = temps.length ? Math.min(...temps) : 0;
      const meanTemp = temps.length ? (temps.reduce((s, v) => s + v, 0) / temps.length) : 0;

      const maxRH = rhs.length ? Math.max(...rhs) : 0;
      const minRH = rhs.length ? Math.min(...rhs) : 0;

      const precip = records.reduce((s, r) => s + (r.precip_mm || 0), 0);
      const maxRad = rads.length ? Math.max(...rads) : 0;

      const maxWind = winds.length ? Math.max(...winds) : 0;
      const minWind = winds.length ? Math.min(...winds) : 0;

      const meanSoil = soils.length ? (soils.reduce((s, v) => s + v, 0) / soils.length) : 0;

      const vpds = records.map(r => calculateVPD(r.temp_c, r.relative_humidity_percentage));
      const meanVPD = vpds.length ? (vpds.reduce((s, v) => s + v, 0) / vpds.length) : 0;

      return {
        weekIndex,
        maxTemp,
        minTemp,
        meanTemp,
        maxRH,
        minRH,
        precip,
        maxRad,
        maxWind,
        minWind,
        meanSoil,
        meanVPD
      };
    });

    return { labels: sortedWeeks.map(w => `Semana ${w}`), records: weeklyRecords, mode: 'semanal' };
  }
}

function renderDynamicKPIs() {
  const data = getAggregatedData();
  const container = $("kpis-container");
  if (!container) return;

  let kpis = [];

  if (data.mode === 'horario') {
    // Find latest record or active record matching picker
    const list = data.rawRecords;
    // Calculate values for "Current hour" (we take the last record from the subset, which would correspond to 23:00 or closest)
    // To make it dynamic, let's grab the last record in this filtered day that is non-zero, or just the last record.
    const currentRec = list[list.length - 1] || {};

    kpis = [
      { label: 'Temperatura actual', value: `${(currentRec.temp_c || 0).toFixed(1)} °C`, icon: 'fa-temperature-half', color: 'orange' },
      { label: 'Humedad Suelo', value: `${((currentRec.soil_moisture_0_to_7cm_m3_m3 || 0) * 100).toFixed(1)} %`, icon: 'fa-droplet', color: 'blue' },
      { label: 'Viento actual', value: `${(currentRec.wind_speed_10m_km_h || 0).toFixed(1)} km/h`, icon: 'fa-wind', color: 'cyan' },
      { label: 'Radiación Solar', value: `${(currentRec.solar_radiation_w_m2 || 0).toFixed(0)} W/m²`, icon: 'fa-sun', color: 'yellow' },
      { label: 'Precipitación', value: `${(currentRec.precip_mm || 0).toFixed(1)} mm`, icon: 'fa-cloud-rain', color: 'indigo' },
      { label: 'DPV actual', value: `${calculateVPD(currentRec.temp_c, currentRec.relative_humidity_percentage).toFixed(2)} kPa`, icon: 'fa-droplet-slash', color: 'teal' }
    ];
  } else if (data.mode === 'diario') {
    const list = data.records;
    // Compute average/max stats over the entire list of daily records
    const maxTemps = list.map(r => r.maxTemp);
    const minTemps = list.map(r => r.minTemp);
    const maxTemp = maxTemps.length ? Math.max(...maxTemps) : 0;
    const minTemp = minTemps.length ? Math.min(...minTemps) : 0;

    const maxRHs = list.map(r => r.maxRH);
    const minRHs = list.map(r => r.minRH);
    const maxRH = maxRHs.length ? Math.max(...maxRHs) : 0;
    const minRH = minRHs.length ? Math.min(...minRHs) : 0;

    const maxRads = list.map(r => r.maxRad);
    const maxRad = maxRads.length ? Math.max(...maxRads) : 0;

    const totalPrecip = list.reduce((s, r) => s + r.precip, 0);

    const maxWinds = list.map(r => r.maxWind);
    const minWinds = list.map(r => r.minWind);
    const maxWind = maxWinds.length ? Math.max(...maxWinds) : 0;
    const minWind = minWinds.length ? Math.min(...minWinds) : 0;

    const meanVPDs = list.map(r => r.meanVPD);
    const avgVPD = meanVPDs.length ? (meanVPDs.reduce((s, v) => s + v, 0) / meanVPDs.length) : 0;

    kpis = [
      { label: 'Temp Máx / Mín', value: `${maxTemp.toFixed(1)}°C / ${minTemp.toFixed(1)}°C`, icon: 'fa-temperature-half', color: 'orange' },
      { label: 'HR Máx / Mín', value: `${maxRH.toFixed(0)}% / ${minRH.toFixed(0)}%`, icon: 'fa-droplet', color: 'blue' },
      { label: 'Radiación Máx', value: `${maxRad.toFixed(0)} W/m²`, icon: 'fa-sun', color: 'yellow' },
      { label: 'Precipitación Acum.', value: `${totalPrecip.toFixed(1)} mm`, icon: 'fa-cloud-showers-water', color: 'indigo' },
      { label: 'Viento Máx / Mín', value: `${maxWind.toFixed(1)} / ${minWind.toFixed(1)} km/h`, icon: 'fa-wind', color: 'cyan' },
      { label: 'DPV Promedio', value: `${avgVPD.toFixed(2)} kPa`, icon: 'fa-droplet-slash', color: 'teal' }
    ];
  } else {
    // Semanal
    const list = data.records;
    const maxTemps = list.map(r => r.maxTemp);
    const minTemps = list.map(r => r.minTemp);
    const maxTempProm = maxTemps.length ? (maxTemps.reduce((s, v) => s + v, 0) / maxTemps.length) : 0;
    const minTempProm = minTemps.length ? (minTemps.reduce((s, v) => s + v, 0) / minTemps.length) : 0;

    const maxRHs = list.map(r => r.maxRH);
    const minRHs = list.map(r => r.minRH);
    const maxRHProm = maxRHs.length ? (maxRHs.reduce((s, v) => s + v, 0) / maxRHs.length) : 0;
    const minRHProm = minRHs.length ? (minRHs.reduce((s, v) => s + v, 0) / minRHs.length) : 0;

    const maxRads = list.map(r => r.maxRad);
    const maxRadHist = maxRads.length ? Math.max(...maxRads) : 0;

    const totalPrecip = list.reduce((s, r) => s + r.precip, 0);

    const maxWinds = list.map(r => r.maxWind);
    const minWinds = list.map(r => r.minWind);
    const maxWindProm = maxWinds.length ? (maxWinds.reduce((s, v) => s + v, 0) / maxWinds.length) : 0;
    const minWindProm = minWinds.length ? (minWinds.reduce((s, v) => s + v, 0) / minWinds.length) : 0;

    const meanVPDs = list.map(r => r.meanVPD);
    const avgVPD = meanVPDs.length ? (meanVPDs.reduce((s, v) => s + v, 0) / meanVPDs.length) : 0;

    kpis = [
      { label: 'Temp Máx/Mín Prom.', value: `${maxTempProm.toFixed(1)}°C / ${minTempProm.toFixed(1)}°C`, icon: 'fa-temperature-half', color: 'orange' },
      { label: 'HR Máx/Mín Prom.', value: `${maxRHProm.toFixed(0)}% / ${minRHProm.toFixed(0)}%`, icon: 'fa-droplet', color: 'blue' },
      { label: 'Radiación Máx Hist.', value: `${maxRadHist.toFixed(0)} W/m²`, icon: 'fa-sun', color: 'yellow' },
      { label: 'Precipitación Acum.', value: `${totalPrecip.toFixed(1)} mm`, icon: 'fa-cloud-showers-water', color: 'indigo' },
      { label: 'Viento Prom. Máx/Mín', value: `${maxWindProm.toFixed(1)} / ${minWindProm.toFixed(1)} km/h`, icon: 'fa-wind', color: 'cyan' },
      { label: 'DPV Promedio Sem.', value: `${avgVPD.toFixed(2)} kPa`, icon: 'fa-droplet-slash', color: 'teal' }
    ];
  }

  container.innerHTML = '';
  kpis.forEach(kpi => {
    const card = document.createElement('div');
    card.className = 'bg-white p-4 rounded-xl border border-stone-200/80 shadow-sm flex items-center justify-between';

    let iconBg = '';
    let iconColor = '';
    if (kpi.color === 'orange') { iconBg = 'bg-orange-50'; iconColor = 'text-orange-600'; }
    else if (kpi.color === 'blue') { iconBg = 'bg-blue-50'; iconColor = 'text-blue-600'; }
    else if (kpi.color === 'cyan') { iconBg = 'bg-cyan-50'; iconColor = 'text-cyan-600'; }
    else if (kpi.color === 'yellow') { iconBg = 'bg-yellow-50'; iconColor = 'text-yellow-600'; }
    else if (kpi.color === 'indigo') { iconBg = 'bg-indigo-50'; iconColor = 'text-indigo-600'; }
    else { iconBg = 'bg-teal-50'; iconColor = 'text-teal-600'; }

    card.innerHTML = `
      <div>
        <span class="text-[9px] font-bold text-stone-400 uppercase tracking-wide block">${kpi.label}</span>
        <h4 class="text-sm font-extrabold text-stone-800 mt-1">${kpi.value}</h4>
      </div>
      <div class="w-8 h-8 rounded-lg ${iconBg} ${iconColor} flex items-center justify-center text-sm shrink-0">
        <i class="fa-solid ${kpi.icon}"></i>
      </div>
    `;
    container.appendChild(card);
  });
}

function drawTopWeatherChart() {
  const ctx = $("main-weather-chart")?.getContext('2d');
  if (!ctx) return;

  chartWeather?.destroy();

  const data = getAggregatedData();
  let labels = data.labels;
  let datasets = [];
  let scalesConfig = {
    x: { grid: { color: '#f3f4f6' } },
    y: { type: 'linear', display: true, position: 'left', grid: { color: '#f3f4f6' } }
  };

  if (data.mode === 'horario') {
    const recs = data.rawRecords;
    if (currentWeatherVariable === 'temperatures') {
      datasets = [
        { label: 'Temperatura (°C)', data: recs.map(r => r.temp_c), borderColor: '#ea580c', tension: 0.3, borderWidth: 2 },
        { label: 'Punto de Rocío (°C)', data: recs.map(r => calculateDewPoint(r.temp_c, r.relative_humidity_percentage)), borderColor: '#3b82f6', borderDash: [4, 4], tension: 0.3, borderWidth: 1.5 }
      ];
    } else if (currentWeatherVariable === 'humidity') {
      datasets = [
        { label: 'Humedad Relativa (%)', data: recs.map(r => r.relative_humidity_percentage), borderColor: '#06b6d4', tension: 0.3, borderWidth: 2 },
        { label: 'Humedad del Suelo (0-7cm %)', data: recs.map(r => (r.soil_moisture_0_to_7cm_m3_m3 || 0) * 100), borderColor: '#2563eb', tension: 0.3, borderWidth: 2 }
      ];
    } else if (currentWeatherVariable === 'water') {
      datasets = [
        { label: 'Precipitación Horaria (mm)', type: 'bar', data: recs.map(r => r.precip_mm), backgroundColor: '#3b82f6', yAxisID: 'y' },
        { label: 'Déficit de Presión de Vapor DPV (kPa)', data: recs.map(r => calculateVPD(r.temp_c, r.relative_humidity_percentage)), borderColor: '#0d9488', tension: 0.3, borderWidth: 2, yAxisID: 'y1' }
      ];
      scalesConfig = {
        x: { grid: { color: '#f3f4f6' } },
        y: { type: 'linear', display: true, position: 'left', title: { display: true, text: 'Precipitación (mm)', font: { size: 9, family: 'Plus Jakarta Sans' } } },
        y1: { type: 'linear', display: true, position: 'right', title: { display: true, text: 'DPV (kPa)', font: { size: 9, family: 'Plus Jakarta Sans' } }, grid: { drawOnChartArea: false } }
      };
    } else {
      datasets = [
        { label: 'Radiación Solar Directa (W/m²)', data: recs.map(r => r.solar_radiation_w_m2), borderColor: '#eab308', tension: 0.3, borderWidth: 2, yAxisID: 'y' },
        { label: 'Velocidad de Viento Promedio (km/h)', data: recs.map(r => r.wind_speed_10m_km_h), borderColor: '#06b6d4', tension: 0.3, borderWidth: 1.5, yAxisID: 'y1' }
      ];
      scalesConfig = {
        x: { grid: { color: '#f3f4f6' } },
        y: { type: 'linear', display: true, position: 'left', title: { display: true, text: 'Radiación Directa (W/m²)', font: { size: 9, family: 'Plus Jakarta Sans' } } },
        y1: { type: 'linear', display: true, position: 'right', title: { display: true, text: 'Viento Promedio (km/h)', font: { size: 9, family: 'Plus Jakarta Sans' } }, grid: { drawOnChartArea: false } }
      };
    }
  } else if (data.mode === 'diario') {
    const recs = data.records;
    if (currentWeatherVariable === 'temperatures') {
      datasets = [
        { label: 'Temp Máxima Diario (°C)', data: recs.map(r => r.maxTemp), borderColor: '#dc2626', tension: 0.3, borderWidth: 2 },
        { label: 'Temp Mínima Diario (°C)', data: recs.map(r => r.minTemp), borderColor: '#2563eb', tension: 0.3, borderWidth: 1.5 }
      ];
    } else if (currentWeatherVariable === 'humidity') {
      datasets = [
        { label: 'HR Máxima Diario (%)', data: recs.map(r => r.maxRH), borderColor: '#0d9488', tension: 0.3 },
        { label: 'HR Mínima Diario (%)', data: recs.map(r => r.minRH), borderColor: '#06b6d4', tension: 0.3, borderDash: [3, 3] },
        { label: 'Humedad Suelo Media (%)', data: recs.map(r => (r.meanSoil || 0) * 100), borderColor: '#2563eb', tension: 0.3 }
      ];
    } else if (currentWeatherVariable === 'water') {
      datasets = [
        { label: 'Precipitación Acumulada Diario (mm)', type: 'bar', data: recs.map(r => r.precip), backgroundColor: '#3b82f6', yAxisID: 'y' },
        { label: 'DPV Promedio Diario (kPa)', data: recs.map(r => r.meanVPD), borderColor: '#0ea5e9', tension: 0.3, yAxisID: 'y1' }
      ];
      scalesConfig = {
        x: { grid: { color: '#f3f4f6' } },
        y: { type: 'linear', display: true, position: 'left', title: { display: true, text: 'Precipitación (mm)', font: { size: 9, family: 'Plus Jakarta Sans' } } },
        y1: { type: 'linear', display: true, position: 'right', title: { display: true, text: 'DPV (kPa)', font: { size: 9, family: 'Plus Jakarta Sans' } }, grid: { drawOnChartArea: false } }
      };
    } else {
      datasets = [
        { label: 'Radiación Máxima Diaria (W/m²)', data: recs.map(r => r.maxRad), borderColor: '#eab308', tension: 0.3, yAxisID: 'y' },
        { label: 'Viento Promedio Diario (km/h)', data: recs.map(r => /** @type {any} */ (r).meanWind), borderColor: '#06b6d4', tension: 0.3, yAxisID: 'y1' }
      ];
      scalesConfig = {
        x: { grid: { color: '#f3f4f6' } },
        y: { type: 'linear', display: true, position: 'left', title: { display: true, text: 'Radiación Directa (W/m²)', font: { size: 9, family: 'Plus Jakarta Sans' } } },
        y1: { type: 'linear', display: true, position: 'right', title: { display: true, text: 'Viento Promedio (km/h)', font: { size: 9, family: 'Plus Jakarta Sans' } }, grid: { drawOnChartArea: false } }
      };
    }
  } else {
    // Semanal
    const recs = data.records;
    if (currentWeatherVariable === 'temperatures') {
      datasets = [
        { label: 'Temp Máxima Promedio Semanal (°C)', data: recs.map(r => r.maxTemp), borderColor: '#dc2626', tension: 0.3, borderWidth: 2 },
        { label: 'Temp Mínima Promedio Semanal (°C)', data: recs.map(r => r.minTemp), borderColor: '#2563eb', tension: 0.3, borderWidth: 1.5 }
      ];
    } else if (currentWeatherVariable === 'humidity') {
      datasets = [
        { label: 'HR Máxima Promedio Semanal (%)', data: recs.map(r => r.maxRH), borderColor: '#0d9488', tension: 0.3 },
        { label: 'HR Mínima Promedio Semanal (%)', data: recs.map(r => r.minRH), borderColor: '#06b6d4', tension: 0.3, borderDash: [3, 3] },
        { label: 'Humedad Suelo Semanal (%)', data: recs.map(r => (r.meanSoil || 0) * 100), borderColor: '#2563eb', tension: 0.3 }
      ];
    } else if (currentWeatherVariable === 'water') {
      datasets = [
        { label: 'Precipitación Total Semanal (mm)', type: 'bar', data: recs.map(r => r.precip), backgroundColor: '#3b82f6', yAxisID: 'y' },
        { label: 'DPV Promedio Semanal (kPa)', data: recs.map(r => r.meanVPD), borderColor: '#0ea5e9', tension: 0.3, yAxisID: 'y1' }
      ];
      scalesConfig = {
        x: { grid: { color: '#f3f4f6' } },
        y: { type: 'linear', display: true, position: 'left', title: { display: true, text: 'Precipitación (mm)', font: { size: 9, family: 'Plus Jakarta Sans' } } },
        y1: { type: 'linear', display: true, position: 'right', title: { display: true, text: 'DPV (kPa)', font: { size: 9, family: 'Plus Jakarta Sans' } }, grid: { drawOnChartArea: false } }
      };
    } else {
      datasets = [
        { label: 'Radiación Máxima Semanal (W/m²)', data: recs.map(r => r.maxRad), borderColor: '#eab308', tension: 0.3, yAxisID: 'y' },
        { label: 'Viento Promedio Semanal (km/h)', data: recs.map(r => r.minWind), borderColor: '#06b6d4', tension: 0.3, yAxisID: 'y1' } // using minWind as a filler or let's use a mean of winds
      ];
      scalesConfig = {
        x: { grid: { color: '#f3f4f6' } },
        y: { type: 'linear', display: true, position: 'left', title: { display: true, text: 'Radiación Directa (W/m²)', font: { size: 9, family: 'Plus Jakarta Sans' } } },
        y1: { type: 'linear', display: true, position: 'right', title: { display: true, text: 'Viento Promedio (km/h)', font: { size: 9, family: 'Plus Jakarta Sans' } }, grid: { drawOnChartArea: false } }
      };
    }
  }

  chartWeather = new Chart(ctx, {
    type: 'line',
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'bottom',
          labels: { boxWidth: 12, font: { size: 10, family: 'Plus Jakarta Sans' } }
        }
      },
      scales: scalesConfig
    }
  });
}

function drawBottomWeatherChart() {
  const ctx = $("water-balance-chart")?.getContext('2d');
  const titleEl = $("bottom-chart-title");
  const subtitleEl = $("bottom-chart-subtitle");
  if (!ctx) return;

  chartWaterBalance?.destroy();

  // Calculations are strictly weekly, starting from the campaign start date
  const campaignStartMs = new Date(weatherCampaignStart).getTime();
  const weeklyMap = new Map();

  weatherRawData.forEach(r => {
    const recordMs = new Date(r.date).getTime();
    const diffDays = Math.floor((recordMs - campaignStartMs) / (1000 * 60 * 60 * 24));
    const weekIndex = Math.max(0, Math.floor(diffDays / 7)) + 1;
    if (!weeklyMap.has(weekIndex)) weeklyMap.set(weekIndex, []);
    weeklyMap.get(weekIndex).push(r);
  });

  const sortedWeeks = Array.from(weeklyMap.keys()).sort((a, b) => a - b);
  const labelsSemanas = sortedWeeks.map(w => `Sem <sup></sup>${w}`);
  let datasets = [];
  let yTitleLeft = '';
  let yTitleRight = '';
  let showY1 = true;

  if (currentBottomChartFilter === 'water_balance') {
    if (titleEl) titleEl.innerHTML = '<i class="fa-solid fa-droplet text-blue-600"></i> Balance Hídrico Acumulado Semanal';
    if (subtitleEl) subtitleEl.textContent = "Diferencia entre Precipitación (ingreso) y Evapotranspiración ET0 (pérdida).";
    yTitleLeft = 'Semanal (mm)';
    yTitleRight = 'Acumulado (mm)';

    const et0s = [];
    const precips = [];
    const deficits = [];
    let accDeficit = 0;

    sortedWeeks.forEach(w => {
      const list = weeklyMap.get(w);
      const wET0 = list.reduce((s, r) => s + (r.et0_fao_evapotranspiration || 0), 0);
      const wPrecip = list.reduce((s, r) => s + (r.precip_mm || 0), 0);
      et0s.push(parseFloat(wET0.toFixed(1)));
      precips.push(parseFloat(wPrecip.toFixed(1)));

      const diff = wPrecip - wET0;
      accDeficit += diff;
      deficits.push(parseFloat(accDeficit.toFixed(1)));
    });

    datasets = [
      {
        type: 'line',
        label: 'Evapotranspiración FAO-56 (ET0 - mm)',
        data: et0s,
        borderColor: '#ea580c',
        borderWidth: 2,
        tension: 0.3,
        yAxisID: 'y'
      },
      {
        label: 'Precipitación Semanal (mm)',
        data: precips,
        backgroundColor: '#3b82f6',
        borderRadius: 4,
        yAxisID: 'y'
      },
      {
        type: 'line',
        label: 'Déficit Hídrico Acumulado (mm)',
        data: deficits,
        borderColor: '#dc2626',
        borderWidth: 2,
        fill: false,
        tension: 0.3,
        yAxisID: 'y1',
        borderDash: [3, 3]
      }
    ];
  } else if (currentBottomChartFilter === 'gdd') {
    if (titleEl) titleEl.innerHTML = '<i class="fa-solid fa-fire-flame-simple text-orange-500"></i> Grados Día Acumulados (GDD)';
    if (subtitleEl) subtitleEl.textContent = "Acumulación de calor por encima de la temperatura base de la variedad (Base 10°C).";
    yTitleLeft = 'Semanal (GD)';
    yTitleRight = 'Acumulado (GD)';

    // Daily GDD is computed as max(0, (max_temp + min_temp)/2 - 10)
    // We group by day first to get correct GDD values
    const dailyGDDMap = new Map();
    weatherRawData.forEach(r => {
      const day = r.date.split("T")[0];
      if (!dailyGDDMap.has(day)) dailyGDDMap.set(day, []);
      dailyGDDMap.get(day).push(r.temp_c);
    });

    const dailyGDDList = Array.from(dailyGDDMap.keys()).sort().map(day => {
      const temps = dailyGDDMap.get(day).filter(v => v !== null && v !== undefined);
      if (!temps.length) return { day, gdd: 0 };
      const max = Math.max(...temps);
      const min = Math.min(...temps);
      const val = Math.max(0, ((max + min) / 2) - 10);
      return { day, gdd: val };
    });

    // Sum GDDs per week index
    const weeklyGDDSums = [];
    const weeklyGDDAccs = [];
    let accGDD = 0;

    sortedWeeks.forEach(w => {
      const list = weeklyMap.get(w);
      const weekDays = new Set(list.map(r => r.date.split("T")[0]));
      const wSum = dailyGDDList
        .filter(d => weekDays.has(d.day))
        .reduce((s, d) => s + d.gdd, 0);

      weeklyGDDSums.push(parseFloat(wSum.toFixed(1)));
      accGDD += wSum;
      weeklyGDDAccs.push(parseFloat(accGDD.toFixed(1)));
    });

    datasets = [
      {
        label: 'Grados Día Semanales (GD)',
        data: weeklyGDDSums,
        backgroundColor: '#f97316',
        borderRadius: 4,
        yAxisID: 'y'
      },
      {
        type: 'line',
        label: 'GDD Acumulados (GD)',
        data: weeklyGDDAccs,
        borderColor: '#dc2626',
        borderWidth: 2.5,
        tension: 0.2,
        yAxisID: 'y1'
      }
    ];
  } else if (currentBottomChartFilter === 'chill_hours') {
    if (titleEl) titleEl.innerHTML = '<i class="fa-solid fa-snowflake text-blue-500"></i> Horas Frío Acumuladas';
    if (subtitleEl) subtitleEl.textContent = "Suma de horas bajo el umbral crítico de vernalización (< 7.2°C) en la campaña.";
    yTitleLeft = 'Semanales (Horas)';
    yTitleRight = 'Acumuladas (Horas)';

    const weeklyChillSums = [];
    const weeklyChillAccs = [];
    let accChill = 0;

    sortedWeeks.forEach(w => {
      const list = weeklyMap.get(w);
      const wSum = list.filter(r => r.temp_c !== null && r.temp_c < 7.2).length;
      weeklyChillSums.push(wSum);
      accChill += wSum;
      weeklyChillAccs.push(accChill);
    });

    datasets = [
      {
        label: 'Horas Frío Semanales',
        data: weeklyChillSums,
        backgroundColor: '#60a5fa',
        borderRadius: 4,
        yAxisID: 'y'
      },
      {
        type: 'line',
        label: 'Horas Frío Acumuladas',
        data: weeklyChillAccs,
        borderColor: '#4f46e5',
        borderWidth: 2.5,
        tension: 0.2,
        yAxisID: 'y1'
      }
    ];
  } else if (currentBottomChartFilter === 'stress_hours') {
    if (titleEl) titleEl.innerHTML = '<i class="fa-solid fa-triangle-exclamation text-red-500"></i> Horas de Estrés de Campaña';
    if (subtitleEl) subtitleEl.textContent = "Horas acumuladas semanales de estrés por calor (> 32°C) y déficit de presión de vapor (> 2.0 kPa).";
    yTitleLeft = 'Horas de Estrés';
    showY1 = false;

    const weeklyThermal = [];
    const weeklyDPV = [];

    sortedWeeks.forEach(w => {
      const list = weeklyMap.get(w);
      const wThermal = list.filter(r => r.temp_c !== null && r.temp_c > 32).length;
      const wDPV = list.filter(r => calculateVPD(r.temp_c, r.relative_humidity_percentage) > 2.0).length;
      weeklyThermal.push(wThermal);
      weeklyDPV.push(wDPV);
    });

    datasets = [
      {
        label: 'Estrés Térmico (> 32°C)',
        data: weeklyThermal,
        backgroundColor: '#ef4444',
        borderRadius: 4,
        yAxisID: 'y'
      },
      {
        label: 'Estrés por DPV (> 2.0 kPa)',
        data: weeklyDPV,
        backgroundColor: '#f59e0b',
        borderRadius: 4,
        yAxisID: 'y'
      }
    ];
  }

  const scalesConfig = {
    x: { grid: { color: '#f3f4f6' } },
    y: {
      type: 'linear',
      display: true,
      position: 'left',
      title: { display: true, text: yTitleLeft, font: { size: 9, family: 'Plus Jakarta Sans' } },
      grid: { color: '#f3f4f6' }
    }
  };

  if (showY1) {
    scalesConfig.y1 = {
      type: 'linear',
      display: true,
      position: 'right',
      title: { display: true, text: yTitleRight, font: { size: 9, family: 'Plus Jakarta Sans' } },
      grid: { drawOnChartArea: false }
    };
  }

  chartWaterBalance = new Chart(ctx, {
    type: 'bar',
    data: { labels: labelsSemanas, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'bottom',
          labels: { boxWidth: 10, font: { size: 9, family: 'Plus Jakarta Sans' } }
        }
      },
      scales: scalesConfig
    }
  });
}

async function loadWeather() {
  const fid = $("select-parcela").value;
  if (!fid) {
    $("weather-empty")?.classList.remove("hidden");
    return;
  }
  const parcel = parcels.find((p) => p.id === fid);
  if (!parcel) {
    $("weather-empty")?.classList.remove("hidden");
    return;
  }
  $("weather-empty")?.classList.add("hidden");

  // Compute campaign start date: use parcel.plantation_date or default to Jan 1st of current year
  const plantationDate = parcel.plantation_date;
  if (plantationDate) {
    weatherCampaignStart = plantationDate.split("T")[0];
  } else {
    const currentYear = new Date().getFullYear();
    weatherCampaignStart = `${currentYear}-01-01`;
  }

  // Update Campaign Start UI element
  const startBadge = $("campaign-start-badge");
  if (startBadge) {
    // Format start date nicely
    try {
      const parts = weatherCampaignStart.split("-");
      startBadge.textContent = `${parts[2]}/${parts[1]}/${parts[0]}`;
    } catch {
      startBadge.textContent = weatherCampaignStart;
    }
  }

  const today = new Date().toISOString().split("T")[0];

  try {
    const rW = await api("/weather", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...authHeaders()
      },
      body: JSON.stringify({
        field_id: fid,
        start: weatherCampaignStart,
        end: today,
        raw: true
      })
    });

    if (!rW.ok) {
      console.error("Failed to load weather data");
      return;
    }

    const responseData = await rW.json();
    const rawSeries = responseData.series || [];
    weatherRawData = rawSeries.map(r => ({
      date: r.timestamp || "",
      temp_c: r.temperature_2m,
      relative_humidity_percentage: r.relative_humidity_2m,
      soil_temperature_0_to_7cm_c: r.soil_temperature_0_to_7cm,
      soil_moisture_0_to_7cm_m3_m3: r.soil_moisture_0_to_7cm,
      precip_mm: r.precipitation,
      solar_radiation_w_m2: r.shortwave_radiation,
      wind_speed_10m_km_h: r.wind_speed_10m,
      et0_fao_evapotranspiration: r.et0_fao_evapotranspiration,
      vapour_pressure_deficit: r.vapour_pressure_deficit
    }));

    if (!weatherRawData.length) {
      console.warn("No weather raw records returned");
      return;
    }

    // Calculate Campaign Agronomic KPIs
    // GDD (Base 10°C): sum of daily max(0, (max_temp + min_temp)/2 - 10)
    const dailyTempsMap = new Map();
    weatherRawData.forEach(r => {
      const day = r.date.split("T")[0];
      if (!dailyTempsMap.has(day)) dailyTempsMap.set(day, []);
      dailyTempsMap.get(day).push(r.temp_c);
    });

    let totalGDD = 0;
    dailyTempsMap.forEach((temps) => {
      const validTemps = temps.filter(v => v !== null && v !== undefined);
      if (validTemps.length) {
        const max = Math.max(...validTemps);
        const min = Math.min(...validTemps);
        totalGDD += Math.max(0, ((max + min) / 2) - 10);
      }
    });

    // Chill hours: sum of hours where temp < 7.2°C
    const chillHours = weatherRawData.filter(r => r.temp_c !== null && r.temp_c < 7.2).length;

    // Heat stress hours: sum of hours where temp > 32°C
    const heatStressHours = weatherRawData.filter(r => r.temp_c !== null && r.temp_c > 32).length;

    // VPD stress hours: sum of hours where VPD > 2.0 kPa
    const vpdStressHours = weatherRawData.filter(r => {
      const vpd = calculateVPD(r.temp_c, r.relative_humidity_percentage);
      return vpd > 2.0;
    }).length;

    // Frost hours: sum of hours where temp < 0°C
    const frostHours = weatherRawData.filter(r => r.temp_c !== null && r.temp_c < 0).length;

    // ET0 accumulation: sum of et0_fao_evapotranspiration
    const et0Accum = weatherRawData.reduce((s, r) => s + (r.et0_fao_evapotranspiration || 0), 0);

    // Net Water Balance: sum of precip_mm - sum of et0_fao_evapotranspiration
    const totalPrecip = weatherRawData.reduce((s, r) => s + (r.precip_mm || 0), 0);
    const netWaterBalance = totalPrecip - et0Accum;

    // Bind Elements
    const bindText = (id, val) => {
      const el = $(id);
      if (el) el.textContent = val;
    };
    bindText("val-gdd", `${totalGDD.toFixed(1)} GD`);
    bindText("val-chill", `${chillHours} horas`);
    bindText("val-thermal", `${heatStressHours} horas`);
    bindText("val-dpv", `${vpdStressHours} horas`);
    bindText("val-frost", `${frostHours} horas`);
    bindText("val-et0", `${et0Accum.toFixed(1)} mm`);

    // Update agronomic notes with actual balance deficit
    weatherNotesData.balance.text = `El déficit hídrico neto acumulado de esta campaña es de ${netWaterBalance.toFixed(1)} mm. Se aconseja ajustar la telemetría del sistema de riego por goteo para compensar la alta evapotranspiración de esta semana.`;

    // If active field changed, reset selectors to default or setup event listeners first time
    if (activeFieldId !== fid) {
      activeFieldId = fid;
      currentGranularity = 'horario';
      currentWeatherVariable = 'temperatures';
      currentBottomChartFilter = 'water_balance';

      // Set defaults on selector elements
      const selectVar = $("weather-variable-select");
      if (selectVar) selectVar.value = "temperatures";
      const selectBottom = $("bottom-chart-filter-select");
      if (selectBottom) selectBottom.value = "water_balance";

      // Set historical date picker to default (latest date in the dataset)
      const datePicker = $("historical-date-picker");
      if (datePicker && weatherRawData.length) {
        const dates = weatherRawData.map(r => r.date.split("T")[0]);
        const latestDate = dates.reduce((max, d) => d > max ? d : max, dates[0]);
        datePicker.value = latestDate;
      }

      // Bind listeners only once or when field is changed
      setupWeatherEventListeners();

      // Set default active note
      updateAgronomicNote("balance");
    }

    // Initial Render
    renderDynamicKPIs();
    drawTopWeatherChart();
    drawBottomWeatherChart();

    track("chart_view", { chart: "weather_advanced", points: weatherRawData.length });

  } catch (error) {
    console.error("Error in loadWeather: ", error);
  }
}

// ===== Análisis Cruzado (Correlación) =====
async function loadAnalysis() {
  const fid = $("select-parcela").value;
  if (!fid) { $("analysis-empty").classList.remove("hidden"); return; }
  const parcel = parcels.find((p) => p.id === fid);
  if (!parcel) { $("analysis-empty").classList.remove("hidden"); return; }
  $("analysis-empty").classList.add("hidden");

  const rI = await api("/vegetation/ndvi", { method: "POST", body: JSON.stringify({ field_id: fid }) });
  const series = rI.ok ? (await rI.json()).series : [];

  let weather = [];
  if (parcel.lat != null) {
    const rW = await api("/weather", { method: "POST", body: JSON.stringify({ field_id: fid }) });
    weather = rW.ok ? (await rW.json()).series : [];
  }
  if (!series.length && !weather.length) { $("analysis-empty").classList.remove("hidden"); return; }

  const weatherMap = new Map(weather.map(w => [w.date, w]));
  const labels = series.map(s => s.date);
  const ndviData = series.map(s => s.mean_value);
  const tempMeanData = series.map(s => {
    const w = weatherMap.get(s.date);
    return w ? w.temp_mean_c : null;
  });
  const precipData = series.map(s => {
    const w = weatherMap.get(s.date);
    return w ? w.precip_mm : null;
  });

  const ctx = $("chart-analysis");
  chartAnalysis?.destroy();
  chartAnalysis = new Chart(ctx, {
    data: {
      labels: labels,
      datasets: [
        { type: "line", label: "NDVI", data: ndviData, borderColor: "#15803d", tension: 0.3, yAxisID: "y" },
        { type: "line", label: "Temp Media (°C)", data: tempMeanData, borderColor: "#f97316", tension: 0.3, yAxisID: "y2" },
        { type: "bar", label: "Precipitación (mm)", data: precipData, backgroundColor: "rgba(59,130,246,0.4)", yAxisID: "y2" }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: { position: "left", min: 0, max: 1, title: { display: true, text: "NDVI" } },
        y2: { position: "right", grid: { drawOnChartArea: false }, title: { display: true, text: "Clima (°C / mm)" } }
      }
    }
  });
  track("chart_view", { chart: "analysis", points: series.length });
}

// ===== Reprocesar Modal =====
function showReprocessModal(preselectIndex = null) {
  const fid = $("select-parcela").value;
  if (!fid) return notify("Selecciona una parcela", "");
  const indices = getParcelIndices(fid);
  setCheckedIndices(".reprocess-index-checkbox", indices);
  if (VALID_INDICES.includes(preselectIndex)) {
    document.querySelectorAll(".reprocess-index-checkbox").forEach((checkbox) => {
      if (checkbox.value === preselectIndex) checkbox.checked = true;
    });
  }
  $("reprocess-indices-error")?.classList.add("hidden");
  $("reprocess-modal").classList.remove("hidden");
  $("reprocess-modal").classList.add("flex");
  $("reprocess-status").classList.add("hidden");
  $("reprocess-status").innerText = "";
  track("reprocess_modal_open", { field_id: fid, indices });
}
function closeReprocessModal() {
  $("reprocess-modal").classList.add("hidden");
  $("reprocess-modal").classList.remove("flex");
}
$("btn-reprocess").addEventListener("click", () => showReprocessModal());
$("btn-close-reprocess").addEventListener("click", closeReprocessModal);
$("btn-cancel-reprocess").addEventListener("click", closeReprocessModal);
$("reprocess-modal").addEventListener("click", (e) => { if (e.target === e.currentTarget) closeReprocessModal(); });
$("btn-reprocess-select-all-indices").addEventListener("click", () => {
  setCheckedIndices(".reprocess-index-checkbox", VALID_INDICES);
});
$("btn-run-reprocess").addEventListener("click", async () => {
  const fid = $("select-parcela").value;
  const mode = document.querySelector('input[name="reprocess-mode"]:checked')?.value || "all";
  const selectedIndices = getCheckedIndices(".reprocess-index-checkbox");
  const indicesError = $("reprocess-indices-error");
  if (mode !== "weather" && !selectedIndices.length) {
    indicesError?.classList.remove("hidden");
    return notify("Falta una variable satelital", "Marca al menos una variable para reprocesar.");
  }
  indicesError?.classList.add("hidden");
  const btn = $("btn-run-reprocess");
  btn.disabled = true; btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Procesando…';
  $("reprocess-status").classList.remove("hidden");
  $("reprocess-status").innerText = "Reprocesando… esto puede tomar varios minutos.";
  const payload = { field_id: fid, mode };
  if (mode !== "weather") payload.indices = selectedIndices;
  track("reprocess_start", { field_id: fid, mode, indices: selectedIndices });
  try {
    const r = await api("/vegetation/reprocess", { method: "POST", body: JSON.stringify(payload) });
    if (r.ok) {
      const data = await r.json();
      const idxCount = data.indices?.length || 0;
      const totalPoints = data.indices?.reduce((s, i) => s + i.points, 0) || 0;
      const mergedIndices = mode === "weather" ? getParcelIndices(fid) : normalizeIndices([...getParcelIndices(fid), ...selectedIndices]);
      const indexSummary = mode === "weather" ? "" : ` (${formatIndices(selectedIndices)})`;
      setParcelIndices(fid, mergedIndices);
      syncSatelliteIndexControls(fid);
      $("reprocess-status").innerText = `Reproceso completado: ${idxCount} índices${indexSummary}, ${totalPoints} puntos.${data.weather ? " Clima actualizado." : ""}`;
      $("reprocess-status").className = "mt-3 text-xs text-emerald-600";
      track("reprocess_done", { field_id: fid, mode, indices: idxCount, points: totalPoints, selected_indices: selectedIndices });
      setTimeout(async () => {
        closeReprocessModal();
        await refreshParcels();
        setParcelIndices(fid, mergedIndices);
        syncSatelliteIndexControls(fid);
        await loadFieldAttributes(fid);
        if (document.querySelector(".tab-content.active")?.id === "tab-satelite") await loadTeledeteccion();
      }, 1500);
    } else {
      const err = await r.json().catch(() => ({}));
      $("reprocess-status").innerText = "Error: " + (err.detail || r.status);
      $("reprocess-status").className = "mt-3 text-xs text-red-600";
      track("reprocess_error", { field_id: fid, mode, status: r.status });
    }
  } catch (e) {
    $("reprocess-status").innerText = "Error de red: " + e;
    $("reprocess-status").className = "mt-3 text-xs text-red-600";
  } finally {
    btn.disabled = false; btn.innerHTML = '<i class="fa-solid fa-play"></i> Ejecutar';
  }
});

// ===== Chat =====
function appendChat(who, text, tools) {
  const div = document.createElement("div");
  const mine = who === "user";
  div.className = "p-3 rounded border max-w-[85%] " + (mine ? "bg-white border-stone-200 ml-auto text-right" : "bg-stone-900 text-stone-100 border-stone-800 text-left");
  div.innerHTML = `<p class="font-bold text-[9px] uppercase mb-1 ${mine ? "text-stone-500" : "text-emerald-400"}">${mine ? "🧑 Tú" : "🤖 Asistente"}${tools && tools.length ? " · " + tools.join(", ") : ""}</p><p class="leading-relaxed whitespace-pre-wrap">${text}</p>`;
  $("chat-history").appendChild(div); $("chat-history").scrollTop = 1e9;
}
async function loadChatHistory() {
  const historyEl = $("chat-history");
  historyEl.innerHTML = '<span class="text-xs text-stone-500">Cargando historial...</span>';
  const fid = $("select-parcela")?.value || "";
  try {
    let url = "/chat/history/" + sessionId;
    if (fid) url += "?field_id=" + fid;
    const r = await api(url);
    if (r.ok) {
      const data = await r.json();
      historyEl.innerHTML = "";
      if (data.length === 0) {
        historyEl.innerHTML = `<p class="text-stone-500">Pregúntame sobre el NDVI, el clima o la densidad de tus parcelas.</p>`;
      } else {
        data.forEach((msg) => {
          appendChat(msg.role, msg.content);
        });
      }
    } else {
      historyEl.innerHTML = '<p class="text-stone-500">Error al cargar historial.</p>';
    }
  } catch (e) {
    historyEl.innerHTML = `<p class="text-stone-500">Error de red al cargar historial: ${e}</p>`;
  }
}
async function sendChat() {
  const msg = $("chat-input").value.trim(); if (!msg) return;
  const fid = $("select-parcela")?.value || null;
  track("chat_send", { len: msg.length, field_id: fid });
  appendChat("user", msg); $("chat-input").value = "";
  try {
    const r = await api("/chat", { method: "POST", body: JSON.stringify({ session_id: sessionId, message: msg, field_id: fid }) });
    if (r.ok) { const d = await r.json(); appendChat("assistant", d.reply, (d.tool_logs || []).map((t) => t.tool)); }
    else { const e = await r.json().catch(() => ({})); appendChat("assistant", "Error: " + (e.detail || r.status)); }
  } catch (e) { appendChat("assistant", "Error de red: " + e); }
}
$("btn-chat").addEventListener("click", sendChat);
$("chat-input").addEventListener("keydown", (e) => { if (e.key === "Enter") sendChat(); });

// ===== Telemetría Modal =====
function openTelemetryModal() {
  $("telemetry-modal").classList.remove("hidden");
  $("telemetry-modal").classList.add("flex");
  $("telemetry-session-id").innerText = sessionId;
  loadTelemetryEvents();
  track("telemetry_open", {});
}
function closeTelemetryModal() {
  $("telemetry-modal").classList.add("hidden");
  $("telemetry-modal").classList.remove("flex");
}
async function loadTelemetryEvents() {
  const content = $("telemetry-content");
  content.innerHTML = '<p class="text-xs text-stone-500">Cargando eventos...</p>';
  try {
    let events = [];
    try {
      const r = await api("/events/all?limit=200");
      if (r.ok) {
        events = await r.json();
      }
    } catch {}
    if (!events || events.length === 0) {
      try {
        const r2 = await api("/events/recent?limit=200");
        if (r2.ok) {
          events = await r2.json();
        }
      } catch {}
    }
    if (!events || events.length === 0) {
      content.innerHTML = '<p class="text-xs text-stone-500">Sin eventos en esta sesión.</p>';
      return;
    }
    renderTelemetryEvents(events, content);
  } catch (e) {
    content.innerHTML = `<p class="text-xs text-red-500">Error al cargar eventos: ${e}</p>`;
  }
}
function renderTelemetryEvents(events, container) {
  const html = events.map((ev) => {
    const ts = ev.created_at || ev.ts || "";
    const time = ts ? new Date(ts).toLocaleTimeString() : "";
    const isError = ev.action.includes("error");
    const bg = isError ? "bg-red-50 border-red-200" : "bg-stone-50 border-stone-200";
    const icon = isError ? "fa-circle-exclamation text-red-500" : "fa-circle-dot text-emerald-500";
    const metaStr = ev.meta && Object.keys(ev.meta).length ? JSON.stringify(ev.meta).slice(0, 120) : "";
    return `<div class="border ${bg} rounded-lg px-3 py-2 text-[10px]">
      <div class="flex items-center gap-2 mb-1">
        <i class="fa-solid ${icon}"></i>
        <span class="font-bold text-stone-700">${ev.action}</span>
        <span class="text-stone-400 ml-auto">${time}</span>
      </div>
      ${metaStr ? `<div class="text-stone-500 font-mono truncate">${metaStr}</div>` : ""}
    </div>`;
  }).join("");
  container.innerHTML = html;
}
$("btn-telemetry").addEventListener("click", openTelemetryModal);
$("btn-close-telemetry").addEventListener("click", closeTelemetryModal);
$("btn-refresh-telemetry").addEventListener("click", loadTelemetryEvents);
$("telemetry-modal").addEventListener("click", (e) => { if (e.target === $("telemetry-modal")) closeTelemetryModal(); });

// ===== Explorador de Datos =====
const TABLES = ["fields", "vegetation_indices", "weather_data", "chat_messages", "events", "plant_counts"];
async function loadDataExplorer() {
  loadSchema();
  const list = $("tables-list");
  list.innerHTML = TABLES.map((t) =>
    `<button data-table="${t}" class="w-full text-left text-xs px-3 py-2 rounded-lg border border-stone-200 bg-stone-50 hover:bg-stone-100 font-semibold text-stone-700"><i class="fa-solid fa-table mr-1 text-emerald-600"></i>${t}</button>`
  ).join("");
  list.querySelectorAll("button").forEach((b) =>
    b.addEventListener("click", () => loadTableData(b.dataset.table))
  );
}
async function loadSchema() {
  const el = $("er-diagram");
  try {
    const r = await api("/data/schema");
    if (!r.ok) { el.innerHTML = '<p class="text-xs text-stone-500">Error al cargar esquema.</p>'; return; }
    const d = await r.json();
    const tables = d.tables || {};
    const shortType = (t) => {
      if (t.includes("timestamp")) return "timestamptz";
      if (t.includes("double")) return "float";
      if (t === "USER-DEFINED") return "geometry";
      return t;
    };
    let mmd = "erDiagram\n";
    for (const [name, cols] of Object.entries(tables)) {
      mmd += `  ${name} {\n`;
      for (const c of cols) {
        const ann = c.name === "id" ? " PK" : c.name.endsWith("_id") ? " FK" : "";
        mmd += `    ${shortType(c.type)} ${c.name}${ann}\n`;
      }
      mmd += "  }\n";
    }
    mmd += '  fields ||--o{ vegetation_indices : "tiene"\n';
    mmd += '  fields ||--o{ weather_data : "registra clima"\n';
    mmd += '  fields ||--o{ plant_counts : "tiene"\n';
    mmd += '  fields ||--o{ events : "genera"\n';
    mmd += '  fields ||--o{ chat_messages : "genera"\n';
    const id = "er-" + Date.now();
    const { svg } = await mermaid.render(id, mmd);
    el.innerHTML = svg;
  } catch (e) {
    el.innerHTML = '<p class="text-xs text-red-500">Error al renderizar diagrama ER: ' + String(e?.message || e) + '</p>';
  }
}
async function loadTableData(table) {
  $("data-view-title").innerText = `Tabla: ${table}`;
  $("data-view-content").innerHTML = '<p class="text-xs text-stone-500">Cargando...</p>';
  try {
    const r = await api(`/data/${table}`);
    if (!r.ok) { $("data-view-content").innerHTML = '<p class="text-xs text-red-500">Error al cargar. Verifica credenciales.</p>'; return; }
    const d = await r.json();
    const rows = d.rows || [];
    $("data-view-count").innerText = `${rows.length} registros`;
    if (!rows.length) { $("data-view-content").innerHTML = '<p class="text-xs text-stone-500">Sin registros.</p>'; return; }
    const cols = Object.keys(rows[0]);
    const html = `<table class="w-full text-[10px] border-collapse"><thead><tr>${cols.map((c) => `<th class="border border-stone-200 px-2 py-1 bg-stone-100 font-bold text-stone-700">${c}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${cols.map((c) => `<td class="border border-stone-200 px-2 py-1">${formatCell(row[c])}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
    $("data-view-content").innerHTML = html;
  } catch (e) { $("data-view-content").innerHTML = `<p class="text-xs text-red-500">Error: ${e}</p>`; }
}
function formatCell(v) {
  if (v === null || v === undefined) return '<span class="text-stone-400">NULL</span>';
  if (typeof v === "object") return `<code class="text-[9px] bg-stone-100 px-1 rounded">${JSON.stringify(v).slice(0, 80)}</code>`;
  return String(v).slice(0, 100);
}
$("btn-run-query").addEventListener("click", async () => {
  const sql = $("sql-query").value.trim();
  if (!sql) return notify("Falta la consulta", "Escribe una consulta SQL.");
  $("query-result").innerHTML = '<p class="text-xs text-stone-500">Ejecutando...</p>';
  try {
    const r = await api("/data/query", { method: "POST", body: JSON.stringify({ sql }) });
    if (!r.ok) { const e = await r.json().catch(() => ({})); $("query-result").innerHTML = `<p class="text-xs text-red-500">Error: ${e.detail || r.status}</p>`; return; }
    const d = await r.json();
    const rows = d.rows || [];
    if (!rows.length) { $("query-result").innerHTML = '<p class="text-xs text-stone-500">Sin registros.</p>'; return; }
    const cols = Object.keys(rows[0]);
    const html = `<table class="w-full text-[10px] border-collapse"><thead><tr>${cols.map((c) => `<th class="border border-stone-200 px-2 py-1 bg-stone-100 font-bold text-stone-700">${c}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${cols.map((c) => `<td class="border border-stone-200 px-2 py-1">${formatCell(row[c])}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
    $("query-result").innerHTML = html;
  } catch (e) { $("query-result").innerHTML = `<p class="text-xs text-red-500">Error: ${e}</p>`; }
});
$("btn-clear-query").addEventListener("click", () => { $("sql-query").value = ""; $("query-result").innerHTML = ""; });

// ===== Credenciales =====
async function connectUserDatabase() {
  if (!creds.dbUrl) return null;
  track("connect_db_attempt", {});
  try {
    const r = await fetch("./api/credentials/connect-db", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ database_url: creds.dbUrl })
    });
    if (!r.ok) {
      const e = await r.json().catch(() => ({}));
      track("connect_db_error", { status: r.status });
      notify(
        r.status === 404 ? "Auto-conexión no disponible" : "Error al conectar la base de datos",
        r.status === 404
          ? "El backend todavía no expone connect-db (pendiente Fase 9)."
          : (e.detail || `Error ${r.status} al conectar con tu Supabase.`)
      );
      return null;
    }
    const data = await r.json();
    const migraciones = Array.isArray(data.migrations_applied) ? data.migrations_applied.length : 0;
    if (migraciones > 0) {
      notify("Esquema inicializado", `Se creó la arquitectura PostGIS automáticamente (${migraciones} migración(es) aplicadas).`);
    } else if ((data.existing_parcels ?? 0) > 0) {
      notify("Base de datos conectada", `Se detectaron ${data.existing_parcels} parcela(s) existentes en tu Supabase.`);
    } else {
      notify("Base de datos conectada", "Tu Supabase se conectó correctamente.");
    }
    track("connect_db_success", { migraciones, existing_parcels: data.existing_parcels ?? 0 });
    updateStatus();
    return data;
  } catch (e) {
    track("connect_db_error", { error: String(e) });
    notify("Error de red", `No se pudo conectar a tu base de datos: ${e}`);
    return null;
  }
}

$("btn-save-creds").addEventListener("click", async () => {
  creds = { groq: $("in-groq").value, copId: $("in-copid").value, copSecret: $("in-copsecret").value, sbUrl: $("in-sburl").value, sbKey: $("in-sbkey").value, dbUrl: $("cred-db-url").value };
  const n = Object.values(creds).filter(Boolean).length;
  track("creds_set", { count: n });
  $("creds-state").innerText = `${n} llave(s) activas (se borran al refrescar)`;
  notify("Credenciales en sesión", `${n} llave(s) activas solo en esta sesión.`);
  updateStatus();
  checkMissingCredentials();
  await connectUserDatabase();
  await refreshParcels();
  await connectUserProfile();
});
$("btn-check-env").addEventListener("click", async () => {
  try {
    const r = await fetch("./api/credentials/status");
    if (!r.ok) return notify("No disponible", "No se pudo consultar el .env del servidor.");
    const s = await r.json();
    appEnv = s.env || "development";
    const have = Object.entries({ Groq: s.groq, Copernicus: s.copernicus, Supabase: s.supabase }).filter(([, v]) => v).map(([k]) => k);
    track("env_check", { have, env: appEnv });
    if (appEnv === "production") {
      $("env-status").innerHTML = " <b>Producción:</b> cada usuario debe ingresar sus propias credenciales.";
    } else {
      $("env-status").innerHTML = have.length
        ? `✅ En el servidor (.env): <b>${have.join(", ")}</b>. Se usan automáticamente; no necesitas reescribirlas aquí.`
        : "No se detectaron credenciales en el .env del servidor.";
    }
  } catch { notify("Error", "No se pudo consultar el .env del servidor."); }
});

// ===== Perfiles y Modos de Sesión =====
$("btn-profile-menu").addEventListener("click", (e) => {
  e.stopPropagation();
  $("profile-dropdown").classList.toggle("hidden");
});
document.addEventListener("click", () => {
  $("profile-dropdown").classList.add("hidden");
});
$("profile-dropdown").addEventListener("click", (e) => {
  e.stopPropagation();
});

document.querySelectorAll(".dropdown-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    $("profile-dropdown").classList.add("hidden");
    switchTab(btn.dataset.action);
  });
});
$("dropdown-telemetry").addEventListener("click", () => {
  $("profile-dropdown").classList.add("hidden");
  openTelemetryModal();
});
$("dropdown-logout").addEventListener("click", () => {
  $("profile-dropdown").classList.add("hidden");
  logout();
});

$("btn-save-settings").addEventListener("click", async () => {
  if (isSharedMode) return notify("Modo compartido", "No puedes editar ajustes en modo de solo lectura.");
  const displayName = $("settings-display-name").value.trim();
  const sessionMode = $("settings-session-mode").value;
  const cfgDbUrl = ($("cfg-db-url")?.value || "").trim();
  if (cfgDbUrl) {
    creds.dbUrl = cfgDbUrl;
    updateStatus();
  }
  if (!displayName) return notify("Falta el nombre", "Escribe un nombre para el perfil.");
  if (!profileId) return notify("Error", "No hay un perfil conectado.");

  try {
    track("profile_update_attempt", { displayName, sessionMode });
    const r = await api(`/profiles/${profileId}`, {
      method: "PATCH",
      body: JSON.stringify({
        display_name: displayName,
        session_mode: sessionMode
      })
    });
    if (r.ok) {
      currentProfile = await r.json();
      notify("Ajustes guardados", "El perfil se ha actualizado correctamente.");
      updateProfileUI();
      if (sessionMode === "saved") {
        localStorage.setItem("agrovision_profile_id", profileId);
      } else {
        localStorage.removeItem("agrovision_profile_id");
      }
      track("profile_update_success", { displayName, sessionMode });
      if (creds.dbUrl) {
        await connectUserDatabase();
        await refreshParcels();
      }
    } else {
      const e = await r.json().catch(() => ({}));
      notify("Error " + r.status, e.detail || "No se pudo actualizar el perfil.");
    }
  } catch (e) {
    notify("Error de red", String(e));
  }
});

$("btn-delete-profile").addEventListener("click", async () => {
  if (isSharedMode) return notify("Modo compartido", "No puedes eliminar perfiles en modo de solo lectura.");
  if (!profileId) return;
  if (!confirm("¿Estás seguro de que deseas eliminar permanentemente tu perfil? Se perderán todas tus preferencias.")) return;

  try {
    track("profile_delete_attempt", { profileId });
    const r = await api(`/profiles/${profileId}`, { method: "DELETE" });
    if (r.ok) {
      track("profile_delete_success", { profileId });
      notify("Perfil eliminado", "Tu perfil ha sido eliminado. Volviendo a sesión efímera.");
      logout();
    } else {
      const e = await r.json().catch(() => ({}));
      notify("Error " + r.status, e.detail || "No se pudo eliminar el perfil.");
    }
  } catch (e) {
    notify("Error de red", String(e));
  }
});

function logout() {
  track("session_logout", { profileId });
  localStorage.removeItem("agrovision_profile_id");
  profileId = null;
  currentProfile = null;
  creds = {};
  $("in-groq").value = "";
  $("in-copid").value = "";
  $("in-copsecret").value = "";
  $("in-sburl").value = "";
  $("in-sbkey").value = "";
  $("cred-db-url").value = "";
  $("cfg-db-url").value = "";
  $("creds-state").innerText = "0 llaves activas (se borran al refrescar)";
  $("settings-display-name").value = "Agrónomo";
  $("settings-session-mode").value = "ephemeral";
  updateProfileUI();
  updateStatus();
  checkMissingCredentials();
  refreshParcels();
  switchTab("tab-resumen");
  notify("Sesión cerrada", "Se han limpiado todas las llaves y preferencias.");
}

async function connectUserProfile() {
  if (isSharedMode) return;
  let sbUrl = creds.sbUrl || creds.dbUrl;
  if (!sbUrl) {
    try {
      const r = await fetch("./api/credentials/status", { headers: authHeaders() });
      if (r.ok) {
        const s = await r.json();
        if (s.supabase_url) sbUrl = s.supabase_url;
      }
    } catch {}
  }
  if (!sbUrl) {
    profileId = null;
    currentProfile = null;
    updateProfileUI();
    return;
  }
  try {
    fingerprint = await sha256(sbUrl);
    track("profile_connect_attempt", { hash: fingerprint });
    const r = await fetch("./api/profiles/connect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ supabase_url_hash: fingerprint, display_name: $("settings-display-name").value || "Agrónomo" })
    });
    if (r.ok) {
      currentProfile = await r.json();
      profileId = currentProfile.id;
      updateProfileUI();
      if (currentProfile.active_field_id) {
        localStorage.setItem("agrovision_last_field_id", currentProfile.active_field_id);
      }
      if (currentProfile.session_mode === "saved") {
        localStorage.setItem("agrovision_profile_id", profileId);
      } else {
        localStorage.removeItem("agrovision_profile_id");
      }
      track("profile_connect_success", { profileId, mode: currentProfile.session_mode });
    }
  } catch (e) {
    track("profile_connect_error", { error: String(e) });
  }
}

async function loadSharedProfile(id) {
  isSharedMode = true;
  profileId = id;
  track("shared_mode_start", { profileId });

  document.body.classList.add("shared-read-only");
  $("btn-save-parcela").disabled = true;
  $("btn-save-parcela").classList.add("opacity-50", "cursor-not-allowed");
  $("btn-demo").style.display = "none";
  $("btn-save-creds").style.display = "none";
  $("btn-save-settings").style.display = "none";
  $("btn-delete-profile").style.display = "none";

  const droneBtn = document.querySelector('[data-tab="tab-vision"]');
  if (droneBtn) droneBtn.style.display = "none";
  const settingsBtn = document.querySelector('[data-action="tab-settings"]');
  if (settingsBtn) settingsBtn.style.display = "none";
  const logoutBtn = $("dropdown-logout");
  if (logoutBtn) logoutBtn.style.display = "none";
  $("btn-telemetry").style.display = "none";

  try {
    const r = await fetch(`./api/profiles/${id}`);
    if (r.ok) {
      currentProfile = await r.json();
      updateProfileUI();
      notify("Modo compartido", `Visualizando perfil de: ${currentProfile.display_name}`);
    } else {
      notify("Error", "No se pudo cargar el perfil compartido.");
    }
  } catch (e) {
    notify("Error de red", String(e));
  }
}

function updateProfileUI() {
  if (currentProfile) {
    $("user-display-name").innerText = currentProfile.display_name;
    $("avatar-circle").innerText = currentProfile.display_name.slice(0, 2).toUpperCase();
    $("settings-display-name").value = currentProfile.display_name;
    $("settings-session-mode").value = currentProfile.session_mode;

    let modeText = "Sesión efímera (BYOK)";
    if (isSharedMode) {
      modeText = "Modo compartido (Lectura)";
    } else if (currentProfile.session_mode === "saved") {
      modeText = "Modo guardado temporal";
    }
    $("user-session-mode").innerText = modeText;

    // Sincronizar con widget flotante
    if ($("floating-user-name")) $("floating-user-name").innerText = currentProfile.display_name;
    if ($("floating-avatar")) $("floating-avatar").innerText = currentProfile.display_name.slice(0, 2).toUpperCase();
    if ($("floating-user-email")) {
      $("floating-user-email").innerText = currentProfile.display_name.toLowerCase().replace(/\s+/g, "") === "alexprieto"
        ? "alexprieto1997@gmail.com"
        : `${currentProfile.display_name.toLowerCase().replace(/\s+/g, ".")}@agrovision.com`;
    }
  } else {
    $("user-display-name").innerText = "Agrónomo";
    $("avatar-circle").innerText = "AG";
    $("settings-display-name").value = "Agrónomo";
    $("settings-session-mode").value = "ephemeral";
    $("user-session-mode").innerText = "Sesión efímera (BYOK)";

    // Valores por defecto para widget flotante
    if ($("floating-user-name")) $("floating-user-name").innerText = "Agrónomo";
    if ($("floating-avatar")) $("floating-avatar").innerText = "AG";
    if ($("floating-user-email")) $("floating-user-email").innerText = "alexprieto1997@gmail.com";
  }
}

async function checkMissingCredentials() {
  try {
    const r = await fetch("./api/credentials/status", { headers: authHeaders() });
    if (!r.ok) return;
    const s = await r.json();
    appEnv = s.env || "development";

    if (appEnv === "production") {
      const missing = [];
      const hasGroq = creds.groq || s.groq;
      const hasCop = (creds.copId && creds.copSecret) || s.copernicus;
      const hasSb = Boolean(creds.dbUrl || (creds.sbUrl && creds.sbKey) || s.supabase);

      if (!hasGroq) missing.push("Groq API Key");
      if (!hasCop) missing.push("Copernicus Credentials");
      if (!hasSb) missing.push("Supabase Connection");

      const toast = $("creds-toast-warning");
      if (missing.length > 0) {
        toast.innerHTML = `<div class="bg-amber-500 text-stone-950 p-4 rounded-xl shadow-2xl border border-amber-400 flex flex-col gap-2">
          <div class="flex items-center gap-2">
            <i class="fa-solid fa-triangle-exclamation text-lg"></i>
            <span class="font-bold text-xs">Faltan credenciales críticas:</span>
          </div>
          <p class="text-[10px] text-stone-900 leading-tight">Para la funcionalidad completa necesitas configurar: ${missing.join(", ")}.</p>
          <button onclick="switchTab('tab-config')" class="mt-1 bg-stone-900 text-amber-400 font-bold text-[10px] px-3 py-1.5 rounded-lg border border-stone-800 hover:bg-stone-800 transition-all">
            Configurar Credenciales
          </button>
        </div>`;
        toast.classList.remove("hidden");
      } else {
        toast.classList.add("hidden");
      }
    }
  } catch {}
}

// ===== Sincronización del Selector de Parcela =====
$("select-parcela").addEventListener("change", async () => {
  const fid = $("select-parcela").value;
  if (fid) {
    localStorage.setItem("agrovision_last_field_id", fid);
    loadFieldAttributes(fid);
    syncSatelliteIndexControls(fid);
    if (profileId && !isSharedMode) {
      try {
        await api(`/profiles/${profileId}`, {
          method: "PATCH",
          body: JSON.stringify({ active_field_id: fid })
        });
      } catch {}
    }
  } else {
    clearFieldAttributes();
  }

  const active = document.querySelector(".tab-content.active")?.id;
  if (active === "tab-satelite") loadTeledeteccion();
  else if (active === "tab-weather") loadWeather();
  else if (active === "tab-analysis") loadAnalysis();
  else loadResumen();
});

(async function init() {
  track("session_start", { w: window.innerWidth, h: window.innerHeight });

  const hashParams = new URLSearchParams(location.hash.slice(1));
  const sharedProfileId = hashParams.get("profile");

  try {
    const r = await fetch("./api/status");
    backendOk = r.ok;
    $("db-status-text").innerText = backendOk ? "Backend conectado" : "Backend no disponible";
    if (backendOk) { $("db-status-text").classList.replace("text-stone-400", "text-emerald-400"); }
  } catch { $("db-status-text").innerText = "Backend no disponible"; }

  try {
    const r = await fetch("./api/credentials/status");
    if (r.ok) {
      const s = await r.json();
      appEnv = s.env || "development";
      if (appEnv === "production") {
        $("creds-production-warning").classList.remove("hidden");
        $("btn-check-env").style.display = "none";
      }
    }
  } catch {}

  if (sharedProfileId) {
    await loadSharedProfile(sharedProfileId);
  } else {
    const savedProfileId = localStorage.getItem("agrovision_profile_id");
    if (savedProfileId) {
      try {
        const r = await fetch(`./api/profiles/${savedProfileId}`);
        if (r.ok) {
          currentProfile = await r.json();
          profileId = currentProfile.id;
          updateProfileUI();
          track("profile_reconnect_success", { profileId });
        } else {
          localStorage.removeItem("agrovision_profile_id");
        }
      } catch (e) {
        track("profile_reconnect_error", { error: String(e) });
      }
    } else {
      await connectUserProfile();
    }
  }

  updateStatus();
  checkMissingCredentials();
  await refreshParcels();

  const lastFieldId = localStorage.getItem("agrovision_last_field_id") || (currentProfile ? currentProfile.active_field_id : null);
  if (lastFieldId && $("select-parcela").querySelector(`option[value="${lastFieldId}"]`)) {
    $("select-parcela").value = lastFieldId;
    loadFieldAttributes(lastFieldId);
  }

  const initialFieldId = $("select-parcela").value;
  if (initialFieldId) syncSatelliteIndexControls(initialFieldId);

  let initial = "tab-resumen";
  if (location.hash && location.hash.startsWith("#tab-")) {
    initial = location.hash.slice(1);
  }
  switchTab(document.getElementById(initial) ? initial : "tab-resumen");
})();
