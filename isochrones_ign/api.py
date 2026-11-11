"""
API layer: request, HTTP client, reading the `getCapabilities` document and the response.

No dependency on QGIS or Qt.
The only optional external dependency is 'requests' (otherwise, the standard library's `urllib` is used).
"""
# Liiust

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

BASE_URL = "https://data.geopf.fr/navigation"
MIN_INTERVAL_S = 0.2  # documented limit: 5 requests / second / IP


# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #
class GeoplateformeError(Exception):
    """Generic API layer error."""


class ValidationError(GeoplateformeError):
    """Invalid request parameters (detected before any network call)."""


class ApiError(GeoplateformeError):
    """HTTP error response or unusable response."""

    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


# --------------------------------------------------------------------------- #
# Options offered to the user (per resource, read from the getCapabilities)
# --------------------------------------------------------------------------- #
@dataclass
class ConstraintSpec:
    """An authorized constraint for a resource  (e.g. waytype / banned / = / tunnel)."""

    key: str
    types: List[str] = field(default_factory=list)
    operators: List[str] = field(default_factory=list)
    values: Optional[List[str]] = None  # None = free value


@dataclass
class ResourceOptions:
    """Parameters for the "isochrone" operation for ONE resource."""

    id: str
    description: str = ""
    profiles: List[str] = field(default_factory=lambda: ["car", "pedestrian"])
    directions: List[str] = field(default_factory=lambda: ["departure", "arrival"])
    cost_types: List[str] = field(default_factory=lambda: ["time", "distance"])
    time_units: List[str] = field(default_factory=lambda: ["hour", "minute", "second"])
    distance_units: List[str] = field(default_factory=lambda: ["kilometer", "meter"])
    geometry_formats: List[str] = field(default_factory=lambda: ["geojson"])
    crs: List[str] = field(default_factory=lambda: ["EPSG:4326"])
    cost_value_max: Optional[float] = 50000
    point_bbox: Optional[Tuple[float, float, float, float]] = None  # lon_min, lat_min, lon_max, lat_max
    constraints: Dict[str, ConstraintSpec] = field(default_factory=dict)


def _default_resources() -> Dict[str, ResourceOptions]:
    # Documentation values, used as long as the getCapabilities has not been read.
    return {rid: ResourceOptions(rid) for rid in ("bdtopo-valhalla", "bdtopo-pgr")}


@dataclass
class Options:
    """Resources compatible with the isochrone, along with their respective parameters."""

    resources: Dict[str, ResourceOptions] = field(default_factory=_default_resources)

    def ids(self) -> List[str]:
        return list(self.resources)

    def for_resource(self, rid: str) -> Optional[ResourceOptions]:
        return self.resources.get(rid)

    def default_resource(self) -> str:
        if "bdtopo-valhalla" in self.resources:
            return "bdtopo-valhalla"
        return next(iter(self.resources), "")


def _str_list(values: Any, fallback: List[str]) -> List[str]:
    if isinstance(values, list):
        out = [v for v in values if isinstance(v, str)]
        if out:
            return out
    return fallback


def _parse_resource(res: Dict[str, Any]) -> Optional[ResourceOptions]:
    ops = [o for o in res.get("availableOperations", []) if isinstance(o, dict) and o.get("id") == "isochrone"]
    if not ops:
        return None  # e.g. bdtopo-osrm : itinerary only
    params = {p["id"]: p.get("values") for p in ops[0].get("availableParameters", []) if isinstance(p, dict) and "id" in p}
    ro = ResourceOptions(id=res["id"], description=str(res.get("description", "")))
    ro.profiles = _str_list(params.get("profile"), ro.profiles)
    ro.directions = _str_list(params.get("direction"), ro.directions)
    ro.cost_types = _str_list(params.get("costType"), ro.cost_types)
    ro.time_units = _str_list(params.get("timeUnit"), ro.time_units)
    ro.distance_units = _str_list(params.get("distanceUnit"), ro.distance_units)
    ro.geometry_formats = _str_list(params.get("geometryFormat"), ro.geometry_formats)
    ro.crs = _str_list(params.get("projection"), ro.crs)  # "projection" in the GetCapabilities, "crs" in the request
    cv = params.get("costValue")
    if isinstance(cv, dict):
        ro.cost_value_max = cv.get("max")
    pt = params.get("point")
    if isinstance(pt, dict) and isinstance(pt.get("bbox"), str):
        try:
            x0, y0, x1, y1 = (float(v) for v in pt["bbox"].split(","))
            ro.point_bbox = (x0, y0, x1, y1)
        except ValueError:
            pass
    cons = params.get("constraints")
    if isinstance(cons, dict):
        for k in cons.get("keys", []):
            if isinstance(k, dict) and isinstance(k.get("key"), str):
                vals = k.get("values")
                ro.constraints[k["key"]] = ConstraintSpec(
                    key=k["key"],
                    types=_str_list(k.get("availableConstraintType"), []),
                    operators=_str_list(k.get("availableOperators"), []),
                    values=[str(v) for v in vals] if isinstance(vals, list) else None,
                )
    return ro


