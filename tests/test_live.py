"""
Test against the ACTUAL service (network required). Ignored by default:

RUN_LIVE=1 python -m unittest tests.test_live -v

Run this once to confirm the actual structure of the responses (e.g., the "geometry" key, etc.).
"""

# Liiust

import os
import unittest

from isochrones_ign.api import GeoplateformeClient, IsochroneRequest


@unittest.skipUnless(os.environ.get("RUN_LIVE") == "1", "RUN_LIVE=1 required (network access)")
class TestLive(unittest.TestCase):
    def test_capabilities_and_isochrone(self):
        c = GeoplateformeClient()
        opts = c.get_options()
        print("Options read:", opts)
        self.assertTrue(opts.resources)
        self.assertNotIn("bdtopo-osrm", opts.resources)  # road only
        resp = c.compute(IsochroneRequest("2.337306,48.849319", opts.default_resource(), "time", 5, profile="pedestrian"), opts)
        self.assertIn(resp.geometry["type"], ("Polygon", "MultiPolygon"))
        print("resourceVersion :", resp.resource_version)
