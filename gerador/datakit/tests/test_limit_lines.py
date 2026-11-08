"""Limites como trechos de via: limites_trechos.csv, schema 10 do pacote.

Do OSM, cada via com limite (sinalizado ou estimado) vira uma linha; vias contíguas de mesmos atributos se juntam; o
trecho de fonte oficial (Rio, CET, placas da ANTT) ganha, e do OSM sai o que ele cobre.
"""
import csv
import json
import os
import tempfile
import unittest
from array import array

try:
    import osmium
    from osmium.osm.mutable import Node, Way
except ImportError:  # pragma: no cover
    osmium = None  # type: ignore[assignment]

from datakit import limit_lines as ll
from datakit.common import LimitLine

LAT = -16.0
LNG = -49.0


def _east(n: int, lat: float = LAT):
    """n-ésimo ponto de uma reta leste-oeste, a ~100 m um do outro (0,001° de longitude)."""
    return (lat, LNG + 0.001 * n)


def _piece(points, kmh=60, source="OSM", estimated=False, directional=False, highway="primary", oneway=False,
           start=None, end=None):
    key = ll.make_key(kmh, source, estimated, 40 if estimated else None, directional, highway, oneway)
    return ll.from_points(points, key, start, end, epsilon_m=0)


def _write_pbf(path, ways):
    """ways: [(id, tags, [(lat, lng) | id de nó já escrito])]. Nós com id próprio: ('n', id, lat, lng)."""
    with osmium.SimpleWriter(path) as w:
        nodes = {}
        for _wid, _tags, pts in ways:
            for p in pts:
                nid, lat, lng = p
                if nid not in nodes:
                    nodes[nid] = (lat, lng)
        for nid in sorted(nodes):
            lat, lng = nodes[nid]
            w.add_node(Node(id=nid, location=(lng, lat)))
        for wid, tags, pts in ways:
            w.add_way(Way(id=wid, nodes=[p[0] for p in pts], tags=tags))


def _line(first_id, n, lat=LAT, step=1):
    """n+1 nós numa reta leste-oeste a partir do id dado: [(id, lat, lng)]."""
    return [(first_id + i, lat, LNG + 0.001 * step * i) for i in range(n + 1)]


def _load(ways):
    from datakit.sources import osm_pbf
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "t.osm.pbf")
        _write_pbf(path, ways)
        pieces = []
        osm_pbf.load(path, lines_out=pieces)
    return pieces


def _lines(ways, join=True):
    pieces = _load(ways)
    return ll.to_lines(ll.join(pieces) if join else pieces)


def _by_value(lines):
    return sorted((x.limit_kmh, x.source, x.estimated, x.direction_deg, x.highway, x.oneway) for x in lines)


