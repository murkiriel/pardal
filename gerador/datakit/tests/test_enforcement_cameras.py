"""Câmeras de fiscalização que não medem velocidade: cameras_fiscalizacao.csv, schema 11 do pacote.

CET de São Paulo (códigos de ENQUADRAMENTO), BHTrans (tipo do controlador) e Setran de Curitiba (títulos dos ícones).
Velocidade e avanço de sinal continuam no radares.csv; aqui entra o resto, uma linha por infração. Os locais ficam FORA do
SourceData.cameras (viram radar na mescla) e usam código próprio na coluna `source` (a reserva pela edição publicada
procura radares pelo código da fonte).
"""
import csv
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from datakit import failures, source_cache
from datakit.common import EnforcementCamera
from datakit.context import BuildContext
from datakit.sources import bh, cet_sp, municipal


def _row(codes, lat="-23.55", lng="-46.63", off="", extra=None):
    return {"LATITUDE": lat, "LONGITUDE": lng, "ENQUADRAMENTOS": codes, "DESATIVAÇÃO": off, **(extra or {})}


def _tuples(cams):
    return sorted((c.kind, c.source, c.active) for c in cams)


class CetCodes(unittest.TestCase):
    def test_each_code_maps_to_the_infraction_the_cet_legend_names(self):
        """Legenda da tabela "Enquadramentos" do relatório da CET (lida em 2026-11-08)."""
        expected = {"EXD": "BUS_LANE", "EXE": "BUS_LANE", "CPD": "NO_TURN", "CPE": "NO_TURN",
                    "P": "STOP_ON_CROSSWALK", "R": "ROAD_ROTATION", "Z": "TRUCK_RESTRICTION",
                    "VR": "TRUCK_RESTRICTION", "PR": "TRUCK_RESTRICTION", "F": "CHARTER_RESTRICTION",
                    "MT": "MOTORCYCLE_RESTRICTION", "S": "OTHER"}
        self.assertEqual(cet_sp.ENFORCEMENT_KINDS, expected)
        for code, kind in expected.items():
            got = cet_sp.rows_to_enforcement_cameras([_row(code)])
            self.assertEqual([(c.kind, c.source) for c in got], [(kind, "CET-SP:CAM")], code)

    def test_speed_and_red_light_stay_out_and_so_do_places_with_only_those(self):
        self.assertEqual(cet_sp.rows_to_enforcement_cameras([_row("V"), _row("A,V"), _row("A")]), [])

    def test_one_line_per_infraction_and_the_speed_code_is_ignored_next_to_them(self):
        got = cet_sp.rows_to_enforcement_cameras([_row("A,P,R,V,VR")])
        self.assertEqual(sorted(c.kind for c in got), ["ROAD_ROTATION", "STOP_ON_CROSSWALK", "TRUCK_RESTRICTION"])

    def test_left_and_right_variants_are_a_single_line(self):
        got = cet_sp.rows_to_enforcement_cameras([_row("CPD,CPE,EXD,EXE,Z,VR")])
        self.assertEqual(sorted(c.kind for c in got), ["BUS_LANE", "NO_TURN", "TRUCK_RESTRICTION"])

    def test_an_unknown_code_is_other_and_a_deactivated_place_is_left_out(self):
        got = cet_sp.rows_to_enforcement_cameras([_row("QQ"), _row("R", off="2024-01-01"), _row("R", lat="", lng="")])
        self.assertEqual([c.kind for c in got], ["OTHER"])

    def test_the_source_code_is_not_a_radar_code(self):
        """A edição publicada busca radares pelas partes de `source`: "CET-SP:CAM" nunca é "CET-SP"."""
        from datakit.common.model import source_parts
        self.assertNotIn("CET-SP", source_parts(cet_sp.SOURCE_CAMERAS))
        self.assertNotIn(cet_sp.SOURCE_CAMERAS, getattr(cet_sp, "SOURCE_CODES", ()))

    def test_the_radar_reading_is_unchanged(self):
        rows = [_row("R,V", extra={"VELOCIDADE": "50 km/h"}), _row("R")]
        cams = cet_sp.rows_to_cameras(rows)
        self.assertEqual([(c.kind.value, c.limit_kmh, c.source) for c in cams], [("FIXED", 50, "CET-SP")])


