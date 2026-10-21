"""Deterministic tests: no requests to the public upstream service."""
import io
import json
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from elevation import ElevationClient, UpstreamError

def test_point_cache_and_nodata():
    c=ElevationClient()
    calls=[]
    def request(op,params):
        calls.append((op,params))
        return b'{"value":"247.433"}'
    c._request=request
    assert c.point(14.4378,50.0755)["elevation_m"]==247.433
    assert c.point(14.4378,50.0755)["verticalDatum"]=="Bpv"
    assert len(calls)==1
    assert json.loads(calls[0][1]["renderingRule"])=={"rasterFunction":"None"}
    c._request=lambda *args:b'{"value":"NoData"}'
    assert c.point(0,0)["elevation_m"] is None

def test_geotiff_orientation_bounds_and_nodata():
    np=pytest.importorskip("numpy")
    tifffile=pytest.importorskip("tifffile")
    stream=io.BytesIO()
    tifffile.imwrite(stream,np.array([[10,20],[30,-9999]],dtype="float32"),
        extratags=[(33550,"d",3,(.1,.1,0),False),
                   (33922,"d",6,(0,0,0,14,50,0),False),
                   (42113,"s",0,"-9999",False)])
    result=ElevationClient.decode_grid(stream.getvalue(),2,2,[14.05,49.85,14.15,49.95])
    assert result["values"]==[30,None,10,20]
    assert result["bbox"]==pytest.approx([14.05,49.85,14.15,49.95])
    assert result["summary"]["value"]=="20.0 m (Bpv)"

def test_reject_rendered_raster():
    np=pytest.importorskip("numpy")
    tifffile=pytest.importorskip("tifffile")
    stream=io.BytesIO()
    tifffile.imwrite(stream,np.ones((2,2),dtype="uint8"))
    with pytest.raises(UpstreamError):
        ElevationClient.decode_grid(stream.getvalue(),2,2,[])

def test_grid_request_is_numeric_and_centers_are_expanded():
    c=ElevationClient()
    captured={}
    def request(op,params):
        captured.update(op=op,params=params)
        return b"tiff"
    c._request=request
    c.decode_grid=lambda raw,w,h,b:{"bbox":b}
    c.grid([14,50,14.1,50.1],2,2)
    assert captured["op"]=="exportImage"
    assert captured["params"]["pixelType"]=="F32"
    assert captured["params"]["format"]=="tiff"
    assert list(map(float,captured["params"]["bbox"].split(",")))==pytest.approx([13.95,49.95,14.15,50.15])

def test_profile_order_distance_and_validation():
    c=ElevationClient()
    c.point=lambda lon,lat:{"elevation_m":200+lon,"timestamp":"sample"}
    result=c.profile([[14,50],[14.01,50]])
    assert result["samples"][0]["distance_m"]==0
    assert 700<result["samples"][1]["distance_m"]<720
    for fn in [lambda:c.profile([]),lambda:c.profile([[True,50]]),
               lambda:c.grid([0,0,2,1]),lambda:c.grid([14,50,15,51],129,10),
               lambda:c.coordinate(float("nan"),50)]:
        with pytest.raises(ValueError):fn()

def test_server_contract_and_upstream_errors(monkeypatch):
    from examples import elevation_server as server
    c=server.app.test_client()
    assert c.get("/elevation/metadata").json["synthetic"] is False
    assert c.get("/elevation/point").status_code==400
    assert c.get("/elevation/grid?bbox=0,0,2,1").status_code==400
    assert c.post("/elevation/profile",json={}).status_code==400
    monkeypatch.setattr(server.client,"point",lambda *args:{"elevation_m":247.433})
    result=c.get("/elevation/point?lon=14.4&lat=50")
    assert result.json["elevation_m"]==247.433
    assert result.headers["Access-Control-Allow-Origin"]=="*"
    def fail(*args):raise UpstreamError("Provider unavailable")
    monkeypatch.setattr(server.client,"point",fail)
    result=c.get("/elevation/point?lon=14.4&lat=50")
    assert result.status_code==502
    assert result.json["syntheticFallback"] is False