@unittest.skipIf(osmium is None, "pyosmium não instalado")
class OsmLines(unittest.TestCase):
    def test_a_signed_way_is_one_line_with_the_class_and_without_direction(self):
        got = _lines([(100, {"highway": "primary", "maxspeed": "60"}, _line(1, 2))])
        self.assertEqual(len(got), 1)
        self.assertEqual(_by_value(got), [(60, "OSM", False, None, "primary", False)])
        self.assertEqual(got[0].points[0], (LAT, LNG))                  # desenhada como no OSM
        self.assertEqual(got[0].points[-1], (LAT, LNG + 0.002))
        self.assertIsNone(got[0].low_kmh)

    def test_an_unsigned_main_road_is_an_estimated_line_with_the_low_side(self):
        got = _lines([(100, {"highway": "tertiary", "lit": "yes"}, _line(1, 1)),
                      (101, {"highway": "secondary", "zone:maxspeed": "BR:urban"}, _line(10, 1, lat=-16.1))])
        by_hw = {x.highway: x for x in got}
        self.assertEqual((by_hw["tertiary"].limit_kmh, by_hw["tertiary"].low_kmh, by_hw["tertiary"].source,
                          by_hw["tertiary"].estimated), (40, 40, "OSM:class", True))
        self.assertEqual((by_hw["secondary"].limit_kmh, by_hw["secondary"].low_kmh, by_hw["secondary"].source),
                         (60, 50, "OSM:zone"))

    def test_a_road_class_outside_the_estimate_and_without_maxspeed_has_no_line(self):
        self.assertEqual(_lines([(100, {"highway": "residential"}, _line(1, 1)),
                                 (101, {"highway": "footway", "maxspeed": "30"}, _line(10, 1, lat=-16.1))]), [])

    def test_a_main_road_without_lit_is_estimated_after_the_whole_read(self):
        """Tronco sem lit: no campo é estrada (100); no meio de ruas é avenida (60, a regra do _is_urban)."""
        rural = _lines([(100, {"highway": "trunk"}, _line(1, 1))])
        self.assertEqual([(x.limit_kmh, x.low_kmh, x.estimated) for x in rural], [(100, 100, True)])
        self.assertEqual(rural[0].highway, "trunk")
        streets = [(200 + i, {"highway": "residential"}, [(50 + 2 * i, LAT + 0.0001 * i, LNG),
                                                         (51 + 2 * i, LAT + 0.0001 * i, LNG + 0.001)])
                   for i in range(5)]
        urban = _lines([(100, {"highway": "primary"}, _line(1, 1))] + streets)
        self.assertEqual([(x.limit_kmh, x.estimated) for x in urban], [(60, True)])

    def test_forward_and_backward_are_one_line_per_direction_drawn_with_the_traffic(self):
        got = _lines([(100, {"highway": "residential", "maxspeed:forward": "60", "maxspeed:backward": "40"},
                       _line(1, 2))])
        self.assertEqual(_by_value(got), [(40, "OSM", False, 270, "residential", False),
                                          (60, "OSM", False, 90, "residential", False)])
        by_kmh = {x.limit_kmh: x for x in got}
        self.assertEqual(by_kmh[60].points[0], (LAT, LNG))                       # sentido do desenho: oeste -> leste
        self.assertEqual(by_kmh[40].points[0], (LAT, LNG + 0.002))               # o contrário: leste -> oeste

    def test_one_side_signed_keeps_the_estimate_for_the_other_side(self):
        got = _lines([(100, {"highway": "tertiary", "maxspeed:forward": "60", "lit": "yes"}, _line(1, 1))])
        self.assertEqual(_by_value(got), [(40, "OSM:class", True, 270, "tertiary", False),
                                          (60, "OSM", False, 90, "tertiary", False)])

    def test_same_value_both_ways_is_a_plain_line(self):
        got = _lines([(100, {"highway": "residential", "maxspeed:forward": "50", "maxspeed:backward": "50"},
                       _line(1, 1))])
        self.assertEqual(_by_value(got), [(50, "OSM", False, None, "residential", False)])

    def test_oneway_follows_the_traffic_and_keeps_no_direction(self):
        got = _lines([(100, {"highway": "primary", "maxspeed": "60", "oneway": "yes"}, _line(1, 1)),
                      (101, {"highway": "primary", "maxspeed": "70", "oneway": "-1"}, _line(10, 1, lat=-16.1))])
        by_kmh = {x.limit_kmh: x for x in got}
        self.assertEqual((by_kmh[60].oneway, by_kmh[60].direction_deg), (True, None))
        self.assertEqual(by_kmh[60].points[0], (LAT, LNG))
        self.assertEqual(by_kmh[70].points[0], (-16.1, LNG + 0.001))              # oneway=-1: contra o desenho

    def test_oneway_ignores_the_limit_of_the_side_without_traffic(self):
        got = _lines([(100, {"highway": "primary", "oneway": "yes", "maxspeed": "60", "maxspeed:backward": "30"},
                       _line(1, 1))])
        self.assertEqual(_by_value(got), [(60, "OSM", False, None, "primary", True)])

    def test_motorway_and_roundabout_are_oneway_without_the_tag(self):
        got = _lines([(100, {"highway": "motorway", "maxspeed": "110"}, _line(1, 1)),
                      (101, {"highway": "primary", "junction": "roundabout", "maxspeed": "30"},
                       _line(10, 1, lat=-16.1)),
                      (102, {"highway": "motorway", "oneway": "no", "maxspeed": "90"}, _line(20, 1, lat=-16.2))])
        self.assertEqual({x.limit_kmh: x.oneway for x in got}, {110: True, 30: True, 90: False})

    def test_two_way_roads_are_not_oneway_and_say_so(self):
        got = _lines([(100, {"highway": "primary", "maxspeed": "60"}, _line(1, 1))])
        self.assertIs(got[0].oneway, False)


