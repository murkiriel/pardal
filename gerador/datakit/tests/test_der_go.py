"""DER-GO / GOINFRA: lista de equipamentos ativos em PDF e malha rodoviária em KMZ (sources/der_go.py).

As linhas de teste são recortes da lista de 03/11/2026 (publicação oficial da GOINFRA), com as colunas
mais juntas que no PDF; a malha é um KML mínimo no mesmo desenho do KMZ do mapa rodoviário.
"""
import io
import os
import shutil
import tempfile
import unittest
import zipfile
from unittest import mock

from datakit import failures, source_cache
from datakit.common.model import Camera, CameraKind
from datakit.context import BuildContext, SourceData
from datakit.sources import der_go

HEADER = ("   Tipo   Cód. Equipamento   Faixa   Sentido - CD   Número de Série   Local   Complemento   Sentido   "
          "Municipio   Código SRE   Latitude   Longitude   Velocidade   Data Autorização")
_TAIL = "09/04/2026   09/04/2026   28/02/2027   Lote 05 - 2025005   1   84541289   ET060L5001"


def _row(kind, code, lane, cd, serial, road, km, where, city, sre, lat, lng, kmh):
    return f"{kind}   {code}   {lane}   {cd}   {serial}   {road}   {km}   {where}   {city}   {sre}   {lat}   {lng}   {kmh}   {_TAIL}"


R1 = _row("RADAR FIXO", "060L5R001", "1C", "Crescente", "118690177", "GO-060", "KM 225+332M",
          "Israelândia/Arenópolis", "IPORA", "060EGO0230", "-16412382", "-51179879", "60")
R2 = _row("RADAR FIXO", "060L5R002", "1D", "Decrescente", "118690138", "GO-060", "KM 225+599M",
          "Arenópolis/Israelândia", "IPORA", "060EGO0240", "-16412542", "-51182319", "60")
# duas faixas do mesmo equipamento: mesma coordenada
L1 = _row("LOMBADA ELET", "164L5B009", "1C", "Crescente", "118690196", "GO-164", "KM 222+636M",
          "Entr. BR-452/Santa Helena", "SANTA HELENA DE GOIAS", "164EGO0193", "-17835219", "-50572096", "40")
L2 = _row("LOMBADA ELET", "164L5B010", "2C", "Crescente", "118690220", "GO-164", "KM 222+636M",
          "Entr. Br-452/Santa Helena", "SANTA HELENA DE GOIAS", "164EGO0193", "-17835219", "-50572096", "40")
# faixas da mesma pista a 11 m uma da outra (na lista chegam a 33 m)
P1 = _row("RADAR FIXO", "347L1R101", "1C", "Crescente", "118690001", "GO-347", "KM 55+917M",
          "Mozarlândia/Entr. GO-164", "MOZARLANDIA", "347EGO0070", "-14000000", "-50000000", "60")
P2 = _row("RADAR FIXO", "347L1R102", "2C", "Crescente", "118690002", "GO-347", "KM 55+917M",
          "Mozarlândia/Entr. GO-164", "MOZARLANDIA", "347EGO0070", "-14000100", "-50000000", "60")
# coordenada com ponto de milhar, série com letras, SRE de "UGO"
DOTTED = _row("LOMBADA ELET", "050L4B068", "1C", "Crescente", "FSC110-0852", "GO-050", "KM 008+084M",
              "PALMEIRAS DE GOIÁS-GO/PALMINÓPOLIS-GO", "PALMEIRAS DE GOIAS", "050UGO1120", "-16.791.786",
              "-49.940.919", "60")
# a edição de 2025 trazia a coordenada em decimal
DECIMAL = _row("RADAR FIXO", "070L1R001", "1C", "Crescente", "516302641", "GO-070", "KM 152+250m",
               "ENTR. BR.070 / BRITÂNIA", "BRITANIA", "070EGO0090", "-16.205504", "-49.596905", "80")
