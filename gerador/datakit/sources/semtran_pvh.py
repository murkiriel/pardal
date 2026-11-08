"""SEMTRAN-PVH — radares fixos de Porto Velho/RO.

A página "Fiscalização eletrônica - radares fixos" da Secretaria Municipal de Trânsito liga a
planilha dos radares em PDF, com o nome trocando a cada versão ("Dados dos Radares fixos
atualizados 2026.1.pdf", "Planilha Radares SEMTRAN - Atualizada  2026.2.pdf"); vale a de maior
versão. Uma linha por faixa: tipo (FSC110, FSC), série, código e número da faixa, local
("Avenida Abuna x Rua Brasilia"), data da aferição e da validade, latitude, longitude e sigla
(FX, NI). Sem limite. A coordenada vem estragada pela planilha, com os pontos de milhar no lugar
da vírgula: "-876.651.999.999.999.000" é -8,76652 e "-6.387.977.999.999.990.000" é -63,87978
(latitude com um dígito inteiro, longitude com dois, o que vale em todo o município; ponto fora
da caixa de Porto Velho sai). Ativo enquanto a validade da aferição não venceu (aferição vencida
não multa). Medido em 2026-11-08 (planilha 2026.2): 39 pontos, 38 com aferição válida, 15 no pacote
a ≤ 50 m.
"""
from __future__ import annotations

import re
from datetime import date
from typing import List, Optional, Tuple

from datakit.context import SourceData, BuildContext
from datakit.common import Camera, CameraKind, Limit, in_bbox
from datakit.sources._http import get_bytes
from datakit.sources._pdf import pdf_text

PAGE = "https://semtran.portovelho.ro.gov.br/pagina/fiscalizacao-eletronica-radares-fixos"
AREA = (-10.0, -67.0, -8.0, -62.0)   # município de Porto Velho, com folga

_PDF = re.compile(r'href="([^"]+\.pdf)"', re.I)
_VERSION = re.compile(r"(20\d{2})\.(\d+)\.pdf$", re.I)
# validade (dd/mm/aaaa hh:mm), latitude, longitude, sigla; no pypdf o texto vem sem espaços
_ROW = re.compile(r"(\d{2})/(\d{2})/(\d{4})\s*\d{2}:\d{2}\s*(-\d{1,3}(?:\.\d{3})+)\s*(-\d{1,3}(?:\.\d{3})+)\s*(FX|NI)(?![A-Za-z])")


def pdf_url(page_html: str) -> str:
    """O PDF da planilha de maior versão (AAAA.N no fim do nome) entre os links da página."""
    found = []
    for href in _PDF.findall(page_html):
        m = _VERSION.search(href.replace("%20", " "))
        if m and "radar" in href.lower():
            found.append(((int(m.group(1)), int(m.group(2))), href))
    if not found:
        raise RuntimeError("SEMTRAN-PVH: a página não tem mais a planilha dos radares")
    return max(found)[1]


def _coord(raw: str, int_digits: int) -> Optional[float]:
    digits = re.sub(r"\D", "", raw)
    if len(digits) <= int_digits:
        return None
    return -float(digits[:int_digits] + "." + digits[int_digits:])


def parse(text: str, today: Optional[date] = None, bbox=None) -> List[Camera]:
    """Linhas do PDF -> um radar por ponto; ativo se alguma faixa do ponto tem aferição válida."""
    today = today or date.today()
    points: dict = {}
    for dd, mm, yyyy, lat_s, lng_s, _sigla in _ROW.findall(text):
        lat, lng = _coord(lat_s, 1), _coord(lng_s, 2)
        if lat is None or lng is None or not in_bbox(AREA, lat, lng) or not in_bbox(bbox, lat, lng):
            continue
        try:
            valid = date(int(yyyy), int(mm), int(dd)) >= today
        except ValueError:
            valid = False
        key = (round(lat, 6), round(lng, 6))
        points[key] = points.get(key, False) or valid
    return [Camera(lat, lng, CameraKind.FIXED, None, "SEMTRAN-PVH", active)
            for (lat, lng), active in points.items()]


def load(raw_dir: str, bbox: Optional[Tuple[float, float, float, float]] = None
         ) -> Tuple[List[Camera], List[Limit]]:
    url = pdf_url(get_bytes(PAGE).decode("utf-8", "replace"))
    cams = parse(pdf_text(get_bytes(url)), bbox=bbox)
    if not cams:
        raise RuntimeError(f"SEMTRAN-PVH: nenhum radar lido de {url} (formato mudou?)")
    return cams, []


def fetch(ctx: BuildContext) -> SourceData:
    """Contrato das fontes (datakit/context.py)."""
    return SourceData(*load(ctx.raw_dir))
