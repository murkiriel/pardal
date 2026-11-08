"""Testes puros das fontes de 2026-11-08 (AGETO-TO, Detran-MA, DER-SE, SEINFRA-BA, Transalvador,
SEMTRAN Porto Velho) e da reserva da CET pelo CSV do GitHub. Os textos são trechos das
publicações reais (o dos PDFs, como o pypdf os extrai).

    python -m unittest discover -s datakit/tests -t .
"""
import json
import os
import tempfile
import unittest
from datetime import date
from unittest import mock

from datakit.common import CameraKind
from datakit.sources import ageto_to, cet_sp, der_se, detran_ma, seinfra_ba, semtran_pvh, transalvador


def _rows(cams):
    return [(c.lat, c.lng, c.kind, c.limit_kmh, c.source, c.active) for c in cams]


class AgetoTo(unittest.TestCase):
    TEXT = (
        "LOCAL Km COORDENADAS MUNICÍPIO TIPO DE \nEQUIPAMENTO VELOC. FAIXAS N° Série Nº INMETRO\n"
        "TO-050  367,5 -12.641756, -47.119498 ARRAIAS BARREIRA ELETRÔNICA 60 2 0001 15.009.069\n"
        "TO-445 12,1 -9.673411, -48.389631 MIRACEMA DO \nTOCANTINS BARREIRA ELETRÔNICA 50 2 0014 00.000.369\n"
        "TO-050 17,4 -10.333256, -48.298925 PALMAS RADAR MISTO 60 2 0006 15.009.071\n"
        "TO-080 56,5 -10.132743, -48.849219PARAÍSO DO TOCANTINS RADAR FIXO 80 2 D0246 00.000.817\n"
        "TO-010    709      -5.70112° -48.140744°     ARAGUATINS          RADAR FIXO          80       2\n"
        "TO-080   119,2    -9.8140121 -49.20464                           RADAR FIXO          60       2\n"
        "TO-050 17,4 -10.333256, -48.298925 PALMAS RADAR MISTO 60 2 0006 15.009.071\n"   # repetido
    )

    def test_reads_every_row_layout(self):
        """Município quebrado em duas linhas, colado na longitude ou ausente, coordenada com "°" e
        sem vírgula: todos entram; barreira eletrônica e radar misto também medem velocidade."""
        self.assertEqual(_rows(ageto_to.parse(self.TEXT)), [
            (-12.641756, -47.119498, CameraKind.FIXED, 60, "AGETO-TO", True),
            (-9.673411, -48.389631, CameraKind.FIXED, 50, "AGETO-TO", True),
            (-10.333256, -48.298925, CameraKind.FIXED, 60, "AGETO-TO", True),
            (-10.132743, -48.849219, CameraKind.FIXED, 80, "AGETO-TO", True),
            (-5.70112, -48.140744, CameraKind.FIXED, 80, "AGETO-TO", True),
            (-9.814012, -49.20464, CameraKind.FIXED, 60, "AGETO-TO", True),
        ])

    def test_bbox(self):
        self.assertEqual(len(ageto_to.parse(self.TEXT, bbox=(-11.0, -49.0, -9.0, -48.0))), 3)

    def test_pdf_url_is_the_general_list(self):
        page = ('<a href="https://central.to.gov.br/download/482946"><i>file_open</i> 1 - CEV 003 - TO 030.pdf</a>'
                '<a href="https://central.to.gov.br/download/499999"> <i>file_open</i>\n LISTA RADARES - AGETO.rev02.pdf</a>')
        self.assertEqual(ageto_to.pdf_url(page), "https://central.to.gov.br/download/499999")
        self.assertEqual(ageto_to.pdf_url("<html></html>"), ageto_to.PDF_FALLBACK)