@unittest.skipIf(osmium is None, "pyosmium não instalado")
class JoinContiguous(unittest.TestCase):
    def test_contiguous_ways_with_the_same_attributes_become_one_line(self):
        tags = {"highway": "primary", "maxspeed": "60"}
        ways = [(100, tags, [(1, LAT, LNG), (2, LAT, LNG + 0.001), (3, LAT, LNG + 0.002)]),
                (101, tags, [(3, LAT, LNG + 0.002), (4, LAT, LNG + 0.003), (5, LAT, LNG + 0.004)])]
        got = _lines(ways)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0].points[0], (LAT, LNG))
        self.assertEqual(got[0].points[-1], (LAT, LNG + 0.004))
        self.assertEqual(len(_lines(ways, join=False)), 2)

    def test_a_different_value_or_class_is_not_joined(self):
        ways = [(100, {"highway": "primary", "maxspeed": "60"}, [(1, LAT, LNG), (2, LAT, LNG + 0.001)]),
                (101, {"highway": "primary", "maxspeed": "70"}, [(2, LAT, LNG + 0.001), (3, LAT, LNG + 0.002)]),
                (102, {"highway": "secondary", "maxspeed": "70"}, [(3, LAT, LNG + 0.002), (4, LAT, LNG + 0.003)])]
        self.assertEqual(len(_lines(ways)), 3)

    def test_ways_drawn_in_opposite_directions_join_when_the_road_is_two_way(self):
        ways = [(100, {"highway": "primary", "maxspeed": "60"}, [(1, LAT, LNG), (2, LAT, LNG + 0.001)]),
                (101, {"highway": "primary", "maxspeed": "60"}, [(3, LAT, LNG + 0.002), (2, LAT, LNG + 0.001)])]
        got = _lines(ways)
        self.assertEqual(len(got), 1)
        self.assertEqual({got[0].points[0], got[0].points[-1]}, {(LAT, LNG), (LAT, LNG + 0.002)})

    def test_oneway_ways_only_join_following_the_traffic(self):
        tags = {"highway": "primary", "maxspeed": "60", "oneway": "yes"}
        following = [(100, tags, [(1, LAT, LNG), (2, LAT, LNG + 0.001)]),
                     (101, tags, [(2, LAT, LNG + 0.001), (3, LAT, LNG + 0.002)])]
        head_on = [(100, tags, [(1, LAT, LNG), (2, LAT, LNG + 0.001)]),
                   (101, tags, [(3, LAT, LNG + 0.002), (2, LAT, LNG + 0.001)])]
        self.assertEqual(len(_lines(following)), 1)
        self.assertEqual(len(_lines(head_on)), 2)

    def test_oneway_reversed_by_the_tag_joins_in_the_traffic_direction(self):
        fwd = {"highway": "primary", "maxspeed": "60", "oneway": "yes"}
        back = {"highway": "primary", "maxspeed": "60", "oneway": "-1"}
        # a 101 é desenhada de leste para oeste mas o trânsito vai de oeste para leste: segue a 100
        ways = [(100, fwd, [(1, LAT, LNG), (2, LAT, LNG + 0.001)]),
                (101, back, [(3, LAT, LNG + 0.002), (2, LAT, LNG + 0.001)])]
        got = _lines(ways)
        self.assertEqual(len(got), 1)
        self.assertEqual((got[0].points[0], got[0].points[-1]), ((LAT, LNG), (LAT, LNG + 0.002)))

    def test_a_node_where_three_ways_meet_is_not_a_join(self):
        tags = {"highway": "primary", "maxspeed": "60"}
        ways = [(100, tags, [(1, LAT, LNG), (2, LAT, LNG + 0.001)]),
                (101, tags, [(2, LAT, LNG + 0.001), (3, LAT, LNG + 0.002)]),
                (102, tags, [(2, LAT, LNG + 0.001), (4, LAT + 0.001, LNG + 0.001)])]
        self.assertEqual(len(_lines(ways)), 3)

    def test_directional_lines_join_per_direction_and_the_direction_is_recomputed(self):
        tags = {"highway": "residential", "maxspeed:forward": "60", "maxspeed:backward": "40"}
        ways = [(100, tags, [(1, LAT, LNG), (2, LAT, LNG + 0.001)]),
                (101, tags, [(2, LAT, LNG + 0.001), (3, LAT + 0.001, LNG + 0.001)])]   # dobra para o norte
        got = _lines(ways)
        self.assertEqual(sorted((x.limit_kmh, len(x.points)) for x in got), [(40, 3), (60, 3)])
        by_kmh = {x.limit_kmh: x for x in got}
        self.assertEqual(by_kmh[60].points[0], (LAT, LNG))
        self.assertEqual(by_kmh[40].points[0], (LAT + 0.001, LNG + 0.001))
        # leste (90) por 111 m e norte (0) por 111 m: rumo médio ~45 para 60, 225 para 40
        self.assertIn(by_kmh[60].direction_deg, range(43, 48))
        self.assertIn(by_kmh[40].direction_deg, range(223, 228))

    def test_a_joined_line_stops_at_the_length_cap(self):
        # 8 vias de ~1,1 km: o teto de 5 km deixa até 4 por linha
        tags = {"highway": "primary", "maxspeed": "60"}
        ways = [(100 + i, tags, [(10 + i, LAT, LNG + 0.01 * i), (11 + i, LAT, LNG + 0.01 * (i + 1))])
                for i in range(8)]
        got = _lines(ways)
        self.assertEqual(sorted(len(x.points) for x in got), [5, 5])

    def test_joined_pieces_keep_one_node_between_them(self):
        a = _piece([_east(0), _east(1)], start=1, end=2)
        b = _piece([_east(1), _east(2)], start=2, end=3)
        (joined,) = ll.join([a, b])
        self.assertEqual(joined.points(), [_east(0), _east(1), _east(2)])
        self.assertEqual((joined.start, joined.end), (1, 3))


