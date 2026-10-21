"""Live integration check: needs internet and requirements-elevation.txt."""
import json
import sys
import threading
from pathlib import Path
from urllib.request import urlopen, Request
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from werkzeug.serving import make_server
from playwright.sync_api import sync_playwright
from app import app as viewer
from examples.elevation_server import app as provider

def main():
    servers=[make_server("127.0.0.1",5057,viewer,threaded=True),
             make_server("127.0.0.1",5010,provider,threaded=True)]
    for server in servers:
        threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with urlopen("http://127.0.0.1:5010/elevation/point?lon=14.4378&lat=50.0755",timeout=30) as r:
            point=json.load(r)
            assert point["synthetic"] is False and 100<point["elevation_m"]<400
        request=Request("http://127.0.0.1:5010/elevation/profile",data=json.dumps({"coordinates":[[14.4378,50.0755],[14.42,50.08]]}).encode(),headers={"Content-Type":"application/json"})
        with urlopen(request,timeout=60) as r:
            profile=json.load(r)
            assert len(profile["samples"])==2 and profile["samples"][1]["distance_m"]>1000
        with sync_playwright() as p:
            browser=p.chromium.launch()
            page=browser.new_page(viewport={"width":1440,"height":1000})
            errors=[]
            page.on("pageerror",lambda e:errors.append(str(e)))
            page.goto("http://127.0.0.1:5057/index.html?config=examples/cuzk-dem.json")
            page.get_by_text("Mean terrain elevation",exact=True).wait_for(timeout=45000)
            assert "Bpv" in page.locator("#summaries").inner_text()
            assert "CUZK DMR 5G terrain" in page.locator("#legend").inner_text()
            assert not errors,errors
            page.wait_for_timeout(600)
            page.screenshot(path=str(Path(__file__).resolve().parents[1]/"docs"/"elevation.png"),full_page=True)
            browser.close()
        print("PASS: real point/profile HTTP API, cross-origin numerical DEM grid, viewer rendering")
    finally:
        for server in servers:server.shutdown()
if __name__=="__main__":main()