# SRE com 3 dígitos no fim, "km" minúsculo sem espaço e sem o "KM"
SHORT_SRE = _row("RADAR FIXO", "221L5R104", "1C", "Crescente", "118690648", "GO-221", "KM 167+930M",
                 "Caiapônia/Doverlândia", "DOVERLANDIA", "221EGO095", "-16719038", "-52312140", "40")
NO_KM_WORD = _row("LOMBADA ELET", "174L5B028", "1C", "Crescente", "118690319", "GO-174", "406+080M",
                  "Amorinópolis/Iporá", "IPORA", "174EGO0310", "-16448265", "-51119225", "40")
# faixa 1D com sentido "Crescente": a lista se contradiz
CONTRADICTION = _row("LOMBADA ELET", "060L4B080", "1D", "Crescente", "FSC110-0859", "GO-060", "km 090+637",
                     "S. LUIS DE MONTES BELOS/NAZÁRIO", "TURVANIA", "060EGO0105", "-16607430", "-50134580", "40")
# coordenadas quebradas da edição de 03/11/2026
SAME_LAT_LNG = _row("LOMBADA ELET", "010L3B185", "1C", "Crescente", "5001", "GO-010", "KM 004+000M",
                    "GOIÂNIA/SENADOR CANEDO", "SENADOR CANEDO", "010EGO0050", "-16615076", "-16615076", "40")
NO_SIGN = _row("LOMBADA ELET", "070L4B031", "1C", "Crescente", "5002", "GO-070", "KM 020+000M",
               "INHUMAS/GOIÂNIA", "INHUMAS", "070EGO0050", "-16425392", "49465963", "40")
WRONG_LIMIT = _row("LOMBADA ELET", "139L3B031", "1D", "Decrescente", "D1362", "GO-139", "KM 171+400M",
                   "VIANÓPOLIS / SÃO MIGUEL DO PASSA QUATRO", "SAO MIGUEL DO PASSA QUATRO", "139EGO0120",
                   "-17045226", "-48664002", "1362")
ODD_LIMIT = _row("LOMBADA ELET", "080L1B001", "1C", "Crescente", "118690276", "GO-080", "KM 112+76M",
                 "Jaraguá/Goianésia", "JARAGUA", "080EGO0230", "-15721817", "-49316912", "39")
BROKEN = "LOMBADA ELET   999L1B001   1C   Crescente   texto sem coordenadas nem SRE"


def lines(*rows):
    return [HEADER, "", "Data de emissão: 03/11/2026", *rows]


class Coordinates(unittest.TestCase):
    def test_both_coordinate_formats(self):
        self.assertAlmostEqual(der_go.parse_coordinate("-16412382"), -16.412382)      # micrograus, 03/11/2026
        self.assertAlmostEqual(der_go.parse_coordinate("-16.412382"), -16.412382)     # decimal, 11/2025
        self.assertAlmostEqual(der_go.parse_coordinate("-16,412382"), -16.412382)
        self.assertAlmostEqual(der_go.parse_coordinate("-16.791.786"), -16.791786)    # ponto de milhar
        self.assertAlmostEqual(der_go.parse_coordinate("49465963"), 49.465963)
        self.assertIsNone(der_go.parse_coordinate("abc"))
        self.assertIsNone(der_go.parse_coordinate(""))

    def test_limit_is_plausible_or_none(self):
        self.assertEqual([der_go.parse_limit(v) for v in ("20", "40", "60", "120", "110")], [20, 40, 60, 120, 110])
        self.assertEqual([der_go.parse_limit(v) for v in ("39", "1362", "10", "130", "0", "x")], [None] * 6)

    def test_sre_without_the_leading_zero_of_the_stretch(self):
        self.assertEqual(der_go.normalize_sre("221EGO095"), "221EGO0095")
        self.assertEqual(der_go.normalize_sre("060EGO0230"), "060EGO0230")
        self.assertEqual(der_go.normalize_sre("050UGO1120"), "050UGO1120")