class Cut(unittest.TestCase):
    def _cut(self, osm, official, **kw):
        out, stats = ll.cut(osm, official, **kw)
        return [p.points() for p in out], stats

    def test_the_osm_line_on_top_of_an_official_one_goes_away(self):
        osm = _piece([_east(0), _east(4)])
        official = _piece([_east(0, LAT + 0.0002), _east(4, LAT + 0.0002)], source="RIO", highway="")  # ~22 m ao lado
        got, stats = self._cut([osm], [official])
        self.assertEqual(got, [])
        self.assertEqual(stats["dropped"], 1)

    def test_a_far_or_cross_street_stays(self):
        official = _piece([_east(0), _east(4)], source="RIO", highway="")
        parallel = _piece([_east(0, LAT + 0.0008), _east(4, LAT + 0.0008)])               # ~89 m
        cross = _piece([(LAT - 0.002, LNG + 0.002), (LAT + 0.002, LNG + 0.002)])           # perpendicular
        got, _ = self._cut([parallel, cross], [official])
        self.assertEqual(len(got), 2)

    def test_only_the_covered_stretch_is_cut_out(self):
        osm = _piece([_east(0), _east(10)])                                                 # ~1 km
        official = _piece([_east(0), _east(4)], source="RIO", highway="")                  # cobre o começo
        got, stats = self._cut([osm], [official])
        self.assertEqual(len(got), 1)
        self.assertGreater(got[0][0][1], LNG + 0.004)                                        # começa depois do oficial
        self.assertLess(got[0][0][1], LNG + 0.0052)
        self.assertEqual(got[0][-1], _east(10))
        self.assertEqual(stats["cut"], 1)
        self.assertLess(stats["km_after"], stats["km_before"])

    def test_a_leftover_shorter_than_the_minimum_is_dropped(self):
        osm = _piece([_east(0), _east(1)])                                                  # ~100 m
        official = _piece([_east(0), _east(0.8)], source="RIO", highway="")                # sobram ~20 m
        got, _ = self._cut([osm], [official])
        self.assertEqual(got, [])

    def test_a_directional_official_covers_the_oneway_of_the_same_sense_only(self):
        official = _piece([_east(0, LAT + 0.0001), _east(4, LAT + 0.0001)], source="ANTT", highway="",
                          directional=True)                                                  # oeste -> leste
        same = _piece([_east(0), _east(4)], oneway=True)
        opposite = _piece([_east(4), _east(0)], oneway=True)
        got, _ = self._cut([same, opposite], [official])
        self.assertEqual(got, [[_east(4), _east(0)]])

    def test_a_two_way_osm_line_needs_official_lines_of_both_senses(self):
        east = _piece([_east(0, LAT + 0.0001), _east(4, LAT + 0.0001)], source="ANTT", highway="", directional=True)
        west = _piece([_east(4, LAT - 0.0001), _east(0, LAT - 0.0001)], source="ANTT", highway="", directional=True)
        osm = _piece([_east(0), _east(4)])
        self.assertEqual(len(self._cut([osm], [east])[0]), 1)                               # só um sentido: fica
        self.assertEqual(self._cut([osm], [east, west])[0], [])                             # os dois: sai

    def test_an_official_line_without_direction_covers_any_sense(self):
        official = _piece([_east(0), _east(4)], source="CET-SP", highway="")
        oneway = _piece([_east(4, LAT + 0.0001), _east(0, LAT + 0.0001)], oneway=True)
        self.assertEqual(self._cut([oneway], [official])[0], [])

    def test_no_official_line_changes_nothing(self):
        osm = _piece([_east(0), _east(4)])
        out, stats = ll.cut([osm], [])
        self.assertEqual((out, stats), ([osm], {}))

    def test_the_cut_piece_keeps_the_attributes(self):
        osm = _piece([_east(0), _east(10)], kmh=70, highway="secondary")
        official = _piece([_east(0), _east(4)], source="RIO", highway="")
        out, _ = ll.cut([osm], [official])
        self.assertEqual(out[0].key, osm.key)


