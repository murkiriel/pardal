"""AGETO-TO — lista dos radares fixos das rodovias estaduais do Tocantins.

A página "Lista de radares" da Agência Tocantinense de Transportes e Obras liga um PDF geral
("LISTA RADARES - AGETO.rev01.pdf") e um estudo técnico por equipamento. O PDF geral traz, por
equipamento: rodovia, km, coordenada ("-12.641756, -47.119498"; às vezes com "°" e sem a vírgula), município, tipo (radar fixo,
radar misto, barreira eletrônica), limite, faixas, série e nº do Inmetro. Medido em 2026-11-08:
58 equipamentos (40 radares fixos, 16 barreiras eletrônicas, 2 mistos), nenhum no pacote a
≤ 50 m. Todos viram FIXED (a barreira eletrônica é a lombada eletrônica, mede velocidade; o
misto mede velocidade e sinal). Sem sentido publicado.
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from datakit.context import SourceData, BuildContext
from datakit.common import Camera, CameraKind, Limit, in_bbox
from datakit.sources._http import get_bytes, in_br, to_float
from datakit.sources._pdf import pdf_text

PAGE = "https://www.to.gov.br/ageto/lista-de-radares/l3d43475lu1"
PDF_FALLBACK = "https://central.to.gov.br/download/482949"

_LINK = re.compile(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.S | re.I)
_ROW = re.compile(
    r"(-\d{1,2}\.\d{3,})°?\s*,?\s*(-\d{2}\.\d{3,})°?\s*(.*?)\s*"
    r"(BARREIRA\s+ELETR[ÔO]NICA|RADAR\s+FIXO|RADAR\s+MISTO|LOMBADA\s+ELETR[ÔO]NICA)\s+(\d{2,3})\b",
    re.S | re.I)


def pdf_url(html: str) -> str:
    """O link do PDF geral ("LISTA RADARES ...") na página; sem ele, o endereço conhecido."""
    for href, text in _LINK.findall(html):
        if "LISTA RADARES" in re.sub(r"<[^>]+>|\s+", " ", text).upper():
            return href
    return PDF_FALLBACK


def parse(text: str, bbox=None) -> List[Camera]:
    """Linhas do PDF -> radares. O nome do município às vezes quebra a linha ("MIRACEMA DO
    \\nTOCANTINS") ou falta, por isso a regex corre o texto inteiro. Pontos repetidos saem."""
    out: List[Camera] = []
    seen = set()
    for lat_s, lng_s, _city, _kind, kmh in _ROW.findall(text):
        lat, lng = to_float(lat_s), to_float(lng_s)
        if lat is None or lng is None or not in_br(lat, lng) or not in_bbox(bbox, lat, lng):
            continue
        key = (round(lat, 6), round(lng, 6))
        if key in seen:
            continue
        seen.add(key)
        limit = int(kmh) if 20 <= int(kmh) <= 130 else None
        out.append(Camera(key[0], key[1], CameraKind.FIXED, limit, "AGETO-TO", True))
    return out


def load(raw_dir: str, bbox: Optional[Tuple[float, float, float, float]] = None
         ) -> Tuple[List[Camera], List[Limit]]:
    url = pdf_url(get_bytes(PAGE).decode("utf-8", "replace"))
    cams = parse(pdf_text(get_bytes(url)), bbox)
    if not cams:
        raise RuntimeError(f"AGETO-TO: nenhum radar lido de {url} (formato mudou?)")
    return cams, []


def fetch(ctx: BuildContext) -> SourceData:
    """Contrato das fontes (datakit/context.py)."""
    return SourceData(*load(ctx.raw_dir))
