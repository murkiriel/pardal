"""Testes da publicação (scripts/publish.py) e das novas tentativas de download (_http).

    python -m unittest discover -s datakit/tests -t .     # de dentro de gerador/
"""
import importlib.util
import os
import re
import subprocess
import unittest

import requests

from datakit.sources import _http

_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "publish.py"))
_spec = importlib.util.spec_from_file_location("publicar", _PATH)
assert _spec is not None and _spec.loader is not None
pub = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pub)


def _cat(**ufs):
    return {"ufs": {uf: {"counts": c} for uf, c in ufs.items()}}


class Drops(unittest.TestCase):
    OLD = _cat(SP={"cameras": 4772, "limits": 459962, "structs": 20092},
               GO={"cameras": 1515, "limits": 120941, "structs": 4915})

    def test_same_or_growing_passes(self):
        new = _cat(SP={"cameras": 4800, "limits": 459962, "structs": 20092},
                   GO={"cameras": 1515, "limits": 125310, "structs": 4915})
        self.assertEqual(pub.drops(self.OLD, new), [])

    def test_a_source_down_is_caught(self):
        # CET-SP fora do ar: ~43 mil pontos de limite a menos em SP
        new = _cat(SP={"cameras": 4772, "limits": 416991, "structs": 20092},
                   GO={"cameras": 1515, "limits": 120941, "structs": 4915})
        self.assertEqual(pub.drops(self.OLD, new), ["SP: limites 459962 -> 416991 (-9%)"])

    def test_small_states_do_not_trip_on_a_few_items(self):
        old = _cat(AC={"cameras": 5, "limits": 6301, "structs": 377})
        new = _cat(AC={"cameras": 3, "limits": 6301, "structs": 377})   # -40%, mas só 2 radares
        self.assertEqual(pub.drops(old, new), [])

    def test_failures_list_never_reaches_the_published_catalog(self):
        self.assertNotIn("failures", pub.rewrite_catalog({"ufs": {}, "failures": ["CET-SP: erro"]}))

    def test_missing_state_and_big_drop(self):
        new = _cat(SP={"cameras": 2000, "limits": 459962, "structs": 20092})
        self.assertEqual(pub.drops(self.OLD, new), ["GO: sumiu do catálogo", "SP: radares 4772 -> 2000 (-58%)"])

    def test_first_publication_has_nothing_to_compare(self):
        self.assertEqual(pub.drops({}, self.OLD), [])


class Failures(unittest.TestCase):
    def test_registered_once_and_listed(self):
        from datakit import failures
        before = len(failures.recorded())
        failures.record("CET-SP", ConnectionResetError("reset"))
        failures.record("CET-SP", ConnectionResetError("reset"))
        self.assertEqual(len(failures.recorded()), before + 1)
        self.assertTrue(failures.recorded()[-1].startswith("CET-SP: ConnectionResetError"))


class OsmUpdate(unittest.TestCase):
    def test_downloads_only_a_newer_extract(self):
        from datakit.sources.osm_pbf import needs_update
        old, new = "Mon, 28 Sep 2026 22:49:39 GMT", "Tue, 29 Sep 2026 21:10:02 GMT"
        self.assertTrue(needs_update(old, new))
        self.assertFalse(needs_update(new, new))
        self.assertFalse(needs_update(new, old))
        self.assertTrue(needs_update("", new))        # sem data guardada: baixa
        self.assertTrue(needs_update(old, ""))        # Geofabrik sem data: baixa


class Retries(unittest.TestCase):
    def _flaky(self, errors):
        calls = []

        def fn():
            calls.append(1)
            if len(calls) <= len(errors):
                raise errors[len(calls) - 1]
            return "ok"
        return fn, calls

    def test_retries_a_dropped_connection_then_succeeds(self):
        fn, calls = self._flaky([requests.exceptions.ChunkedEncodingError("reset")])
        waits = []
        self.assertEqual(_http.with_retries(fn, sleep_fn=waits.append), "ok")
        self.assertEqual((len(calls), waits), (2, [_http.WAIT_S]))

    def test_gives_up_after_the_last_attempt(self):
        fn, calls = self._flaky([requests.ConnectionError("x")] * 5)
        with self.assertRaises(requests.ConnectionError):
            _http.with_retries(fn, sleep_fn=lambda s: None)
        self.assertEqual(len(calls), _http.ATTEMPTS)

    def test_client_errors_are_not_retried(self):
        resp = requests.Response()
        resp.status_code = 404
        fn, calls = self._flaky([requests.HTTPError(response=resp)])
        with self.assertRaises(requests.HTTPError):
            _http.with_retries(fn, sleep_fn=lambda s: None)
        self.assertEqual(len(calls), 1)
        self.assertFalse(_http.is_transient(subprocess.CalledProcessError(22, "curl")))
        resp.status_code = 503
        self.assertTrue(_http.is_transient(requests.HTTPError(response=resp)))


