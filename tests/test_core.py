"""
Testing the entire logic without QGIS or a network: python -m unittest discover -s tests -v
"""

# Liiust

import json
import math
import os
import tempfile
import unittest

from isochrones_ign.api import (
    ApiError, GeoplateformeClient, IsochroneRequest, Options, ValidationError,
    parse_capabilities, parse_constraints, parse_point, parse_response, MIN_INTERVAL_S, ResourceOptions,
)
from isochrones_ign.controller import IsochroneController
from isochrones_ign.geo import approx_area_km2, bbox, build_feature_collection, layer_name, write_geojson
from isochrones_ign.offline import CAPABILITIES, FakeResponse, FakeSession, circle
from isochrones_ign import cli

FORM = {"point": "2.337306,48.849319", "resource": "bdtopo-valhalla", "cost_type": "time",
        "cost_value": 10, "profile": "pedestrian", "direction": "departure",
        "time_unit": "minute", "distance_unit": "meter", "constraints": ""}


class FakeClock:
    def __init__(self):
        self.t, self.sleeps = 0.0, []

    def now(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


class TestPointAndRequest(unittest.TestCase):
    def test_parse_point_ok(self):
        self.assertEqual(parse_point(" 2.337306 , 48.849319 "), (2.337306, 48.849319))

    def test_parse_point_invalid(self):
        for bad in ["", "abc", "2.3;48.8", "200,10", "10,95", "2.3"]:
            with self.assertRaises(ValidationError, msg=bad):
                parse_point(bad)

    def test_to_params_names_and_constraints(self):
        c = {"constraintType": "banned", "key": "wayType", "operator": "=", "value": "tunnel"}
        p = IsochroneRequest("2.3,48.8", "bdtopo-osrm", "distance", 2000, constraints=c).to_params()
        self.assertEqual(p["costType"], "distance")
        self.assertEqual(p["costValue"], 2000)
        self.assertEqual(p["timeUnit"], "minute")
        self.assertEqual(json.loads(p["constraints"]), c)
        self.assertNotIn("constraints", IsochroneRequest("2.3,48.8", "r", "time", 5).to_params())

    def test_validation(self):
        with self.assertRaises(ValidationError):
            IsochroneRequest("2.3,48.8", "r", "time", 0).validate()
        with self.assertRaises(ValidationError):
            IsochroneRequest("2.3,48.8", "", "time", 5).validate()
        opts = parse_capabilities(CAPABILITIES)
        with self.assertRaises(ValidationError):
            IsochroneRequest("2.3,48.8", "bdtopo-valhalla", "time", 5, profile="bike").validate(opts)
        with self.assertRaises(ValidationError):  # cost ceiling
            IsochroneRequest("2.3,48.8", "bdtopo-valhalla", "time", 60000).validate(opts)

    def test_resource_without_isochrone_is_rejected_locally(self):
        """Reason for a HTTP 400 error: bdtopo-osrm only handles routing."""
        opts = parse_capabilities(CAPABILITIES)
        with self.assertRaises(ValidationError) as cm:
            IsochroneRequest("2.3,48.8", "bdtopo-osrm", "time", 5).validate(opts)
        self.assertIn("does not offer isochrone calculation", str(cm.exception))

    def test_point_outside_resource_bbox(self):
        opts = parse_capabilities(CAPABILITIES)
        IsochroneRequest("2.34,48.85", "graphe_routier_r100_IGN", "time", 5).validate(opts)  # Paris : ok
        with self.assertRaises(ValidationError):  # Marseille : out of Seine Grands Lacs
            IsochroneRequest("5.37,43.30", "graphe_routier_r100_IGN", "time", 5).validate(opts)
        IsochroneRequest("5.37,43.30", "bdtopo-valhalla", "time", 5).validate(opts)  # covered

    def test_constraints_validated_against_capabilities(self):
        opts = parse_capabilities(CAPABILITIES)
        ok = {"constraintType": "banned", "key": "waytype", "operator": "=", "value": "tunnel"}
        IsochroneRequest("2.3,48.8", "bdtopo-valhalla", "time", 5, constraints=ok).validate(opts)
        for bad in [
            {**ok, "value": "rocade"},                   # unknown value
            {**ok, "operator": "!="},                    # operator not allowed (valhalla: "=" alone)
            {**ok, "key": "wayType"},                    # key: case-sensitive (“waytype”)
            {"key": "waytype"},                          # incomplete
        ]:
            with self.assertRaises(ValidationError, msg=bad):
                IsochroneRequest("2.3,48.8", "bdtopo-valhalla", "time", 5, constraints=bad).validate(opts)
        with self.assertRaises(ValidationError):         # 4 constraints > 3 max
            IsochroneRequest("2.3,48.8", "bdtopo-valhalla", "time", 5, constraints=[ok] * 4).validate(opts)

    def test_constraints_pipe_delimited(self):
        a = {"constraintType": "banned", "key": "waytype", "operator": "=", "value": "tunnel"}
        b = {**a, "value": "pont"}
        p = IsochroneRequest("2.3,48.8", "bdtopo-valhalla", "time", 5, constraints=[a, b]).to_params()
        self.assertEqual(p["constraints"].count("|"), 1)
        self.assertEqual([json.loads(x) for x in p["constraints"].split("|")], [a, b])

    def test_parse_constraints(self):
        self.assertIsNone(parse_constraints("  "))
        self.assertEqual(parse_constraints('{"a": 1}'), {"a": 1})
        for bad in ["{oops", "3", '"x"']:
            with self.assertRaises(ValidationError):
                parse_constraints(bad)


class TestCapabilities(unittest.TestCase):
    def test_parse_fake_capabilities(self):
        o = parse_capabilities(CAPABILITIES)
        self.assertEqual(o.ids(), ["bdtopo-valhalla", "bdtopo-pgr", "graphe_routier_r100_IGN"])
        self.assertNotIn("bdtopo-osrm", o.resources)
        self.assertEqual(o.default_resource(), "bdtopo-valhalla")
        self.assertEqual(o.resources["bdtopo-pgr"].profiles, ["car", "pedestrian"])

    def test_unknown_doc_falls_back_to_defaults(self):
        for doc in [{"foo": 1}, "n'importe quoi", {"resources": []}, {"resources": [{"id": "x", "availableOperations": []}]}]:
            self.assertEqual(parse_capabilities(doc).ids(), ["bdtopo-valhalla", "bdtopo-pgr"])


class TestRealCapabilities(unittest.TestCase):
    """Test the parser using the ACTUAL getCapabilities"""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(os.path.dirname(__file__), "capabilities_reel.json"), encoding="utf-8") as fh:
            cls.opts = parse_capabilities(json.load(fh))

    def test_osrm_excluded_and_12_isochrone_resources(self):
        self.assertNotIn("bdtopo-osrm", self.opts.resources)
        self.assertEqual(len(self.opts.resources), 12)
        self.assertEqual(self.opts.default_resource(), "bdtopo-valhalla")

    def test_valhalla_details(self):
        r: ResourceOptions = self.opts.resources["bdtopo-valhalla"]
        self.assertEqual(r.cost_value_max, 50000)
        self.assertEqual(r.point_bbox[:2], (-63.28125, -21.42148437))
        self.assertIn("EPSG:2154", r.crs)
        self.assertEqual(list(r.constraints), ["waytype"])
        self.assertEqual(r.constraints["waytype"].values, ["autoroute", "pont", "tunnel"])

    def test_pgr_has_more_constraints_and_r100_is_regional(self):
        self.assertEqual(len(self.opts.resources["bdtopo-pgr"].constraints), 11)
        self.assertEqual(self.opts.resources["graphe_routier_r100_IGN"].crs, ["EPSG:4326"])
        self.assertAlmostEqual(self.opts.resources["graphe_routier_r100_IGN"].point_bbox[0], 1.3623, places=3)