class Geometry(unittest.TestCase):
    def test_wkt_has_lng_then_lat_with_five_places_and_the_row_format(self):
        line = LimitLine(((-16.0, -49.0), (-16.00123, -48.99877)), 60, "OSM", False, None, None, "primary", True)
        self.assertEqual(line.row(), ["60", "OSM", "0", "", "", "primary", "1",
                                      "LINESTRING(-49.00000 -16.00000, -48.99877 -16.00123)"])
        est = LimitLine(((-16.0, -49.0), (-16.001, -49.001)), 40, "OSM:class", True, 40, 90, "tertiary", False)
        self.assertEqual(est.row()[:7], ["40", "OSM:class", "1", "40", "90", "tertiary", "0"])
        official = LimitLine(((-16.0, -49.0), (-16.001, -49.001)), 50, "RIO")
        self.assertEqual((official.row()[5], official.row()[6]), ("", ""))                  # fonte sem classe nem mão
        self.assertEqual(LimitLine.HEADER, ("limit_kmh", "source", "estimated", "limit_low_kmh", "direction_deg",
                                            "highway", "oneway", "wkt"))

    def test_encode_drops_repeated_vertices_and_keeps_five_places(self):
        xy = ll.encode([(-16.0, -49.0), (-16.000001, -49.000001), (-16.0001, -49.0)])
        self.assertEqual(ll.decode(xy), [(-16.0, -49.0), (-16.0001, -49.0)])
        self.assertIsInstance(xy, array)

    def test_mean_bearing_is_weighted_by_length(self):
        xy = ll.encode([(LAT, LNG), (LAT, LNG + 0.003), (LAT + 0.001, LNG + 0.003)])        # 333 m a leste, 111 m a norte
        b = ll.mean_bearing(xy)
        assert b is not None
        self.assertTrue(60 < b < 80, b)

    def test_simplifying_keeps_the_ends_and_the_curve_beyond_the_tolerance(self):
        pts = [(LAT, LNG), (LAT + 0.00001, LNG + 0.001), (LAT, LNG + 0.002), (LAT + 0.001, LNG + 0.003)]
        got = ll.simplified(pts, 3.0)
        self.assertEqual((got[0], got[-1]), (pts[0], pts[-1]))
        self.assertNotIn(pts[1], got)                       # 1 m fora da reta: sai
        self.assertIn(pts[2], got)                          # a curva de 111 m fica