def parse_capabilities(doc: Any) -> Options:
    """getCapabilities -> options per resource (only for those that offer the isochrone feature). 

    Structure read: resources[].availableOperations[id="isochrone"].availableParameters[] (id + values). 
    If the document does not follow this structure, default values ​​are used.
    """
    if not isinstance(doc, dict) or not isinstance(doc.get("resources"), list):
        return Options()
    found: Dict[str, ResourceOptions] = {}
    for res in doc["resources"]:
        if isinstance(res, dict) and isinstance(res.get("id"), str):
            ro = _parse_resource(res)
            if ro is not None:
                found[ro.id] = ro
    return Options(resources=found) if found else Options()


# --------------------------------------------------------------------------- #
# Request
# --------------------------------------------------------------------------- #
_POINT_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")


def parse_point(text: str, geographic: bool = True) -> tuple[float, float]:
    """'2.337306,48.849319' -> (lon, lat) ; raise ValidationError if not valid."""
    m = _POINT_RE.match(text or "")
    if not m:
        raise ValidationError("Invalid point : expected ' lon,lat ' (e.g. 2.587476,48.849319).")
    lon, lat = float(m.group(1)), float(m.group(2))
    if geographic and not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise ValidationError("Out-of-bounds point : lon ∈ [-180;180], lat ∈ [-90;90].")
    return lon, lat


@dataclass
class IsochroneRequest:
    point: str  # "lon,lat" in the resource's CRS (EPSG:4326 by default)
    resource: str  # bdtopo-osrm | bdtopo-valhalla | bdtopo-pgr
    cost_type: str  # "time" | "distance"
    cost_value: float
    profile: str = "car"
    direction: str = "departure"
    time_unit: str = "minute"
    distance_unit: str = "meter"
    geometry_format: str = "geojson"
    crs: str = "EPSG:4326"
    constraints: Optional[Any] = None  # dict (or dict list) ; serialized in JSON

    def constraints_list(self) -> List[Dict[str, Any]]:
        if not self.constraints:
            return []
        return list(self.constraints) if isinstance(self.constraints, list) else [self.constraints]

    def validate(self, options: Optional[Options] = None) -> None:
        geographic = self.crs == "EPSG:4326"
        lon, lat = parse_point(self.point, geographic)
        if not self.resource:
            raise ValidationError("The resource is mandatory.")
        if self.cost_value is None or float(self.cost_value) <= 0:
            raise ValidationError("The cost value must be strictly positive.")
        if options is None:
            return
        ro = options.for_resource(self.resource)
        if ro is None:
            raise ValidationError(
                f"The resource '{self.resource}' does not offer isochrone calculation. "
                f"Available resources : {', '.join(options.ids()) or 'none'}."
            )
        for name, value, allowed in [
            ("costType", self.cost_type, ro.cost_types),
            ("profile", self.profile, ro.profiles),
            ("direction", self.direction, ro.directions),
            ("timeUnit", self.time_unit, ro.time_units),
            ("distanceUnit", self.distance_unit, ro.distance_units),
            ("geometryFormat", self.geometry_format, ro.geometry_formats),
            ("crs", self.crs, ro.crs),
        ]:
            if allowed and value not in allowed:
                raise ValidationError(f"{name} = ' {value} ' not offered by ' {ro.id} ' ({', '.join(allowed)}).")
        if ro.cost_value_max is not None and float(self.cost_value) > ro.cost_value_max:
            raise ValidationError(f"The cost value exceeds the permitted maximum ({ro.cost_value_max:g}).")
        if geographic and ro.point_bbox:
            x0, y0, x1, y1 = ro.point_bbox
            if not (x0 <= lon <= x1 and y0 <= lat <= y1):
                raise ValidationError(
                    f"The point is outside the area covered by ' {ro.id} ' "
                    f"(lon {x0:.2f} to {x1:.2f}, lat {y0:.2f} to {y1:.2f})."
                )
        self._validate_constraints(ro)

    def _validate_constraints(self, ro: ResourceOptions) -> None:
        cons = self.constraints_list()
        if len(cons) > 3:
            raise ValidationError("Maximum of 3 constraints.")
        for c in cons:
            if not isinstance(c, dict) or not {"constraintType", "key", "operator", "value"} <= set(c):
                raise ValidationError("Each constraint must contain constraintType, key, operator and value.")
            spec = ro.constraints.get(c["key"])
            if spec is None:
                raise ValidationError(
                    f"Constraint ' {c['key']} ' not available for ' {ro.id} ' "
                    f"(available : {', '.join(ro.constraints) or 'none'})."
                )
            if spec.types and c["constraintType"] not in spec.types:
                raise ValidationError(f"constraintType ' {c['constraintType']} ' invalid for {spec.key} ({', '.join(spec.types)}).")
            if spec.operators and c["operator"] not in spec.operators:
                raise ValidationError(f"operator ' {c['operator']} ' invalid for {spec.key} ({', '.join(spec.operators)}).")
            if spec.values is not None and str(c["value"]) not in spec.values:
                raise ValidationError(f"value ' {c['value']} ' invalid for {spec.key} ({', '.join(spec.values)}).")

    def to_params(self) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "point": self.point,
            "resource": self.resource,
            "costType": self.cost_type,
            "costValue": self.cost_value,
            "profile": self.profile,
            "direction": self.direction,
            "timeUnit": self.time_unit,
            "distanceUnit": self.distance_unit,
            "geometryFormat": self.geometry_format,
            "crs": self.crs,
        }
        cons = self.constraints_list()
        if cons:  # style ' pipeDelimited ' : one JSON object per constraint, separated by |
            params["constraints"] = "|".join(json.dumps(c, separators=(",", ":"), ensure_ascii=False) for c in cons)
        return params