class DetranMa(unittest.TestCase):
    TEXT = (
        "CÓDIGO \nEQUIPAMENTO\nNº DE \nSÉRIE MARCA / MODELO ENDEREÇO SENTIDO MUNICÍPIO TIPO VELOCIDADE INMETRO LATITUDE LONGITUDE\n"
        "MA301R L0533 FOCALLE / F-LIN MA 203 - KM 012 + 400 - SÃO JOSÉ DE RIBAMAR - MA LESTE/OESTE S. J. DE RIBAMAR "
        "FIXO 60 Km/h 00.001.002  -2.478711° -44.211409°\n"
        "MA301R L0533 FOCALLE / F-LIN MA 203 - KM 012 + 400 - SÃO JOSÉ DE RIBAMAR - MA LESTE/OESTE S. J. DE RIBAMAR "
        "FIXO 60 Km/h 00.001.002  -2.478711° -44.211409°\n"
        "MA349R   L0308   FOCALLE / F-LIN     MA 026 - KM 117+673 - CODO - MA        NORTE/SUL       CODÓ      "
        "FIXO   80 Km/h   00.001.871   -4.499200°   -43.900500°\n"
    )

    def test_one_camera_per_point(self):
        """A lista repete o equipamento por faixa e sentido: um radar por ponto, com o limite."""
        self.assertEqual(_rows(detran_ma.parse(self.TEXT)), [
            (-2.478711, -44.211409, CameraKind.FIXED, 60, "DETRAN-MA", True),
            (-4.4992, -43.9005, CameraKind.FIXED, 80, "DETRAN-MA", True),
        ])

    def test_pdf_url(self):
        page = ('<a href="https://sgp5.detran.ma.gov.br/uploads/midias/outro.pdf">Resolução</a>'
                '<a href="https://sgp5.detran.ma.gov.br/uploads/midias/abc123.pdf" target="_blank">'
                'Fiscaliza&ccedil;&atilde;o Eletr&ocirc;nica</a>')
        self.assertEqual(detran_ma.pdf_url(page), "https://sgp5.detran.ma.gov.br/uploads/midias/abc123.pdf")
        with self.assertRaises(RuntimeError):
            detran_ma.pdf_url("<html></html>")


class DerSe(unittest.TestCase):
    CSV = (
        '"CÓDIGO \nEQUIPAMENTO",RODOVIA,MUNICÍPIO,VELOCIDADE,Localização do Radares,\n'
        'SE001R,SE-100,Aracaju (3105),50Km/h,"https://www.google.com/maps/search/?api=1&query=-11.062782,-37.101103",'
        '"https://www.google.com/maps/search/?api=1&query=-11.062782,-37.101103"\n'
        'SE348L,SE-200,Canindé do São Francisco (3123),40 Km/h,"9° 40\' 0.588"" S 37° 47\' 35.88"" W",'
        '"https://www.google.com.br/maps/place/x/@-9.6668247,-37.7958749,1071m/data=!3m2!1e3!4b1!4m4!3m3!8m2!3d-9.66683!4d-37.7933"\n'
        'SE349R,SE-200,Canindé do São Francisco (3123),50Km/h,"9° 39\' 34.2"" S 37° 47\' 25.764"" W",\n'
        'SE390R,SE-245,Laranjeiras (3171),50Km/h,https://maps.app.goo.gl/3Xpprzq5ULGYqCzXA,\n'
        ',,,,,\n'
    )

    def test_point_from_link_place_dms_and_short_link(self):
        """?query= e !3d!4d dos links; sem link, graus/minutos/segundos; link curto, pelo redirecionamento."""
        target = "https://www.google.com/maps/place/a/@-10.7653,-37.15934,17z/data=!3m1!4b1!4m4!3m3!8m2!3d-10.7653!4d-37.15934"
        cams = der_se.parse(self.CSV, resolve=lambda url: target if url.endswith("3Xpprzq5ULGYqCzXA") else None)
        self.assertEqual([(c.lat, c.lng, c.limit_kmh, c.source) for c in cams], [
            (-11.062782, -37.101103, 50, "DER-SE"),
            (-9.66683, -37.7933, 40, "DER-SE"),
            (-9.6595, -37.790490, 50, "DER-SE"),
            (-10.7653, -37.15934, 50, "DER-SE"),
        ])

    def test_short_link_without_resolver_or_failing_is_left_out(self):
        self.assertEqual(len(der_se.parse(self.CSV)), 3)

        def boom(url):
            raise ConnectionError("fora")
        self.assertEqual(len(der_se.parse(self.CSV, resolve=boom)), 3)

    def test_csv_url_is_the_radares_sheet(self):
        page = ('<iframe title="radares" src="https://docs.google.com/spreadsheets/d/e/2PACX-R/pubhtml?gid=19&#038;single=true">'
                '<iframe title="cameras" src="https://docs.google.com/spreadsheets/d/e/2PACX-C/pubhtml?gid=7">')
        self.assertEqual(der_se.csv_url(page),
                         "https://docs.google.com/spreadsheets/d/e/2PACX-R/pub?gid=19&single=true&output=csv")