class TestResponse(unittest.TestCase):
    def test_ok(self):
        r = parse_response({"geometry": {"type": "Polygon", "coordinates": []}, "resourceVersion": "v1"})
        self.assertEqual(r.resource_version, "v1")

    def test_errors(self):
        for bad in [[], {}, {"geometry": "abc~def"}, {"geometry": {"type": "Point", "coordinates": [0, 0]}}]:
            with self.assertRaises(ApiError):
                parse_response(bad)


class TestClient(unittest.TestCase):
    def test_throttle_respects_5_req_per_second(self):
        clk, s = FakeClock(), FakeSession()
        c = GeoplateformeClient(session=s, clock=clk.now, sleep=clk.sleep)
        for _ in range(3):
            c.get_capabilities_raw()
        self.assertEqual(len(s.calls), 3)
        self.assertEqual(len(clk.sleeps), 2)
        self.assertTrue(all(abs(x - MIN_INTERVAL_S) < 1e-9 for x in clk.sleeps))

    def test_server_400_reproduced_when_validation_is_bypassed(self):
        c = GeoplateformeClient(session=FakeSession())
        with self.assertRaises(ApiError) as cm:  # no options => no local control, the server refuses
            c.compute(IsochroneRequest("2.3,48.8", "bdtopo-osrm", "time", 5))
        self.assertEqual(cm.exception.status, 400)
        self.assertIn("Operation not permitted", str(cm.exception))

    def test_http_error_message(self):
        c = GeoplateformeClient(session=FakeSession(fail_with=400))
        with self.assertRaises(ApiError) as cm:
            c.compute(IsochroneRequest("2.3,48.8", "bdtopo-valhalla", "time", 5))
        self.assertEqual(cm.exception.status, 400)
        self.assertIn("refusée", str(cm.exception))

    def test_network_exception_and_bad_json(self):
        class Boom:
            def get(self, *a, **k):
                raise TimeoutError("too long")

        with self.assertRaises(ApiError):
            GeoplateformeClient(session=Boom()).get_capabilities_raw()

        class BadJson:
            def get(self, *a, **k):
                r = FakeResponse(None)
                r.json = lambda: (_ for _ in ()).throw(ValueError("x"))
                return r

        with self.assertRaises(ApiError):
            GeoplateformeClient(session=BadJson()).get_capabilities_raw()

    def test_validation_happens_before_network(self):
        s = FakeSession()
        with self.assertRaises(ValidationError):
            GeoplateformeClient(session=s).compute(IsochroneRequest("nope", "bdtopo-valhalla", "time", 5))
        self.assertEqual(s.calls, [])