class ParseList(unittest.TestCase):
    def test_reads_radars_and_lombadas_in_both_coordinate_formats(self):
        rows, discards, total = der_go.parse_list(lines(R1, L1, DOTTED, DECIMAL, SHORT_SRE))
        self.assertEqual((len(rows), discards, total), (5, [], 5))
        by_code = {r.code: r for r in rows}
        self.assertEqual((by_code["060L5R001"].lat, by_code["060L5R001"].lng), (-16.412382, -51.179879))
        self.assertEqual((by_code["050L4B068"].lat, by_code["050L4B068"].lng), (-16.791786, -49.940919))
        self.assertEqual((by_code["070L1R001"].lat, by_code["070L1R001"].lng), (-16.205504, -49.596905))
        self.assertEqual(by_code["221L5R104"].sre, "221EGO0095")
        self.assertEqual((by_code["060L5R001"].road, by_code["060L5R001"].limit, by_code["060L5R001"].increasing),
                         ("GO-060", 60, True))
        self.assertEqual(by_code["164L5B009"].lane, "1C")

    def test_broken_coordinates_and_lines_are_discarded_with_the_reason(self):
        rows, discards, total = der_go.parse_list(lines(R1, SAME_LAT_LNG, NO_SIGN, BROKEN, R2))
        self.assertEqual([r.code for r in rows], ["060L5R001", "060L5R002"])
        self.assertEqual(total, 5)
        self.assertEqual([reason for reason, _ in discards],
                         [der_go.OUTSIDE, der_go.OUTSIDE, der_go.UNREAD])
        self.assertIn("010L3B185 1C", discards[0][1])
        self.assertIn("070L4B031 1C", discards[1][1])

    def test_limit_out_of_range_keeps_the_radar_without_limit(self):
        rows, discards, _ = der_go.parse_list(lines(WRONG_LIMIT, ODD_LIMIT, R1))
        self.assertEqual(discards, [])
        self.assertEqual([r.limit for r in rows], [None, None, 60])

    def test_lane_letter_that_contradicts_the_direction_leaves_it_unknown(self):
        rows, _, _ = der_go.parse_list(lines(CONTRADICTION, R2))
        self.assertEqual([r.increasing for r in rows], [None, False])

    def test_km_with_and_without_the_word(self):
        self.assertEqual(der_go.printed_km("KM 225+332M   Israelândia"), 225.332)
        self.assertEqual(der_go.printed_km("km89+469m"), 89.469)
        self.assertEqual(der_go.printed_km("KM 39 + 806M"), 39.806)
        self.assertEqual(der_go.printed_km("406+080M   Amorinópolis/Iporá"), 406.08)
        self.assertIsNone(der_go.printed_km("TURVÂNIA/S. LUÍS DE MONTES BELOS"))
        rows, _, _ = der_go.parse_list(lines(NO_KM_WORD))
        self.assertEqual(der_go.printed_km(rows[0].km_text), 406.08)

    def test_a_list_with_a_different_layout_fails_instead_of_publishing_a_piece(self):
        with self.assertRaises(RuntimeError) as ctx:
            der_go.read_list("\n".join(lines(R1, R2)))     # só 2 linhas lidas: abaixo de MIN_ROWS
        self.assertIn("outro formato", str(ctx.exception))
        with mock.patch.object(der_go, "MIN_ROWS", 1):
            rows, discards = der_go.read_list("\n".join(lines(R1, R2)))
            self.assertEqual((len(rows), discards), (2, []))
            with self.assertRaises(RuntimeError):          # 1 de 4 não lida: acima de MAX_UNREAD
                der_go.read_list("\n".join(lines(R1, R2, L1, BROKEN)))
        # a edição de 11/2025 tinha outra ordem de colunas: nenhuma linha bate
        old = "Lote 1   LOMBADA ELET   KB16410-1   1   516302356   GO 164   KM 557+500M   FAINA/ARAGUAPAZ   Crescente"
        with mock.patch.object(der_go, "MIN_ROWS", 1):
            with self.assertRaises(RuntimeError):
                der_go.read_list(old)


