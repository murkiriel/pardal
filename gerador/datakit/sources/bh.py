"""Belo Horizonte (BHTrans) — equipamentos de fiscalização eletrônica.

CKAN da PBH, dataset `fiscalizacao-eletronica`, CSV mensal (CC-BY). Geometria em WKT
"POINT (e n)" no SIRGAS 2000 / UTM 23S (EPSG:31983). Controlador de velocidade -> FIXED
(com VELOCIDADE_REGULAMENTAR), detector de avanço de semáforo -> RED_LIGHT; invasão de faixa
exclusiva e conversão proibida não vão para o radares.csv (não são aviso de velocidade nem de sinal), e sim para o
cameras_fiscalizacao.csv (`other_cameras`).
"""
from __future__ import annotations

import csv
import functools
import io
import json
import re
from typing import List, Optional

from datakit.context import SourceData, BuildContext
from datakit.common.geo import utm_to_latlng
from datakit.common.model import Camera, CameraKind, EnforcementCamera

from datakit.sources._http import get_bytes_curl, in_br, newest

CKAN = "https://dados.pbh.gov.br/api/3/action/package_show?id=fiscalizacao-eletronica"
_POINT = re.compile(r"POINT\s*\(\s*([\d.]+)\s+([\d.]+)\s*\)", re.I)


def _kind(kind_text: str) -> Optional[CameraKind]:
    t = kind_text.lower()
    if "velocidade" in t:
        return CameraKind.FIXED
    if "avan" in t and "sem" in t:
        return CameraKind.RED_LIGHT
    return None


def parse(text: str) -> List[Camera]:
    out: List[Camera] = []
    for r in csv.DictReader(io.StringIO(text), delimiter=";"):
        kind = _kind(r.get("DESC_TIPO_CONTROLADOR_TRANSITO") or "")
        m = _POINT.search(r.get("GEOMETRIA") or "")
        if kind is None or m is None:
            continue
        lat, lng = utm_to_latlng(float(m.group(1)), float(m.group(2)), 23, south=True)
        if not in_br(lat, lng):
            continue
        v = (r.get("VELOCIDADE_REGULAMENTAR") or "").strip()
        kmh = int(v) if v.isdigit() and 20 <= int(v) <= 130 and kind == CameraKind.FIXED else None
        out.append(Camera(round(lat, 6), round(lng, 6), kind, kmh, "BHTRANS", True))
    return out


SOURCE_CAMERAS = "BHTRANS:CAM"   # código próprio: a reserva pela edição busca radares pelas partes de `source`


def other_cameras(text: str) -> List[EnforcementCamera]:
    """Detectores que não são de velocidade nem de avanço de semáforo: conversão/retorno proibido (NO_TURN) e invasão
    de faixa exclusiva do MOVE (BUS_LANE); outro tipo novo vira OTHER. Puro, testado."""
    out: List[EnforcementCamera] = []
    for r in csv.DictReader(io.StringIO(text), delimiter=";"):
        t = (r.get("DESC_TIPO_CONTROLADOR_TRANSITO") or "")
        m = _POINT.search(r.get("GEOMETRIA") or "")
        if m is None or _kind(t) is not None:
            continue
        low = t.lower()
        kind = "NO_TURN" if ("convers" in low or "retorno" in low) else "BUS_LANE" if "faixa" in low else "OTHER"
        lat, lng = utm_to_latlng(float(m.group(1)), float(m.group(2)), 23, south=True)
        if in_br(lat, lng):
            out.append(EnforcementCamera(round(lat, 6), round(lng, 6), kind, SOURCE_CAMERAS))
    return out


@functools.lru_cache(maxsize=1)
def _csv_text() -> str:
    """O CSV mais novo da BHTrans, lido uma vez por execução (os radares e as outras câmeras saem da mesma leitura).
    Falha não fica guardada."""
    resources = json.loads(get_bytes_curl(CKAN))["result"]["resources"]
    res = newest(resources, "CSV", "fiscalizacao_eletronica")
    return get_bytes_curl(res["url"]).decode("utf-8", "replace")


def load(raw_dir: str, bbox=None):
    return parse(_csv_text()), []


def load_other_cameras() -> List[EnforcementCamera]:
    return other_cameras(_csv_text())


def fetch(ctx: BuildContext) -> SourceData:
    """Contrato das fontes (datakit/context.py)."""
    return SourceData(*load(ctx.raw_dir))