if __name__ == "__main__":
    unittest.main()


class Resilience(unittest.TestCase):
    def setUp(self):
        from unittest import mock
        _http._DEAD_HOSTS.clear()
        # as esperas entre tentativas (5 s, 10 s) não precisam acontecer de verdade no teste
        self._sleep = mock.patch.object(_http.time, "sleep", lambda s: None)
        self._sleep.start()

    def tearDown(self):
        self._sleep.stop()
        _http._DEAD_HOSTS.clear()

    def test_host_that_never_connects_is_skipped_for_the_rest_of_the_run(self):
        calls = []

        def boom():
            calls.append(1)
            raise requests.ConnectTimeout("sem conexão")
        orig = _http.WAIT_S
        _http.WAIT_S = 0
        try:
            with self.assertRaises(requests.ConnectTimeout):
                _http.guarded("https://servicos.exemplo.gov.br/a.json", boom)
            self.assertEqual(len(calls), _http.ATTEMPTS)
            with self.assertRaises(ConnectionError):
                _http.guarded("https://servicos.exemplo.gov.br/b.json", boom)
            self.assertEqual(len(calls), _http.ATTEMPTS)           # nem tentou de novo
            self.assertEqual(_http.guarded("https://outro.gov.br/x", lambda: "ok"), "ok")
        finally:
            _http.WAIT_S = orig
            _http._DEAD_HOSTS.clear()

    def test_read_timeout_does_not_condemn_the_host(self):
        orig = _http.WAIT_S
        _http.WAIT_S = 0
        try:
            def slow():
                raise requests.ReadTimeout("lento")
            with self.assertRaises(requests.ReadTimeout):
                _http.guarded("https://lento.gov.br/a", slow)
            self.assertNotIn("lento.gov.br", _http._DEAD_HOSTS)
        finally:
            _http.WAIT_S = orig

    def test_cet_uses_the_saved_copy_and_warns_when_power_bi_fails(self):
        import json
        import tempfile
        from unittest import mock
        from datakit import failures
        from datakit.sources import cet_sp
        raw = tempfile.mkdtemp()
        rows = [{"CÓDIGO LOCAL": "1", "LATITUDE": -23.60, "LONGITUDE": -46.66, "DESCRIÇÃO DO LOCAL": "R X",
                 "ENQUADRAMENTOS": "V", "VELOCIDADE": "50 km/h", "DESATIVAÇÃO": None}]
        no_github = mock.patch("datakit.sources._http.get_bytes", side_effect=ConnectionError("sem rede"))
        with mock.patch.object(cet_sp._powerbi, "model_id", return_value=1), \
                mock.patch.object(cet_sp._powerbi, "query_table", return_value=rows), no_github:
            self.assertEqual(len(cet_sp.load(raw)[0]), 1)             # leitura boa: guarda a cópia
        before = len(failures.warnings())
        with mock.patch.object(cet_sp._powerbi, "model_id", side_effect=RuntimeError("mudou")), no_github:
            self.assertEqual(len(cet_sp.load(raw)[0]), 1)             # falhou (e a reserva do GitHub também): usa a cópia
        self.assertEqual(len(failures.warnings()), before + 1)
        self.assertIn("CET-SP", failures.warnings()[-1])
        with open(os.path.join(raw, cet_sp.CACHE_FILE), encoding="utf-8") as f:
            self.assertEqual(json.load(f), rows)

    def test_inmetro_state_without_copy_is_a_failure_with_copy_a_warning(self):
        import tempfile
        from unittest import mock
        from datakit import failures
        from datakit.sources import inmetro
        raw = tempfile.mkdtemp()
        os.makedirs(os.path.join(raw, "inmetro"))
        with open(os.path.join(raw, "inmetro", "GO.json"), "w", encoding="utf-8") as f:
            f.write("[]")
        f0, a0 = len(failures.recorded()), len(failures.warnings())
        with mock.patch.object(inmetro, "get_bytes", side_effect=requests.ConnectTimeout("x")):
            inmetro.load(raw)
        self.assertEqual(len(failures.recorded()) - f0, 25)            # 25 UFs sem cópia (o DF não tem arquivo)
        self.assertEqual(len(failures.warnings()) - a0, 1)            # GO usou a cópia
        self.assertTrue(failures.warnings()[-1].startswith("Inmetro GO"))

    def test_warnings_never_reach_the_published_catalog(self):
        self.assertNotIn("warnings", pub.rewrite_catalog({"ufs": {}, "warnings": ["Inmetro DF: cópia"]}))


