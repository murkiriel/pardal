"""Cópia da última leitura boa de cada fonte (datakit/source_cache.py) e a reserva do SNV."""
import os
import shutil
import tempfile
import unittest
from unittest import mock

from datakit import failures, source_cache
from datakit.common.model import Camera, CameraKind
from datakit.context import BuildContext, SourceData


def _cam(lat=-15.8, lng=-47.9):
    return Camera(lat, lng, CameraKind.FIXED, 60, "TESTE", True)


class _Isolated(unittest.TestCase):
    def setUp(self):
        self.raw = tempfile.mkdtemp()
        self._f, self._w = list(failures._FAILURES), list(failures._WARNINGS)
        self._d = dict(source_cache._DATES)

    def tearDown(self):
        failures._FAILURES[:], failures._WARNINGS[:] = self._f, self._w
        source_cache._DATES.clear()
        source_cache._DATES.update(self._d)
        shutil.rmtree(self.raw, ignore_errors=True)

    def new_failures(self):
        return failures._FAILURES[len(self._f):]

    def new_warnings(self):
        return failures._WARNINGS[len(self._w):]


class SourceCacheTest(_Isolated):
    def test_good_read_is_saved_and_returned(self):
        data = SourceData(cameras=[_cam()])
        self.assertIs(source_cache.load("FONTE", self.raw, lambda: data, SourceData()), data)
        self.assertTrue(os.path.exists(source_cache.path_for(self.raw, "FONTE")))
        self.assertEqual((self.new_failures(), self.new_warnings()), ([], []))

    def test_failure_without_copy_is_recorded_and_returns_default(self):
        def down():
            raise ConnectionError("fora do ar")
        default = SourceData()
        self.assertIs(source_cache.load("FONTE", self.raw, down, default), default)
        self.assertEqual(len(self.new_failures()), 1)
        self.assertTrue(self.new_failures()[0].startswith("FONTE: ConnectionError"))
        self.assertEqual(self.new_warnings(), [])

    def test_failure_with_copy_uses_it_and_only_warns(self):
        source_cache.load("FONTE", self.raw, lambda: SourceData(cameras=[_cam()]), SourceData())

        def down():
            raise TimeoutError("lento")
        got = source_cache.load("FONTE", self.raw, down, SourceData())
        self.assertEqual(len(got.cameras), 1)
        self.assertEqual(self.new_failures(), [])
        self.assertEqual(len(self.new_warnings()), 1)
        self.assertIn("usada a cópia de", self.new_warnings()[0])

    def test_inner_base_failure_with_copy_uses_the_whole_copy(self):
        source_cache.load("capitais", self.raw, lambda: SourceData(cameras=[_cam(), _cam(-8.0, -34.9)]),
                          SourceData())

        def partial():
            failures.record("municipal (Recife)", ConnectionError("dns"))
            return SourceData(cameras=[_cam()])
        got = source_cache.load("capitais", self.raw, partial, SourceData(), owns=("municipal",))
        self.assertEqual(len(got.cameras), 2)
        self.assertEqual(self.new_failures(), [])
        self.assertIn("municipal (Recife)", self.new_warnings()[0])

    def test_inner_base_failure_without_copy_keeps_the_partial_read_and_the_failure(self):
        def partial():
            failures.record("DER-SP (_artesp)", ConnectionError("timeout"))
            return SourceData(cameras=[_cam()])
        got = source_cache.load("DER-SP", self.raw, partial, SourceData())
        self.assertEqual(len(got.cameras), 1)
        self.assertEqual(len(self.new_failures()), 1)
        # leitura parcial não vira cópia: a próxima falha não deve cair nela como se fosse completa
        self.assertFalse(os.path.exists(source_cache.path_for(self.raw, "DER-SP")))

    def test_failure_of_another_base_called_inside_is_not_hidden(self):
        source_cache.load("DER-MG", self.raw, lambda: SourceData(cameras=[_cam()]), SourceData())

        def with_snv_down():
            failures.record("SNV (rotas)", ConnectionError("fora"))
            return SourceData(cameras=[_cam(), _cam(-19.9, -43.9)])
        got = source_cache.load("DER-MG", self.raw, with_snv_down, SourceData(), owns=("der_mg",))
        self.assertEqual(len(got.cameras), 2)   # leitura nova vale: a falha não é do DER-MG
        self.assertEqual(len(self.new_failures()), 1)
        self.assertTrue(self.new_failures()[0].startswith("SNV"))

    def test_empty_read_does_not_replace_a_copy_with_data(self):
        source_cache.load("FONTE", self.raw, lambda: [1, 2, 3], [])
        self.assertEqual(source_cache.load("FONTE", self.raw, lambda: [], []), [1, 2, 3])
        self.assertIn("veio vazia", self.new_warnings()[0])

    def test_empty_read_without_copy_is_accepted(self):
        self.assertEqual(source_cache.load("FONTE", self.raw, lambda: ("", []), ("", [])), ("", []))
        self.assertEqual((self.new_failures(), self.new_warnings()), ([], []))

    def test_tuple_with_data_is_not_empty(self):
        self.assertFalse(source_cache._empty(("2026-10", [1])))
        self.assertTrue(source_cache._empty(("2026-10", [])))
        self.assertTrue(source_cache._empty((("", ""), 0, [])))

    def test_unreadable_copy_counts_as_no_copy(self):
        path = source_cache.path_for(self.raw, "FONTE")
        os.makedirs(os.path.dirname(path))
        with open(path, "wb") as f:
            f.write(b"lixo")

        def down():
            raise ConnectionError("fora")
        self.assertEqual(source_cache.load("FONTE", self.raw, down, []), [])
        self.assertEqual(len(self.new_failures()), 1)

    def test_not_implemented_passes_through_untouched(self):
        def off():
            raise NotImplementedError("desligada")
        with self.assertRaises(NotImplementedError):
            source_cache.load("FONTE", self.raw, off, [])
        self.assertEqual(self.new_failures(), [])