class SeinfraBa(unittest.TestCase):
    TEXT = (
        "ID ANO TIPO MARCA MODELO COD. ORGAO Nº SERIE INMETRO VELOCIDADE MUNICIPIO RODOVIA KM LATITUDE LONGITUDE\n"
        "1 2026 RADAR CONSILUX CSC-II FIGCT0005 / FIGCT0006 2100006 13854596 50km SENHOR DO BONFIM BA131 9+500m -10,51770 -40,22950\n"
        "49 2026 RADAR CONSILUX CSC-II FIGCT0125 / FIGCT0126 \n"
        "FIGCT0127 / FIGCT0128 2100023 14812860 60km JUAZEIRO BA210 398+400m -9,45140 -40,51420\n"
        "62 2026 RADAR FISCAL TECNOLOGIA FSCII FIGCT0153 / FIGCT0154 FSCII6228 14751083 60km CAMAÇARI BA099 48+400m -12,60020 38,04553\n"
    )

    def test_rows_split_in_two_lines_and_lost_minus_sign(self):
        self.assertEqual(_rows(seinfra_ba.parse(self.TEXT)), [
            (-10.5177, -40.2295, CameraKind.FIXED, 50, "SEINFRA-BA", True),
            (-9.4514, -40.5142, CameraKind.FIXED, 60, "SEINFRA-BA", True),
            (-12.6002, -38.04553, CameraKind.FIXED, 60, "SEINFRA-BA", True),
        ])

    def test_pdf_url_is_the_newest_list(self):
        page = ('<a href="/infraestrutura/sites/site-seinfra/files/2026-09/Lista-Radar_15-09-2026.pdf">Tabela</a>'
                '<a href="/infraestrutura/sites/site-seinfra/files/2025-12/Lista-Radar_02-12-2025.pdf">Tabela</a>'
                '<a href="/infraestrutura/sites/site-seinfra/files/2026-09/Mapa-Radar_15-09-2026.rar">KML</a>')
        self.assertEqual(seinfra_ba.pdf_url(page),
                         "https://www.ba.gov.br/infraestrutura/sites/site-seinfra/files/2026-09/Lista-Radar_15-09-2026.pdf")


class Transalvador(unittest.TestCase):
    PAGE = (
        'var gmarker3 = new google.maps.Marker({"icon":"https://transonline.salvador.ba.gov.br/georeferenciamento/'
        'markers/radar.png","map":gmap1,"position":new google.maps.LatLng(-12.9285140000, -38.3863510000),'
        '"title":"Endereço de Pórtico"});\ngoogle.maps.event.addListener(gmarker3, \'click\', function(event)'
        '{gmap1infoWindow.setContent(\'<b><p>AV. LUÍS VIANA / SENTIDO AEROPORTO<br/><br/><u>Dados Equipamento:</u>'
        '<br/><br/>FIXO - CONTROLADOR<br/> Série: 0000030040<br/> Aferido em: 05/09/2022<br/> Velocidade: 80 Km</p></b>\');});\n'
        'var gmarker4 = new google.maps.Marker({"icon":"https://x/markers/camera.png","position":'
        'new google.maps.LatLng(-12.9, -38.4)});\n'
        'var gmarker5 = new google.maps.Marker({"icon":"https://x/markers/radar.png","position":'
        'new google.maps.LatLng(-13.0055710000, -38.5282850000)});\n'
        'var gmarker6 = new google.maps.Marker({"icon":"https://x/markers/radar.png","position":'
        'new google.maps.LatLng(-12.9285140000, -38.3863510000)});\n'   # o mesmo ponto do 3
    )

    def test_only_radar_markers_once_each(self):
        self.assertEqual(_rows(transalvador.parse(self.PAGE)), [
            (-12.928514, -38.386351, CameraKind.FIXED, 80, "TRANSALVADOR", True),
            (-13.005571, -38.528285, CameraKind.FIXED, None, "TRANSALVADOR", True),
        ])