class OsmDatedFallback(unittest.TestCase):
    """O <região>-latest.osm.pbf da Geofabrik em laço de redirecionamento (301 para si mesmo)."""
    BASE = "https://download.geofabrik.de/south-america/brazil"
    LISTING = ('<a href="sudeste-260929.osm.pbf">sudeste-260929.osm.pbf</a>'
               '<a href="sudeste-260930.osm.pbf">sudeste-260930.osm.pbf</a>'
               '<a href="sudeste-260930.osm.pbf.md5">sudeste-260930.osm.pbf.md5</a>'
               '<a href="sudeste-latest.osm.pbf">sudeste-latest.osm.pbf</a>'
               '<a href="sul-261001.osm.pbf">sul-261001.osm.pbf</a>')
    STAMP = "Wed, 30 Sep 2026 21:10:02 GMT"

    def setUp(self):
        import tempfile
        from unittest import mock
        from datakit.sources import osm_pbf
        self.osm, self.mock = osm_pbf, mock
        self.raw = tempfile.mkdtemp()
        self.asked = []
        self.waits = []
        osm_pbf._LISTING = None          # a listagem fica guardada pela execução inteira
        self._sleep = mock.patch.object(_http.time, "sleep", self.waits.append)
        self._sleep.start()

    def tearDown(self):
        self._sleep.stop()
        self.osm._LISTING = None

    def _urlopen(self, latest_loops=True, dated_ok=True):
        """urlopen simulado: o -latest em laço (como o urllib relata) e o datado respondendo."""
        import io
        from urllib.error import HTTPError

        class Resp(io.BytesIO):
            headers = {"Last-Modified": self.STAMP}

        def fake(req, timeout=None):
            url = req.full_url
            self.asked.append(url.rsplit("/", 1)[-1])
            if url.endswith("-latest.osm.pbf") and latest_loops:
                raise HTTPError(url, 301, "redirect error that would lead to an infinite loop", None, None)
            if not dated_ok:
                raise HTTPError(url, 404, "Not Found", None, None)
            return Resp(b"pbf")
        return fake

    def _stored(self, stamp):
        with open(os.path.join(self.raw, "sudeste-latest.osm.pbf"), "wb") as f:
            f.write(b"stored!")
        with open(os.path.join(self.raw, "sudeste.last-modified"), "w") as f:
            f.write(stamp)

    def test_download_falls_back_to_the_newest_dated_file_and_warns(self):
        from datakit import failures
        f0 = len(failures.recorded())
        with self.mock.patch.object(self.osm, "urlopen", self._urlopen()), \
                self.mock.patch.object(self.osm, "get_text", return_value=self.LISTING) as listing:
            ex = self.osm.ensure_extract("sudeste", self.raw)
        listing.assert_called_once_with(self.BASE + "/")
        self.assertEqual(self.asked, ["sudeste-latest.osm.pbf"] * _http.ATTEMPTS + ["sudeste-260930.osm.pbf"])
        self.assertEqual((ex.bytes, ex.file_date), (3, self.STAMP))
        self.assertTrue(ex.path.endswith("sudeste-latest.osm.pbf"))       # o nome guardado não muda
        self.assertEqual(len(failures.recorded()), f0)                    # aviso, não falha
        # (os avisos não se repetem na lista: outro teste pode já ter registrado este)
        self.assertIn("OSM sudeste: -latest falhou (HTTPError); usado sudeste-260930.osm.pbf", failures.warnings())

    def test_version_check_falls_back_and_the_download_goes_straight_to_the_dated_file(self):
        self._stored("Tue, 29 Sep 2026 21:10:02 GMT")
        heads = []

        def head(url):
            heads.append(url.rsplit("/", 1)[-1])
            if url.endswith("-latest.osm.pbf"):
                raise requests.TooManyRedirects("Exceeded 30 redirects.")
            return self.STAMP
        with self.mock.patch.object(self.osm, "_remote_last_modified", head), \
                self.mock.patch.object(self.osm, "urlopen", self._urlopen()), \
                self.mock.patch.object(self.osm, "get_text", return_value=self.LISTING):
            ex = self.osm.ensure_extract("sudeste", self.raw)
        self.assertEqual(heads[-1], "sudeste-260930.osm.pbf")
        self.assertEqual(self.asked, ["sudeste-260930.osm.pbf"])         # sem insistir no -latest
        self.assertEqual((ex.bytes, ex.file_date), (3, self.STAMP))

    def test_stored_extract_is_kept_when_the_dated_file_is_not_newer(self):
        self._stored(self.STAMP)

        def head(url):
            if url.endswith("-latest.osm.pbf"):
                raise requests.TooManyRedirects("Exceeded 30 redirects.")
            return self.STAMP
        with self.mock.patch.object(self.osm, "_remote_last_modified", head), \
                self.mock.patch.object(self.osm, "urlopen", self._urlopen()), \
                self.mock.patch.object(self.osm, "get_text", return_value=self.LISTING):
            ex = self.osm.ensure_extract("sudeste", self.raw)
        self.assertEqual((self.asked, ex.bytes), ([], 7))   # nada baixado

    def test_listing_down_raises_the_error_of_the_latest_link(self):
        from urllib.error import HTTPError
        with self.mock.patch.object(self.osm, "urlopen", self._urlopen()), \
                self.mock.patch.object(self.osm, "get_text", side_effect=requests.ConnectionError("fora do ar")):
            with self.assertRaises(HTTPError) as raised:
                self.osm.ensure_extract("sudeste", self.raw)
        self.assertEqual(raised.exception.code, 301)

    def test_dated_file_down_too_raises_its_error(self):
        from urllib.error import HTTPError
        with self.mock.patch.object(self.osm, "urlopen", self._urlopen(dated_ok=False)), \
                self.mock.patch.object(self.osm, "get_text", return_value=self.LISTING):
            with self.assertRaises(HTTPError) as raised:
                self.osm.ensure_extract("sudeste", self.raw)
        self.assertEqual(raised.exception.code, 404)
        self.assertFalse(os.path.exists(os.path.join(self.raw, "sudeste-latest.osm.pbf")))

    def test_version_check_with_latest_and_dated_down_keeps_the_stored_file_as_a_warning(self):
        from datakit import failures
        self._stored(self.STAMP)
        f0, w0 = len(failures.recorded()), len(failures.warnings())
        with self.mock.patch.object(self.osm, "_remote_last_modified",
                                    side_effect=requests.TooManyRedirects("Exceeded 30 redirects.")), \
                self.mock.patch.object(self.osm, "get_text", return_value=self.LISTING):
            ex = self.osm.ensure_extract("sudeste", self.raw)
        self.assertEqual(ex.bytes, 7)
        self.assertEqual(len(failures.recorded()), f0)
        self.assertEqual(len(failures.warnings()), w0 + 1)

    def test_new_version_that_fails_to_download_keeps_the_stored_file_as_a_warning(self):
        from datakit import failures
        self._stored("Mon, 01 Jan 2001 00:00:00 GMT")   # guardado mais velho que o publicado: tenta baixar
        f0, w0 = len(failures.recorded()), len(failures.warnings())
        with self.mock.patch.object(self.osm, "_remote_last_modified", return_value=self.STAMP), \
                self.mock.patch.object(self.osm, "_download", side_effect=OSError("conexão caiu")), \
                self.mock.patch.object(self.osm, "get_text", side_effect=OSError("listagem fora")):
            ex = self.osm.ensure_extract("sudeste", self.raw)
        self.assertEqual(ex.bytes, 7)
        self.assertEqual(ex.file_date, "Mon, 01 Jan 2001 00:00:00 GMT")
        self.assertEqual(len(failures.recorded()), f0)
        self.assertEqual(len(failures.warnings()), w0 + 1)

    def test_listing_that_fails_for_a_while_is_waited_for(self):
        # 01/10/2026: a listagem respondeu com erro por até 45 s; as esperas comuns (5 s, 10 s) não bastaram
        resp = requests.Response()
        resp.status_code = 502
        down = requests.HTTPError("502 Server Error: Bad Gateway", response=resp)
        with self.mock.patch.object(self.osm, "urlopen", self._urlopen()), \
                self.mock.patch.object(self.osm, "get_text", side_effect=[down, down, self.LISTING]) as listing:
            ex = self.osm.ensure_extract("sudeste", self.raw)
        self.assertEqual((listing.call_count, ex.bytes), (3, 3))
        self.assertEqual(self.waits[-2:], [self.osm.FALLBACK_WAIT_S, 2 * self.osm.FALLBACK_WAIT_S])

    def test_listing_is_read_once_for_all_regions(self):
        with self.mock.patch.object(self.osm, "urlopen", self._urlopen()), \
                self.mock.patch.object(self.osm, "get_text", return_value=self.LISTING) as listing:
            self.osm.ensure_extract("sudeste", self.raw)
            self.osm.ensure_extract("sul", self.raw)
        self.assertEqual(listing.call_count, 1)
        self.assertEqual(self.asked[-1], "sul-261001.osm.pbf")

    def test_newest_dated_file_of_the_region_only(self):
        with self.mock.patch.object(self.osm, "get_text", return_value=self.LISTING):
            self.assertEqual(self.osm._dated_url("sudeste"), self.BASE + "/sudeste-260930.osm.pbf")
            self.assertEqual(self.osm._dated_url("sul"), self.BASE + "/sul-261001.osm.pbf")
            with self.assertRaises(RuntimeError):
                self.osm._dated_url("norte")


