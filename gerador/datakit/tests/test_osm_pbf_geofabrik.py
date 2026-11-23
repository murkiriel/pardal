"""Extrato regional do OSM na Geofabrik, depois da mudança para subpastas (20/11/2026): o endereço
pedido, o plano B que pula o datado do dia quando ele responde 404 (22/11/2026) e a espera que o 404
não gasta. Sem rede: a sessão HTTP, `get_text` e `urlopen` são simulados."""
from __future__ import annotations

import io
import os
import shutil
import tempfile
import unittest
from unittest import mock
from urllib.error import HTTPError

import requests

from datakit import failures
from datakit.sources import _http, osm_pbf

BASE = "https://download.geofabrik.de/south-america/brazil"
STAMP = "Sun, 22 Nov 2026 02:10:00 GMT"
OLD_STAMP = "Fri, 20 Nov 2026 02:10:00 GMT"


def _listing(region: str, dates=("261119", "261120", "261121", "261122")) -> str:
    """A listagem da subpasta: o datado do dia aparece, mesmo quando não abre."""
    rows = []
    for d in dates:
        url = f"{BASE}/{region}/{region}-{d}.osm.pbf"
        rows += [f'<a href="{url}">{region}-{d}.osm.pbf</a>', f'<a href="{url}.md5">{region}-{d}.osm.pbf.md5</a>']
    rows.append(f'<a href="{BASE}/{region}/{region}-latest.osm.pbf">{region}-latest.osm.pbf</a>')
    return "".join(rows)


def _http_error(code: int) -> requests.HTTPError:
    resp = requests.Response()
    resp.status_code = code
    return requests.HTTPError(f"{code} Error", response=resp)


class FakeSession:
    """session().head(): responde por nome de arquivo; o que não está em `answers` abre com STAMP."""

    def __init__(self, answers: dict):
        self.answers = answers
        self.asked: list = []

    def head(self, url, **kw):
        self.asked.append(url)
        answer = self.answers.get(url.rsplit("/", 1)[-1], STAMP)
        if isinstance(answer, BaseException):
            raise answer
        resp = mock.Mock()
        resp.headers = {"Last-Modified": answer}
        return resp


class Base(unittest.TestCase):
    def setUp(self):
        self.raw = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.raw, True)
        self.waits: list = []
        osm_pbf._LISTINGS.clear()
        self.addCleanup(osm_pbf._LISTINGS.clear)
        sleep = mock.patch.object(_http.time, "sleep", self.waits.append)
        sleep.start()
        self.addCleanup(sleep.stop)
        self.listing_calls: list = []

    def get_text(self, url, *a, **kw):
        self.listing_calls.append(url)
        region = url.rstrip("/").rsplit("/", 1)[-1]
        return _listing(region)

    def stored(self, region: str, stamp: str = OLD_STAMP) -> None:
        with open(os.path.join(self.raw, f"{region}-latest.osm.pbf"), "wb") as f:
            f.write(b"guardado")
        with open(os.path.join(self.raw, f"{region}.last-modified"), "w") as f:
            f.write(stamp)

    def urlopen(self, answers: dict):
        """urlopen simulado: `answers` por nome de arquivo (exceção ou nada = abre com STAMP)."""
        asked: list = []

        class Resp(io.BytesIO):
            headers = {"Last-Modified": STAMP}

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake(req, timeout=None):
            url = req.full_url
            asked.append(url)
            answer = answers.get(url.rsplit("/", 1)[-1])
            if isinstance(answer, BaseException):
                raise answer
            return Resp(b"pbf")
        fake.asked = asked  # type: ignore[attr-defined]
        return fake

    def run_extract(self, region="sul", head=None, urlopen=None):
        """ensure_extract com a rede simulada; devolve (extrato, sessão, urlopen)."""
        session = FakeSession(head or {})
        urlopen = urlopen or self.urlopen({})
        with mock.patch.object(_http, "session", lambda: session), \
                mock.patch.object(osm_pbf, "urlopen", urlopen), \
                mock.patch.object(osm_pbf, "get_text", self.get_text):
            ex = osm_pbf.ensure_extract(region, self.raw)
        return ex, session, urlopen


