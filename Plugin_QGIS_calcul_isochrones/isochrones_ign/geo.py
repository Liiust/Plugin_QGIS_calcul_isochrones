"""
Dependency-free GeoJSON utilities (testable outside QGIS)
"""

# Liiust

from __future__ import annotations

import json
import math
import os
import re
import tempfile
import time
from typing import Any, Dict, Iterator, List, Tuple

from .api import IsochroneRequest, IsochroneResponse

EARTH_RADIUS_M = 6_371_008.8


def build_feature_collection(request: IsochroneRequest, response: IsochroneResponse) -> Dict[str, Any]:
    """Service response -> GeoJSON FeatureCollection with useful attributes."""
    props = {
        "resource": request.resource,
        "resourceVersion": response.resource_version,
        "profile": request.profile,
        "direction": request.direction,
        "costType": request.cost_type,
        "costValue": request.cost_value,
        "timeUnit": request.time_unit,
        "distanceUnit": request.distance_unit,
        "point": request.point,
    }
    return {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "properties": props, "geometry": response.geometry}],
    }


def _rings(geometry: Dict[str, Any]) -> Iterator[List[List[float]]]:
    if geometry["type"] == "Polygon":
        yield from geometry["coordinates"]
    elif geometry["type"] == "MultiPolygon":
        for poly in geometry["coordinates"]:
            yield from poly
    else:
        raise ValueError(f"Unhandled type : {geometry['type']}")


def bbox(geometry: Dict[str, Any]) -> Tuple[float, float, float, float]:
    xs, ys = [], []
    for ring in _rings(geometry):
        for x, y, *_ in ring:
            xs.append(x)
            ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


def _ring_area_km2(ring: List[List[float]]) -> float:
    """Area of ​​a longitude/latitude ring, calculated via local equirectangular projection."""
    lat0 = math.radians(sum(p[1] for p in ring) / len(ring))
    pts = [
        (math.radians(p[0]) * EARTH_RADIUS_M * math.cos(lat0), math.radians(p[1]) * EARTH_RADIUS_M)
        for p in ring
    ]
    s = sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]))
    return s / 2 / 1e6


def approx_area_km2(geometry: Dict[str, Any]) -> float:
    """Approximate area (km²): outer rings minus holes, per polygon."""
    polys = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
    total = 0.0
    for poly in polys:
        for i, ring in enumerate(poly):
            a = abs(_ring_area_km2(ring))
            total += a if i == 0 else -a
    return total


def write_geojson(fc: Dict[str, Any], name: str, directory: str | None = None) -> str:
    """Writes the FeatureCollection to a .geojson file and returns its path."""
    directory = directory or os.path.join(tempfile.gettempdir(), "isochrones_ign")
    os.makedirs(directory, exist_ok=True)
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_") or "isochrone"
    path = os.path.join(directory, f"{slug}_{int(time.time() * 1000)}.geojson")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(fc, fh, ensure_ascii=False)
    return path


def layer_name(request: IsochroneRequest) -> str:
    unit = request.time_unit if request.cost_type == "time" else request.distance_unit
    value = int(request.cost_value) if float(request.cost_value).is_integer() else request.cost_value
    return f"Isochrone {value} {unit} ({request.profile}, {request.direction})"
