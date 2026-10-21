"""Local Flask host. Run: python app.py"""
import json
import math
import threading
from pathlib import Path
from flask import Flask, Response, jsonify, request, send_from_directory
from providers import CENTERS, snapshot

ROOT = Path(__file__).parent
app = Flask(__name__, static_folder="static")
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024
KINDS = {"temperature", "pressure", "dem", "wind", "stations", "route"}
latest = {}
lock = threading.Lock()

@app.get("/index.html")
@app.get("/")
def index():
    return send_from_directory(ROOT, "index.html")

@app.get("/config.json")
def static_config():
    return send_from_directory(ROOT, "config.json")

@app.get("/examples/<path:filename>")
def examples(filename):
    return send_from_directory(ROOT / "examples", filename)

@app.get("/api/config")
def config():
    return jsonify(json.loads((ROOT / "config.json").read_text(encoding="utf-8")))

@app.get("/api/data/<kind>")
def data(kind):
    location = request.args.get("location", "prague")
    if kind not in KINDS or location not in CENTERS:
        return jsonify(error="Unknown layer or location"), 404
    with lock:
        pushed = latest.get((location, kind))
    return jsonify(pushed if pushed is not None else snapshot(kind, location))

@app.post("/api/push/<kind>")
def push(kind):
    """Local trusted-producer ingress; replace snapshot via REST."""
    location = request.args.get("location", "prague")
    if kind not in KINDS or location not in CENTERS:
        return jsonify(error="Unknown layer or location"), 404
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or (kind in {"stations", "route"} and payload.get("type") != "FeatureCollection"):
        return jsonify(error="Expected a JSON snapshot matching the layer contract"), 400
    try:
        json.dumps(payload, allow_nan=False)
    except (ValueError, TypeError):
        return jsonify(error="Snapshots must contain finite JSON numbers"), 400
    if kind in {"stations", "route"} and not isinstance(payload.get("features"), list):
        return jsonify(error="FeatureCollection requires a features array"), 400
    if kind in {"temperature", "pressure", "dem", "wind"}:
        try:
            w, h = payload["width"], payload["height"]
            def number(n):
                return type(n) in (int, float) and math.isfinite(n)
            valid = type(w) is int and type(h) is int and 1 < w <= 512 and 1 < h <= 512
            valid = valid and payload.get("schema") == "map-viz.grid/v1"
            valid = valid and payload["crs"] == "EPSG:4326" and payload["rowOrder"] == "south-to-north"
            bounds = payload["bbox"]
            valid = valid and isinstance(bounds, list) and len(bounds) == 4 and all(number(n) for n in bounds)
            valid = valid and -180 <= bounds[0] < bounds[2] <= 180 and -90 <= bounds[1] < bounds[3] <= 90
            for key in (["u", "v"] if kind == "wind" else ["values"]):
                array = payload[key]
                valid = valid and isinstance(array, list) and len(array) == w * h
                valid = valid and all(n is None or number(n) for n in array)
            if not valid:
                raise ValueError("Invalid grid")
        except (KeyError, TypeError, ValueError, IndexError):
            return jsonify(error="Invalid grid dimensions, CRS, bbox or arrays"), 400
    with lock:
        latest[(location, kind)] = payload
    return jsonify(ok=True)

@app.get("/api/events")
def events():
    location = request.args.get("location", "prague")
    if location not in CENTERS:
        return jsonify(error="Unknown location"), 404
    def stream():
        # SSE naturally supports sparse events too; this demo emits every 3 seconds.
        import time
        while True:
            frames = {}
            for kind in KINDS:
                with lock:
                    pushed = latest.get((location, kind))
                frames[kind] = pushed if pushed is not None else snapshot(kind, location)
            yield "data: " + json.dumps(frames, allow_nan=False) + "\n\n"
            time.sleep(3)
    return Response(stream(), mimetype="text/event-stream", headers={"Cache-Control":"no-cache", "X-Accel-Buffering":"no"})

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, threaded=True)