class JoinLanes(unittest.TestCase):
    def points(self, *rows):
        parsed, _, _ = der_go.parse_list(lines(*rows))
        return der_go.join_lanes(parsed)

    def test_lanes_of_the_same_spot_and_direction_become_one_radar(self):
        pts = self.points(L1, L2)
        self.assertEqual(len(pts), 1)
        self.assertEqual((pts[0].lat, pts[0].lng, pts[0].limit, pts[0].lanes), (-17.835219, -50.572096, 40, 2))

    def test_lanes_a_few_meters_apart_are_joined_at_the_mean_position(self):
        pts = self.points(P1, P2)
        self.assertEqual(len(pts), 1)
        self.assertAlmostEqual(pts[0].lat, -14.00005, places=6)

    def test_one_radar_per_direction_even_at_the_same_coordinate(self):
        both = _row("RADAR FIXO", "060L5R003", "1D", "Decrescente", "1", "GO-060", "KM 225+332M", "x/y", "IPORA",
                    "060EGO0230", "-16412382", "-51179879", "60")
        pts = self.points(R1, both)
        self.assertEqual(sorted(p.increasing for p in pts), [False, True])
        self.assertEqual(len(self.points(R1, R2)), 2)

    def test_same_direction_far_apart_or_on_another_road_stays_separate(self):
        far = _row("RADAR FIXO", "060L5R009", "1C", "Crescente", "9", "GO-060", "KM 230+000M", "x/y", "IPORA",
                   "060EGO0230", "-16415000", "-51179879", "60")
        self.assertEqual(len(self.points(R1, far)), 2)
        other_road = _row("RADAR FIXO", "070L5R001", "1C", "Crescente", "8", "GO-070", "KM 1+000M", "x/y", "IPORA",
                          "070EGO0230", "-16412382", "-51179879", "60")
        self.assertEqual(len(self.points(R1, other_road)), 2)

    def test_the_most_common_limit_wins_and_the_lowest_breaks_the_tie(self):
        a = _row("RADAR FIXO", "1", "1C", "Crescente", "1", "GO-060", "KM 1+000M", "x", "C", "060EGO0230",
                 "-16412382", "-51179879", "80")
        b = _row("RADAR FIXO", "2", "2C", "Crescente", "2", "GO-060", "KM 1+000M", "x", "C", "060EGO0230",
                 "-16412382", "-51179879", "60")
        self.assertEqual(self.points(a, b)[0].limit, 60)
        self.assertEqual(self.points(a, a, b)[0].limit, 80)
        self.assertIsNone(self.points(ODD_LIMIT)[0].limit)


PAGE = """<html><head><title>Relatório de Equipamentos</title></head><body>
<a href="https://goias.gov.br/goinfra/wp-content/uploads/sites/77/2026/07/formulario_suspensao_dirigir_v2.pdf">Formulário</a>
<ul><li>vigentes a partir de abril de 2026, <strong><a href="https://goias.gov.br/goinfra/wp-content/uploads/sites/77/2026/11/Lista_de_Equipamento_03_11_2026.xlsx-Equipamentos-Ativos.pdf">clique aqui</a></strong>.</li>
<li>vigentes até 30/05/2026, <a href="https://goias.gov.br/goinfra/wp-content/uploads/sites/77/2026/09/Equipamentos_Fiscalizacao_Ativos_11_2025-Publicacao_links_atualizados_completo.xlsx-Planilha-1.pdf">clique aqui</a>.</li></ul>
<a href="https://goias.gov.br/goinfra/wp-content/uploads/sites/77/2026/08/Despacho_795_2025.pdf">clique aqui</a>
</body></html>"""