class OfficialSources(unittest.TestCase):
    def test_rio_segments_become_lines_with_the_prefecture_as_source(self):
        from datakit.sources import rio
        got = rio.segment_lines([[[-43.2, -22.9], [-43.19, -22.9]]], 40)
        (line,) = ll.to_lines(got)
        self.assertEqual((line.limit_kmh, line.source, line.estimated, line.highway, line.oneway),
                         (40, "RIO", False, "", None))
        self.assertEqual(line.points, ((-22.9, -43.2), (-22.9, -43.19)))

    def test_cet_features_become_lines_only_for_the_two_classes(self):
        from datakit.sources import cet_sp
        feats = [{"properties": {"dc_tipo_classificacao_viaria": "VTR"},
                  "geometry": {"type": "LineString", "coordinates": [[-46.6, -23.5], [-46.59, -23.5]]}},
                 {"properties": {"dc_tipo_classificacao_viaria": "Arterial"},
                  "geometry": {"type": "MultiLineString", "coordinates": [[[-46.6, -23.6], [-46.59, -23.6]],
                                                                         [[-46.6, -23.7], [-46.59, -23.7]]]}},
                 {"properties": {"dc_tipo_classificacao_viaria": "Local"},
                  "geometry": {"type": "LineString", "coordinates": [[-46.6, -23.8], [-46.59, -23.8]]}}]
        got = ll.to_lines(cet_sp.features_to_lines(feats))
        self.assertEqual(sorted((x.limit_kmh, x.source) for x in got), [(50, "CET-SP"), (50, "CET-SP"), (70, "CET-SP")])

    def test_rio_segments_that_meet_with_the_same_limit_are_joined(self):
        from datakit.sources import rio
        a = rio.segment_lines([[[-43.2, -22.9], [-43.19, -22.9]]], 40)
        b = rio.segment_lines([[[-43.19, -22.9], [-43.18, -22.9]]], 40)
        c = rio.segment_lines([[[-43.18, -22.9], [-43.17, -22.9]]], 60)
        self.assertEqual(sorted(len(p.points()) for p in ll.join(a + b + c)), [2, 3])

    def test_antt_signs_become_lines_per_direction_in_the_traffic_direction(self):
        from datakit.common.lrs import MeasuredLine, SnvRoutes
        from datakit.sources import antt_placas
        from datakit.sources.antt_placas import Sign
        line = MeasuredLine([(-16.10, -49.0), (-16.05, -49.0), (-16.00, -49.0)], [0.0, 5.56, 11.12])   # sul -> norte
        snv = SnvRoutes({(60, "GO"): [line]})
        signs = [Sign(60, "GO", True, -16.095, -49.0, 80), Sign(60, "GO", False, -16.005, -49.0, 60)]
        got = ll.to_lines(antt_placas.lines_from_signs(signs, snv))
        up = [x for x in got if x.direction_deg is not None and x.limit_kmh == 80]
        down = [x for x in got if x.limit_kmh == 60]
        self.assertTrue(up and down)
        self.assertTrue(all(x.source == "ANTT" and not x.estimated and x.direction_deg is not None for x in got))
        self.assertTrue(all(x.points[0][0] < x.points[-1][0] for x in up))                  # crescente: do sul para o norte
        self.assertTrue(all(x.points[0][0] > x.points[-1][0] for x in down))                # decrescente: do norte para o sul
        self.assertEqual({x.direction_deg for x in up}, {0})
        self.assertEqual({x.direction_deg for x in down}, {180})

    def test_antt_same_limit_in_both_senses_is_one_line_without_direction(self):
        from datakit.common.lrs import MeasuredLine, SnvRoutes
        from datakit.sources import antt_placas
        from datakit.sources.antt_placas import Sign
        line = MeasuredLine([(-16.10, -49.0), (-16.00, -49.0)], [0.0, 11.12])
        snv = SnvRoutes({(60, "GO"): [line]})
        signs = [Sign(60, "GO", True, -16.095, -49.0, 80), Sign(60, "GO", False, -16.005, -49.0, 80)]
        got = ll.to_lines(antt_placas.lines_from_signs(signs, snv))
        both = [x for x in got if x.direction_deg is None]
        self.assertTrue(both)
        self.assertTrue(all(x.limit_kmh == 80 for x in both))


