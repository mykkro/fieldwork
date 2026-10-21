import { createLayer, kmlToGeoJSON } from "./toolkit.js";
const $ = (s) => document.querySelector(s),
  map = L.map("map", { zoomControl: false }).setView([50.0755, 14.4378], 11);
const zoomControl = L.control.zoom({ position: "topright" }).addTo(map);
const scaleControl = L.control.scale({ position: "bottomleft", imperial: false }).addTo(map);
let config,
  locationId,
  base,
  events,
  backend = false,
  generation = 0,
  aborter;
const states = new Map();
function notice(t) {
  $("#notice").textContent = t;
  $("#notice").hidden = !t;
}
function inspect(p) {
  $("#inspector-title").textContent = p.name || "Feature details";
  $("#inspector").textContent =
    Object.entries(p)
      .filter(([k]) => k !== "name")
      .map(
        ([k, v]) => k + ": " + (typeof v === "object" ? JSON.stringify(v) : v),
      )
      .join(" · ") || "No additional properties";
}
function summaries() {
  const box = $("#summaries");
  box.replaceChildren();
  for (const s of states.values()) {
    if (!s.def.enabled || !s.data?.summary) continue;
    const row = document.createElement("div"),
      label = document.createElement("span"),
      v = document.createElement("b");
    label.textContent = s.data.summary.label;
    v.textContent = s.data.summary.value;
    row.append(label, v);
    box.append(row);
  }
  const legend = $("#legend");
  legend.replaceChildren();
  for (const {def,data} of states.values()) {
    if (!def.enabled || def.type !== "grid" || !data) continue;
    const section = document.createElement("section"); section.className = "scalar-legend";
    const title = document.createElement("div"); title.textContent = def.name;
    const unit = document.createElement("span"); unit.textContent = data.unit || ""; title.append(unit);
    const gradient = document.createElement("div"); gradient.className = "gradient";
    if(def.palette) gradient.style.background = "linear-gradient(90deg,"+def.palette.join(",")+")";
    const labels = document.createElement("div"); labels.className = "legend-labels";
    const range = def.range || (data.unit === "m" ? [150,700] : [12,30]);
    for(let i=0;i<4;i++){const label=document.createElement("span");label.textContent=Math.round(range[0]+(range[1]-range[0])*i/3);labels.append(label);}
    section.append(title,gradient,labels);legend.append(section);
  }
  legend.hidden = config.ui?.legend === false || !legend.children.length;
}
function render(s, data) {
  const next = createLayer(s.def, data, inspect);
  if (s.layer) map.removeLayer(s.layer);
  s.data = data;
  s.layer = next;
  if (s.def.enabled) next.addTo(map);
  s.status.textContent = s.def.description || s.def.type;
  summaries();
}
async function load(s, version = generation) {
  if (["xyz", "wms"].includes(s.def.type)) {
    render(s, null);
    return;
  }
  s.status.textContent = "Loading…";
  try {
    let url = s.def.url;
    if (!backend && url.startsWith("/api/data/"))
      url = "static/demo/" + locationId + "/" + s.def.id + ".json";
    else if (url.startsWith("/api/data/")) {
      const parsed = new URL(url, window.location.href);
      parsed.searchParams.set("location", locationId);
      url = parsed.href;
    }
    const r = await fetch(url, { signal: aborter?.signal });
    if (!r.ok) throw Error("HTTP " + r.status);
    const data =
      s.def.type === "kml" ? kmlToGeoJSON(await r.text()) : await r.json();
    if (version === generation) render(s, data);
  } catch (e) {
    if (e.name === "AbortError") return;
    s.status.textContent = "Unavailable: " + e.message;
    notice(s.def.name + ": " + e.message);
  }
}
function add(def) {
  const row = document.createElement("div");
  row.className = "layer";
  row.style.setProperty("--layer-color", def.color || "#60825a");
  const head = document.createElement("div");
  head.className = "layer-head";
  const icon = document.createElement("span");
  icon.className = "layer-symbol";
  icon.textContent = {
    grid: "▦",
    wind: "≋",
    geojson: "⌾",
    kml: "⌁",
    xyz: "▧",
    wms: "▧",
  }[def.type];
  const copy = document.createElement("div");
  copy.className = "layer-copy";
  const title = document.createElement("b"),
    status = document.createElement("small");
  title.textContent = def.name;
  status.textContent = def.description || def.type;
  copy.append(title, status);
  const toggle = document.createElement("input");
  toggle.type = "checkbox";
  toggle.className = "switch";
  toggle.checked = def.enabled;
  toggle.setAttribute("aria-label", "Show " + def.name);
  head.append(icon, copy, toggle);
  const opacity = document.createElement("div");
  opacity.className = "opacity-row";
  const range = document.createElement("input");
  range.type = "range";
  range.min = 0;
  range.max = 100;
  range.value = Math.round(def.opacity * 100);
  range.setAttribute("aria-label", def.name + " opacity");
  const v = document.createElement("span");
  v.textContent = range.value + "%";
  opacity.append(range, v);
  row.append(head, opacity);
  let windControls;
  if (def.type === "wind") {
    windControls = document.createElement("div");
    windControls.className = "wind-controls";
    const update = () => s.layer?.setWindStyle({color: def.color, windStyle: def.windStyle, windSize: def.windSize, windWidth: def.windWidth, windReference: def.windReference});
    const field = (title, input) => {
      const label = document.createElement("label");
      label.textContent = title;
      input.setAttribute("aria-label", def.name + " " + title.toLowerCase());
      label.append(input);
      windControls.append(label);
    };
    def.color ||= "#164d63";
    def.windStyle ||= "arrows";
    def.windSize ??= 18;
    def.windWidth ??= 2.4;
    def.windReference ??= 5;
    const style = document.createElement("select");
    for (const [value, text] of [["arrows", "Arrows"], ["streamlines", "Streamlines"], ["trails", "Stream trails"], ["dots", "Particles"]]) {
      const option = document.createElement("option"); option.value = value; option.textContent = text; style.append(option);
    }
    style.value = def.windStyle;
    style.onchange = () => {def.windStyle = style.value; update();};
    field("Style", style);
    const color = document.createElement("input"); color.type = "color"; color.value = def.color;
    color.oninput = () => {def.color = color.value; row.style.setProperty("--layer-color", def.color); update();};
    field("Color", color);
    for (const [title, key, min, max, step] of [["Size", "windSize", 6, 40, 1], ["Width", "windWidth", 1, 6, 0.2], ["Reference speed", "windReference", 1, 20, 0.5]]) {
      const input = document.createElement("input"); input.type = "range"; input.min = min; input.max = max; input.step = step; input.value = def[key];
      const unit = key === "windReference" ? " m/s" : " px";
      const output = document.createElement("output"); output.textContent = def[key] + unit;
      input.oninput = () => {def[key] = Number(input.value); output.textContent = input.value + unit; update();};
      field(title, input); input.parentElement.append(output);
    }
    const hint = document.createElement("small");
    hint.textContent = "Size and width apply at reference speed. Faster winds have larger arrows (up to 3x length). Streamlines follow the current field; Size sets their reach.";
    hint.style.lineHeight = "1.5";
    windControls.append(hint);
    windControls.hidden = !def.enabled;
    row.append(windControls);
  }
  $("#layers").append(row);
  const s = { def, status };
  states.set(def.id, s);
  toggle.onchange = () => {
    def.enabled = toggle.checked;
    if (s.layer) {
      if (def.enabled) s.layer.addTo(map);
      else map.removeLayer(s.layer);
    } else if (def.enabled) load(s);
    opacity.hidden = !def.enabled;
    if (windControls) windControls.hidden = !def.enabled;
    summaries();
  };
  range.oninput = () => {
    def.opacity = range.value / 100;
    v.textContent = range.value + "%";
    if (s.layer?.setOpacity) s.layer.setOpacity(def.opacity);
    else if (s.layer?.setStyle)
      s.layer.setStyle({ opacity: def.opacity, fillOpacity: def.opacity });
  };
  opacity.hidden = !def.enabled;
  return s;
}
function chooseBase(d) {
  if (base) map.removeLayer(base);
  base =
    d.type === "wms"
      ? L.tileLayer.wms(d.url, {
          layers: d.layers,
          format: "image/jpeg",
          attribution: d.attribution,
          maxZoom: d.maxZoom,
        })
      : L.tileLayer(d.url, { attribution: d.attribution, maxZoom: d.maxZoom });
  base.addTo(map);
  let reported = false;
  base.on("tileerror", () => {
    if (!reported) {
      notice(
        "Some basemap tiles could not load. Check connectivity or choose another base map.",
      );
      reported = true;
    }
  });
  for (const b of document.querySelectorAll(".base"))
    b.classList.toggle("active", b.dataset.id === d.id);
}
function stop() {
  events?.close();
  events = null;
  $("#stream").setAttribute("aria-pressed", "false");
  $("#stream").innerHTML = "▶ <span>Start live</span>";
  $("#feed-dot").classList.add("muted");
}
async function select() {
  stop();
  aborter?.abort();
  aborter = new AbortController();
  generation++;
  locationId = $("#location").value;
  const p = config.locations.find((l) => l.id === locationId);
  map.setView(p.center, p.zoom);
  $("#map-location").textContent = p.name;
  notice("");
  for (const s of states.values()) {
    if (s.layer) map.removeLayer(s.layer);
    s.layer = null;
    s.data = null;
  }
  await Promise.all([...states.values()].map((s) => load(s)));
  $("#update").textContent = "Snapshot ready";
  if (config.live && backend) $("#stream").click();
}
$("#stream").onclick = () => {
  if (events) {
    stop();
    return;
  }
  if (!backend) {
    notice(
      "Live mode needs Python. Run python app.py; static snapshots remain available here.",
    );
    return;
  }
  events = new EventSource(
    "/api/events?location=" + encodeURIComponent(locationId),
  );
  $("#stream").setAttribute("aria-pressed", "true");
  $("#stream").innerHTML = "Ⅱ <span>Pause live</span>";
  events.onmessage = (e) => {
    try {
      for (const [id, data] of Object.entries(JSON.parse(e.data))) {
        const s = states.get(id);
        if (s) render(s, data);
      }
      $("#update").textContent = "Updated " + new Date().toLocaleTimeString();
      $("#feed-dot").classList.remove("muted");
      $("#transport").textContent = "Server-Sent Events · 3 s cadence";
    } catch (err) {
      notice("Stream frame rejected: " + err.message);
    }
  };
  events.onerror = () => {
    $("#transport").textContent = "Connection lost · reconnecting…";
    $("#feed-dot").classList.add("muted");
  };
};
$("#fit").onclick = () => {
  const p = config.locations.find((l) => l.id === locationId);
  map.setView(p.center, p.zoom);
};
$("#location").onchange = select;
$("#add").onclick = () => $("#source-dialog").showModal();
$("#close-dialog").onclick = () => $("#source-dialog").close();
$("#source-form").onsubmit = (e) => {
  e.preventDefault();
  const f = new FormData(e.target),
    url = f.get("url").trim();
  try {
    if (
      !["http:", "https:"].includes(new URL(url, window.location.href).protocol)
    )
      throw Error("Use HTTP or HTTPS");
    const type = f.get("type");
    if (type === "wms" && !f.get("detail").trim())
      throw Error("WMS layer name required");
    load(
      add({
        id: "custom-" + Date.now(),
        name: f.get("name"),
        type,
        url,
        enabled: true,
        opacity: 0.8,
        color: "#7564cd",
        description: "Custom provider",
        layers: type === "wms" ? f.get("detail") : undefined,
        attribution: type === "xyz" ? f.get("detail") : undefined,
      }),
    );
    $("#source-dialog").close();
    e.target.reset();
  } catch (err) {
    notice(err.message);
  }
};
function applyUI() {
  const embed = new URLSearchParams(location.search).get("embed") === "1";
  const ui = {header: true, sidebar: true, location: true, recenter: true, inspector: true, toolbar: true, legend: true, zoom: true, scale: true, ...config.ui};
  if (embed) for (const key of ["header", "sidebar", "location", "recenter", "inspector", "toolbar", "legend"]) ui[key] = false;
  config.ui = ui;
  for (const [key, selector] of Object.entries({header:"header", sidebar:"aside", location:".map-title", recenter:"#fit", inspector:".map-caption", toolbar:".timeline", legend:"#legend"})) $(selector).hidden = !ui[key];
  document.body.classList.toggle("no-header", !ui.header);
  document.body.classList.toggle("no-sidebar", !ui.sidebar);
  document.body.classList.toggle("no-toolbar", !ui.toolbar);
  if (!ui.zoom) map.removeControl(zoomControl);
  if (!ui.scale) map.removeControl(scaleControl);
  map.invalidateSize();
}
async function init() {
  try {
    const configURL = new URLSearchParams(location.search).get("config") || "config.json";
    const r = await fetch(configURL);
    if (!r.ok) throw Error("Could not read config.json");
    config = await r.json();
    applyUI();
    if (config.dataNote) $(".observations p").textContent = config.dataNote;
    try {
      const p = await fetch("api/config");
      backend =
        p.ok &&
        (p.headers.get("content-type") || "").includes("application/json");
    } catch {}
    $("#mode").textContent = backend ? "● Python connected" : "● Static mode";
    $("#transport").textContent = backend
      ? "REST snapshots · live feed available"
      : "Bundled snapshots · no backend";
    for (const p of config.locations) {
      const o = document.createElement("option");
      o.value = p.id;
      o.textContent = p.name;
      $("#location").append(o);
    }
    for (const d of config.basemaps) {
      const b = document.createElement("button");
      b.className = "base " + d.id;
      b.dataset.id = d.id;
      const sw = document.createElement("div");
      sw.className = "map-swatch";
      const n = document.createElement("span");
      n.textContent = d.name;
      b.append(sw, n);
      b.onclick = () => {
        notice("");
        chooseBase(d);
      };
      $("#basemaps").append(b);
    }
    if (config.initialLocation) $("#location").value = config.initialLocation;
    if (!$("#location").value) throw Error("Unknown initialLocation or empty locations");
    chooseBase(config.basemaps.find(b=>b.id===config.initialBasemap) || config.basemaps[0]);
    for (const d of config.layers) add({ ...d });
    await select();
  } catch (e) {
    notice(
      "Initialization failed: " +
        e.message +
        ". Serve the directory over HTTP.",
    );
  }
}
init();