class PublishedNames(unittest.TestCase):
    """Todo arquivo de dado do pacote vai para o repositório ou para o zip da release (só um dos
    dois): o catálogo aponta para ele."""

    def test_every_pack_data_file_is_published_or_release_only(self):
        from datakit import build_brazil, build_pack
        names = [v for k, v in vars(build_pack).items()
                 if k.endswith("_FILE") and isinstance(v, str) and v.endswith(".csv")]
        self.assertGreaterEqual(len(names), 8)
        for name in names:
            with self.subTest(name=name):
                committed = bool(pub._PUBLISHED_NAME.match(name))
                self.assertNotEqual(committed, bool(pub._RELEASE_ONLY_NAME.match(name)), name)
                self.assertEqual(committed, bool(build_brazil.PUBLISHED_NAME.match(name)), name)
        self.assertEqual(pub._PUBLISHED_NAME.pattern, build_brazil.PUBLISHED_NAME.pattern)

    def test_lines_stay_out_of_the_commit(self):
        self.assertIsNone(pub._PUBLISHED_NAME.match("limites_trechos.csv"))
        self.assertTrue(pub._PUBLISHED_NAME.match("ufs.geojson"))

    def test_published_catalog_points_release_only_files_to_the_zip(self):
        entry = {"file": "estados/SP/limites_trechos.csv", "bytes": 10, "sha256": "ab", "count": 3}
        cat = {"failures": [], "warnings": ["x"],
               "ufs": {"SP": {"limit_lines": dict(entry), "limits": {"file": "estados/SP/limites.csv"}}}}
        out = pub.rewrite_catalog(cat)
        self.assertEqual(out["ufs"]["SP"]["limit_lines"],
                         {"bytes": 10, "sha256": "ab", "count": 3,
                          "release_asset": "pardal-SP.zip", "asset_path": "SP/limites_trechos.csv"})
        self.assertEqual(out["ufs"]["SP"]["limits"], {"file": "estados/SP/limites.csv"})
        self.assertNotIn("failures", out)
        self.assertEqual(cat["ufs"]["SP"]["limit_lines"], entry)   # o do build fica como estava


