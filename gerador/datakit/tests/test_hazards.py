"""Pontos de atenção do OSM nos pacotes por estado: pontos_atencao.csv, schema 9 do pacote (hoje 11).

Entram: passagem de nível (railway=level_crossing), painel de velocidade (highway=speed_display) e hazard=*
(travessia de animais, curva, cruzamento perigoso, área escolar, queda de barreira; outro valor vira HAZARD).
Nó vira o ponto; via com hazard=* vira o seu nó do meio, como nas lombadas.
"""
import csv
import json
import os
import tempfile
import unittest

try:
    import osmium
    from osmium.osm.mutable import Node, Way
except ImportError:  # pragma: no cover
    osmium = None  # type: ignore[assignment]

from datakit.common import Hazard

BBOX = (-17.0, -50.0, -15.9, -48.9)


def _write_pbf(path):
    with osmium.SimpleWriter(path) as w:
        w.add_node(Node(id=1, location=(-49.0, -16.0), tags={"railway": "level_crossing"}))
        w.add_node(Node(id=2, location=(-49.1, -16.1), tags={"hazard": "animal_crossing"}))
        w.add_node(Node(id=3, location=(-49.2, -16.2), tags={"hazard": "dangerous_curve"}))
        w.add_node(Node(id=4, location=(-49.3, -16.3), tags={"hazard": "slippery"}))
        w.add_node(Node(id=5, location=(-49.4, -16.4), tags={"highway": "speed_display"}))
        w.add_node(Node(id=6, location=(-49.5, -16.5), tags={"highway": "traffic_signals"}))   # fica de fora
        w.add_node(Node(id=7, location=(-49.55, -16.55), tags={"railway": "crossing"}))         # pedestre: fora
        w.add_node(Node(id=8, location=(-49.56, -16.56), tags={"hazard": "no"}))                # fora
        w.add_node(Node(id=9, location=(-48.0, -15.0), tags={"hazard": "school_zone"}))          # fora da bbox
        w.add_node(Node(id=10, location=(-49.6000, -16.6)))
        w.add_node(Node(id=11, location=(-49.6002, -16.6)))
        w.add_node(Node(id=12, location=(-49.6004, -16.6)))
        w.add_way(Way(id=100, nodes=[10, 11, 12], tags={"hazard": "curves", "highway": "primary"}))
        w.add_way(Way(id=101, nodes=[10, 11, 12], tags={"highway": "primary"}))                # via comum: fora


@unittest.skipIf(osmium is None, "pyosmium não instalado")
class LoadHazards(unittest.TestCase):
    def test_kinds_and_what_stays_out(self):
        from datakit.sources import osm_pbf
        with tempfile.TemporaryDirectory() as tmp:
            pbf = os.path.join(tmp, "x.osm.pbf")
            _write_pbf(pbf)
            got = osm_pbf.load_hazards(pbf, bbox=BBOX)
        self.assertEqual(sorted((round(h.lat, 4), round(h.lng, 4), h.kind) for h in got), [
            (-16.6, -49.6002, "CURVE"),          # a via: o ponto do meio
            (-16.4, -49.4, "SPEED_DISPLAY"),
            (-16.3, -49.3, "HAZARD"),            # hazard sem tipo próprio
            (-16.2, -49.2, "CURVE"),
            (-16.1, -49.1, "ANIMAL_CROSSING"),
            (-16.0, -49.0, "LEVEL_CROSSING"),
        ])

    def test_without_a_bbox_every_one_comes_in(self):
        from datakit.sources import osm_pbf
        with tempfile.TemporaryDirectory() as tmp:
            pbf = os.path.join(tmp, "x.osm.pbf")
            _write_pbf(pbf)
            self.assertEqual(len(osm_pbf.load_hazards(pbf)), 7)


class HazardKind(unittest.TestCase):
    def test_tags(self):
        from datakit.sources.osm_pbf import hazard_kind
        self.assertEqual(hazard_kind({"railway": "level_crossing"}), "LEVEL_CROSSING")
        self.assertEqual(hazard_kind({"highway": "speed_display"}), "SPEED_DISPLAY")
        self.assertEqual(hazard_kind({"hazard": "Animal_Crossing"}), "ANIMAL_CROSSING")
        self.assertEqual(hazard_kind({"hazard": "school_zone;children"}), "SCHOOL_ZONE")   # o primeiro valor
        self.assertEqual(hazard_kind({"hazard": "dangerous_junction"}), "DANGEROUS_JUNCTION")
        self.assertEqual(hazard_kind({"hazard": "falling_rocks"}), "FALLING_ROCKS")
        self.assertEqual(hazard_kind({"hazard": "fog"}), "HAZARD")
        self.assertIsNone(hazard_kind({"hazard": "no"}))
        self.assertIsNone(hazard_kind({"highway": "traffic_signals"}))
        self.assertIsNone(hazard_kind({"railway": "rail"}))


class PackAndCatalog(unittest.TestCase):
    def test_the_pack_writes_each_point_once_and_counts_them(self):
        from datakit.build_pack import build as build_pack
        hazards = [Hazard(-16.0, -49.0, "LEVEL_CROSSING"), Hazard(-16.0, -49.0, "LEVEL_CROSSING"),
                   Hazard(-16.1, -49.1, "CURVE")]
        with tempfile.TemporaryDirectory() as d:
            m = build_pack("GO", d, [], [], [], sources=[], hazards=hazards)
            with open(os.path.join(d, "GO", "pontos_atencao.csv"), encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
        self.assertEqual(rows, [{"lat": "-16.100000", "lng": "-49.100000", "kind": "CURVE"},
                                {"lat": "-16.000000", "lng": "-49.000000", "kind": "LEVEL_CROSSING"}])
        self.assertEqual(m["counts"]["hazards"], 2)
        self.assertIn("pontos_atencao.csv", m["files"])
        self.assertEqual(m["schema"], 12)  # 12 desde o banco SQLite

    def test_the_catalog_lists_them_only_for_a_state_that_has_them(self):
        from datakit import build_catalog
        from datakit.build_pack import build as build_pack
        with tempfile.TemporaryDirectory() as tmp:
            packs, dist = os.path.join(tmp, "p"), os.path.join(tmp, "d")
            build_pack("GO", packs, [], [], [], sources=[], hazards=[Hazard(-16.0, -49.0, "LEVEL_CROSSING")])
            build_pack("AC", packs, [], [], [], sources=[])
            cat = build_catalog.build(packs, dist)
            published = os.path.exists(os.path.join(dist, "estados", "GO", "pontos_atencao.csv"))
        self.assertEqual((cat["ufs"]["GO"]["hazards"]["file"], cat["ufs"]["GO"]["hazards"]["count"]),
                         ("estados/GO/pontos_atencao.csv", 1))
        self.assertTrue(published)
        self.assertNotIn("hazards", cat["ufs"]["AC"])
        self.assertEqual(json.loads(json.dumps(cat))["schema"], 2, "o catálogo só ganha uma chave")


if __name__ == "__main__":
    unittest.main()