class _Mod:
    """Fonte oficial de mentira: fetch(ctx) devolve ou falha conforme `down`."""
    __name__ = "datakit.sources.fake"

    def __init__(self):
        self.down = False

    def fetch(self, ctx):
        if self.down:
            raise ConnectionError("portal fora do ar")
        return SourceData(cameras=[_cam()])


class OfficialSourcesTest(_Isolated):
    def test_source_down_on_the_next_build_keeps_the_previous_read(self):
        mod, other = _Mod(), _Mod()
        BuildContext(self.raw, sources={"RIO": mod, "OUTRA": other}).official()
        mod.down = True
        got = BuildContext(self.raw, sources={"RIO": mod, "OUTRA": other}).official()
        self.assertEqual((len(got["RIO"].cameras), len(got["OUTRA"].cameras)), (1, 1))
        self.assertEqual(self.new_failures(), [])
        self.assertTrue(self.new_warnings()[0].startswith("RIO:"))


class SnvStoredVersionTest(_Isolated):
    def test_listing_down_uses_the_newest_stored_zips(self):
        from datakit.sources import snv
        for name in ("snv_rota_202607A.zip", "snv_rota_202610A.zip", "snv_base_202610A.zip"):
            open(os.path.join(self.raw, name), "wb").close()
        with mock.patch.object(snv, "_latest", side_effect=ConnectionError("webdav fora")):
            routes, base, version = snv.ensure(self.raw)
        self.assertEqual((os.path.basename(routes), os.path.basename(base), version),
                         ("snv_rota_202610A.zip", "snv_base_202610A.zip", "202610A"))
        self.assertEqual(len(self.new_warnings()), 1)

    def test_listing_down_without_stored_zips_raises(self):
        from datakit.sources import snv
        with mock.patch.object(snv, "_latest", side_effect=ConnectionError("webdav fora")):
            with self.assertRaises(ConnectionError):
                snv.ensure(self.raw)