class RegionFolder(Base):
    def test_a_the_version_check_asks_for_the_region_folder(self):
        self.stored("norte")
        _, session, _ = self.run_extract("norte")
        self.assertEqual(session.asked, [f"{BASE}/norte/norte-latest.osm.pbf"])

    def test_a_the_download_asks_for_the_region_folder(self):
        ex, session, urlopen = self.run_extract("sudeste")     # sem guardado: baixa, sem consultar a versão
        self.assertEqual(session.asked, [])
        self.assertEqual(urlopen.asked, [f"{BASE}/sudeste/sudeste-latest.osm.pbf"])
        self.assertEqual((ex.bytes, ex.file_date), (3, STAMP))

    def test_e_stored_file_and_stamp_names_do_not_change(self):
        # o cache do Actions e o build (Extract.path) dependem destes nomes, não da pasta da Geofabrik
        ex, _, _ = self.run_extract("centro-oeste")
        self.assertEqual(ex.path, os.path.join(self.raw, "centro-oeste-latest.osm.pbf"))
        self.assertEqual(sorted(os.listdir(self.raw)), ["centro-oeste-latest.osm.pbf", "centro-oeste.last-modified"])
        with open(os.path.join(self.raw, "centro-oeste.last-modified")) as f:
            self.assertEqual(f.read(), STAMP)


class DatedFallback(Base):
    def test_b_latest_down_and_todays_dated_file_404_uses_yesterdays_and_says_which(self):
        self.stored("sul")
        head = {"sul-latest.osm.pbf": _http_error(404), "sul-261122.osm.pbf": _http_error(404)}
        ex, session, urlopen = self.run_extract("sul", head=head)
        self.assertEqual([u.rsplit("/", 1)[-1] for u in session.asked],
                         ["sul-latest.osm.pbf", "sul-261122.osm.pbf", "sul-261121.osm.pbf"])
        # o download vai direto ao datado que respondeu, sem passar de novo pelo -latest nem pelo do dia
        self.assertEqual(urlopen.asked, [f"{BASE}/sul/sul-261121.osm.pbf"])
        self.assertEqual((ex.bytes, ex.file_date), (3, STAMP))
        self.assertIn("OSM sul: -latest falhou (HTTPError); usado sul-261121.osm.pbf; pulado sul-261122.osm.pbf",
                      failures.warnings())

    def test_b_the_download_also_skips_the_broken_dated_file(self):
        gone = HTTPError("u", 404, "Not Found", None, None)
        urlopen = self.urlopen({"sul-latest.osm.pbf": gone, "sul-261122.osm.pbf": gone})
        f0 = len(failures.recorded())
        ex, _, urlopen = self.run_extract("sul", urlopen=urlopen)          # sem guardado: baixa
        self.assertEqual([u.rsplit("/", 1)[-1] for u in urlopen.asked],
                         ["sul-latest.osm.pbf", "sul-261122.osm.pbf", "sul-261121.osm.pbf"])
        self.assertEqual(ex.bytes, 3)
        self.assertEqual(len(failures.recorded()), f0)                       # aviso, não falha

    def test_c_a_404_does_not_wait(self):
        gone = HTTPError("u", 404, "Not Found", None, None)
        urlopen = self.urlopen({"sul-latest.osm.pbf": gone, "sul-261122.osm.pbf": gone})
        self.run_extract("sul", urlopen=urlopen)
        self.assertEqual(self.waits, [])                                       # nenhuma espera, nem a curta
        self.assertEqual([u.rsplit("/", 1)[-1] for u in urlopen.asked].count("sul-261122.osm.pbf"), 1)
        self.assertEqual([u.rsplit("/", 1)[-1] for u in urlopen.asked].count("sul-latest.osm.pbf"), 1)

    def test_c_410_does_not_wait_either(self):
        urlopen = self.urlopen({"sul-latest.osm.pbf": HTTPError("u", 410, "Gone", None, None)})
        self.run_extract("sul", urlopen=urlopen)
        self.assertEqual(self.waits, [])

    def test_c_a_transient_error_on_a_dated_file_keeps_the_patient_waits(self):
        down = HTTPError("u", 503, "Unavailable", None, None)
        urlopen = self.urlopen({"sul-latest.osm.pbf": HTTPError("u", 404, "Not Found", None, None),
                                "sul-261122.osm.pbf": down})
        self.run_extract("sul", urlopen=urlopen)
        w = osm_pbf.FALLBACK_WAIT_S
        self.assertEqual(self.waits, [w, 2 * w, 3 * w])
        names = [u.rsplit("/", 1)[-1] for u in urlopen.asked]
        self.assertEqual(names.count("sul-261122.osm.pbf"), osm_pbf.FALLBACK_ATTEMPTS)
        self.assertEqual(names[-1], "sul-261121.osm.pbf")

    def test_d_every_dated_file_down_uses_the_stored_one_and_warns(self):
        self.stored("sul")
        gone = _http_error(404)
        head = {n: gone for n in ("sul-latest.osm.pbf", "sul-261122.osm.pbf", "sul-261121.osm.pbf", "sul-261120.osm.pbf")}
        f0 = len(failures.recorded())
        ex, session, urlopen = self.run_extract("sul", head=head)
        names = [u.rsplit("/", 1)[-1] for u in session.asked]
        self.assertEqual(names, ["sul-latest.osm.pbf", "sul-261122.osm.pbf", "sul-261121.osm.pbf", "sul-261120.osm.pbf"])
        self.assertNotIn("sul-261119.osm.pbf", names)                       # no máximo 3 datados
        self.assertEqual(urlopen.asked, [])
        self.assertEqual((ex.bytes, ex.file_date), (8, OLD_STAMP))          # o guardado, intacto
        self.assertEqual(len(failures.recorded()), f0)
        self.assertIn(f"OSM sul: conferir a versão falhou (HTTPError); usado o arquivo guardado ({OLD_STAMP})",
                      failures.warnings())
        self.assertEqual(self.waits, [])

    def test_d_without_a_stored_file_the_error_of_the_newest_dated_file_rises(self):
        gone = HTTPError("u", 404, "Not Found", None, None)
        urlopen = self.urlopen({n: gone for n in ("sul-latest.osm.pbf", "sul-261122.osm.pbf",
                                                  "sul-261121.osm.pbf", "sul-261120.osm.pbf")})
        with self.assertRaises(HTTPError) as raised:
            self.run_extract("sul", urlopen=urlopen)
        self.assertEqual(raised.exception.code, 404)
        self.assertFalse(os.path.exists(os.path.join(self.raw, "sul-latest.osm.pbf")))

    def test_the_latest_link_working_never_reads_the_listing(self):
        self.stored("sul")
        self.run_extract("sul")
        self.assertEqual(self.listing_calls, [])


