"""
Using the plugin WITHOUT QGIS (via terminal). 

  python -m dev.cli capabilities            # displays the service's raw JSON
  python -m dev.cli compute --point 2.587476,48.841221 --cost-type time \\ # test centered on Géodata Paris (ENSG)
        --cost-value 20 --profile pedestrian --out iso.geojson
  python -m dev.cli compute ... --demo       # without a network (mock server), using offline.py

The resulting .geojson file can be opened in QGIS (via drag-and-drop for example).
"""

# Liiust

from __future__ import annotations

import argparse
import json
import sys

from .api import GeoplateformeClient, GeoplateformeError
from .controller import IsochroneController
from .geo import approx_area_km2, bbox
from .offline import FakeSession


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="isochrones_ign")
    ap.add_argument("--demo", action="store_true", help="uses a dummy server (no network access)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    cp = sub.add_parser("capabilities", help="displays the raw getCapabilities")
    cp.add_argument("--summary", action="store_true", help="readable summary of isochrone-compatible resources")
    c = sub.add_parser("compute", help="calculate an isochrone/isodistance")
    c.add_argument("--point", required=True, help="lon,lat (EPSG:4326)")
    c.add_argument("--resource", default="bdtopo-valhalla")
    c.add_argument("--cost-type", default="time", choices=["time", "distance"])
    c.add_argument("--cost-value", type=float, required=True)
    c.add_argument("--profile", default="car")
    c.add_argument("--direction", default="departure")
    c.add_argument("--time-unit", default="minute")
    c.add_argument("--distance-unit", default="meter")
    c.add_argument("--constraints", default="", help="ex. '{\"constraintType\":\"banned\",\"key\":\"waytype\",\"operator\":\"=\",\"value\":\"tunnel\"}' (Max 3, separated by | )")
    c.add_argument("--out", default="isochrone.geojson")
    args = ap.parse_args(argv)

    client = GeoplateformeClient(session=FakeSession() if args.demo else None)
    try:
        if args.cmd == "capabilities":
            raw = client.get_capabilities_raw()
            if not args.summary:
                print(json.dumps(raw, indent=2, ensure_ascii=False))
                return 0
            from .api import parse_capabilities

            for ro in parse_capabilities(raw).resources.values():
                print(f"{ro.id}\n  zone : {ro.point_bbox}  max : {ro.cost_value_max}  crs : {', '.join(ro.crs)}")
                print(f"  contraintes : {', '.join(ro.constraints) or '-'}")
            return 0
        ctrl = IsochroneController(client)
        ctrl.load_options()
        res = ctrl.compute(
            {
                "point": args.point, "resource": args.resource, "cost_type": args.cost_type,
                "cost_value": args.cost_value, "profile": args.profile, "direction": args.direction,
                "time_unit": args.time_unit, "distance_unit": args.distance_unit,
                "constraints": args.constraints,
            }
        )
    except GeoplateformeError as exc:
        print(f"Error : {exc}", file=sys.stderr)
        return 1

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(res.feature_collection, fh, ensure_ascii=False)
    g = res.response.geometry
    print(f"{res.name}\n  data version: {res.response.resource_version}")
    print(f"  ground footprint : {tuple(round(v, 5) for v in bbox(g))}\n  area ≈ {approx_area_km2(g):.2f} km²\n  -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
