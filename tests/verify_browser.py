"""End-to-end verification and README screenshot; launches and stops own servers."""
import sys,threading
from pathlib import Path
from functools import partial
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import app
from werkzeug.serving import make_server
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
def main():
    backend=make_server('127.0.0.1',5055,app,threaded=True)
    static=ThreadingHTTPServer(('127.0.0.1',5056),partial(SimpleHTTPRequestHandler,directory=str(ROOT)))
    for server in (backend,static):threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch()
            page=browser.new_page(viewport={'width':1440,'height':1200},device_scale_factor=1)
            errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto('http://127.0.0.1:5055')
            page.get_by_text('Python connected',exact=False).wait_for()
            page.get_by_text('4 / 4',exact=True).wait_for()
            page.wait_for_function("document.querySelectorAll('.leaflet-tile-loaded').length > 0", timeout=20000)
            page.wait_for_timeout(1000)
            (ROOT/'docs').mkdir(exist_ok=True)
            page.screenshot(path=str(ROOT/'docs'/'screenshot.png'),full_page=True)
            page.locator('.base.ortho').click()
            page.wait_for_function("Array.from(document.querySelectorAll('.leaflet-tile-loaded')).some(t=>t.src.includes('cuzk.gov.cz'))", timeout=30000)
            page.get_by_role('button',name='OpenStreetMap').click()
            # Adapter-level checks cover KML parsing, nodata and grid orientation.
            assert page.evaluate("""async () => {
                const {kmlToGeoJSON,gridSample,validateGrid}=await import('/static/toolkit.js');
                const g={crs:'EPSG:4326',rowOrder:'south-to-north',width:2,height:2,bbox:[0,0,1,1],values:[1,2,3,null]};
                validateGrid(g);
                const k=kmlToGeoJSON('<kml xmlns="http://www.opengis.net/kml/2.2"><Placemark><name>Route</name><LineString><coordinates>14,50 15,51</coordinates></LineString></Placemark></kml>');
                return gridSample(g,0,0)===1 && gridSample(g,1,1)===null && k.features[0].geometry.coordinates.length===2;
            }""")
            page.get_by_role('checkbox',name='Show Air pressure').check()
            page.get_by_text('Mean pressure',exact=True).wait_for()
            assert 'hPa' in page.locator('#legend').inner_text()
            assert page.locator('#legend .scalar-legend').count()==2
            page.get_by_role('checkbox',name='Show Air pressure').uncheck()
            page.get_by_role('checkbox',name='Show Vltava survey route').check()
            page.get_by_role('slider',name='Air temperature opacity').fill('25')
            assert page.evaluate("""async () => {
                const {windGlyph,sampleWind,traceStreamline}=await import('/static/toolkit.js');
                const a=windGlyph(2,18,2,5), b=windGlyph(4,18,2,5);
                if(Math.abs(b.length/a.length-2)>1e-9 || b.width<=a.width || windGlyph(100,18,2,5).length!==54) return false;
                const d={bbox:[-10,-10,10,10],width:21,height:21,u:[],v:[]};
                for(let y=-10;y<=10;y++)for(let x=-10;x<=10;x++){d.u.push(-y);d.v.push(x);}
                const uv=sampleWind(d,.5,2.5);
                if(uv[0]!==-.5 || uv[1]!==2.5) return false;
                const fake={containerPointToLatLng:p=>({lng:p[0],lat:-p[1]})};
                const line=traceStreamline(d,fake,[5,0],1,40,.2);
                if(line.length<30 || line.at(-1)[1]>-2 || Math.abs(Math.hypot(...line.at(-1))-5)>.05) return false;
                d.u.fill(null);
                return traceStreamline(d,fake,[5,0],1,40,.2).length===1;
            }""")
            page.get_by_role('combobox',name='Wind field style').select_option('streamlines')
            page.wait_for_timeout(500)
            assert page.evaluate("""() => {
                const c=document.querySelector('.leaflet-wind-pane canvas');
                return c.getContext('2d').getImageData(0,0,c.width,c.height).data.some((v,i)=>i%4===3&&v>0);
            }""")
            before=page.locator('.leaflet-wind-pane canvas').evaluate('(c)=>c.toDataURL()')
            page.wait_for_timeout(350)
            after=page.locator('.leaflet-wind-pane canvas').evaluate('(c)=>c.toDataURL()')
            assert before!=after, 'Streamline pulses must move between frames'
            page.screenshot(path=str(ROOT/'docs'/'streamlines.png'),full_page=True)
            assert page.evaluate("""async () => {
                const {createLayer}=await import('/static/toolkit.js');
                const host=document.createElement('div');
                Object.assign(host.style,{position:'absolute',top:'0',left:'0',width:'320px',height:'240px',zIndex:'9999'});
                document.body.append(host);
                const m=L.map(host,{zoomAnimation:false}).setView([50,14],8);
                const d={crs:'EPSG:4326',rowOrder:'south-to-north',bbox:[10,45,20,55],width:2,height:2,u:[5,5,5,5],v:[0,0,0,0]};
                const layer=createLayer({type:'wind',opacity:1,windSize:18,windWidth:2},d).addTo(m);
                const ctx=layer.canvas.getContext('2d');
                const originalMove=ctx.moveTo.bind(ctx),originalLine=ctx.lineTo.bind(ctx);
                let from, length;
                ctx.moveTo=(x,y)=>{from=[x,y];originalMove(x,y);};
                ctx.lineTo=(x,y)=>{if(from && y===from[1] && x>from[0])length=x-from[0];originalLine(x,y);};
                try {
                    for(const z of [8,11,14,9]) {
                        length=undefined;m.setZoom(z);
                        await new Promise(r=>setTimeout(r,150));
                        const rect=layer.canvas.getBoundingClientRect();
                        if(Math.abs(length-18)>.001 || Math.abs(rect.width-320)>.1 || Math.abs(rect.height-240)>.1) return false;
                    }
                    return layer.canvas.parentElement.parentElement===host;
                } finally {m.remove();host.remove();}
            }"""), 'Wind glyphs must keep identical pixel dimensions across zoom levels'
            page.get_by_role('slider',name='Wind field reference speed').fill('8')
            page.get_by_role('combobox',name='Wind field style').select_option('trails')
            page.get_by_role('slider',name='Wind field size').fill('30')
            page.get_by_role('slider',name='Wind field width').fill('4')
            page.get_by_label('Wind field color',exact=True).fill('#ff0044')
            page.wait_for_timeout(100)
            assert page.evaluate("document.querySelector('.leaflet-wind-pane canvas').getContext('2d').strokeStyle")=='#ff0044'
            assert 1 < page.evaluate("document.querySelector('.leaflet-wind-pane canvas').getContext('2d').lineWidth") < 8
            page.get_by_role('combobox',name='Wind field style').select_option('dots')
            page.wait_for_timeout(100)
            assert page.evaluate("document.querySelector('.leaflet-wind-pane canvas').getContext('2d').fillStyle")=='#ff0044'
            page.get_by_role('button',name='Start live').click()
            page.get_by_text('Server-Sent Events · 3 s cadence',exact=True).wait_for()
            page.wait_for_timeout(3200)
            assert page.get_by_role('combobox',name='Wind field style').input_value()=='dots'
            assert page.get_by_role('slider',name='Wind field size').input_value()=='30'
            assert 1 < page.evaluate("document.querySelector('.leaflet-wind-pane canvas').getContext('2d').lineWidth") < 8
            page.get_by_role('button',name='Pause live').click()
            page.locator('#location').select_option('brno')
            page.get_by_text('Brno, Czechia',exact=True).last.wait_for()
            page.get_by_text('4 / 4',exact=True).wait_for()
            assert page.get_by_label('Wind field color',exact=True).input_value()=='#ff0044'
            page.wait_for_timeout(100)
            assert page.evaluate("document.querySelector('.leaflet-wind-pane canvas').getContext('2d').strokeStyle")=='#ff0044'
            page.get_by_role('button',name='+ Add source').click()
            page.locator('[name=name]').fill('Extra stations')
            page.locator('[name=url]').fill('/api/data/stations?location=brno')
            page.get_by_role('button',name='Connect source').click()
            page.get_by_text('Extra stations',exact=True).wait_for()
            page.wait_for_timeout(500)
            page.goto('http://127.0.0.1:5056')
            page.get_by_text('Static mode',exact=False).wait_for()
            page.get_by_text('4 / 4',exact=True).wait_for()
            page.get_by_role('button',name='Start live').click()
            assert 'needs Python' in page.locator('#notice').inner_text()
            page.locator('#location').select_option('krkonose')
            page.get_by_text('4 / 4',exact=True).wait_for()
            page.set_viewport_size({'width':390,'height':844})
            page.wait_for_timeout(500)
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.screenshot(path=str(ROOT/'docs'/'mobile.png'),full_page=True)
            assert not errors,errors
            browser.close()
            print('PASS: backend, SSE, layer controls, provider dialog, static mode, locations, mobile; no JS errors')
    finally:
        backend.shutdown()
        static.shutdown()
if __name__=='__main__':main()
