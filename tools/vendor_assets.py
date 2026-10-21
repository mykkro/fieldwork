"""Fetch pinned Leaflet; runtime uses local assets."""
from pathlib import Path
from urllib.request import urlopen
import hashlib, base64
ROOT=Path(__file__).resolve().parents[1]/'static'/'vendor'
def main():
    files=['leaflet.js','leaflet.css','images/marker-icon.png','images/marker-icon-2x.png','images/marker-shadow.png','images/layers.png','images/layers-2x.png']
    expected={'leaflet.js':'20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=','leaflet.css':'p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY='}
    for name in files:
        target=ROOT/name
        target.parent.mkdir(parents=True,exist_ok=True)
        with urlopen('https://unpkg.com/leaflet@1.9.4/dist/'+name,timeout=30) as r:data=r.read()
        if name in expected:assert base64.b64encode(hashlib.sha256(data).digest()).decode()==expected[name]
        target.write_bytes(data)
        print(name)
    with urlopen('https://raw.githubusercontent.com/Leaflet/Leaflet/v1.9.4/LICENSE',timeout=30) as r:(ROOT/'LEAFLET-LICENSE').write_bytes(r.read())
if __name__=='__main__':main()
