"""
Mock HTTP server for testing/demonstrating the plugin without a network or QGIS.

!!! Mimics the expected response format from the service (e.g., "geometry" key in GeoJSON, "resourceVersion", etc.). 
Should be validated against the actual service using `cli.py capabilities` and `cli.py compute` (see README).
"""

# Liiust

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

EARTH_RADIUS_M = 6_371_008.8
_SPEED_M_S = {"car": 13.9, "pedestrian": 1.11}  # ≈ 50 km/h et 4 km/h
_TO_SECONDS = {"hour": 3600.0, "minute": 60.0, "second": 1.0}
_TO_METERS = {"kilometer": 1000.0, "meter": 1.0}

def _iso_params(rid: str, bbox: str, crs: List[str], constraints: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {"id": "resource", "values": [rid]},
        {"id": "point", "values": {"bbox": bbox}},
        {"id": "costType", "values": ["time", "distance"]},
        {"id": "costValue", "values": {"min": None, "max": 50000}},
        {"id": "profile", "values": ["car", "pedestrian"], "defaultValue": "car"},
        {"id": "direction", "values": ["departure", "arrival"], "defaultValue": "departure"},
        {"id": "projection", "values": crs, "defaultValue": "EPSG:4326"},
        {"id": "geometryFormat", "values": ["geojson", "polyline", "wkt"], "defaultValue": "geojson"},
        {"id": "timeUnit", "values": ["hour", "minute", "second", "standard"], "defaultValue": "second"},
        {"id": "distanceUnit", "values": ["meter", "kilometer"], "defaultValue": "meter"},
        {"id": "constraints", "values": {"keys": constraints}},
    ]


_WAYTYPE = {"key": "waytype", "availableConstraintType": ["banned"], "availableOperators": ["="],
            "values": ["autoroute", "pont", "tunnel"]}
_IMPORTANCE = {"key": "importance", "availableConstraintType": ["banned", "prefer", "avoid"],
               "availableOperators": ["=", "!=", ">", ">=", "<", "<="]}
_FRANCE = "-63.28125,-21.42148437,55.8984375,51.27109375"
_PROJ = ["EPSG:4326", "EPSG:2154", "EPSG:3857"]

# Extrait fidèle de la structure du vrai getCapabilities (ressources réduites à 4).
CAPABILITIES: Dict[str, Any] = {
    "info": {"name": "Road2"},
    "operations": [{"id": "route"}, {"id": "isochrone"}, {"id": "nearest"}],
    "resources": [
        {"id": "bdtopo-osrm", "description": "Itinéraire via OSRM",
         "availableOperations": [{"id": "route", "availableParameters": []}]},  # PAS d'isochrone
        {"id": "bdtopo-valhalla", "description": "Itinéraire via Valhalla",
         "availableOperations": [{"id": "route", "availableParameters": []},
                                 {"id": "isochrone", "availableParameters": _iso_params("bdtopo-valhalla", _FRANCE, _PROJ, [_WAYTYPE])}]},
        {"id": "bdtopo-pgr", "description": "Itinéraire / Isochrone via PGRouting",
         "availableOperations": [{"id": "isochrone", "availableParameters": _iso_params("bdtopo-pgr", _FRANCE, _PROJ, [_WAYTYPE, _IMPORTANCE])}]},
        {"id": "graphe_routier_r100_IGN", "description": "Seine Grands Lacs (r100)",
         "availableOperations": [{"id": "isochrone", "availableParameters": _iso_params(
             "graphe_routier_r100_IGN", "1.362304688,48.022753906,3.647460938,49.339648438", ["EPSG:4326"], [_WAYTYPE, _IMPORTANCE])}]},
    ],
}


class FakeResponse:
    def __init__(self, payload: Any, status: int = 200):
        self._payload, self.status_code = payload, status
        self.text = str(payload)

    def json(self) -> Any:
        return self._payload


def circle(lon: float, lat: float, radius_m: float, n: int = 72) -> List[List[float]]:
    ring = []
    for i in range(n):
        a = 2 * math.pi * i / n
        dlat = math.degrees(radius_m * math.sin(a) / EARTH_RADIUS_M)
        dlon = math.degrees(radius_m * math.cos(a) / (EARTH_RADIUS_M * math.cos(math.radians(lat))))
        ring.append([lon + dlon, lat + dlat])
    ring.append(ring[0])
    return ring


class FakeSession:
    """Remplace requests.Session : mémorise les appels dans `self.calls`."""

    def __init__(self, fail_with: Optional[int] = None):
        self.calls: List[Dict[str, Any]] = []
        self.fail_with = fail_with

    def get(self, url: str, params: Optional[dict] = None, timeout: float = 30) -> FakeResponse:
        self.calls.append({"url": url, "params": params})
        if self.fail_with:
            return FakeResponse({"error": {"message": "requête refusée (simulation)"}}, self.fail_with)
        if url.endswith("/getCapabilities"):
            return FakeResponse(CAPABILITIES)
        if url.endswith("/isochrone"):
            p = params or {}
            allowed = {r["id"] for r in CAPABILITIES["resources"]
                       if any(o["id"] == "isochrone" for o in r["availableOperations"])}
            if p.get("resource") not in allowed:
                return FakeResponse({"error": {"message": "Operation not permitted on this resource."}}, 400)
            lon, lat = (float(v) for v in p["point"].split(","))
            value = float(p["costValue"])
            if p["costType"] == "distance":
                radius = value * _TO_METERS[p.get("distanceUnit", "meter")]
            else:
                radius = value * _TO_SECONDS[p.get("timeUnit", "second")] * _SPEED_M_S[p.get("profile", "car")]
            return FakeResponse(
                {
                    "point": p["point"],
                    "resource": p["resource"],
                    "resourceVersion": "demo-2026-01-01",
                    "costType": p["costType"],
                    "costValue": value,
                    "geometry": {"type": "Polygon", "coordinates": [circle(lon, lat, radius)]},
                }
            )
        return FakeResponse({"error": "not found"}, 404)
