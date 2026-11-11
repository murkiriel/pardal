"""DETRAN-MA — medidores de velocidade instalados e em operação nas rodovias maranhenses.

A página de fiscalização eletrônica do Detran-MA liga um PDF ("Fiscalização Eletrônica", em
sgp5.detran.ma.gov.br/uploads/midias/<hash>.pdf, nome que muda a cada versão) com uma linha por
equipamento e sentido: código (MA301R), série, marca/modelo, endereço (rodovia + km), sentido
nominal (LESTE/OESTE), município, tipo, velocidade, nº do Inmetro, latitude e longitude ("-2.478711°").
Medido em 2026-11-08: 68 linhas, 33 pontos únicos, 1 no pacote a ≤ 50 m. Tudo FIXED; o sentido
nominal não vira rumo (como o da Artesp em via de mão dupla).
"""
from __future__ import annotations

import html as htmllib
import re
from typing import List, Optional, Tuple

from datakit.context import SourceData, BuildContext
from datakit.common import Camera, CameraKind, Limit, in_bbox
from datakit.sources._http import get_bytes, in_br, to_float
from datakit.sources._pdf import pdf_text

PAGE = "https://www.detran.ma.gov.br/inicio/paginas/Pagina.xhtml?id=23582"

_PDF = re.compile(r'href="(https?://sgp5\.detran\.ma\.gov\.br/uploads/midias/[^"]+\.pdf)"[^>]*>([^<]*)', re.I)
_ROW = re.compile(r"^\s*(MA\d{3,}[A-Z]?)\s.*?\b(\d{2,3})\s*Km/h\s+\S+\s+(-\d{1,2}\.\d{3,})°?\s+(-\d{2}\.\d{3,})°?",
                  re.M | re.I)


def pdf_url(page_html: str) -> str:
    """O PDF da lista na página: o link "Fiscalização Eletrônica" (ou o único da SGP)."""
    links = _PDF.findall(page_html)
    for href, text in links:
        if "fiscaliza" in htmllib.unescape(text).lower():
            return href
    if links:
        return links[0][0]
    raise RuntimeError("DETRAN-MA: a página não tem mais o link do PDF da lista")


def parse(text: str, bbox=None) -> List[Camera]:
    """Linhas do PDF -> um radar por ponto (a lista repete o equipamento por sentido e faixa)."""
    out: List[Camera] = []
    seen = set()
    for code, kmh, lat_s, lng_s in _ROW.findall(text):
        lat, lng = to_float(lat_s), to_float(lng_s)
        if lat is None or lng is None or not in_br(lat, lng) or not in_bbox(bbox, lat, lng):
            continue
        key = (round(lat, 6), round(lng, 6))
        if key in seen:
            continue
        seen.add(key)
        limit = int(kmh) if 20 <= int(kmh) <= 130 else None
        out.append(Camera(key[0], key[1], CameraKind.FIXED, limit, "DETRAN-MA", True, source_ref=("DETRAN-MA", code)))
    return out


def load(raw_dir: str, bbox: Optional[Tuple[float, float, float, float]] = None
         ) -> Tuple[List[Camera], List[Limit]]:
    url = pdf_url(get_bytes(PAGE).decode("utf-8", "replace"))
    cams = parse(pdf_text(get_bytes(url)), bbox)
    if not cams:
        raise RuntimeError(f"DETRAN-MA: nenhum radar lido de {url} (formato mudou?)")
    return cams, []


def fetch(ctx: BuildContext) -> SourceData:
    """Contrato das fontes (datakit/context.py)."""
    return SourceData(*load(ctx.raw_dir))
