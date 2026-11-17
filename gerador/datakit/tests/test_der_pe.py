"""DER-PE: a tabela de lombadas (artigo 1382, com linhas de continuação por sentido) e a lista de equipamentos
mistos (artigo 1383); endereço estável do artigo com o do menu de reserva. Sem rede."""
import unittest
from unittest import mock

from datakit.common.model import CameraKind
from datakit.sources import der_pe

TD = '<td style="padding: 8px 6px;"{}>{}</td>'


def _row(cells):
    return "<tr>" + "".join(cells) + "</tr>"


LOMBADAS = (
    "<html><body><table><thead><tr>"
    + "".join(f"<th>{h}</th>" for h in ("EQUIPAMENTO", "PROCESSADOR", "SÉRIE", "TIPO", "ENDEREÇO", "SENTIDO",
                                        "MUNICÍPIO", "VELOCIDADE", "LATITUDE", "LONGITUDE"))
    + "</tr></thead><tbody>"
    # equipamento com duas faixas: linha completa (rowspan=2) e linha de continuação com 2 células
    + _row([TD.format(' rowspan="2"', '<a href="#">📍 DERPE1348</a>'), TD.format("", "1348-1"),
            TD.format(' rowspan="2"', "R15086"), TD.format(' rowspan="2"', "CEV"),
            TD.format(' rowspan="2"', "Rodovia BR-232 - Km 10+700"), TD.format("", "Recife"),
            TD.format(' rowspan="2"', "Jaboatão dos Guararapes"), TD.format(' rowspan="2"', "60 km/h"),
            TD.format(' rowspan="2"', "-8.0828050"), TD.format(' rowspan="2"', "-34.996406000")])
    + _row([TD.format("", "1348-2"), TD.format("", "Recife")])
    # redutor, 40 km/h, uma faixa só
    + _row([TD.format("", "DERPE2001"), TD.format("", "2001-1"), TD.format("", "R1"), TD.format("", "REV"),
            TD.format("", "Rodovia PE-060 - Km 2+000"), TD.format("", "Cabo"), TD.format("", "Ipojuca"),
            TD.format("", "40 km/h"), TD.format("", "-8.3000000"), TD.format("", "-35.0300000")])
    # tipo desconhecido, sem velocidade e coordenada fora do formato: ficam de fora
    + _row([TD.format("", "DERPE2002"), TD.format("", "2002-1"), TD.format("", "R2"), TD.format("", "CMV"),
            TD.format("", "x"), TD.format("", "y"), TD.format("", "z"), TD.format("", "60 km/h"),
            TD.format("", "-8.4"), TD.format("", "-35.4")])
    + _row([TD.format("", "DERPE2003"), TD.format("", "2003-1"), TD.format("", "R3"), TD.format("", "CEV"),
            TD.format("", "x"), TD.format("", "y"), TD.format("", "z"), TD.format("", ""),
            TD.format("", "&nbsp;"), TD.format("", "")])
    + "</tbody></table></body></html>"
)

MISTOS = (
    "<table><tr><td colspan='3'>EQUIPAMENTOS MISTOS</td></tr>"
    "<tr><td>EQP</td><td>ENDEREÇO</td><td>COORDENADAS</td></tr>"
    "<tr><td>8336</td><td>Rodovia PE-08 Km 14,460</td><td>-8.162896,-34.930979</td></tr>"
    "<tr><td>8337</td><td>Rodovia PE-08 Km 14,460</td><td>-8.163227,-34.931028</td></tr>"
    "<tr><td>8360</td><td>Rodovia PE-01 Km 18,030</td><td>-7.934459,-34.824247</td></tr>"
    "<tr><td>8361</td><td>Rodovia PE-01 Km 18,030</td><td>-7.934459,-34.824247</td></tr></table>"
)


class Parse(unittest.TestCase):
    def test_lombadas_one_point_per_equipment_with_the_limit_and_no_continuation_rows(self):
        self.assertEqual([(-8.082805, -34.996406, 60), (-8.3, -35.03, 40)], der_pe.parse_lombadas(LOMBADAS))

    def test_lombadas_page_without_the_table_gives_nothing(self):
        self.assertEqual([], der_pe.parse_lombadas("<html><h1>Página não encontrada</h1></html>"))

    def test_mistos_skip_header_and_have_no_limit(self):
        got = der_pe.parse_mistos(MISTOS)
        self.assertEqual(4, len(got))
        self.assertEqual((-8.162896, -34.930979, None), got[0])


class Load(unittest.TestCase):
    def _get(self, pages):
        def get(url, *a, **k):
            body = pages[url]
            if isinstance(body, Exception):
                raise body
            return body.encode()
        return get

    def test_load_merges_both_lists_and_drops_the_repeated_point(self):
        pages = {der_pe.URL: LOMBADAS, der_pe.MISTOS_URL: MISTOS}
        with mock.patch.object(der_pe, "get_bytes", self._get(pages)):
            cams, limits = der_pe.load("data/raw")
        self.assertEqual([], limits)
        self.assertEqual(2 + 3, len(cams))    # 8360 e 8361 têm a mesma coordenada
        self.assertTrue(all(c.kind == CameraKind.FIXED and c.source == "DER-PE" and c.active for c in cams))
        self.assertEqual([60, 40, None, None, None], [c.limit_kmh for c in cams])
        self.assertTrue(all(c.direction_deg is None for c in cams))

    def test_load_respects_the_bbox(self):
        pages = {der_pe.URL: LOMBADAS, der_pe.MISTOS_URL: MISTOS}
        with mock.patch.object(der_pe, "get_bytes", self._get(pages)):
            cams, _ = der_pe.load("data/raw", bbox=(-8.1, -35.1, -8.0, -34.9))
        self.assertEqual({(-8.082805, -34.996406)}, {(c.lat, c.lng) for c in cams})

    def test_stable_address_failing_falls_back_to_the_menu_address(self):
        pages = {der_pe.URL: OSError("404"), der_pe.FALLBACKS[der_pe.ID_LOMBADAS]: LOMBADAS,
                 der_pe.MISTOS_URL: MISTOS}
        with mock.patch.object(der_pe, "get_bytes", self._get(pages)):
            cams, _ = der_pe.load("data/raw")
        self.assertEqual(5, len(cams))

    def test_page_without_the_table_at_both_addresses_raises(self):
        pages = {der_pe.URL: "<html>reorganizado</html>", der_pe.FALLBACKS[der_pe.ID_LOMBADAS]: "<html/>",
                 der_pe.MISTOS_URL: MISTOS}
        with mock.patch.object(der_pe, "get_bytes", self._get(pages)):
            with self.assertRaises(RuntimeError) as ctx:
                der_pe.load("data/raw")
        self.assertIn("1382", str(ctx.exception))
        self.assertIn("sem a tabela", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