class Listing(Base):
    def test_f_the_listing_is_read_once_per_region(self):
        self.stored("sul")
        self.stored("sudeste")
        head = {"sul-latest.osm.pbf": _http_error(404), "sudeste-latest.osm.pbf": _http_error(404)}
        # a consulta e o download de cada região usam a mesma leitura da listagem
        for region in ("sul", "sudeste", "sul"):
            with mock.patch.object(_http, "session", lambda: FakeSession(head)), \
                    mock.patch.object(osm_pbf, "urlopen", self.urlopen({f"{region}-latest.osm.pbf": _http_error(404)})), \
                    mock.patch.object(osm_pbf, "get_text", self.get_text):
                osm_pbf.ensure_extract(region, self.raw)
        self.assertEqual(self.listing_calls, [f"{BASE}/sul/", f"{BASE}/sudeste/"])

    def test_dated_urls_come_newest_first_and_skip_the_checksum_links(self):
        with mock.patch.object(osm_pbf, "get_text", self.get_text):
            urls = osm_pbf._dated_urls("sul")
        self.assertEqual(urls, [f"{BASE}/sul/sul-{d}.osm.pbf" for d in ("261122", "261121", "261120", "261119")])

    def test_the_listing_of_another_region_is_not_confused(self):
        # "sul" não pode casar "sudeste-AAMMDD" nem o contrário
        text = _listing("sudeste") + _listing("sul", dates=("261101",))
        with mock.patch.object(osm_pbf, "get_text", return_value=text):
            self.assertEqual(osm_pbf._dated_urls("sul"), [f"{BASE}/sul/sul-261101.osm.pbf"])
            self.assertEqual(len(osm_pbf._dated_urls("sudeste")), 4)


if __name__ == "__main__":
    unittest.main()