class StoredCopy(unittest.TestCase):
    def test_pieces_survive_the_source_cache_pickle(self):
        """A cópia guardada de uma fonte (datakit/source_cache.py) é um pickle: Piece, array e Key têm de voltar iguais."""
        from datakit import source_cache
        pieces = [_piece([_east(0), _east(3)], source="RIO", highway=""),
                  _piece([_east(3), _east(0)], kmh=50, directional=True, start=7, end=8)]
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "rio.pickle")
            source_cache._write(path, pieces)
            got, _when = source_cache._read(path)    # type: ignore[misc]
        self.assertEqual([(p.start, p.end, p.key, list(p.xy)) for p in got],
                         [(p.start, p.end, p.key, list(p.xy)) for p in pieces])
        self.assertFalse(source_cache._empty(got))

    def test_rio_and_cet_read_their_service_once_for_points_and_lines(self):
        from unittest import mock
        from datakit.sources import cet_sp, rio
        feats = [{"attributes": {"velocidade_regulamentada": 40},
                  "geometry": {"paths": [[[-43.2, -22.9], [-43.19, -22.9]]]}}]
        rio._segments.cache_clear()
        with mock.patch("datakit.sources._arcgis.query_all", return_value=feats) as q:
            points, lines = rio.load_limits(), rio.load_limit_lines()
        self.assertEqual(q.call_count, 1)
        self.assertTrue(points and len(lines) == 1)
        rio._segments.cache_clear()

        page = {"features": [{"properties": {"dc_tipo_classificacao_viaria": "VTR"},
                              "geometry": {"type": "LineString", "coordinates": [[-46.6, -23.5], [-46.59, -23.5]]}}]}
        cet_sp._classified_features.cache_clear()
        with mock.patch.object(cet_sp, "get_json", return_value=page) as g:
            points, lines = cet_sp.load_limits(), cet_sp.load_limit_lines()
        self.assertEqual(g.call_count, 1)
        self.assertTrue(points and len(lines) == 1)
        cet_sp._classified_features.cache_clear()


class OfficialLinesInTheContext(unittest.TestCase):
    def test_lines_that_cannot_be_read_without_a_copy_only_warn(self):
        """Os trechos oficiais são complemento dos pontos: sem cópia guardada e sem edição, a falha vira aviso e não barra
        o publish.py."""
        from unittest import mock
        from datakit import failures
        from datakit.context import BuildContext
        from datakit.sources import cet_sp, inmetro, rio, snv

        def down():
            raise TimeoutError("fora do ar")
        before_f, before_w = list(failures._FAILURES), list(failures._WARNINGS)
        try:
            with tempfile.TemporaryDirectory() as raw, \
                    mock.patch.object(rio, "load_limits", lambda: []), mock.patch.object(cet_sp, "load_limits", lambda: []), \
                    mock.patch.object(rio, "load_limit_lines", down), mock.patch.object(cet_sp, "load_limit_lines", down), \
                    mock.patch.object(snv, "ensure", lambda raw_dir: None), \
                    mock.patch.object(BuildContext, "snv_routes", lambda self: None), \
                    mock.patch.object(inmetro, "load", lambda raw_dir: []):
                nat = BuildContext(raw).national()
            new_failures = failures.recorded()[len(before_f):]
            new_warnings = failures.warnings()[len(before_w):]
        finally:
            failures._FAILURES[:] = before_f
            failures._WARNINGS[:] = before_w
        self.assertEqual(nat["official_lines"], {"ANTT": [], "RIO": [], "CET-SP": []})
        self.assertEqual([f for f in new_failures if "linhas" in f or "trechos" in f], [])
        self.assertEqual(sorted(w.split(":")[0] for w in new_warnings if "não há cópia guardada da leitura anterior" in w),
                         ["CET-SP limites (linhas)", "Rio trechos (linhas)"])


