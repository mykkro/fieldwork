"""Small provider contract: return JSON-serializable snapshots, never HTML."""
import math
import time
from datetime import datetime, timezone

CENTERS = {"prague": (50.0755, 14.4378), "brno": (49.1951, 16.6068), "krkonose": (50.73, 15.62)}

def snapshot(kind, location="prague", tick=None):
    lat, lon = CENTERS[location]
    phase = (time.time() if tick is None else tick) / 30
    timestamp = datetime.now(timezone.utc).isoformat()
    if kind in ("temperature", "pressure", "dem", "wind"):
        width = height = 24
        result = {"schema":"map-viz.grid/v1", "crs":"EPSG:4326", "bbox":[lon-.24,lat-.15,lon+.24,lat+.15], "width":width,"height":height,"rowOrder":"south-to-north", "timestamp":timestamp}
        values, u, v = [], [], []
        for y in range(height):
            for x in range(width):
                values.append(round(1013 + 9*math.sin(x/8+phase*.08)*math.cos(y/10) if kind == "pressure" else 18 + 5*math.sin(x/7+phase*.1)*math.cos(y/9) if kind == "temperature" else 180+500*math.exp(-((x-16)**2+(y-15)**2)/100), 2))
                u.append(round(3+2*math.sin(y/8+phase*.1),2))
                v.append(round(1.5*math.cos(x/7+phase*.1),2))
        if kind == "wind":
            result.update(u=u,v=v,unit="m/s",summary={"label":"Mean wind","value":f"{sum(math.hypot(a,b) for a,b in zip(u,v))/len(u):.1f} m/s"})
        else:
            unit = "°C" if kind == "temperature" else "m"
            if kind == "pressure": unit = "hPa"
            result.update(values=values,unit=unit,summary={"label":"Mean pressure" if kind == "pressure" else "Mean temperature" if kind == "temperature" else "Mean elevation","value":f"{sum(values)/len(values):.1f} {unit}"})
        return result
    if kind == "stations":
        points = [(-.08,.035,"West station"),(.035,.02,"City station"),(.10,-.045,"East station"),(-.02,-.07,"South station")]
        return {"type":"FeatureCollection","timestamp":timestamp,"summary":{"label":"Stations online","value":"4 / 4"},"features":[{"type":"Feature","geometry":{"type":"Point","coordinates":[lon+x,lat+y]},"properties":{"name":name,"temperature":round(20+2*math.sin(i+phase*.1),1),"unit":"°C"}} for i,(x,y,name) in enumerate(points)]}
    if kind == "route":
        return {"type":"FeatureCollection","features":[{"type":"Feature","properties":{"name":"Survey trajectory (illustrative)"},"geometry":{"type":"LineString","coordinates":[[lon-.025,lat-.095],[lon-.01,lat-.06],[lon-.03,lat-.025],[lon-.02,lat+.005],[lon+.005,lat+.035],[lon-.025,lat+.065]]}}]}
    raise KeyError(kind)
