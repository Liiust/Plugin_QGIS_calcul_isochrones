"""
Interface independent of Qt: should be tested outside of QGIS.

The PyQt dialog merely reads from/writes to widgets and calls this controller.
"""

# Liiust

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

from .api import (
    GeoplateformeClient,
    IsochroneRequest,
    IsochroneResponse,
    Options,
    parse_constraints,
    parse_point,
)
from .geo import build_feature_collection, layer_name


@dataclass
class IsochroneResult:
    request: IsochroneRequest
    response: IsochroneResponse
    feature_collection: Dict[str, Any]
    name: str


class IsochroneController:
    def __init__(self, client: Optional[GeoplateformeClient] = None):
        self.client = client or GeoplateformeClient()
        self.options = Options()

    def load_options(self) -> Options:
        """Call getCapabilities; in case of failure, keep the default values."""
        self.options = self.client.get_options()
        return self.options

    def constraint_help(self, resource: str) -> str:
        """Help text (tooltip): constraints available for the selected resource."""
        ro = self.options.for_resource(resource)
        if ro is None or not ro.constraints:
            return "No constraints available for this resource."
        lines = ["Maximum 3 constraints, separated by | or provided as a JSON list. Available:"]
        for spec in ro.constraints.values():
            vals = f" = {'/'.join(spec.values)}" if spec.values else ""
            lines.append(f"• {spec.key} : {'/'.join(spec.types)} ; operators {' '.join(spec.operators)}{vals}")
        return "\n".join(lines)

    def constraint_example(self, resource: str) -> str:
        ro = self.options.for_resource(resource)
        if ro is None or not ro.constraints:
            return ""
        spec = next(iter(ro.constraints.values()))
        value = spec.values[0] if spec.values else "1"
        return json.dumps({"constraintType": spec.types[0] if spec.types else "banned", "key": spec.key,
                           "operator": spec.operators[0] if spec.operators else "=", "value": value},
                          separators=(",", ":"))

    def build_request(self, form: Dict[str, Any]) -> IsochroneRequest:
        """Raw form values ​​-> Validated IsochroneRequest."""
        parse_point(form.get("point", ""), form.get("crs", "EPSG:4326") == "EPSG:4326")
        req = IsochroneRequest(
            point=form["point"].strip().replace(" ", ""),
            resource=form.get("resource") or self.options.default_resource(),
            cost_type=form.get("cost_type", "time"),
            cost_value=float(form.get("cost_value") or 0),
            profile=form.get("profile", "car"),
            direction=form.get("direction", "departure"),
            time_unit=form.get("time_unit", "minute"),
            distance_unit=form.get("distance_unit", "meter"),
            geometry_format=form.get("geometry_format", "geojson"),
            crs=form.get("crs", "EPSG:4326"),
            constraints=parse_constraints(form.get("constraints", "")),
        )
        req.validate(self.options)
        return req

    def compute(self, form: Dict[str, Any]) -> IsochroneResult:
        req = self.build_request(form)
        resp = self.client.compute(req, self.options)
        return IsochroneResult(req, resp, build_feature_collection(req, resp), layer_name(req))