class CnefeStoredListingTest(_Isolated):
    def test_listing_down_uses_the_stored_zips_of_that_uf(self):
        from datakit.sources import cnefe
        folder = os.path.join(self.raw, cnefe.FOLDER)
        os.makedirs(folder)
        for name in ("5208707_GOIÂNIA.zip", "5201108_ANÁPOLIS.zip", "5300108_BRASÍLIA.zip"):
            open(os.path.join(folder, name), "wb").close()
        with mock.patch.object(cnefe, "get_text", side_effect=ConnectionError("ftp fora")):
            files = cnefe.municipality_files("GO", self.raw)
        self.assertEqual(sorted(files), ["ANAPOLIS", "GOIANIA"])   # Brasília é de outra UF (53)
        # o caminho que ensure() monta a partir do href é o do arquivo guardado (sem baixar)
        self.assertTrue(os.path.exists(cnefe.ensure("GO", cnefe.file_for("Goiânia", files), self.raw)))
        self.assertEqual(len(self.new_warnings()), 1)

    def test_listing_down_without_stored_zips_raises(self):
        from datakit.sources import cnefe
        with mock.patch.object(cnefe, "get_text", side_effect=ConnectionError("ftp fora")):
            with self.assertRaises(ConnectionError):
                cnefe.municipality_files("GO", self.raw)


def _edition(root, built_at="2026-10-06T13:43:38Z", source_dates=None):
    """Uma edição publicada mínima em `root` (catálogo + brasil/radares.csv e limites.csv)."""
    import json
    os.makedirs(os.path.join(root, "brasil"))
    cat = {"built_at": built_at, "ufs": {}}
    if source_dates:
        cat["source_dates"] = source_dates
    with open(os.path.join(root, "catalogo.json"), "w", encoding="utf-8") as f:
        json.dump(cat, f)
    with open(os.path.join(root, "brasil", "radares.csv"), "w", encoding="utf-8") as f:
        f.write("lat,lng,kind,limit_kmh,source,active,end_lat,end_lng,direction_deg\n"
                "-22.900000,-43.200000,FIXED,60,RIO,1,,,90\n"
                "-22.910000,-43.210000,RED_LIGHT,,RIO+OSM,1,,,\n"
                "-22.920000,-43.220000,FIXED,50,RIO+INMETRO,0,,,\n"
                "-7.100000,-34.800000,FIXED,40,PMJP,1,,,\n"
                "-23.500000,-46.600000,FIXED,70,OSM,1,,,\n")
    with open(os.path.join(root, "brasil", "limites.csv"), "w", encoding="utf-8") as f:
        f.write("lat,lng,limit_kmh,source,estimated,limit_low_kmh,direction_deg\n"
                "-22.900000,-43.200000,60,RIO,0,,\n"
                "-22.901000,-43.201000,40,RIO,0,,\n"
                "-23.550000,-46.630000,50,CET-SP,0,,\n"
                "-23.351015,-44.724119,60,OSM:class,1,40,\n")