class TestGeo(unittest.TestCase):
    def test_area_of_circle(self):
        g = {"type": "Polygon", "coordinates": [circle(2.33, 48.85, 2000)]}
        self.assertAlmostEqual(approx_area_km2(g), math.pi * 2.0**2, delta=0.02 * math.pi * 4)

    def test_hole_and_multipolygon(self):
        outer, hole = circle(2.3, 48.8, 3000), circle(2.3, 48.8, 1000)
        a = approx_area_km2({"type": "Polygon", "coordinates": [outer, hole]})
        self.assertAlmostEqual(a, math.pi * (9 - 1), delta=0.6)
        mp = {"type": "MultiPolygon", "coordinates": [[outer], [circle(2.4, 48.9, 1000)]]}
        self.assertAlmostEqual(approx_area_km2(mp), math.pi * (9 + 1), delta=0.6)

    def test_bbox(self):
        x0, y0, x1, y1 = bbox({"type": "Polygon", "coordinates": [[[0, 0], [2, 0], [2, 1], [0, 1], [0, 0]]]})
        self.assertEqual((x0, y0, x1, y1), (0, 0, 2, 1))

    def test_write_geojson_roundtrip(self):
        req = IsochroneRequest("2.3,48.8", "r", "time", 10)
        res = parse_response({"geometry": {"type": "Polygon", "coordinates": [circle(2.3, 48.8, 500)]}, "resourceVersion": "v"})
        fc = build_feature_collection(req, res)
        with tempfile.TemporaryDirectory() as d:
            path = write_geojson(fc, "Isochrone 10 minute (car, departure)", d)
            self.assertTrue(path.endswith(".geojson") and os.path.dirname(path) == d)
            with open(path, encoding="utf-8") as fh:
                back = json.load(fh)
        self.assertEqual(back["features"][0]["properties"]["resourceVersion"], "v")
        self.assertEqual(layer_name(req), "Isochrone 10 minute (car, departure)")


class TestControllerEndToEnd(unittest.TestCase):
    def setUp(self):
        self.session = FakeSession()
        self.ctrl = IsochroneController(GeoplateformeClient(session=self.session))

    def test_full_flow(self):
        opts = self.ctrl.load_options()
        self.assertIn("pedestrian", opts.resources["bdtopo-valhalla"].profiles)
        res = self.ctrl.compute(FORM)
        call = self.session.calls[-1]
        self.assertTrue(call["url"].endswith("/isochrone"))
        self.assertEqual(call["params"]["profile"], "pedestrian")
        # 10 min à pied (≈1,11 m/s) -> rayon ≈ 666 m -> aire ≈ 1,39 km²
        self.assertAlmostEqual(approx_area_km2(res.response.geometry), math.pi * 0.666**2, delta=0.05)
        self.assertEqual(res.feature_collection["features"][0]["properties"]["costValue"], 10.0)

    def test_invalid_form(self):
        self.ctrl.load_options()
        n = len(self.session.calls)
        for patch in [{"point": "x"}, {"cost_value": 0}, {"constraints": "{bad"}, {"profile": "bike"},
                      {"resource": "bdtopo-osrm"}, {"point": "5.37,43.30", "resource": "graphe_routier_r100_IGN"}]:
            with self.assertRaises(ValidationError, msg=patch):
                self.ctrl.build_request({**FORM, **patch})
        self.assertEqual(len(self.session.calls), n)  # no network call for invalid input

    def test_constraint_helpers_and_pipe_input(self):
        self.ctrl.load_options()
        ex = self.ctrl.constraint_example("bdtopo-valhalla")
        self.assertEqual(json.loads(ex)["key"], "waytype")
        self.assertIn("waytype", self.ctrl.constraint_help("bdtopo-valhalla"))
        two = ex + "|" + ex.replace("autoroute", "pont")
        req = self.ctrl.build_request({**FORM, "constraints": two})
        self.assertEqual(len(req.constraints_list()), 2)


class TestCli(unittest.TestCase):
    def test_demo_compute_writes_geojson(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "iso.geojson")
            code = cli.main(["--demo", "compute", "--point", "2.3373,48.8493", "--cost-type", "distance",
                             "--cost-value", "2000", "--profile", "car", "--out", out])
            self.assertEqual(code, 0)
            with open(out, encoding="utf-8") as fh:
                fc = json.load(fh)
        self.assertEqual(fc["features"][0]["geometry"]["type"], "Polygon")

    def test_demo_error_code(self):
        self.assertEqual(cli.main(["--demo", "compute", "--point", "bad", "--cost-value", "5"]), 1)


if __name__ == "__main__":
    unittest.main()
