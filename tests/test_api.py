import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import app,latest
from providers import snapshot,CENTERS

def test_assets_and_config():
    c=app.test_client()
    assert c.get('/').status_code==200
    assert c.get('/static/vendor/leaflet.js').status_code==200
    assert c.get('/config.json').json==c.get('/api/config').json

def test_layers_all_locations():
    c=app.test_client()
    for location in CENTERS:
        for kind in ('temperature','pressure','wind','dem','stations','route'):
            r=c.get('/api/data/'+kind+'?location='+location)
            assert r.status_code==200
            data=r.json
            if kind in ('temperature','pressure','wind','dem'):
                assert len(data['u' if kind=='wind' else 'values'])==data['width']*data['height']
    assert c.get('/api/data/nope').status_code==404
    assert c.get('/api/data/wind?location=nope').status_code==404

def test_push_validation_and_isolation():
    latest.clear()
    c=app.test_client()
    assert c.post('/api/push/temperature',json={}).status_code==400
    assert c.post('/api/push/stations',json=[]).status_code==400
    data=snapshot('temperature',tick=0)
    data['summary']={'label':'External','value':'99 °C'}
    assert c.post('/api/push/temperature',json=data).status_code==200
    assert c.get('/api/data/temperature').json['summary']['value']=='99 °C'
    assert c.get('/api/data/temperature?location=brno').json['summary']['value']!='99 °C'
    latest.clear()

def test_stream_first_frame():
    c=app.test_client()
    r=c.get('/api/events',buffered=False)
    assert r.mimetype=='text/event-stream'
    first=next(r.response).decode()
    assert set(json.loads(first.removeprefix('data: ')))=={'temperature','pressure','wind','stations','route','dem'}
    r.close()

def test_invalid_grid_never_poisons_stream():
    c=app.test_client()
    for bounds in ([1,2,0,3], [0,0,float('nan'),1], [0,0,1]):
        data=snapshot('temperature')
        data['bbox']=bounds
        assert c.post('/api/push/temperature',json=data).status_code==400
    data=snapshot('wind')
    data['u'][0]=True
    assert c.post('/api/push/wind',json=data).status_code==400

def test_invalid_feature_snapshots_rejected():
    c=app.test_client()
    assert c.post('/api/push/stations',json={'type':'FeatureCollection'}).status_code==400
    data=snapshot('stations')
    data['features'][0]['properties']['temperature']=float('nan')
    assert c.post('/api/push/stations',json=data).status_code==400