class CompressOversized(unittest.TestCase):
    """Arquivo publicado acima do teto sai compactado e o catálogo aponta para o .gz."""

    def test_big_file_becomes_gz_and_the_catalog_follows(self):
        import gzip
        import json
        import shutil
        import tempfile
        from datakit import build_brazil
        dist = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(dist, "estados", "SP"))
            big = "lat,lng\n" + "-23.5,-46.6\n" * 2000
            with open(os.path.join(dist, "estados", "SP", "limites.csv"), "w") as f:
                f.write(big)
            with open(os.path.join(dist, "estados", "SP", "radares.csv"), "w") as f:
                f.write("lat,lng\n-23.5,-46.6\n")
            with open(os.path.join(dist, "estados", "SP", "radares.csv.gz"), "wb") as f:   # sobra de um build antigo
                f.write(b"velho")
            cat = {"ufs": {"SP": {"limits": {"file": "estados/SP/limites.csv", "bytes": len(big), "count": 2000},
                                  "cameras": {"file": "estados/SP/radares.csv", "count": 1}}}}
            with open(os.path.join(dist, "catalogo.json"), "w") as f:
                json.dump(cat, f)
            done = build_brazil.compress_oversized(dist, limit=1000)
            self.assertEqual([d[0] for d in done], ["estados/SP/limites.csv"])
            self.assertFalse(os.path.exists(os.path.join(dist, "estados", "SP", "limites.csv")))
            self.assertFalse(os.path.exists(os.path.join(dist, "estados", "SP", "radares.csv.gz")))
            with gzip.open(os.path.join(dist, "estados", "SP", "limites.csv.gz"), "rt") as f:
                self.assertEqual(f.read(), big)
            with open(os.path.join(dist, "catalogo.json")) as f:
                lim = json.load(f)["ufs"]["SP"]["limits"]
            self.assertEqual(lim["file"], "estados/SP/limites.csv.gz")
            self.assertEqual((lim["count"], lim["uncompressed_bytes"]), (2000, len(big)))
            self.assertEqual(lim["sha256"], pub._sha(os.path.join(dist, "estados", "SP", "limites.csv.gz")))
            self.assertEqual(build_brazil.oversized(dist, limit=1000), [])
            self.assertIn("estados/SP/limites.csv.gz", pub.published_files(dist))
        finally:
            shutil.rmtree(dist, ignore_errors=True)

    def test_any_published_extension_may_be_gzipped(self):
        for name in ("limites.csv.gz", "radares.geojson.gz", "radares.kml.gz", "lombadas.csv.gz"):
            self.assertTrue(pub._PUBLISHED_NAME.match(name), name)
        self.assertIsNone(pub._PUBLISHED_NAME.match("limites.gz"))


