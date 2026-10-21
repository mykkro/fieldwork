"""Independent read-only numerical elevation provider on localhost:5010."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from flask import Flask, jsonify, request
from elevation import ElevationClient, METADATA, UpstreamError

app=Flask(__name__)
app.config["MAX_CONTENT_LENGTH"]=32*1024
client=ElevationClient()

@app.after_request
def cors(response):
    response.headers["Access-Control-Allow-Origin"]="*"
    response.headers["Access-Control-Allow-Methods"]="GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"]="Content-Type"
    return response

@app.errorhandler(ValueError)
def invalid(exc):
    return jsonify(error=str(exc)),400

@app.errorhandler(UpstreamError)
def upstream(exc):
    return jsonify(error=str(exc),syntheticFallback=False),502

@app.get("/")
def index():
    return jsonify(name="Fieldwork elevation provider",endpoints={
        "metadata":"/elevation/metadata",
        "point":"/elevation/point?lon=14.4378&lat=50.0755",
        "grid":"/elevation/grid?bbox=14.40,50.05,14.48,50.10&width=32&height=32",
        "profile":"POST /elevation/profile with coordinates: [[lon,lat], ...]"
    })

@app.get("/elevation/metadata")
def metadata():
    return jsonify(**METADATA,cache={"ttlSeconds":client.ttl,"maxEntries":client.max_entries},
                   limits={"maxGridAxis":128,"maxBboxSpanDegrees":1,"maxProfileWaypoints":32})

@app.get("/elevation/point")
def point():
    try:
        lon,lat=float(request.args["lon"]),float(request.args["lat"])
    except (KeyError,ValueError):
        raise ValueError("lon and lat query parameters are required numbers")
    return jsonify(client.point(lon,lat))

@app.get("/elevation/grid")
def grid():
    try:
        bbox=[float(v) for v in request.args["bbox"].split(",")]
        width,height=int(request.args.get("width",32)),int(request.args.get("height",32))
    except (KeyError,ValueError):
        raise ValueError("Use bbox=west,south,east,north and integer width/height")
    return jsonify(client.grid(bbox,width,height))

@app.post("/elevation/profile")
def profile():
    data=request.get_json(silent=True)
    if not isinstance(data,dict):
        raise ValueError("Expected a JSON object with coordinates")
    return jsonify(client.profile(data.get("coordinates")))

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--port",type=int,default=5010)
    args=p.parse_args()
    app.run(host="127.0.0.1",port=args.port,threaded=True)