class PageLinks(unittest.TestCase):
    def test_current_list_is_picked_over_the_old_edition_and_the_other_pdfs(self):
        self.assertEqual(der_go.pdf_url(PAGE),
                         "https://goias.gov.br/goinfra/wp-content/uploads/sites/77/2026/11/"
                         "Lista_de_Equipamento_03_11_2026.xlsx-Equipamentos-Ativos.pdf")

    def test_newer_edition_wins_whatever_the_order_on_the_page(self):
        new = "https://goias.gov.br/goinfra/wp-content/uploads/sites/77/2026/12/Lista_de_Equipamento_15_12_2026.xlsx-Equipamentos-Ativos.pdf"
        html = PAGE.replace("</body>", f'<a href="{new}">nova</a></body>')
        self.assertEqual(der_go.pdf_url(html), new)
        first = PAGE.replace("<ul>", f'<a href="{new}">nova</a><ul>')
        self.assertEqual(der_go.pdf_url(first), new)

    def test_does_not_depend_on_the_exact_file_name(self):
        html = '<a href="/goinfra/wp-content/uploads/sites/77/2027/02/Equipamentos-ativos-fev.pdf">x</a>' + PAGE
        self.assertEqual(der_go.pdf_url(html),
                         "https://goias.gov.br/goinfra/wp-content/uploads/sites/77/2027/02/Equipamentos-ativos-fev.pdf")

    def test_no_list_gives_none(self):
        self.assertIsNone(der_go.pdf_url("<html><a href='/x/Despacho.pdf'>a</a><a href='/x/lista_equipamentos.xlsx'>b</a></html>"))
        self.assertIsNone(der_go.pdf_url(""))

    def test_kmz_link_from_the_map_page_then_the_known_address(self):
        html = '<a href="https://cdn.goinfra.go.gov.br/site/assets/paginas/images/SRE-GO_2026.kmz">mapa</a>'
        self.assertEqual(der_go.kmz_urls(html), ["https://cdn.goinfra.go.gov.br/site/assets/paginas/images/SRE-GO_2026.kmz",
                                                  der_go.MAP_KMZ])
        self.assertEqual(der_go.kmz_urls("<html></html>"), [der_go.MAP_KMZ])
        self.assertEqual(der_go.kmz_urls(f'<a href="{der_go.MAP_KMZ}">x</a>'), [der_go.MAP_KMZ])


def _placemark(sre, k0, k1, *paths):
    geoms = "".join("<LineString><coordinates>" + " ".join(f"{lng},{lat},800" for lat, lng in p)
                    + "</coordinates></LineString>" for p in paths)
    data = "".join(f'<Data name="{k}"><value>{v}</value><displayName>{k}</displayName></Data>'
                   for k, v in (("sre", sre), ("go", "GO-060"), ("km_inicial", k0), ("km_final", k1)))
    return f"<Placemark><name>{sre}</name><ExtendedData>{data}</ExtendedData><MultiGeometry>{geoms}</MultiGeometry></Placemark>"


def _kml(*placemarks):
    return ('<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><Folder>'
            + "".join(placemarks) + "</Folder></Document></kml>")


# trecho do km 225,000 ao 225,556 desenhado de norte para sul, 2 m a leste do R1 e do R2 (060EGO0230 e 060EGO0240
# são trechos seguidos: o mesmo desenho serve para os dois)
SOUTH = [(-16.4100, -51.1799), (-16.4150, -51.1799)]