class CommitDataOnly(unittest.TestCase):
    """publish.py --commit só leva brasil/, estados/ e catalogo.json — nunca o que mais estiver
    pendente no repositório (código do gerador não revisado, arquivos soltos)."""

    def _git(self, repo, *a):
        return subprocess.run(["git", "-C", repo, *a], check=True, capture_output=True, text=True).stdout

    def test_stray_files_stay_out_of_the_data_commit(self):
        import json
        import shutil
        import tempfile
        repo, dist = tempfile.mkdtemp(), tempfile.mkdtemp()
        try:
            self._git(repo, "init", "-q")
            self._git(repo, "config", "user.email", "teste@example.invalid")
            self._git(repo, "config", "user.name", "teste")
            with open(os.path.join(repo, "LEIAME.md"), "w", encoding="utf-8") as f:
                f.write("x")
            with open(os.path.join(repo, "catalog.json"), "w", encoding="utf-8") as f:   # nome do schema 1
                f.write('{"schema": 1, "ufs": {}}')
            self._git(repo, "add", "-A")
            self._git(repo, "commit", "-q", "-m", "inicial")
            # pendências que NÃO podem entrar no commit de dados
            os.makedirs(os.path.join(repo, "gerador"))
            with open(os.path.join(repo, "gerador", "codigo_novo.py"), "w", encoding="utf-8") as f:
                f.write("print(1)\n")
            with open(os.path.join(repo, "solto.txt"), "w", encoding="utf-8") as f:
                f.write("pessoal\n")
            with open(os.path.join(repo, "LEIAME.md"), "w", encoding="utf-8") as f:
                f.write("editado\n")
            # um build mínimo em dist
            os.makedirs(os.path.join(dist, "estados", "GO"))
            with open(os.path.join(dist, "estados", "GO", "radares.csv"), "w", encoding="utf-8") as f:
                f.write("lat,lng\n-16,-49\n")
            with open(os.path.join(dist, "catalogo.json"), "w", encoding="utf-8") as f:
                json.dump({"built_at": "2026-09-30T00:00:00Z", "ufs": {"GO": {"counts": {"cameras": 1}}}}, f)
            self.assertEqual(pub.main(["--repo", repo, "--dist", dist, "--commit"]), 0)
            committed = set(self._git(repo, "show", "--name-only", "--pretty=format:", "HEAD").split())
            self.assertEqual(committed, {"catalogo.json", "catalog.json", "estados/GO/radares.csv"})
            self.assertFalse(os.path.exists(os.path.join(repo, "catalog.json")))   # o nome antigo sai
            self.assertEqual(self._git(repo, "ls-files", "catalog.json"), "")
            pending = self._git(repo, "status", "--porcelain")
            self.assertIn("solto.txt", pending)
            self.assertIn("gerador/", pending)
            self.assertIn("LEIAME.md", pending)
        finally:
            shutil.rmtree(repo, ignore_errors=True)
            shutil.rmtree(dist, ignore_errors=True)

    def test_new_build_date_alone_makes_no_commit(self):
        # geração diária: dia sem dado novo não vira commit (nem release) só pela data do catálogo
        import json
        import shutil
        import tempfile
        repo, dist = tempfile.mkdtemp(), tempfile.mkdtemp()
        try:
            self._git(repo, "init", "-q")
            self._git(repo, "config", "user.email", "teste@example.invalid")
            self._git(repo, "config", "user.name", "teste")
            os.makedirs(os.path.join(dist, "estados", "GO"))
            with open(os.path.join(dist, "estados", "GO", "radares.csv"), "w", encoding="utf-8") as f:
                f.write("lat,lng\n-16,-49\n")
            cat = {"built_at": "2026-11-07T06:30:00Z", "ufs": {"GO": {"counts": {"cameras": 1}}}}
            with open(os.path.join(dist, "catalogo.json"), "w", encoding="utf-8") as f:
                json.dump(cat, f)
            self.assertEqual(pub.main(["--repo", repo, "--dist", dist, "--commit"]), 0)
            head = self._git(repo, "rev-parse", "HEAD")
            with open(os.path.join(dist, "catalogo.json"), "w", encoding="utf-8") as f:
                json.dump({**cat, "built_at": "2026-11-08T06:30:00Z"}, f)
            self.assertEqual(pub.main(["--repo", repo, "--dist", dist, "--commit"]), 0)
            self.assertEqual(self._git(repo, "rev-parse", "HEAD"), head)
            self.assertEqual(self._git(repo, "status", "--porcelain"), "")
        finally:
            shutil.rmtree(repo, ignore_errors=True)
            shutil.rmtree(dist, ignore_errors=True)