class BhTypes(unittest.TestCase):
    CSV = (
        "ID_FISCALIZACAO_ELETRONICA;DESC_TIPO_CONTROLADOR_TRANSITO;VELOCIDADE_REGULAMENTAR;GEOMETRIA\n"
        "1;Controlador Eletrônico de Velocidade;60;POINT (610000.00 7797000.00)\n"
        "2;Detector de Avanço de Semáforo;;POINT (610100.00 7797000.00)\n"
        "3;Detector de Conversão-Retorno em local Proibido;;POINT (610200.00 7797000.00)\n"
        "4;Detector de Invasão de Faixa de Exclusiva - MOVE;;POINT (610300.00 7797000.00)\n"
        "5;Detector de Coisa Nova;;POINT (610400.00 7797000.00)\n"
        "6;Detector de Conversão-Retorno em local Proibido;;sem ponto\n")

    def test_turn_and_bus_lane_detectors_are_enforcement_cameras(self):
        got = bh.other_cameras(self.CSV)
        self.assertEqual([(c.kind, c.source) for c in got],
                         [("NO_TURN", "BHTRANS:CAM"), ("BUS_LANE", "BHTRANS:CAM"), ("OTHER", "BHTRANS:CAM")])
        self.assertTrue(all(-20.1 < c.lat < -19.7 and -44.2 < c.lng < -43.8 for c in got))

    def test_the_radar_reading_keeps_only_speed_and_red_light(self):
        self.assertEqual([c.kind.value for c in bh.parse(self.CSV)], ["FIXED", "RED_LIGHT"])


class CuritibaIcons(unittest.TestCase):
    PAGE = """
    <div class="item-lista"> <span id="x_lblIdentificacao_0">RADAR AR-15</span>
      <span title='Velocidade controlada'></span><span title='Parada na faixa'></span><span title='Avanço de sinal'></span>
      <span class='icn-velocidade-50'></span>
      <a onclick="javascript:verNoMapa(&#39;-25.38096&#39;,&#39;-49.27183&#39;);">ver no mapa</a></div>
    <div class="item-lista"> <span id="x_lblIdentificacao_1">Radar MO-07A</span>
      <span title='Velocidade controlada'></span><span title='Faixa Exclusiva'></span>
      <a onclick="javascript:verNoMapa(&#39;-25.43010&#39;,&#39;-49.26560&#39;);">ver no mapa</a></div>
    <div class="item-lista"> <span id="x_lblIdentificacao_2">RADAR MO-91A</span>
      <span title='Conversão proibida'></span><span title='Retorno proibido'></span><span title='Conversão obrigatória'></span>
      <span title='Peso Bruto Total'></span><span title='Coisa nova'></span>
      <a onclick="javascript:verNoMapa(&#39;-25.45000&#39;,&#39;-49.29000&#39;);">ver no mapa</a></div>
    <div class="item-lista"> <span id="x_lblIdentificacao_3">So velocidade</span>
      <span title='Velocidade controlada'></span>
      <a onclick="javascript:verNoMapa(&#39;-25.46000&#39;,&#39;-49.30000&#39;);">ver no mapa</a></div>
    <div class="item-lista"> <span title='Faixa Exclusiva'></span>
      <a onclick="javascript:verNoMapa(&#39;0&#39;,&#39;0&#39;);">fora do Brasil</a></div>
    """

    def test_each_icon_other_than_speed_and_red_light_is_a_line(self):
        got = municipal.other_cameras(self.PAGE)
        self.assertEqual([(c.lat, c.lng, c.kind) for c in got], [
            (-25.38096, -49.27183, "STOP_ON_CROSSWALK"),
            (-25.4301, -49.2656, "BUS_LANE"),
            (-25.45, -49.29, "MANDATORY_TURN"),
            (-25.45, -49.29, "NO_TURN"),
            (-25.45, -49.29, "NO_U_TURN"),
            (-25.45, -49.29, "OTHER"),
            (-25.45, -49.29, "TRUCK_RESTRICTION"),
        ])
        self.assertTrue(all(c.source == "CURITIBA:CAM" and c.active for c in got))

    def test_the_radar_reading_is_unchanged(self):
        cams = municipal.parse_curitiba(self.PAGE)
        self.assertEqual([(c.source, c.kind.value) for c in cams], [("CURITIBA", "FIXED"), ("CURITIBA", "FIXED"),
                                                                     ("CURITIBA", "FIXED")])
        self.assertNotIn("CURITIBA:CAM", municipal.SOURCE_CODES)