class Network(unittest.TestCase):
    def test_kml_to_lines_with_km_per_vertex(self):
        net = der_go.parse_network(_kml(_placemark("060EGO0230", "225.0", "225.556", SOUTH)))
        line = net["060EGO0230"][0]
        self.assertEqual((line.m_min, round(line.m_max, 3)), (225.0, 225.556))
        self.assertEqual(line.pts[0], (-16.41, -51.1799))     # lat, lng (o KML guarda lng,lat)

    def test_placemark_without_sre_or_km_or_line_is_skipped(self):
        net = der_go.parse_network(_kml(
            _placemark("", "1", "2", SOUTH), _placemark("A", "5", "5", SOUTH), _placemark("B", "x", "9", SOUTH),
            _placemark("C", "1", "2"), _placemark("D", "1", "2", [(-16.4, -51.1)])))
        self.assertEqual(net, {})

    def test_placemark_with_two_lines_splits_the_km_range_by_length(self):
        a = [(-16.40, -51.10), (-16.41, -51.10)]
        b = [(-16.41, -51.10), (-16.43, -51.10)]      # o dobro do comprimento
        net = der_go.parse_network(_kml(_placemark("060EGO0230", "10.0", "13.0", a, b)))
        first, second = net["060EGO0230"]
        self.assertEqual((first.m_min, round(first.m_max, 2)), (10.0, 11.0))
        self.assertEqual((round(second.m_min, 2), round(second.m_max, 2)), (11.0, 13.0))

    def test_kmz_and_plain_kml_are_read(self):
        kml = _kml(_placemark("060EGO0230", "225.0", "225.556", SOUTH))
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("doc.kml", kml)
        self.assertEqual(der_go.kml_from_kmz(buf.getvalue()), kml)
        self.assertEqual(der_go.kml_from_kmz(kml.encode()), kml)


class Direction(unittest.TestCase):
    def cameras(self, rows, net):
        parsed, _, _ = der_go.parse_list(lines(*rows))
        return der_go.cameras_from(parsed, net)

    def net(self, k0="225.0", k1="225.556"):
        return der_go.parse_network(_kml(_placemark("060EGO0230", k0, k1, SOUTH)))

    def test_direction_from_the_kmz_following_the_km_drawn_start_to_end(self):
        cams, far = self.cameras([R1], self.net())
        self.assertEqual((far, [c.direction_deg for c in cams]), ([], [180]))       # crescente: para o sul
        dec = _row("RADAR FIXO", "060L5R005", "1D", "Decrescente", "5", "GO-060", "KM 225+332M", "a/b", "IPORA",
                   "060EGO0230", "-16412382", "-51179879", "60")
        self.assertEqual([c.direction_deg for c in self.cameras([dec], self.net())[0]], [0])

    def test_line_drawn_backwards_in_the_data_still_gives_the_driving_direction(self):
        # km 225,556 -> 225,000 do norte para o sul: o km cresce para o norte
        cams, _ = self.cameras([R1], self.net("225.556", "225.0"))
        self.assertEqual([c.direction_deg for c in cams], [0])

    def test_printed_km_that_only_fits_the_mirrored_position_flips_the_direction(self):
        # trecho de 5,56 km desenhado de sul (km 0) para norte (km 5,56); o radar a 2,2 km do começo, com o km
        # impresso espelhado (3,34): a lista conta o km do outro lado
        net = {"060EGO0230": [der_go.MeasuredLine.from_extent([(-16.10, -49.0), (-16.05, -49.0)], 0.0, 5.56)]}
        row = lambda km: _row("RADAR FIXO", "060L5R001", "1C", "Crescente", "1", "GO-060", km, "a/b", "IPORA",  # noqa: E731
                              "060EGO0230", "-16080000", "-48999700", "60")
        cams = lambda km: [c.direction_deg for c in self.cameras([row(km)], net)[0]]  # noqa: E731
        self.assertEqual((cams("KM 2+220M"), cams("KM 3+340M")), ([0], [180]))
        # km que não bate nem com a posição nem com a espelhada: vale como o trecho foi desenhado
        self.assertEqual(cams("KM 4+500M"), [0])

    def test_sre_missing_from_the_network_keeps_the_radar_without_direction(self):
        cams, far = self.cameras([R2, SHORT_SRE], self.net())          # 060EGO0240 e 221EGO0095 não estão na malha
        self.assertEqual((far, [c.direction_deg for c in cams]), ([], [None, None]))

    def test_without_the_network_the_radars_have_no_direction_and_nothing_is_dropped(self):
        cams, far = self.cameras([R1, R2], {})
        self.assertEqual((far, [c.direction_deg for c in cams]), ([], [None, None]))

    def test_contradictory_direction_in_the_list_gives_no_direction(self):
        net = der_go.parse_network(_kml(_placemark("060EGO0105", "90.0", "91.0",
                                                   [(-16.6000, -50.1346), (-16.6100, -50.1346)])))
        self.assertEqual([c.direction_deg for c in self.cameras([CONTRADICTION], net)[0]], [None])

    def test_point_far_from_its_own_stretch_is_dropped(self):
        far_row = _row("RADAR FIXO", "060L5R001", "1C", "Crescente", "1", "GO-060", "KM 225+332M", "a/b", "IPORA",
                       "060EGO0230", "-16412382", "-50179879", "60")      # 1 grau de longitude a leste (typo)
        cams, far = self.cameras([far_row], self.net())
        self.assertEqual(cams, [])
        self.assertEqual([reason for reason, _ in far], [der_go.FAR])

    def test_wrong_sre_on_the_right_road_keeps_the_radar_and_the_direction_only_if_the_km_agrees(self):
        net = self.net()
        net.update(der_go.parse_network(_kml(_placemark("060EGO0300", "300.0", "300.556", SOUTH))))
        other = lambda km: _row("RADAR FIXO", "060L5R001", "1C", "Crescente", "1", "GO-060", km, "a/b", "IPORA",  # noqa: E731
                                "060EGO0230", "-16412382", "-51179879", "60")
        # o ponto está a 2 m de 060EGO0300 e a 1,5 km da 060EGO0230: o SRE da lista não é o do trecho
        net["060EGO0230"] = [der_go.MeasuredLine.from_extent([(-16.30, -51.17), (-16.31, -51.17)], 225.0, 225.5)]
        near_other = [c.direction_deg for c in self.cameras([other("KM 300+265M")], net)[0]]
        no_km = [c.direction_deg for c in self.cameras([other("KM 12+000M")], net)[0]]
        self.assertEqual((near_other, no_km), ([180], [None]))
        cams, far = self.cameras([other("KM 12+000M")], net)
        self.assertEqual((len(cams), far), (1, []))

    def test_cameras_are_fixed_active_der_go_with_the_lombada_as_fixed(self):
        cams, _ = self.cameras([R1, L1, L2], {})
        self.assertTrue(all(c.kind == CameraKind.FIXED and c.source == "DER-GO" and c.active for c in cams))
        self.assertEqual(len(cams), 2)      # as duas faixas da lombada viram uma


