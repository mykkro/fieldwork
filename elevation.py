"""Reusable numerical CUZK DMR 5G client; no Leaflet or Flask dependency."""
import io
import json
import math
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SOURCE = "https://ags.cuzk.gov.cz/arcgis2/rest/services/dmr5g/ImageServer"
METADATA = {
    "provider": "CUZK DMR 5G", "source": SOURCE, "attribution": "\u00a9 \u010c\u00daZK",
    "unit": "m", "verticalDatum": "Bpv", "verticalCrs": "EPSG:8357",
    "nativeCrs": "EPSG:5514", "sourcePixelSize_m": 2,
    "outputCrs": "EPSG:4326", "synthetic": False,
    "interpolation": "bilinear", "horizontalTransformation": "upstream ArcGIS default",
    "note": "Raster sampling, not original TIN vertices. Output spacing does not increase source accuracy."
}

class UpstreamError(Exception):
    pass

class ElevationClient:
    def __init__(self, ttl=3600, max_entries=64, timeout=25):
        self.ttl, self.max_entries, self.timeout = ttl, max_entries, timeout
        self.cache = OrderedDict()
        self.lock = threading.Lock()

    def _cached(self, key, fetch):
        with self.lock:
            entry = self.cache.get(key)
            if entry and time.monotonic() - entry[0] < self.ttl:
                self.cache.move_to_end(key)
                return entry[1]
            self.cache.pop(key, None)
        result = fetch()
        with self.lock:
            self.cache[key] = (time.monotonic(), result)
            self.cache.move_to_end(key)
            while len(self.cache) > self.max_entries:
                self.cache.popitem(last=False)
        return result

    def _request(self, operation, params):
        req = Request(SOURCE + "/" + operation + "?" + urlencode(params),
                      headers={"User-Agent": "Fieldwork/0.1 elevation-provider-demo"})
        try:
            with urlopen(req, timeout=self.timeout) as response:
                data = response.read(8 * 1024 * 1024 + 1)
            if len(data) > 8 * 1024 * 1024:
                raise UpstreamError("Upstream response exceeds 8 MB")
            return data
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise UpstreamError("CUZK request failed: " + str(exc)) from exc

    @staticmethod
    def coordinate(lon, lat):
        if type(lon) not in (float, int) or type(lat) not in (float, int):
            raise ValueError("Coordinates must be numbers")
        if not math.isfinite(lon) or not math.isfinite(lat) or not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise ValueError("Invalid longitude or latitude")
        return float(lon), float(lat)

    def point(self, lon, lat):
        lon, lat = self.coordinate(lon, lat)
        def fetch():
            raw = self._request("identify", {
                "f": "json", "geometryType": "esriGeometryPoint",
                "geometry": json.dumps({"x": lon, "y": lat, "spatialReference": {"wkid": 4326}}),
                "returnCatalogItems": "false", "returnGeometry": "false",
                "renderingRule": '{"rasterFunction":"None"}'
            })
            try:
                data = json.loads(raw)
                if "error" in data:
                    raise UpstreamError("CUZK identify error: " + str(data["error"]))
                value = data.get("value")
                if value is None or str(value).lower() in ("nodata", "no data", ""):
                    height = None
                else:
                    height = float(value)
                    if not math.isfinite(height):
                        height = None
            except (ValueError, TypeError) as exc:
                raise UpstreamError("Invalid numerical identify response") from exc
            return {**METADATA, "lon": lon, "lat": lat, "elevation_m": height, "interpolation": "upstream identify default",
                    "timestamp": datetime.now(timezone.utc).isoformat()}
        return self._cached(("point", lon, lat), fetch)

    def grid(self, bbox, width=32, height=32):
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            raise ValueError("bbox must contain west,south,east,north")
        west, south = self.coordinate(bbox[0], bbox[1])
        east, north = self.coordinate(bbox[2], bbox[3])
        if west >= east or south >= north or east-west > 1 or north-south > 1:
            raise ValueError("Ordered bbox must span at most one degree per axis")
        if type(width) is not int or type(height) is not int or not (2 <= width <= 128 and 2 <= height <= 128):
            raise ValueError("width and height must be integers from 2 to 128")
        def fetch():
            # Fieldwork bounds denote sample centers; ArcGIS export bounds denote pixel edges.
            dx, dy = (east-west)/(width-1), (north-south)/(height-1)
            raw = self._request("exportImage", {
                "f": "image", "bbox": ",".join(map(str, [west-dx/2,south-dy/2,east+dx/2,north+dy/2])),
                "bboxSR": 4326, "imageSR": 4326, "size": f"{width},{height}",
                "format": "tiff", "pixelType": "F32", "noData": -9999,
                "interpolation": "RSP_BilinearInterpolation", "adjustAspectRatio": "false",
                "renderingRule": '{"rasterFunction":"None"}'
            })
            return self.decode_grid(raw, width, height, [west,south,east,north])
        return self._cached(("grid", west,south,east,north,width,height), fetch)

    @staticmethod
    def decode_grid(raw, width, height, requested_bbox):
        import numpy as np
        import tifffile
        try:
            with tifffile.TiffFile(io.BytesIO(raw)) as tif:
                page = tif.pages[0]
                array = page.asarray()
                if array.shape != (height,width) or array.dtype.kind != "f":
                    raise UpstreamError("Expected a single-band floating-point height raster")
                scale = page.tags[33550].value
                tie = page.tags[33922].value
                if 34264 in page.tags or scale[0] <= 0 or scale[1] <= 0:
                    raise UpstreamError("Unexpected rotated or inverted GeoTIFF")
                x0, y0 = tie[3]-tie[0]*scale[0], tie[4]+tie[1]*scale[1]
                bbox = [x0+scale[0]/2,y0-(height-.5)*scale[1],
                        x0+(width-.5)*scale[0],y0-scale[1]/2]
                nodata = float(page.tags[42113].value) if 42113 in page.tags else -9999
                # TIFF rows are north-to-south; Fieldwork rows are south-to-north.
                array = np.flipud(array)
                valid = np.isfinite(array) & (array != nodata)
                values = [round(float(v),3) if ok else None for v,ok in zip(array.flat,valid.flat)]
                mean = float(array[valid].mean()) if valid.any() else None
        except UpstreamError:
            raise
        except Exception as exc:
            raise UpstreamError("Could not decode georeferenced numeric elevation TIFF") from exc
        return {**METADATA, "schema":"map-viz.grid/v1", "crs":"EPSG:4326",
                "rowOrder":"south-to-north", "bbox":bbox, "requestedBbox":requested_bbox,
                "width":width,"height":height,"values":values,"nodata":None,
                "sampleSpacing_degrees":[scale[0],scale[1]],
                "timestamp":datetime.now(timezone.utc).isoformat(),
                "summary":{"label":"Mean terrain elevation","value":f"{mean:.1f} m (Bpv)" if mean is not None else "No coverage"}}

    def profile(self, coordinates):
        if not isinstance(coordinates,list) or not 1 <= len(coordinates) <= 32:
            raise ValueError("Provide 1-32 [longitude, latitude] waypoints")
        points = []
        for point in coordinates:
            if not isinstance(point,(list,tuple)) or len(point)!=2:
                raise ValueError("Each waypoint must be [longitude, latitude]")
            points.append(self.coordinate(*point))
        samples, distance = [], 0.
        for i,(lon,lat) in enumerate(points):
            if i:
                a,b=points[i-1]
                dlat,dlon=math.radians(lat-b),math.radians(lon-a)
                q=math.sin(dlat/2)**2+math.cos(math.radians(b))*math.cos(math.radians(lat))*math.sin(dlon/2)**2
                distance+=6371008.8*2*math.asin(min(1,math.sqrt(q)))
            item=self.point(lon,lat)
            samples.append({"sequence":i,"lon":lon,"lat":lat,"distance_m":round(distance,2),
                            "elevation_m":item["elevation_m"],"sampledAt":item["timestamp"]})
        return {**METADATA,"samples":samples,"sampling":"supplied waypoints only; no densification"}