class _Env(unittest.TestCase):
    def setUp(self):
        self.raw = tempfile.mkdtemp()
        self._failures, self._warnings = list(failures._FAILURES), list(failures._WARNINGS)
        self._dates = dict(source_cache._DATES)

    def tearDown(self):
        shutil.rmtree(self.raw, ignore_errors=True)
        failures._FAILURES[:] = self._failures
        failures._WARNINGS[:] = self._warnings
        source_cache._DATES.clear()
        source_cache._DATES.update(self._dates)

    def new_failures(self):
        return failures.recorded()[len(self._failures):]

    def new_warnings(self):
        return failures.warnings()[len(self._warnings):]


class Context(_Env):
    SOURCES = {"CET-SP": cet_sp, "BHTRANS": bh, "capitais": municipal}

    def _patched(self, **kw):
        cams = [EnforcementCamera(-23.55, -46.63, "ROAD_ROTATION", "CET-SP:CAM")]
        return (
            mock.patch.object(cet_sp, "load_other_cameras", kw.get("cet", lambda raw: cams)),
            mock.patch.object(bh, "load_other_cameras",
                              kw.get("bh", lambda: [EnforcementCamera(-19.9, -43.9, "NO_TURN", "BHTRANS:CAM")])),
            mock.patch.object(municipal, "load_other_cameras",
                              kw.get("cwb", lambda: [EnforcementCamera(-25.4, -49.2, "BUS_LANE", "CURITIBA:CAM")])),
            mock.patch.object(BuildContext, "official", lambda self: {}))

    def test_the_three_sources_are_read_once_and_kept_out_of_the_radars(self):
        calls = []
        p = self._patched(bh=lambda: calls.append(1) or [])
        with p[0], p[1], p[2], p[3]:
            ctx = BuildContext(self.raw, sources=self.SOURCES)
            first = ctx.enforcement_cameras()
            self.assertIs(ctx.enforcement_cameras(), first)
        self.assertEqual(sorted(c.source for c in first), ["CET-SP:CAM", "CURITIBA:CAM"])
        self.assertEqual(calls, [1])

    def test_only_the_sources_turned_on_in_the_build_are_read(self):
        p = self._patched()
        with p[0], p[1], p[2], p[3]:
            got = BuildContext(self.raw, sources={"BHTRANS": bh}).enforcement_cameras()
        self.assertEqual([c.source for c in got], ["BHTRANS:CAM"])

    def test_each_source_has_its_own_stored_copy_and_a_failure_uses_it(self):
        ok = self._patched()
        with ok[0], ok[1], ok[2], ok[3]:
            BuildContext(self.raw, sources=self.SOURCES).enforcement_cameras()   # grava as três cópias
        for slug in ("cet_sp_outras_cameras", "bhtrans_outras_cameras", "curitiba_outras_cameras"):
            self.assertTrue(os.path.exists(os.path.join(self.raw, "fontes", slug + ".pickle")), slug)

        def down(*a):
            raise TimeoutError("fora do ar")
        bad = self._patched(bh=down)
        with bad[0], bad[1], bad[2], bad[3]:
            got = BuildContext(self.raw, sources=self.SOURCES).enforcement_cameras()
        self.assertEqual(len(got), 3)                                   # a BH veio da cópia
        self.assertEqual(self.new_failures(), [])
        self.assertTrue(any(w.startswith("BHTRANS (outras câmeras)") and "usada a cópia" in w
                            for w in self.new_warnings()))

    def test_without_a_copy_the_failure_is_only_a_warning_and_the_others_still_come(self):
        def down(*a):
            raise TimeoutError("fora do ar")
        bad = self._patched(bh=down)
        with bad[0], bad[1], bad[2], bad[3]:
            got = BuildContext(self.raw, sources=self.SOURCES).enforcement_cameras()
        self.assertEqual(sorted(c.source for c in got), ["CET-SP:CAM", "CURITIBA:CAM"])
        self.assertEqual(self.new_failures(), [])                       # não barra o publish.py
        self.assertTrue(any(w.startswith("BHTRANS (outras câmeras)") for w in self.new_warnings()))

    def test_the_cet_cameras_are_read_from_the_table_the_radar_reading_stored(self):
        rows = [_row("R"), _row("V")]
        with open(os.path.join(self.raw, cet_sp.CACHE_FILE), "w", encoding="utf-8") as f:
            json.dump(rows, f)
        self.assertEqual([c.kind for c in cet_sp.load_other_cameras(self.raw)], ["ROAD_ROTATION"])

    def test_fetch_of_the_sources_does_not_carry_them(self):
        from datakit.context import SourceData
        rows = [_row("R", extra={"VELOCIDADE": ""}), _row("V", extra={"VELOCIDADE": "50 km/h"})]
        with mock.patch.object(cet_sp, "_rows_with_fallback", lambda raw_dir: rows):
            loaded = cet_sp.fetch(BuildContext(self.raw))
        self.assertIsInstance(loaded, SourceData)
        self.assertEqual([c.source for c in loaded.cameras], ["CET-SP"])


