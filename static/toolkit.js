/* Reusable Leaflet adapters. Payload coordinates are longitude, latitude. */
export function validateGrid(d, wind = false) {
  const { width: w, height: h, bbox: b } = d;
  if (
    d.crs !== "EPSG:4326" ||
    d.rowOrder !== "south-to-north" ||
    !Number.isInteger(w) ||
    !Number.isInteger(h) ||
    w < 2 ||
    h < 2 ||
    w > 512 ||
    h > 512 ||
    !Array.isArray(b) ||
    b.length !== 4 ||
    !b.every(Number.isFinite) ||
    b[0] >= b[2] ||
    b[1] >= b[3]
  )
    throw Error("Invalid grid metadata");
  for (const k of wind ? ["u", "v"] : ["values"])
    if (
      !Array.isArray(d[k]) ||
      d[k].length !== w * h ||
      !d[k].every((v) => v === null || Number.isFinite(v))
    )
      throw Error("Invalid grid " + k);
  return d;
}
export function gridSample(d, lat, lon, k = "values") {
  const [w, s, e, n] = d.bbox;
  if (lon < w || lon > e || lat < s || lat > n) return null;
  return d[k][
    Math.round(((lat - s) / (n - s)) * (d.height - 1)) * d.width +
      Math.round(((lon - w) / (e - w)) * (d.width - 1))
  ];
}
// Bilinear interpolation avoids cell-boundary kinks in integrated streamlines.
export function sampleWind(d, lat, lon) {
  const [w, s, e, n] = d.bbox;
  if (lon < w || lon > e || lat < s || lat > n) return null;
  const x = (lon-w)/(e-w)*(d.width-1), y = (lat-s)/(n-s)*(d.height-1);
  const ix = Math.min(d.width-2, Math.floor(x)), iy = Math.min(d.height-2, Math.floor(y));
  const fx = x-ix, fy = y-iy;
  const indices = [iy*d.width+ix, iy*d.width+ix+1, (iy+1)*d.width+ix, (iy+1)*d.width+ix+1];
  const weights = [(1-fx)*(1-fy), fx*(1-fy), (1-fx)*fy, fx*fy];
  const values = [];
  for (const key of ["u", "v"]) {
    let value = 0;
    for (let i=0; i<4; i++) {
      if (weights[i] === 0) continue;
      if (d[key][indices[i]] === null) return null;
      value += d[key][indices[i]] * weights[i];
    }
    values.push(value);
  }
  return values;
}
export function windGlyph(speed, size, width, reference = 5) {
  const ratio = Math.min(3, Math.max(0, speed) / Math.max(0.1, reference));
  return {length: size * ratio, width: width * Math.max(0.35, Math.sqrt(ratio))};
}
// Midpoint (RK2) integration of an instantaneous field in Mercator screen space.
export function traceStreamline(data, map, seed, direction=1, maxSteps=90, step=4) {
  const points = [seed];
  const heading = (p) => {
    const ll = map.containerPointToLatLng(p), uv = sampleWind(data, ll.lat, ll.lng);
    if (!uv) return null;
    const speed = Math.hypot(...uv);
    return speed < 0.01 ? null : [direction*uv[0]/speed, -direction*uv[1]/speed];
  };
  for (let i=0; i<maxSteps; i++) {
    const p = points[points.length-1], a = heading(p);
    if (!a) break;
    const b = heading([p[0]+a[0]*step/2, p[1]+a[1]*step/2]);
    if (!b) break;
    const next = [p[0]+b[0]*step, p[1]+b[1]*step];
    if (!heading(next)) break;
    if (points.length>12 && Math.hypot(next[0]-seed[0],next[1]-seed[1])<step) break;
    points.push(next);
  }
  return points;
}
const palette = [
  [67, 142, 174],
  [132, 198, 173],
  [227, 220, 134],
  [239, 169, 97],
  [216, 107, 81],
];
function color(t, colors = palette) {
  const v = Math.max(0, Math.min(0.9999, t)) * (colors.length - 1),
    i = Math.floor(v),
    f = v - i;
  return colors[i].map((a, k) =>
    Math.round(a + (colors[Math.min(i + 1, colors.length - 1)][k] - a) * f),
  );
}
export const GridLayer = L.Layer.extend({
  initialize(d, o = {}) {
    this.data = validateGrid(d, o.wind);
    this.options = { opacity: 0.5, color: "#164d63", windStyle: "arrows", windSize: 18, windWidth: 2.4, windReference: 5, ...o };
    this.particles = [];
  },
  onAdd(m) {
    this._map = m;
    this.canvas = L.DomUtil.create("canvas", "raster-canvas");
    if (this.options.wind && !m.getPane("windPane")) {
      // Keep wind in viewport coordinates, outside Leaflet's transformed map pane.
      const pane = m.createPane("windPane", m.getContainer());
      pane.style.zIndex = 410;
      pane.style.pointerEvents = "none";
    }
    m.getPane(this.options.wind ? "windPane" : "overlayPane").appendChild(this.canvas);
    m.on("moveend zoomend resize", this.reset, this);
    if (this.options.wind) m.on("movestart zoomstart", this.hideWind, this);
    this.reset();
    if (this.options.wind) this.animate();
  },
  onRemove(m) {
    m.off("moveend zoomend resize", this.reset, this);
    m.off("movestart zoomstart", this.hideWind, this);
    cancelAnimationFrame(this.frame);
    this.canvas.remove();
  },
  hideWind() {
    this.canvas.hidden = true;
  },
  setOpacity(v) {
    this.options.opacity = v;
    if (this.canvas) this.canvas.style.opacity = v;
  },
  setWindStyle(options) {
    Object.assign(this.options, options);
    this.streamlinesDirty = true;
    if (this.canvas) this.canvas.getContext("2d").clearRect(0, 0, this.canvas.width, this.canvas.height);
  },
  setData(d) {
    this.data = validateGrid(d, this.options.wind);
    if (this._map) this.reset();
  },
  reset() {
    const s = this._map.getSize();
    this.canvas.hidden = false;
    this.canvas.style.width = s.x + "px";
    this.canvas.style.height = s.y + "px";
    this.canvas.width = s.x;
    this.canvas.height = s.y;
    L.DomUtil.setPosition(
      this.canvas,
      this.options.wind ? L.point(0, 0) : this._map.containerPointToLayerPoint([0, 0]),
    );
    this.canvas.style.opacity = this.options.opacity;
    this.particles = [];
    this.streamlinesDirty = true;
    if (!this.options.wind) this.draw();
  },
  draw() {
    const ctx = this.canvas.getContext("2d"),
      d = this.data,
      step = 7;
    ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    for (let y = 0; y < this.canvas.height; y += step)
      for (let x = 0; x < this.canvas.width; x += step) {
        const ll = this._map.containerPointToLatLng([
            x + step / 2,
            y + step / 2,
          ]),
          v = gridSample(d, ll.lat, ll.lng);
        if (v === null) continue;
        ctx.fillStyle =
          "rgb(" +
          color((v - (this.options.range?.[0] ?? (d.unit === "m" ? 150 : 12))) / ((this.options.range?.[1] ?? (d.unit === "m" ? 700 : 30)) - (this.options.range?.[0] ?? (d.unit === "m" ? 150 : 12))), this.options.palette).join(",") +
          ")";
        ctx.fillRect(x, y, step, step);
      }
  },
  drawStreamlines() {
    const ctx = this.canvas.getContext("2d"), {width, height} = this.canvas;
    ctx.clearRect(0, 0, width, height);
    ctx.globalCompositeOperation = "source-over";
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    this.streamlinePaths = [];
    const occupied = new Set(), cell = p => Math.round(p[0]/12)+","+Math.round(p[1]/12);
    const steps = Math.round(this.options.windSize*5);
    for (let y=25; y<height; y+=48) for (let x=25; x<width; x+=48) {
      if (occupied.has(cell([x,y]))) continue;
      const forward = traceStreamline(this.data, this._map, [x,y], 1, steps);
      const backward = traceStreamline(this.data, this._map, [x,y], -1, steps);
      const trim = points => {
        const result = [];
        for (const p of points) {
          if (p[0]<0 || p[0]>width || p[1]<0 || p[1]>height || (result.length>2 && occupied.has(cell(p)))) break;
          result.push(p);
        }
        return result;
      };
      const points = [...trim(backward).reverse(), ...trim(forward).slice(1)];
      if (points.length<4) continue;
      points.forEach(p=>occupied.add(cell(p)));
      const times = [0];
      for (let i=1; i<points.length; i++) {
        const ll=this._map.containerPointToLatLng(points[i]);
        const uv=sampleWind(this.data,ll.lat,ll.lng);
        const speed=uv ? Math.hypot(...uv) : 0;
        times.push(times[i-1]+Math.hypot(points[i][0]-points[i-1][0],points[i][1]-points[i-1][1])/Math.max(.09,speed*9));
      }
      this.streamlinePaths.push({points,times});
      ctx.beginPath();
      ctx.moveTo(...points[0]);
      for (const p of points.slice(1)) ctx.lineTo(...p);
      // Direction markers point downstream, independent of integration direction.
      for (let i=12; i<points.length; i+=26) {
        const a=points[i-1], b=points[i], angle=Math.atan2(b[1]-a[1],b[0]-a[0]);
        ctx.moveTo(b[0]-6*Math.cos(angle-.5), b[1]-6*Math.sin(angle-.5));
        ctx.lineTo(...b);
        ctx.lineTo(b[0]-6*Math.cos(angle+.5), b[1]-6*Math.sin(angle+.5));
      }
      ctx.strokeStyle = "rgba(255,255,255,.85)";
      ctx.lineWidth = this.options.windWidth+2;
      ctx.stroke();
      ctx.strokeStyle = this.options.color;
      ctx.lineWidth = this.options.windWidth;
      ctx.stroke();
    }
  },
  cacheStreamlines() {
    this.drawStreamlines();
    this.streamlineBase = document.createElement("canvas");
    this.streamlineBase.width = this.canvas.width;
    this.streamlineBase.height = this.canvas.height;
    this.streamlineBase.getContext("2d").drawImage(this.canvas,0,0);
    this.streamlinesDirty = false;
  },
  animateStreamlines(now) {
    if (this.streamlinesDirty) this.cacheStreamlines();
    const ctx=this.canvas.getContext("2d");
    ctx.clearRect(0,0,this.canvas.width,this.canvas.height);
    ctx.globalCompositeOperation="source-over";
    ctx.globalAlpha=.35;
    ctx.drawImage(this.streamlineBase,0,0);
    ctx.globalAlpha=1;
    ctx.beginPath();
    const elapsed=now/1000, spacing=2.2, pulseDuration=.45;
    for (const {points,times} of this.streamlinePaths) {
      const duration=times[times.length-1];
      const at = t => {
        let i=1;
        while(i<times.length-1 && times[i]<t) i++;
        const f=Math.max(0,Math.min(1,(t-times[i-1])/(times[i]-times[i-1])));
        return [points[i-1][0]+f*(points[i][0]-points[i-1][0]),points[i-1][1]+f*(points[i][1]-points[i-1][1])];
      };
      // Travel time along each curve encodes local speed, rather than a fixed dash offset.
      for(let head=elapsed%spacing; head<duration+pulseDuration; head+=spacing) {
        const start=Math.max(0,head-pulseDuration), end=Math.min(duration,head);
        if(start>=end) continue;
        ctx.moveTo(...at(start));
        for(let i=1;i<times.length;i++) if(times[i]>start && times[i]<end) ctx.lineTo(...points[i]);
        ctx.lineTo(...at(end));
      }
    }
    ctx.strokeStyle="rgba(255,255,255,.95)";
    ctx.lineWidth=this.options.windWidth+3;
    ctx.stroke();
    ctx.strokeStyle=this.options.color;
    ctx.lineWidth=this.options.windWidth+1;
    ctx.stroke();
  },
  animate() {
    this.frame = requestAnimationFrame(() => this.animate());
    if (this.canvas.hidden) return;
    const now = performance.now();
    if (now - (this.last || 0) < 33) return;
    const dt = Math.min(0.1, (now - (this.last || now)) / 1000);
    this.last = now;
    if (this.options.windStyle === "streamlines") {
      this.animateStreamlines(now);
      return;
    }
    const c = this.canvas,
      ctx = c.getContext("2d");
    const { windStyle, windSize, windWidth, color } = this.options;
    if (windStyle === "trails") {
      ctx.globalCompositeOperation = "destination-in";
      ctx.fillStyle = "rgba(0,0,0,.90)";
      ctx.fillRect(0, 0, c.width, c.height);
    } else {
      ctx.clearRect(0, 0, c.width, c.height);
    }
    ctx.globalCompositeOperation = "source-over";
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    if (!this.particles.length)
      for (let i = 0; i < 400; i++)
        this.particles.push({
          x: Math.random() * c.width,
          y: Math.random() * c.height,
          age: Math.random() * 100,
        });
    for (const p of this.particles) {
      const ll = this._map.containerPointToLatLng([p.x, p.y]),
        uv = sampleWind(this.data, ll.lat, ll.lng),
        u = uv?.[0] ?? null, v = uv?.[1] ?? null;
      if (u === null || v === null || p.age++ > 100) {
        p.x = Math.random() * c.width;
        p.y = Math.random() * c.height;
        p.age = 0;
        continue;
      }
      const nx = p.x + u * dt * 9,
        ny = p.y - v * dt * 9;
      const speed = Math.hypot(u, v);
      if (speed < 0.01) continue;
      const dx = u / speed, dy = -v / speed;
      const glyph = windGlyph(speed, windSize, windWidth, this.options.windReference);
      ctx.beginPath();
      if (windStyle === "dots") {
        ctx.arc(nx, ny, glyph.length / 6, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();
      } else {
        const tx = nx - dx * glyph.length, ty = ny - dy * glyph.length;
        ctx.moveTo(tx, ty);
        ctx.lineTo(nx, ny);
        if (windStyle === "arrows") {
          const head = glyph.length * 0.35;
          ctx.moveTo(nx - dx * head + dy * head * 0.6, ny - dy * head - dx * head * 0.6);
          ctx.lineTo(nx, ny);
          ctx.lineTo(nx - dx * head - dy * head * 0.6, ny - dy * head + dx * head * 0.6);
        }
      }
      // A light casing keeps the chosen color legible over aerial imagery.
      ctx.strokeStyle = "rgba(255,255,255,.85)";
      ctx.lineWidth = glyph.width + 2;
      ctx.stroke();
      ctx.strokeStyle = color;
      ctx.lineWidth = glyph.width;
      ctx.stroke();
      p.x = nx;
      p.y = ny;
    }
  },
});
export function kmlToGeoJSON(xml) {
  const doc = new DOMParser().parseFromString(xml, "application/xml");
  if (doc.querySelector("parsererror")) throw Error("Invalid KML");
  const all = (e, n) => Array.from(e.getElementsByTagNameNS("*", n)),
    features = [];
  for (const p of all(doc, "Placemark"))
    for (const kind of ["Point", "LineString"])
      for (const g of all(p, kind)) {
        const raw = all(g, "coordinates")[0]?.textContent.trim();
        if (!raw) continue;
        const cs = raw
          .split(/\s+/)
          .map((s) => s.split(",").slice(0, 2).map(Number));
        if (cs.some((c) => c.length !== 2 || !c.every(Number.isFinite)))
          throw Error("Invalid coordinates");
        features.push({
          type: "Feature",
          properties: { name: all(p, "name")[0]?.textContent || "KML feature" },
          geometry: { type: kind, coordinates: kind === "Point" ? cs[0] : cs },
        });
      }
  if (!features.length)
    throw Error("KML requires Point or LineString placemarks");
  return { type: "FeatureCollection", features };
}
export function createLayer(d, data, inspect = () => {}) {
  if (["grid", "wind"].includes(d.type))
    return new GridLayer(data, {
      wind: d.type === "wind", opacity: d.opacity,
      range: d.range, palette: d.palette?.map(hex => [1,3,5].map(i=>parseInt(hex.slice(i,i+2),16))),
      ...(d.type === "wind" ? {color: d.color || "#164d63", windStyle: d.windStyle || "arrows", windSize: d.windSize ?? 18, windWidth: d.windWidth ?? 2.4, windReference: d.windReference ?? 5} : {})
    });
  if (d.type === "xyz")
    return L.tileLayer(d.url, {
      attribution: d.attribution || "",
      opacity: d.opacity,
      maxZoom: 19,
    });
  if (d.type === "wms")
    return L.tileLayer.wms(d.url, {
      layers: d.layers,
      format: "image/png",
      transparent: true,
      attribution: d.attribution || "",
      opacity: d.opacity,
    });
  return L.geoJSON(data, {
    style: { color: d.color || "#7564cd", weight: 3, opacity: d.opacity },
    pointToLayer: (_, ll) =>
      L.circleMarker(ll, {
        radius: 6,
        fillColor: d.color || "#187a70",
        color: "#fff",
        weight: 2,
        fillOpacity: d.opacity,
      }),
    onEachFeature: (f, l) => {
      l.on("click", () => inspect(f.properties || {}));
      if (f.properties?.name) {
        const el = document.createElement("span");
        el.textContent = f.properties.name;
        l.bindTooltip(el);
      }
    },
  });
}