FIXTURE = [R1, R2, L1, L2, DOTTED, SAME_LAT_LNG, NO_SIGN, WRONG_LIMIT]


class FetchAndBackup(unittest.TestCase):
    """O build usa a última cópia boa (a de antes da troca de fonte tem o mesmo formato: SourceData) quando a
    página, o PDF ou o KMZ falham."""

    def setUp(self):
        self.raw = tempfile.mkdtemp()
        self._f, self._w = list(failures._FAILURES), list(failures._WARNINGS)
        self._d = dict(source_cache._DATES)
        # cópia da leitura anterior, no tempo do ArcGIS: um radar que a lista nova não tem
        self.old = Camera(-16.5, -49.5, CameraKind.FIXED, 60, "DER-GO", True, direction_deg=90)
        source_cache.load("DER-GO", self.raw, lambda: SourceData(cameras=[self.old]), SourceData())
        self.page = mock.Mock(status_code=200, url=der_go.PAGE, text=PAGE)

    def tearDown(self):
        failures._FAILURES[:], failures._WARNINGS[:] = self._f, self._w
        source_cache._DATES.clear()
        source_cache._DATES.update(self._d)
        shutil.rmtree(self.raw, ignore_errors=True)

    def official(self, **patches):
        defaults = dict(
            get_response=mock.Mock(return_value=self.page),
            get_bytes=mock.Mock(return_value=b"%PDF"),
            pdf_layout_text=mock.Mock(return_value="\n".join(lines(*FIXTURE))),
            load_network=mock.Mock(return_value=der_go.parse_network(_kml(_placemark("060EGO0230", "225.0", "225.556", SOUTH)))),
        )
        defaults.update(patches)
        with mock.patch.multiple(der_go, **defaults), mock.patch.object(der_go, "MIN_ROWS", 1):
            return BuildContext(self.raw, sources={"DER-GO": der_go}).official()["DER-GO"]

    def new_failures(self):
        return failures._FAILURES[len(self._f):]

    def new_warnings(self):
        return failures._WARNINGS[len(self._w):]

    def test_good_read_replaces_the_old_copy(self):
        data = self.official()
        # R1 e R2 (sentidos opostos), a lombada de 2 faixas e a de ponto de milhar; os 3 de coordenada quebrada saem
        self.assertEqual(len(data.cameras), 5)
        self.assertEqual((self.new_failures(), self.new_warnings()), ([], []))
        copy = source_cache._read(source_cache.path_for(self.raw, "DER-GO"))
        self.assertEqual(len(copy[0].cameras), 5)     # a cópia passou a ser a da fonte nova

    def test_page_down_uses_the_old_copy_with_a_warning(self):
        data = self.official(get_response=mock.Mock(side_effect=ConnectionError("fora do ar")))
        self.assertEqual(data.cameras, [self.old])
        self.assertEqual(self.new_failures(), [])
        self.assertEqual(len(self.new_warnings()), 1)
        self.assertIn("DER-GO: atualização ConnectionError; usada a cópia de", self.new_warnings()[0])

    def test_page_without_the_list_link_uses_the_copy(self):
        page = mock.Mock(status_code=200, url=der_go.PAGE, text="<html>sem link</html>")
        data = self.official(get_response=mock.Mock(return_value=page))
        self.assertEqual(data.cameras, [self.old])
        self.assertEqual(self.new_failures(), [])
        self.assertIn("usada a cópia de", self.new_warnings()[0])

    def test_pdf_in_another_layout_uses_the_copy(self):
        data = self.official(pdf_layout_text=mock.Mock(return_value="texto qualquer\noutra tabela"))
        self.assertEqual(data.cameras, [self.old])
        self.assertEqual(self.new_failures(), [])
        self.assertIn("usada a cópia de", self.new_warnings()[0])

    def test_network_down_uses_the_copy_instead_of_publishing_radars_without_direction(self):
        data = self.official(load_network=mock.Mock(side_effect=RuntimeError("malha estadual (KMZ) não lida")))
        self.assertEqual(data.cameras, [self.old])
        self.assertEqual(self.new_failures(), [])
        self.assertIn("usada a cópia de", self.new_warnings()[0])

    def test_without_copy_the_failure_is_recorded(self):
        os.remove(source_cache.path_for(self.raw, "DER-GO"))
        data = self.official(get_response=mock.Mock(side_effect=ConnectionError("fora do ar")))
        self.assertEqual(data.cameras, [])
        self.assertEqual(len(self.new_failures()), 1)
        self.assertTrue(self.new_failures()[0].startswith("DER-GO: ConnectionError"))

    def test_the_network_is_read_from_the_page_link_or_the_known_address(self):
        kml = _kml(_placemark("060EGO0230", "225.0", "225.556", SOUTH))
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("doc.kml", kml)
        calls = []

        def fake_bytes(url, **kw):
            calls.append(url)
            if url.endswith("SRE-GO_2026.kmz"):
                raise ConnectionError("fora")
            return buf.getvalue()
        page = mock.Mock(status_code=200, text='<a href="https://cdn.example/SRE-GO_2026.kmz">x</a>')
        with mock.patch.object(der_go, "get_response", return_value=page), \
                mock.patch.object(der_go, "get_bytes", side_effect=fake_bytes):
            net = der_go.load_network()
        self.assertEqual(list(net), ["060EGO0230"])
        self.assertEqual(calls, ["https://cdn.example/SRE-GO_2026.kmz", der_go.MAP_KMZ])


if __name__ == "__main__":
    unittest.main()