class SemtranPvh(unittest.TestCase):
    # como o pypdf extrai: as colunas coladas, a coordenada com pontos de milhar no lugar da vírgula
    TEXT = (
        "TIPONUMERO_SERIECOD_FAIXA_CLIENTENUM_FAIXA NOME_PISTA DATA_AFERICAODATA_V ALIDADEPOSICAO_LATPOSICAO_LONSIGLA"
        "1 FSC110 448 4481 1 Rua Raimundo Cantuária x Rua Buenos Aires17/03/2026 00:0016/03/2027 23:59"
        "-876.651.999.999.999.000-6.387.977.999.999.990.000FX"
        "2 FSC110 448 4482 2 Rua Raimundo Cantuária x Rua Buenos Aires17/03/2026 00:0016/03/2027 23:59"
        "-876.651.999.999.999.000-6.387.977.999.999.990.000FX"
        "3 FSC 4066 40661 1 Avenida Mamore x Avenida Amazonas18/03/2025 00:0017/03/2026 23:59"
        "-873.760.000.000.000.000-6.387.901.000.000.000.000NI"
        "4 FSC 4067 40671 1 Fora x Fora18/03/2026 00:0017/03/2027 23:59"
        "-123.000.000.000.000.000-4.500.000.000.000.000.000FX"
    )

    def test_fixes_the_coordinate_and_uses_the_calibration_validity(self):
        """-876.651.999... -> -8,76652; -6.387.977... -> -63,87978; faixa repetida vira um ponto;
        aferição vencida -> inativo; ponto fora de Porto Velho sai."""
        self.assertEqual(_rows(semtran_pvh.parse(self.TEXT, today=date(2026, 11, 8))), [
            (-8.76652, -63.87978, CameraKind.FIXED, None, "SEMTRAN-PVH", True),
            (-8.7376, -63.87901, CameraKind.FIXED, None, "SEMTRAN-PVH", False),
        ])

    def test_pdf_url_is_the_highest_version(self):
        base = "https://semtran.portovelho.ro.gov.br/uploads/arquivos/"
        page = (f'<a href="{base}Carta_de_Servicos_SEMTRAN.pdf.pdf">Carta</a>'
                f'<a href="{base}Dados%20dos%20Radares%20fixos%20atualizados%202026.1.pdf">x</a>'
                f'<a href="{base}Planilha%20Radares%20SEMTRAN%20-%20Atualizada%20%202026.2.pdf">x</a>')
        self.assertEqual(semtran_pvh.pdf_url(page), f"{base}Planilha%20Radares%20SEMTRAN%20-%20Atualizada%20%202026.2.pdf")