def parse_constraints(text: str) -> Optional[Any]:
    """Input text -> dict, or list of dicts (JSON, or JSON objects separated by ' | ')."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        try:  # service format : {...}|{...}
            obj = [json.loads(part) for part in text.split("|")]
        except json.JSONDecodeError as exc:
            raise ValidationError(f"Constraints : invalid JSON ({exc.msg}).") from exc
    items = obj if isinstance(obj, list) else [obj]
    if not items or not all(isinstance(i, dict) for i in items):
        raise ValidationError("Constraints : a JSON object (or a list of objects) is expected.")
    return obj


# --------------------------------------------------------------------------- #
# Response
# --------------------------------------------------------------------------- #
@dataclass
class IsochroneResponse:
    geometry: Dict[str, Any]
    resource_version: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)


def parse_response(data: Any) -> IsochroneResponse:
    """Validates the service response and extracts the GeoJSON geometry from it."""
    if not isinstance(data, dict):
        raise ApiError("Unexpected response: a JSON object is expected.")
    geom = data.get("geometry")
    if isinstance(geom, str):
        raise ApiError("Geometry returned as a polyline: only the GeoJSON format is supported.")
    if not isinstance(geom, dict) or geom.get("type") not in ("Polygon", "MultiPolygon"):
        raise ApiError("Response lacks usable Polygon/MultiPolygon geometry (key 'geometry').")
    return IsochroneResponse(geometry=geom, resource_version=data.get("resourceVersion"), raw=data)


# --------------------------------------------------------------------------- #
# HTTP Transport
# --------------------------------------------------------------------------- #
class _UrllibResponse:
    def __init__(self, status: int, text: str):
        self.status_code = status
        self.text = text

    def json(self) -> Any:
        return json.loads(self.text)


class _UrllibSession:
    """Minimal fallback if `requests` is not installed."""

    def get(self, url: str, params: Optional[dict] = None, timeout: float = 30) -> _UrllibResponse:
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
                return _UrllibResponse(r.status, r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return _UrllibResponse(e.code, e.read().decode("utf-8", "replace"))
        except urllib.error.URLError as e:
            raise ApiError(f"Network unavailable : {e.reason}") from e


def default_session():
    try:
        import requests

        return requests.Session()
    except ImportError:
        return _UrllibSession()


class GeoplateformeClient:
    def __init__(
        self,
        base_url: str = BASE_URL,
        timeout: float = 60,
        session: Any = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session if session is not None else default_session()
        self._clock, self._sleep = clock, sleep
        self._last_call: Optional[float] = None

    def _throttle(self) -> None:
        now = self._clock()
        if self._last_call is not None:
            wait = MIN_INTERVAL_S - (now - self._last_call)
            if wait > 0:
                self._sleep(wait)
                now = self._clock()
        self._last_call = now

    def _get_json(self, path: str, params: Optional[dict] = None) -> Any:
        self._throttle()
        try:
            resp = self.session.get(f"{self.base_url}/{path}", params=params, timeout=self.timeout)
        except ApiError:
            raise
        except Exception as exc:  # network errors of requests, timeouts…
            raise ApiError(f"Échec de la requête : {exc}") from exc
        if resp.status_code != 200:
            raise ApiError(f"HTTP {resp.status_code} : {_error_text(resp)}", status=resp.status_code)
        try:
            return resp.json()
        except ValueError as exc:
            raise ApiError("The response is not valid JSON.") from exc

    def get_capabilities_raw(self) -> Any:
        return self._get_json("getCapabilities")

    def get_options(self) -> Options:
        return parse_capabilities(self.get_capabilities_raw())

    def compute(self, request: IsochroneRequest, options: Optional[Options] = None) -> IsochroneResponse:
        request.validate(options)
        return parse_response(self._get_json("isochrone", request.to_params()))


def _error_text(resp: Any) -> str:
    try:
        body = resp.json()
        if isinstance(body, dict):
            err = body.get("error", body)
            if isinstance(err, dict):
                return str(err.get("message") or err.get("detail") or err)
            return str(err)
    except Exception:  # noqa: BLE001
        pass
    return (getattr(resp, "text", "") or "")[:300]