class SplitByState(unittest.TestCase):
    def test_a_line_crossing_the_border_belongs_to_both_states(self):
        from shapely.geometry import box
        from datakit.build import _Split
        from datakit.common.ufassign import UfAssigner
        west = box(-50.0, -17.0, -49.0, -15.0)
        east = box(-49.0, -17.0, -48.0, -15.0)
        split = _Split(UfAssigner({"GO": west, "DF": east}))
        a = _piece([(LAT, -49.002), (LAT, -49.001)])                                          # só em GO
        b = _piece([(LAT, -49.001), (LAT, -48.999)])                                          # cruza a divisa
        c = _piece([(LAT, -48.9), (LAT, -48.8)])                                              # só em DF
        items = [a, b, c]
        self.assertEqual(split.lines("GO", "k", items), [a, b])
        self.assertEqual(split.lines("DF", "k", items), [b, c])

    def test_without_polygons_the_bbox_decides(self):
        from datakit.build import _Split
        a = _piece([(-16.0, -49.0), (-16.0, -48.99)])
        far = _piece([(10.0, 10.0), (10.0, 10.1)])
        self.assertEqual(_Split().lines("GO", "k", [a, far]), [a])


class PackAndCatalog(unittest.TestCase):
    LINES = [LimitLine(((-16.0, -49.0), (-16.0, -48.999)), 60, "OSM", False, None, None, "primary", False),
             LimitLine(((-16.0, -49.0), (-16.0, -48.999)), 60, "OSM", False, None, None, "primary", False),   # repetida
             LimitLine(((-16.1, -49.0), (-16.1, -48.999)), 40, "OSM:class", True, 40, 90, "tertiary", False)]

    def test_the_pack_writes_each_line_once_sorted_and_counts_them(self):
        from datakit.build_pack import build as build_pack
        with tempfile.TemporaryDirectory() as d:
            m = build_pack("GO", d, [], [], [], sources=[], limit_lines=self.LINES)
            with open(os.path.join(d, "GO", "limites_trechos.csv"), encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
        self.assertEqual([r["limit_kmh"] for r in rows], ["40", "60"])                      # pelo primeiro vértice
        self.assertEqual(rows[1]["wkt"], "LINESTRING(-49.00000 -16.00000, -48.99900 -16.00000)")
        self.assertEqual(list(rows[0]), list(LimitLine.HEADER))
        self.assertEqual(m["counts"]["limit_lines"], 2)
        self.assertIn("limites_trechos.csv", m["files"])
        self.assertGreaterEqual(m["schema"], 10)

    def test_the_catalog_lists_them_only_for_a_state_that_has_them(self):
        from datakit import build_catalog
        from datakit.build_pack import build as build_pack
        with tempfile.TemporaryDirectory() as tmp:
            packs, dist = os.path.join(tmp, "p"), os.path.join(tmp, "d")
            build_pack("GO", packs, [], [], [], sources=[], limit_lines=self.LINES)
            build_pack("AC", packs, [], [], [], sources=[])
            cat = build_catalog.build(packs, dist)
            published = os.path.exists(os.path.join(dist, "estados", "GO", "limites_trechos.csv"))
        self.assertEqual((cat["ufs"]["GO"]["limit_lines"]["file"], cat["ufs"]["GO"]["limit_lines"]["count"]),
                         ("estados/GO/limites_trechos.csv", 2))
        self.assertTrue(published)
        self.assertNotIn("limit_lines", cat["ufs"]["AC"])
        self.assertEqual(json.loads(json.dumps(cat))["schema"], 2, "o catálogo só ganha uma chave")

    def test_the_file_goes_only_to_the_release_and_counts_have_no_drop_guard_yet(self):
        import importlib.util
        from datakit import build_brazil
        path = os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "publish.py")
        spec = importlib.util.spec_from_file_location("publicar_trechos", path)
        assert spec is not None and spec.loader is not None
        publish = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(publish)
        # decisão de 2026-11-08: os trechos vão só no zip do estado na release, não no commit
        self.assertIsNone(build_brazil.PUBLISHED_NAME.match("limites_trechos.csv"))
        self.assertIsNone(publish._PUBLISHED_NAME.match("limites_trechos.csv"))
        self.assertTrue(publish._RELEASE_ONLY_NAME.match("limites_trechos.csv"))
        self.assertNotIn("limit_lines", [k for k, _ in publish._COUNT_FIELDS])


if __name__ == "__main__":
    unittest.main()
