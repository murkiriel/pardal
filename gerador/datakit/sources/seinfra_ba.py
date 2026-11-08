"""SEINFRA-BA — radares fixos de controle de velocidade das rodovias estaduais da Bahia.

A página "Mapas" da Secretaria de Infraestrutura publica o mesmo cadastro em três formas: KML
(dentro de um RAR, que a biblioteca padrão não abre), página web e a "Tabela" em PDF
(Lista-Radar_DD-MM-AAAA.pdf, nome datado e descoberto na página). O PDF tem, por equipamento: ID,
ano, tipo, marca, modelo, códigos do órgão, série, Inmetro, velocidade ("50km"), município,
rodovia (BA131), km ("9+500m"), latitude e longitude com vírgula decimal ("-10,51770").
Medido em 2026-11-08 (lista de 15/09/2026): 79 radares, 78 pontos únicos (um com a longitude sem o
sinal de menos). Esteve fora do ar no período eleitoral (FONTES.md, seção D). Tudo FIXED; sem
sentido publicado.
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple
from urllib.parse import urljoin

from datakit.context import SourceData, BuildContext
from datakit.common import Camera, CameraKind, Limit, in_bbox
from datakit.sources._http import get_bytes, in_br, to_float
from datakit.sources._pdf import pdf_text

PAGE = "https://www.ba.gov.br/infraestrutura/12046/mapas"

_PDF = re.compile(r'href="([^"]*Lista-Radar_(\d{2})-(\d{2})-(\d{4})[^"]*\.pdf)"', re.I)
_ROW = re.compile(r"\b(\d{2,3})\s*km\s+[^\n]*?\bBA\s*-?\d{3}\s+\d+\s*\+\s*\d+\s*m\s+(-?\d{1,2},\d+)\s+(-?\d{2},\d+)", re.I)


def pdf_url(page_html: str) -> str:
    """A lista em PDF mais nova da página (pela data no nome)."""
    found = sorted(((y, m, d), href) for href, d, m, y in _PDF.findall(page_html))
    if not found:
        raise RuntimeError("SEINFRA-BA: a página não tem mais a lista de radares em PDF")
    return urljoin(PAGE, found[-1][1])


def parse(text: str, bbox=None) -> List[Camera]:
    """Linhas do PDF -> radares. Uma linha com muitos códigos do órgão quebra em duas no texto,
    mas velocidade, rodovia, km e coordenada ficam juntas na segunda."""
    out: List[Camera] = []
    seen = set()
    for kmh, lat_s, lng_s in _ROW.findall(text):
        lat, lng = to_float(lat_s), to_float(lng_s)
        if lat is not None and lng is not None:
            lat, lng = -abs(lat), -abs(lng)   # a Bahia inteira fica ao sul e a oeste; a lista às vezes perde o "-"
        if lat is None or lng is None or not in_br(lat, lng) or not in_bbox(bbox, lat, lng):
            continue
        key = (round(lat, 6), round(lng, 6))
        if key in seen:
            continue
        seen.add(key)
        limit = int(kmh) if 20 <= int(kmh) <= 130 else None
        out.append(Camera(key[0], key[1], CameraKind.FIXED, limit, "SEINFRA-BA", True))
    return out


def load(raw_dir: str, bbox: Optional[Tuple[float, float, float, float]] = None
         ) -> Tuple[List[Camera], List[Limit]]:
    url = pdf_url(get_bytes(PAGE).decode("utf-8", "replace"))
    cams = parse(pdf_text(get_bytes(url)), bbox)
    if not cams:
        raise RuntimeError(f"SEINFRA-BA: nenhum radar lido de {url} (formato mudou?)")
    return cams, []


def fetch(ctx: BuildContext) -> SourceData:
    """Contrato das fontes (datakit/context.py)."""
    return SourceData(*load(ctx.raw_dir))