class CetGithubBackup(unittest.TestCase):
    CSV = ("﻿CÓDIGO LOCAL,ATIVAÇÃO,DESATIVAÇÃO,NÚMERO DE SÉRIE,DESCRIÇÃO DO LOCAL,LATITUDE,LONGITUDE,FAIXAS,"
           "TIPO,METROLÓGICO,VELOCIDADE,FISCALIZA FAIXA AZUL,CAPTURA,REDUTOR,ENQUADRAMENTO\n"
           "2400,2024-07-10,2025-07-01,5301062,AV. INTERLAGOS (CENTRO/BAIRRO),-23.679847,-46.686833,3,FIXO,SIM,"
           "50 km/h,Não,T,N,EXD; V\n"
           "100,2024-11-19,,1,AV SANTA INES B/C,-23.4603904,-46.642978,2,FIXO,SIM,40 km/h,Não,T,N,V\n"
           "200,2026-10-20,,2,R X,-23.5,-46.6,1,FIXO,NÃO,,Não,T,N,A; CPD\n")
    # Power BI: datas em milissegundos (1793750400000 = 2026-11-04)
    PBI = [{"CÓDIGO LOCAL": "100", "LATITUDE": -23.4603904, "LONGITUDE": -46.642978, "DESCRIÇÃO DO LOCAL": "AV SANTA INES",
            "ENQUADRAMENTOS": "V", "VELOCIDADE": "40 km/h", "ATIVAÇÃO": 1731974400000, "DESATIVAÇÃO": None},
           {"CÓDIGO LOCAL": "300", "LATITUDE": -23.6, "LONGITUDE": -46.7, "DESCRIÇÃO DO LOCAL": "R Y",
            "ENQUADRAMENTOS": "V", "VELOCIDADE": "50 km/h", "ATIVAÇÃO": 1700000000000, "DESATIVAÇÃO": 1793750400000}]

    def test_csv_rows_read_like_the_power_bi(self):
        rows = cet_sp.csv_rows(self.CSV)
        self.assertEqual([r["ENQUADRAMENTOS"] for r in rows], ["EXD,V", "V", "A,CPD"])
        self.assertEqual(_rows(cet_sp.rows_to_cameras(rows)), [
            (-23.46039, -46.642978, CameraKind.FIXED, 40, "CET-SP", True),
            (-23.5, -46.6, CameraKind.RED_LIGHT, None, "CET-SP", True),
        ])
        self.assertEqual(cet_sp.rows_to_deactivated(rows), [(-23.679847, -46.686833)])

    def test_last_change_reads_both_date_formats(self):
        self.assertEqual(cet_sp.last_change(cet_sp.csv_rows(self.CSV)), date(2026, 10, 20))
        self.assertEqual(cet_sp.last_change(self.PBI), date(2026, 11, 4))
        self.assertIsNone(cet_sp.last_change([{"ATIVAÇÃO": None, "DESATIVAÇÃO": ""}]))

    def test_choose(self):
        """Power BI em dia -> Power BI; falhou ou mais velho que o CSV -> CSV do GitHub, com o motivo."""
        github = cet_sp.csv_rows(self.CSV)
        self.assertEqual(cet_sp.choose(self.PBI, github), (self.PBI, ""))
        self.assertEqual(cet_sp.choose(self.PBI, None), (self.PBI, ""))
        self.assertEqual(cet_sp.choose(None, github), (github, "Power BI falhou"))
        self.assertEqual(cet_sp.choose(None, None), (None, ""))
        old = [dict(self.PBI[0])]   # só a ativação de 2024-11-19
        rows, why = cet_sp.choose(old, github)
        self.assertIs(rows, github)
        self.assertIn("desatualizado", why)

    def _run(self, raw_dir, pbi, github):
        """_rows_with_fallback com o Power BI e o GitHub simulados (lista, ou exceção = fora do ar)."""
        from datakit.sources import _powerbi

        def table(*a):
            if isinstance(pbi, Exception):
                raise pbi
            return pbi

        def csv_bytes(url, *a, **k):
            if isinstance(github, Exception):
                raise github
            return github.encode("utf-8")
        with mock.patch.object(_powerbi, "resource_key", lambda v: "k"), \
                mock.patch.object(_powerbi, "model_id", lambda api, key: 1), \
                mock.patch.object(_powerbi, "query_table", table), \
                mock.patch("datakit.sources._http.get_bytes", csv_bytes):
            return cet_sp._rows_with_fallback(raw_dir)

    def test_fallback_order(self):
        from datakit import failures
        raw = tempfile.mkdtemp()
        self.assertEqual(self._run(raw, self.PBI, self.CSV), self.PBI)                  # Power BI em dia
        with open(os.path.join(raw, cet_sp.CACHE_FILE), encoding="utf-8") as f:
            self.assertEqual(json.load(f), self.PBI)                                    # cópia gravada
        before = len(failures._WARNINGS)
        got = self._run(raw, ConnectionError("fora"), self.CSV)                         # Power BI fora
        self.assertEqual([r["CÓDIGO LOCAL"] for r in got], ["2400", "100", "200"])
        self.assertTrue(any("Power BI falhou; usado o CSV do GitHub" in w for w in failures._WARNINGS[before:]))
        got = self._run(raw, ConnectionError("fora"), ConnectionError("fora"))          # os dois fora: cópia
        self.assertEqual([r["CÓDIGO LOCAL"] for r in got], ["2400", "100", "200"])
        with self.assertRaises(ConnectionError):                                        # sem cópia, sobe
            self._run(tempfile.mkdtemp(), ConnectionError("fora"), ConnectionError("fora"))


class Registry(unittest.TestCase):
    NEW = {"AGETO-TO": "TO", "DETRAN-MA": "MA", "DER-SE": "SE", "SEINFRA-BA": "BA",
           "TRANSALVADOR": "BA", "SEMTRAN-PVH": "RO"}

    def test_new_sources_are_official_with_a_home_uf(self):
        from datakit.build import OFFICIAL
        from datakit.common.ufs import SOURCE_HOME_UF
        for name, uf in self.NEW.items():
            self.assertIn(name, OFFICIAL)
            self.assertTrue(hasattr(OFFICIAL[name], "fetch"))
            self.assertEqual(SOURCE_HOME_UF.get(name), uf)

    def test_catalog_coverage_level(self):
        from datakit.build_catalog import _coverage
        for sources, uf, level in ((["AGETO-TO", "OSM"], "TO", "state"), (["DETRAN-MA"], "MA", "state"),
                                   (["SEINFRA-BA", "TRANSALVADOR+OSM"], "BA", "state+municipal"),
                                   (["DER-SE"], "SE", "state"), (["SEMTRAN-PVH"], "RO", "municipal"),
                                   (["AGETO-TO"], "GO", "none")):
            with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
                f.write("lat,lng,source\n" + "".join(f"-10,-48,{s}\n" for s in sources))
            try:
                self.assertEqual(_coverage(f.name, uf)["level"], level, (sources, uf))
            finally:
                os.unlink(f.name)


if __name__ == "__main__":
    unittest.main()
