"""Contorno das UFs: brasil/ufs.geojson e a chave `ufs_geojson` do catalogo.json."""
import json
import os
import tempfile
import unittest

try:
    from shapely.geometry import MultiPolygon, Point, box, shape
except ImportError:  # pragma: no cover
    box = None  # type: ignore[assignment]

from datakit import build_ufs


def _wiggly():
    """Um retângulo de 2° x 1° com a borda de cima cheia de dentes de 0,0005° (somem na simplificação)."""
    top = [(-48.0 - i * 0.02, -15.0 + (0.0005 if i % 2 else 0.0)) for i in range(101)]
    return shape({"type": "Polygon", "coordinates": [[(-50.0, -16.0), (-48.0, -16.0)] + top + [(-50.0, -16.0)]]})


@unittest.skipIf(box is None, "shapely não instalado")
class UfsGeojson(unittest.TestCase):
    def test_one_feature_per_state_with_uf_and_name_in_order(self):
        fc = build_ufs.feature_collection({"SP": box(-48, -24, -46, -22), "GO": box(-50, -17, -48, -15)})
        self.assertEqual(fc["type"], "FeatureCollection")
        self.assertEqual([(f["properties"]["uf"], f["properties"]["name"], f["geometry"]["type"])
                          for f in fc["features"]], [("GO", "Goiás", "Polygon"), ("SP", "São Paulo", "Polygon")])

    def test_multipolygons_stay_multipolygons(self):
        islands = MultiPolygon([box(-40, -20, -39, -19), box(-38, -20, -37.5, -19.5)])
        (feature,) = build_ufs.feature_collection({"ES": islands})["features"]
        self.assertEqual(feature["geometry"]["type"], "MultiPolygon")
        self.assertEqual(len(feature["geometry"]["coordinates"]), 2)

    def test_simplifying_drops_the_small_teeth_but_keeps_the_shape_within_the_tolerance(self):
        poly = _wiggly()
        (feature,) = build_ufs.feature_collection({"GO": poly}, tolerance=0.01)["features"]
        simple = shape(feature["geometry"])
        self.assertLess(len(feature["geometry"]["coordinates"][0]), len(poly.exterior.coords) / 5)
        self.assertLessEqual(poly.hausdorff_distance(simple), 0.011)
        self.assertTrue(simple.contains(Point(-49.5, -15.5)))

    def test_coordinates_are_rounded(self):
        (feature,) = build_ufs.feature_collection({"GO": box(-50.123456789, -17.987654321, -48.5, -15.5)},
                                                  decimals=4)["features"]
        flat = [c for ring in feature["geometry"]["coordinates"] for pt in ring for c in pt]
        self.assertTrue(all(round(c, 4) == c for c in flat))
        self.assertIn(-50.1235, flat)

    def test_the_file_and_the_catalog_key(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "catalogo.json"), "w", encoding="utf-8") as f:
                json.dump({"schema": 2, "ufs": {}}, f)
            entry = build_ufs.build({"GO": box(-50, -17, -48, -15)}, d)
            assert entry is not None
            with open(os.path.join(d, "brasil", "ufs.geojson"), encoding="utf-8") as f:
                body = f.read()
            with open(os.path.join(d, "catalogo.json"), encoding="utf-8") as f:
                cat = json.load(f)
            import hashlib
            digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        self.assertEqual(cat["ufs_geojson"], {"file": "brasil/ufs.geojson", "bytes": len(body.encode("utf-8")),
                                              "sha256": digest})
        self.assertEqual(cat["schema"], 2)
        self.assertEqual(json.loads(body)["features"][0]["properties"]["uf"], "GO")

    def test_without_polygons_there_is_no_file_and_an_old_one_goes_away(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "brasil"))
            path = os.path.join(d, "brasil", "ufs.geojson")
            with open(path, "w", encoding="utf-8") as f:
                f.write("{}")
            with open(os.path.join(d, "catalogo.json"), "w", encoding="utf-8") as f:
                json.dump({"schema": 2, "ufs": {}, "ufs_geojson": {"file": "brasil/ufs.geojson"}}, f)
            self.assertIsNone(build_ufs.build({}, d))
            gone = not os.path.exists(path)
            with open(os.path.join(d, "catalogo.json"), encoding="utf-8") as f:
                cat = json.load(f)
        self.assertTrue(gone)
        self.assertNotIn("ufs_geojson", cat)

    def test_the_name_is_published(self):
        from datakit import build_brazil
        self.assertTrue(build_brazil.PUBLISHED_NAME.match("ufs.geojson"))


if __name__ == "__main__":
    unittest.main()
