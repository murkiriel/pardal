"""TRANSALVADOR — mapa dos equipamentos de fiscalização eletrônica de Salvador/BA.

A página "Mapa de Pórticos" do sistema da Transalvador (transonline) desenha cada equipamento
num marcador do Google Maps: o ponto em `google.maps.LatLng(lat, lng)` e, na janela do marcador,
o endereço com o sentido nominal ("/ SENTIDO AEROPORTO"), o tipo ("FIXO - CONTROLADOR"), a série,
a data da última aferição e a velocidade ("Velocidade: 60 Km"). Só os marcadores com o ícone
`markers/radar.png` são radares. Medido em 2026-11-08: 106 marcadores, 102 pontos únicos, 27 no
pacote a ≤ 50 m. Tudo FIXED e ativo: a data de aferição da página é velha (52 de 2022) e não é
usada para desativar; o sentido nominal não vira rumo.
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from datakit.context import SourceData, BuildContext
from datakit.common import Camera, CameraKind, Limit, in_bbox
from datakit.sources._http import get_bytes, in_br, to_float

PAGE = "https://transonline.salvador.ba.gov.br/geral_sistema/web/index.php/mapa/mapa-porticos"

_MARKER = re.compile(r"var gmarker\d+\s*=")
_POINT = re.compile(r"LatLng\(\s*(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)\s*\)")
_SPEED = re.compile(r"Velocidade:\s*(\d{2,3})")


def parse(page_html: str, bbox=None) -> List[Camera]:
    """Marcadores de radar da página -> radares, sem repetir o ponto."""
    out: List[Camera] = []
    seen = set()
    for block in _MARKER.split(page_html)[1:]:
        if "/markers/radar.png" not in block:
            continue
        m = _POINT.search(block)
        if not m:
            continue
        lat, lng = to_float(m.group(1)), to_float(m.group(2))
        if lat is None or lng is None or not in_br(lat, lng) or not in_bbox(bbox, lat, lng):
            continue
        key = (round(lat, 6), round(lng, 6))
        if key in seen:
            continue
        seen.add(key)
        s = _SPEED.search(block)
        limit = int(s.group(1)) if s and 20 <= int(s.group(1)) <= 130 else None
        out.append(Camera(key[0], key[1], CameraKind.FIXED, limit, "TRANSALVADOR", True))
    return out


def load(raw_dir: str, bbox: Optional[Tuple[float, float, float, float]] = None
         ) -> Tuple[List[Camera], List[Limit]]:
    cams = parse(get_bytes(PAGE).decode("utf-8", "replace"), bbox)
    if not cams:
        raise RuntimeError("TRANSALVADOR: nenhum radar no mapa (formato mudou?)")
    return cams, []


def fetch(ctx: BuildContext) -> SourceData:
    """Contrato das fontes (datakit/context.py)."""
    return SourceData(*load(ctx.raw_dir))
