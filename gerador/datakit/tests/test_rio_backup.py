"""Rio: geocodificador da prefeitura com o CNEFE de reserva (sources/rio.py: locate e fetch)."""
import os
import tempfile
import unittest
from unittest import mock

from datakit import source_cache
from datakit.common.model import CameraKind
from datakit.context import BuildContext
from datakit.sources import rio

ITEMS = [
    ("AVENIDA AREIA BRANCA,PROXIMO AO Nº 1672 - SENTIDO SANTA CRUZ", CameraKind.FIXED, 60),
    ("AVENIDA AREIA BRANCA,PROXIMO AO Nº 1672 - SENTIDO CENTRO", CameraKind.FIXED, 60),   # mesma consulta
    ("RUA JARDIM BOTANICO, OPOSTO AO Nº 1008", CameraKind.RED_LIGHT, None),
    ("ACESSO AO MERGULHAO - SENTIDO BARRA", CameraKind.FIXED, 50),                         # sem número
]


class Locate(unittest.TestCase):
    def test_city_geocoder_up_is_used_once_per_query(self):
        calls = []

        def city(q):
            calls.append(q)
            return (-22.9, -43.5) if "AREIA" in q else None

        def backup(addrs):
            raise AssertionError("o CNEFE não deve ser usado com o geocodificador no ar")
        cams, error = rio.locate(ITEMS, city, backup)
        self.assertIsNone(error)
        self.assertEqual(calls, ["AVENIDA AREIA BRANCA 1672", "RUA JARDIM BOTANICO 1008"])
        self.assertEqual([(c.lat, c.kind, c.limit_kmh) for c in cams],
                         [(-22.9, CameraKind.FIXED, 60), (-22.9, CameraKind.FIXED, 60)])

    def test_city_geocoder_down_moves_every_address_to_the_backup(self):
        def city(q):
            raise TimeoutError("pgeo3 fora")
        asked = []

        def backup(addrs):
            asked.extend(addrs)
            return lambda addr: (-22.97, -43.22) if "JARDIM" in addr else (-22.91, -43.56)
        cams, error = rio.locate(ITEMS, city, backup)
        self.assertIsInstance(error, TimeoutError)
        self.assertEqual(len(asked), 3)    # só os que têm número de porta
        self.assertEqual(sorted((c.lat, c.kind) for c in cams),
                         [(-22.97, CameraKind.RED_LIGHT), (-22.91, CameraKind.FIXED), (-22.91, CameraKind.FIXED)])
        self.assertTrue(all(c.source == "RIO" and c.active for c in cams))

    def test_backup_that_refuses_lets_the_failure_rise(self):
        def city(q):
            raise TimeoutError("pgeo3 fora")

        def backup(addrs):
            raise RuntimeError("há cópia guardada")
        with self.assertRaises(RuntimeError):
            rio.locate(ITEMS, city, backup)


class ListPage(unittest.TestCase):
    PAGE = ('<html><head><title>Fiscaliza&#231;&#227;o Eletr&#244;nica &#8211; CET-Rio</title></head><body>'
            '<a href="https://cetrio.prefeitura.rio/wp-content/uploads/sites/36/2026/09/2026-09-01-ListagemSMTR.pdf">a</a>'
            '<a href="https://cetrio.prefeitura.rio/wp-content/uploads/sites/36/2026/10/2026-10-23-ListagemSMTR.pdf">b</a>'
            '</body></html>')

    def test_pdf_url_is_the_newest_listing(self):
        self.assertEqual("https://cetrio.prefeitura.rio/wp-content/uploads/sites/36/2026/10/2026-10-23-ListagemSMTR.pdf",
                         rio.pdf_url(self.PAGE))
        self.assertIsNone(rio.pdf_url("<html><title>x</title></html>"))

    def test_describe_page_says_status_size_title_and_start_of_the_text(self):
        html = ("<html><head><title>Just a moment...</title><script>var a = 1;</script></head>"
                "<body><h1>Verificando se voc&#234; &eacute; humano</h1><p>Aguarde</p></body></html>")
        got = rio.describe_page(403, "https://cetrio.prefeitura.rio/fiscalizacao-eletronica/", html)
        self.assertIn("HTTP 403", got)
        self.assertIn(f"{len(html)} bytes", got)
        self.assertIn("https://cetrio.prefeitura.rio/fiscalizacao-eletronica/", got)
        self.assertIn("«Just a moment...»", got)
        self.assertIn("Verificando se você é humano Aguarde", got)
        self.assertNotIn("var a", got)

    def test_describe_page_without_title_and_with_a_huge_title_stays_short(self):
        self.assertIn("sem título", rio.describe_page(200, "https://x/", ""))
        long = rio.describe_page(200, "https://x/" + "a" * 200, f"<title>{'t' * 500}</title>" + "p" * 500)
        self.assertLess(len(f"RIO: RuntimeError: lista de radares do Rio não encontrada; recebido: {long}"), 300)

    def test_error_without_the_link_describes_the_page_received(self):
        class Page:
            status_code = 200
            url = rio.LIST_PAGE
            text = "<html><head><title>Manutenção</title></head><body>Voltamos já</body></html>"
        with mock.patch.object(rio, "get_response", return_value=Page()):
            with self.assertRaises(RuntimeError) as ctx:
                rio._latest_pdf_url()
        msg = str(ctx.exception)
        self.assertIn("lista de radares do Rio não encontrada", msg)
        self.assertIn("HTTP 200", msg)
        self.assertIn("«Manutenção»", msg)
        self.assertIn("Voltamos já", msg)

    def test_page_with_the_link_gives_the_url(self):
        class Page:
            status_code = 200
            url = rio.LIST_PAGE
            text = ListPage.PAGE
        with mock.patch.object(rio, "get_response", return_value=Page()):
            self.assertTrue(rio._latest_pdf_url().endswith("2026-10-23-ListagemSMTR.pdf"))


class FetchUsesCnefeOnlyWithoutCopy(unittest.TestCase):
    def _fetch(self, raw):
        with mock.patch.object(rio, "load", return_value=([], [])) as load:
            rio.fetch(BuildContext(raw))
        return load.call_args.kwargs["cnefe_backup"]

    def test_without_copy_cnefe_is_allowed(self):
        self.assertTrue(self._fetch(tempfile.mkdtemp()))

    def test_with_copy_the_failure_rises_to_use_it(self):
        raw = tempfile.mkdtemp()
        path = source_cache.path_for(raw, "RIO")
        os.makedirs(os.path.dirname(path))
        open(path, "wb").close()
        self.assertFalse(self._fetch(raw))


if __name__ == "__main__":
    unittest.main()