class EditionDoesNotReturnThem(_Env):
    def test_a_radar_reserve_never_brings_back_an_enforcement_camera(self):
        from datakit.edition import Edition
        root = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(root, "brasil"))
            with open(os.path.join(root, "catalogo.json"), "w", encoding="utf-8") as f:
                json.dump({"schema": 2, "built_at": "2026-11-08T00:00:00Z", "ufs": {}}, f)
            with open(os.path.join(root, "brasil", "radares.csv"), "w", encoding="utf-8") as f:
                f.write("lat,lng,kind,limit_kmh,source,active,end_lat,end_lng,direction_deg\n"
                        "-23.55,-46.63,FIXED,50,CET-SP,1,,,\n")
            ed = Edition.open(root)
            assert ed is not None
            self.assertEqual(len(ed.cameras(("CET-SP",))), 1)
            self.assertEqual(ed.cameras(("CET-SP:CAM", "BHTRANS:CAM", "CURITIBA:CAM")), [])
        finally:
            shutil.rmtree(root, ignore_errors=True)


class PackAndCatalog(unittest.TestCase):
    CAMS = [EnforcementCamera(-23.55, -46.63, "ROAD_ROTATION", "CET-SP:CAM"),
            EnforcementCamera(-23.55, -46.63, "ROAD_ROTATION", "CET-SP:CAM"),      # repetida
            EnforcementCamera(-23.55, -46.63, "BUS_LANE", "CET-SP:CAM"),
            EnforcementCamera(-23.56, -46.64, "NO_TURN", "CET-SP:CAM")]

    def test_the_pack_writes_one_line_per_place_and_kind_and_counts_them(self):
        from datakit.build_pack import build as build_pack
        with tempfile.TemporaryDirectory() as d:
            m = build_pack("SP", d, [], [], [], sources=[], enforcement_cameras=self.CAMS)
            with open(os.path.join(d, "SP", "cameras_fiscalizacao.csv"), encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
        self.assertEqual([(r["lat"], r["kind"], r["source"], r["active"]) for r in rows], [
            ("-23.560000", "NO_TURN", "CET-SP:CAM", "1"),
            ("-23.550000", "BUS_LANE", "CET-SP:CAM", "1"),
            ("-23.550000", "ROAD_ROTATION", "CET-SP:CAM", "1")])
        self.assertEqual(sorted(r["kind"] for r in rows), ["BUS_LANE", "NO_TURN", "ROAD_ROTATION"])
        self.assertEqual(list(rows[0]), list(EnforcementCamera.HEADER))
        self.assertEqual(m["counts"]["enforcement_cameras"], 3)
        self.assertIn("cameras_fiscalizacao.csv", m["files"])
        self.assertEqual(m["schema"], 11)

    def test_the_catalog_lists_them_only_for_a_state_that_has_them(self):
        from datakit import build_catalog
        from datakit.build_pack import build as build_pack
        with tempfile.TemporaryDirectory() as tmp:
            packs, dist = os.path.join(tmp, "p"), os.path.join(tmp, "d")
            build_pack("SP", packs, [], [], [], sources=[], enforcement_cameras=self.CAMS)
            build_pack("AC", packs, [], [], [], sources=[])
            cat = build_catalog.build(packs, dist)
            published = os.path.exists(os.path.join(dist, "estados", "SP", "cameras_fiscalizacao.csv"))
        self.assertEqual((cat["ufs"]["SP"]["enforcement_cameras"]["file"], cat["ufs"]["SP"]["enforcement_cameras"]["count"]),
                         ("estados/SP/cameras_fiscalizacao.csv", 3))
        self.assertTrue(published)
        self.assertNotIn("enforcement_cameras", cat["ufs"]["AC"])
        self.assertEqual(cat["schema"], 2)


if __name__ == "__main__":
    unittest.main()