class EditionTest(_Isolated):
    def setUp(self):
        super().setUp()
        self.root = tempfile.mkdtemp()
        _edition(self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)
        super().tearDown()

    def test_cameras_by_any_part_of_the_source(self):
        from datakit.edition import Edition
        ed = Edition.open(self.root)
        cams = ed.cameras(("RIO",))
        self.assertEqual(len(cams), 3)   # RIO, RIO+OSM e RIO+INMETRO
        self.assertTrue(all(c.source == "RIO" for c in cams))
        self.assertEqual([(c.kind, c.limit_kmh, c.active, c.direction_deg) for c in cams],
                         [(CameraKind.FIXED, 60, True, 90), (CameraKind.RED_LIGHT, None, True, None),
                          (CameraKind.FIXED, 50, False, None)])
        self.assertEqual(len(ed.cameras(("PMJP", "PMF"))), 1)
        self.assertEqual(ed.cameras(("OSM",)), [])   # o OSM nunca vem da edição

    def test_limits_by_source_without_estimated(self):
        from datakit.edition import Edition
        ed = Edition.open(self.root)
        self.assertEqual([(lim.limit_kmh, lim.source) for lim in ed.limits(("RIO",))], [(60, "RIO"), (40, "RIO")])
        self.assertEqual(ed.limits(("OSM:class",)), [])

    def test_no_edition_without_catalog_or_brasil(self):
        from datakit.edition import Edition
        self.assertIsNone(Edition.open(None))
        self.assertIsNone(Edition.open(tempfile.mkdtemp()))

    def test_source_date_prefers_the_recorded_one(self):
        from datakit.edition import Edition
        other = tempfile.mkdtemp()
        _edition(other, source_dates={"Rio trechos": "2026-09-01"})
        ed = Edition.open(other)
        self.assertEqual((ed.source_date("Rio trechos"), ed.source_date("RIO")), ("2026-09-01", "2026-10-06"))
        shutil.rmtree(other, ignore_errors=True)

    def test_source_down_without_copy_uses_the_edition_and_only_warns(self):
        def down():
            raise TimeoutError("pgeo3 fora")
        ctx = BuildContext(self.raw, edition_dir=self.root)
        with mock.patch("datakit.sources.rio.load_limits", down), \
                mock.patch("datakit.sources.cet_sp.load_limits", lambda: [_lim()]), \
                mock.patch("datakit.sources.rio.load_limit_lines", lambda: []), \
                mock.patch("datakit.sources.cet_sp.load_limit_lines", lambda: []), \
                mock.patch("datakit.context.BuildContext.snv_routes", lambda self: None), \
                mock.patch("datakit.sources.snv.ensure", side_effect=ConnectionError("fora")), \
                mock.patch("datakit.sources.inmetro.load", lambda raw: []):
            limits = ctx.national()["official_limits"]
        self.assertEqual(len(limits["RIO"]), 2)
        self.assertEqual(len(limits["CET-SP"]), 1)   # leitura boa: a edição nem é consultada
        rio_warn = [w for w in self.new_warnings() if w.startswith("Rio trechos")]
        self.assertEqual(len(rio_warn), 1)
        self.assertIn("edição publicada (dado de 2026-10-06)", rio_warn[0])
        self.assertNotIn(True, [f.startswith("Rio trechos") for f in self.new_failures()])
        self.assertEqual(source_cache.dates()["Rio trechos"], "2026-10-06")

    def test_official_source_down_without_copy_comes_back_from_the_edition(self):
        mod = _Mod()
        mod.down = True
        got = BuildContext(self.raw, sources={"RIO": mod}, edition_dir=self.root).official()
        self.assertEqual(len(got["RIO"].cameras), 3)
        self.assertEqual(self.new_failures(), [])

    def test_copy_wins_over_the_edition(self):
        mod = _Mod()
        BuildContext(self.raw, sources={"RIO": mod}, edition_dir=self.root).official()   # grava a cópia (1)
        mod.down = True
        got = BuildContext(self.raw, sources={"RIO": mod}, edition_dir=self.root).official()
        self.assertEqual(len(got["RIO"].cameras), 1)
        self.assertIn("usada a cópia de", self.new_warnings()[-1])

    def test_source_missing_from_the_edition_is_still_a_failure(self):
        mod = _Mod()
        mod.down = True
        BuildContext(self.raw, sources={"FONTE-NOVA": mod}, edition_dir=self.root).official()
        self.assertEqual(len(self.new_failures()), 1)

    def test_stale_data_gets_attention_in_the_warning(self):
        from datetime import date
        self.assertEqual(source_cache._age_note("2026-10-06", date(2026, 11, 8)), "")
        self.assertIn("ATENÇÃO: dado de 94 dias", source_cache._age_note("2026-08-06", date(2026, 11, 8)))


def _lim():
    from datakit.common.model import Limit
    return Limit(-23.55, -46.63, 50, "CET-SP")


if __name__ == "__main__":
    unittest.main()