class BuildInProgress(unittest.TestCase):
    """Enquanto o build roda (ou se ele caiu no meio), data/dist tem pacotes de dois builds
    misturados: o publish.py não monta nada."""

    def _dist(self, tmp):
        import json
        dist = os.path.join(tmp, "dist")
        os.makedirs(dist)
        with open(os.path.join(dist, "catalogo.json"), "w", encoding="utf-8") as f:
            json.dump({"ufs": {}}, f)
        return dist

    def test_publish_refuses_while_the_marker_exists(self):
        import tempfile
        from datakit import build
        with tempfile.TemporaryDirectory() as tmp:
            dist, repo = self._dist(tmp), os.path.join(tmp, "repo")
            os.makedirs(repo)
            with open(os.path.join(dist, build.IN_PROGRESS_MARKER), "w", encoding="utf-8") as f:
                f.write("2026-09-30T00:00:00Z\n")
            with self.assertRaises(SystemExit) as cm:
                pub.main(["--repo", repo, "--dist", dist, "--accept-failures", "--accept-drop"])
            self.assertIn("andamento", str(cm.exception.code))
            self.assertEqual(os.listdir(repo), [])

    def _run_build(self, tmp, catalog_fails=False):
        import json
        from unittest import mock
        from datakit import build
        dist = os.path.join(tmp, "dist")
        seen = []

        def fake_one(uf, ctx, packs_dir, split):
            seen.append(os.path.exists(os.path.join(dist, build.IN_PROGRESS_MARKER)))

        def fake_catalog(packs, d):
            if catalog_fails:
                raise RuntimeError("disco cheio")
            with open(os.path.join(d, "catalogo.json"), "w", encoding="utf-8") as f:
                json.dump({"ufs": {}}, f)
            return {"ufs": {}}

        with mock.patch.object(build, "build_one", fake_one), \
                mock.patch.object(build, "build_catalog", fake_catalog):
            try:
                build.main(["--uf", "GO", "--no-polygon", "--dist", dist, "--packs", os.path.join(tmp, "p")])
            except RuntimeError:
                pass
        return seen, os.path.exists(os.path.join(dist, build.IN_PROGRESS_MARKER))

    def test_build_marks_while_running_and_clears_at_the_end(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self._run_build(tmp), ([True], False))

    def test_marker_stays_when_the_build_dies(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self._run_build(tmp, catalog_fails=True), ([True], True))


class HttpSession(unittest.TestCase):
    """Uma sessão HTTP para o build inteiro: as requisições ao mesmo servidor (27 UFs do Inmetro,
    páginas do ArcGIS) reusam a conexão. Mesmos cabeçalhos e tempos de antes."""

    def test_one_shared_session(self):
        self.assertIs(_http.session(), _http.session())
        self.assertIsInstance(_http.session(), requests.Session)

    def test_get_goes_through_the_session_with_the_same_arguments(self):
        from unittest import mock

        class Resp:
            content, text = b"x", "x"

            def raise_for_status(self):
                pass

            def json(self):
                return {"ok": 1}

        with mock.patch.object(_http.session(), "get", return_value=Resp()) as get:
            self.assertEqual(_http.get_json("https://x.gov.br/a", params={"q": 1}), {"ok": 1})
            self.assertEqual(_http.get_bytes("https://x.gov.br/b", headers={"A": "b"}, timeout=5), b"x")
        self.assertEqual(get.call_args_list[0], mock.call(
            "https://x.gov.br/a", headers=_http.UA, timeout=(_http.CONNECT_TIMEOUT, _http.HTTP_TIMEOUT),
            params={"q": 1}))
        self.assertEqual(get.call_args_list[1], mock.call(
            "https://x.gov.br/b", headers={"A": "b"}, timeout=(_http.CONNECT_TIMEOUT, 5), params=None))


class ForkSchedule(unittest.TestCase):
    """Um fork com o Actions ligado não pode gerar e publicar sozinho todo dia: o agendamento só vale
    no repositório do projeto (à mão, gera onde for disparado). Sem a trava, o fork lia a data dos
    dados do repositório original e geraria sem o segredo do túnel."""

    def test_the_schedule_only_runs_in_the_project_repository(self):
        path = os.path.join(os.path.dirname(__file__), "..", "..", "..", ".github", "workflows", "gerar-dados.yml")
        with open(path, encoding="utf-8") as f:
            text = f.read()
        job = text.split("\n  interval:\n", 1)[1].split("\n  generate:\n", 1)[0]
        guard = [ln.strip() for ln in job.splitlines() if ln.startswith("    if:")]
        # o repositório passou a murkiriel/pardal (minúsculo); a expressão do GitHub ignora maiúsculas
        self.assertEqual(guard, ["if: github.event_name != 'schedule' || github.repository == 'murkiriel/pardal'"])


class TunnelStepNeverFailsTheJob(unittest.TestCase):
    """O passo do túnel roda com bash -e: qualquer comando que falhe fora de um `|| down` derruba a geração
    inteira, quando a intenção é seguir sem o túnel (as fontes de TUNNEL_HOSTS caem nas cópias guardadas).
    Em 2026-11-11 o `apt-get install wireguard-tools` falhou com o índice do apt velho e derrubou o job."""

    def _tunnel_step(self):
        path = os.path.join(os.path.dirname(__file__), "..", "..", "..", ".github", "workflows", "gerar-dados.yml")
        with open(path, encoding="utf-8") as f:
            text = f.read()
        return text.split("- name: Túnel para", 1)[1].split("\n      - name: ", 1)[0]

    def test_apt_runs_inside_a_retry_loop_after_an_update(self):
        step = self._tunnel_step()
        apt = [ln.strip() for ln in step.splitlines() if "apt-get" in ln and not ln.strip().startswith("#")]
        self.assertEqual(len(apt), 1, apt)
        self.assertRegex(apt[0], r"apt-get update .*&& sudo apt-get install .*wireguard-tools.*&& break$")
        self.assertIn('command -v wg-quick >/dev/null || down "', step)

    def test_every_network_command_falls_back_to_down(self):
        step = self._tunnel_step()
        for cmd in ("wg-quick up", "curl -s"):
            lines = [i for i, ln in enumerate(step.splitlines()) if cmd in ln]
            self.assertTrue(lines, cmd)
            for i in lines:
                block = " ".join(step.splitlines()[i:i + 2])
                self.assertIn("|| down", block, cmd)


