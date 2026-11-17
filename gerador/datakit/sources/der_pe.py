"""DER-PE — listas de trechos monitorados do site do DER (rodovias estaduais de PE); source="DER-PE".

* Artigo 1382, "Lista de trechos monitorados — lombadas": tabela com EQUIPAMENTO, PROCESSADOR, SÉRIE,
  TIPO, ENDEREÇO, SENTIDO, MUNICÍPIO, VELOCIDADE, LATITUDE e LONGITUDE (119 equipamentos em 17/11/2026:
  74 CEV, controlador eletrônico de velocidade, e 45 REV, redutor eletrônico de velocidade; 60 e 40 km/h).
  Cada equipamento ocupa uma linha completa e, nas linhas seguintes (rowspan), traz só o processador e o
  sentido de cada faixa: essas linhas de continuação não têm coordenada e são puladas. O "sentido" é
  nominal (a cidade para onde a pista segue), não um rumo: sem direction_deg. Substitui o antigo artigo
  1392 ("Equipamentos velocidade"): todos os equipamentos dele estão no 1382 (31 de 31 pelo número), que
  ainda corrige uma longitude do 1392 (EQP 1588, a ~3 km do ponto certo) e traz o limite.
* Artigo 1383, "Equipamentos mistos": EQP, ENDEREÇO e COORDENADAS de 61 pontos nas PE-01, 05, 07, 08, 15, 22,
  60, 90, 95 e 160 (a maioria em semáforos da Grande Recife). O site não diz o que "misto" fiscaliza, mas os
  levantamentos técnicos que o DER publica (site, "Levantamento técnico") de 24 desses equipamentos, com o
  mesmo número e a mesma coordenada, são todos "Levantamento técnico — controlador de velocidade" (60
  km/h, nos semáforos). Entram como radar fixo, sem limite (a lista não o traz).
  As "câmeras dome" (artigo 1391) são monitoramento, não fiscalização: fora.

Cada artigo abre por /component/content/article/<id>, que não muda quando o DER reorganiza o menu
(o endereço antigo do 1392 deu 404 em novembro de 2026); o endereço com o caminho do menu fica de
reserva.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Callable, List, Optional, Tuple

from datakit.context import SourceData, BuildContext
from datakit.common import Camera, CameraKind, Limit, in_bbox
from datakit.sources._http import get_bytes, in_br, to_float

BASE = "https://www.der.pe.gov.br"
ID_LOMBADAS = 1382
ID_MISTOS = 1383
URL = f"{BASE}/component/content/article/{ID_LOMBADAS}"
MISTOS_URL = f"{BASE}/component/content/article/{ID_MISTOS}"
# o mesmo artigo pelo caminho do menu (muda quando o site é reorganizado): só se o endereço estável falhar
FALLBACKS = {
    ID_LOMBADAS: (f"{BASE}/transito-menu/lombadas-eletronicas/lista-de-trechos-monitorados-2/"
                  "1382-lista-de-trechos-monitorados-lombadas"),
    ID_MISTOS: (f"{BASE}/transito-menu/equipamentos-de-fiscalizacao-eletronica/lista-de-trechos-2/"
                "1383-equipamentos-mistos"),
}
# TIPO da tabela de lombadas: CEV controlador e REV redutor eletrônico de velocidade
FIXED_TYPES = ("CEV", "REV")

Point = Tuple[float, float, Optional[int]]


def _cells(html: str) -> List[List[str]]:
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S | re.I):
        rows.append([re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", c)).replace("&nbsp;", " ").strip()
                     for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)])
    return rows


def _name(s: str) -> str:
    """Cabeçalho sem acento e em maiúsculas ("SÉRIE" -> "SERIE")."""
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().upper().strip()


def _coordinate(s: str) -> Optional[float]:
    return to_float(s) if re.fullmatch(r"-?\d{1,3}[.,]\d+", s.strip()) else None


def parse_lombadas(html: str) -> List[Point]:
    """Artigo 1382 -> (lat, lng, limite) de cada equipamento CEV/REV. Colunas pelo nome do cabeçalho; só as linhas
    completas (com as células de EQUIPAMENTO a LONGITUDE) valem: as de continuação por sentido/faixa vêm com
    2 células. Puro, testado."""
    header: Optional[List[str]] = None
    out: List[Point] = []
    for cells in _cells(html):
        names = [_name(c) for c in cells]
        if header is None:
            if "LATITUDE" in names and "LONGITUDE" in names and "TIPO" in names:
                header = names
            continue
        if len(cells) != len(header):
            continue
        row = dict(zip(header, cells))
        lat, lng = _coordinate(row["LATITUDE"]), _coordinate(row["LONGITUDE"])
        if lat is None or lng is None or row["TIPO"].upper() not in FIXED_TYPES:
            continue
        m = re.search(r"\d{2,3}", row.get("VELOCIDADE", ""))
        kmh = int(m.group()) if m else None
        out.append((lat, lng, kmh if kmh and 20 <= kmh <= 130 else None))
    return out


def parse_mistos(html: str) -> List[Point]:
    """Artigo 1383 -> (lat, lng, None) de cada linha EQP / ENDEREÇO / COORDENADAS. Puro, testado."""
    out: List[Point] = []
    for cells in _cells(html):
        if len(cells) < 3 or not re.fullmatch(r"\d{3,6}", cells[0]):
            continue
        m = re.search(r"(-?\d{1,2}[.,]\d{3,})\s*,\s*(-?\d{1,2}[.,]\d{3,})", cells[-1])
        if m:
            lat, lng = to_float(m.group(1)), to_float(m.group(2))
            if lat is not None and lng is not None:
                out.append((lat, lng, None))
    return out


def read_article(article_id: int, parse: Callable[[str], List[Point]]) -> List[Point]:
    """Pontos do artigo: pelo endereço estável e, se ele falhar ou vier sem a tabela, pelo do menu."""
    errors = []
    for url in (f"{BASE}/component/content/article/{article_id}", FALLBACKS[article_id]):
        try:
            points = parse(get_bytes(url).decode("utf-8", "replace"))
        except Exception as e:  # noqa: BLE001 — tenta o outro endereço
            errors.append(f"{url}: {type(e).__name__}: {e}")
            continue
        if points:
            return points
        errors.append(f"{url}: página sem a tabela esperada")
    raise RuntimeError(f"lista do DER-PE (artigo {article_id}) não encontrada: " + "; ".join(errors))


def load(raw_dir: str, bbox: Optional[Tuple[float, float, float, float]] = None
         ) -> Tuple[List[Camera], List[Limit]]:
    points = read_article(ID_LOMBADAS, parse_lombadas) + read_article(ID_MISTOS, parse_mistos)
    out: List[Camera] = []
    seen = set()
    for lat, lng, kmh in points:
        if not in_br(lat, lng) or not in_bbox(bbox, lat, lng):
            continue
        key = (round(lat, 6), round(lng, 6))
        if key in seen:   # o mesmo ponto com um equipamento por sentido
            continue
        seen.add(key)
        out.append(Camera(key[0], key[1], CameraKind.FIXED, kmh, "DER-PE", True))
    return out, []


def fetch(ctx: BuildContext) -> SourceData:
    """Contrato das fontes (datakit/context.py)."""
    return SourceData(*load(ctx.raw_dir))