class PinnedBuild(unittest.TestCase):
    """Só a geração corrente precisa ser reproduzível, mas ela tem de ser. Duas regras: toda action
    dos workflows fixada por SHA de commit (a tag fica no comentário: uma tag pode ser movida, o SHA não), e
    toda instalação do pip com --require-hashes, de um requirements*.txt gerado do .in, com cada pacote
    (inclusive os transitivos) em versão exata e com hash."""

    ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")
    GERADOR = os.path.join(ROOT, "gerador")

    def _workflows(self):
        folder = os.path.join(self.ROOT, ".github", "workflows")
        names = sorted(n for n in os.listdir(folder) if n.endswith((".yml", ".yaml")))
        self.assertIn("gerar-dados.yml", names)
        for n in names:
            with open(os.path.join(folder, n), encoding="utf-8") as f:
                yield n, f.read()

    def _requirements(self, name):
        """{pacote: (versão, nº de hashes)} de um requirements*.txt gerado pelo uv pip compile."""
        with open(os.path.join(self.GERADOR, name), encoding="utf-8") as f:
            text = f.read()
        self.assertTrue(text.startswith("# This file was autogenerated by uv via the following command:\n"
                                        "#    uv pip compile "), name)
        self.assertIn("--generate-hashes", text.splitlines()[1], name)
        out = {}
        for block in re.split(r"\n(?=[^\s#])", text):
            if not block.strip() or block.startswith("#"):
                continue
            m = re.match(r"([A-Za-z0-9._-]+)==([^\s;\\]+)", block)
            self.assertIsNotNone(m, f"{name}: dependência sem versão exata: {block.splitlines()[0]}")
            out[m.group(1).lower()] = (m.group(2), len(re.findall(r"--hash=sha256:[0-9a-f]{64}\b", block)))
        return out

    def test_every_action_is_pinned_by_commit_sha(self):
        pinned = 0
        for name, text in self._workflows():
            for ln in text.splitlines():
                if re.match(r"\s*(-\s+)?uses:", ln):
                    self.assertRegex(ln.strip(), r"^(- )?uses: [\w.-]+/[\w./-]+@[0-9a-f]{40}  # v\d+(\.\d+)*$",
                                     f"{name}: action sem SHA de 40 caracteres e tag no comentário")
                    pinned += 1
        self.assertGreater(pinned, 0)

    def test_every_pip_install_requires_hashes(self):
        files = set()
        for name, text in self._workflows():
            for ln in text.splitlines():
                if "pip install" in ln and not ln.strip().startswith("#"):
                    self.assertIn("--require-hashes", ln, name)
                    m = re.search(r"-r (\S*requirements[\w-]*\.txt)\b", ln)
                    self.assertIsNotNone(m, f"{name}: pip install sem -r requirements*.txt: {ln.strip()}")
                    files.add(os.path.basename(m.group(1)))
        self.assertEqual(files, {"requirements.txt", "requirements-dev.txt"})

    def test_lockfiles_pin_everything_with_hashes_and_follow_the_in_files(self):
        locks = {n: self._requirements(n) for n in ("requirements.txt", "requirements-dev.txt")}
        for name, pkgs in locks.items():
            self.assertTrue(pkgs, name)
            for pkg, (_, hashes) in pkgs.items():
                self.assertGreater(hashes, 0, f"{name}: {pkg} sem hash")
        # as diretas do .in, na versão escrita lá; o dev usa as mesmas versões do gerador
        for src, lock in (("requirements.in", "requirements.txt"), ("requirements-dev.in", "requirements-dev.txt")):
            with open(os.path.join(self.GERADOR, src), encoding="utf-8") as f:
                for ln in f:
                    m = re.match(r"([A-Za-z0-9._-]+)==(\S+)", ln)
                    if m:
                        self.assertEqual(locks[lock].get(m.group(1).lower(), (None,))[0], m.group(2), f"{lock}: {ln.strip()}")
        for pkg, (version, _) in locks["requirements.txt"].items():
            self.assertEqual(locks["requirements-dev.txt"].get(pkg, (None,))[0], version, pkg)
