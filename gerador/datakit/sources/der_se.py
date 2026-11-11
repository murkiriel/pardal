"""DER-SE — localização dos radares e lombadas fixas das rodovias estaduais de Sergipe.

A página "Localização de Radares Fixos" do DER-SE embute duas planilhas do Google publicadas na
web: a de título "radares" (a lista) e a de "cameras" (câmeras de monitoramento, não são radar).
A da lista sai em CSV trocando `pubhtml` por `pub` com `output=csv`. Colunas: código do
equipamento (SE001R radar, SE348L lombada), rodovia, município, velocidade e "Localização do
Radares", que traz a coordenada num link do Google Maps (`?query=lat,lng`, ou `!3d<lat>!4d<lng>`
num link de lugar), em graus, minutos e segundos ou num link curto (maps.app.goo.gl), cujo
redirecionamento leva ao link de lugar. Medido em 2026-11-08: 129 equipamentos, cada um num ponto
(9 só com link curto), 5 no pacote a ≤ 50 m. Tudo FIXED (a lombada eletrônica mede velocidade).
Sem sentido publicado.
"""
from __future__ import annotations

import csv
import html as htmllib
import io
import re
from typing import Callable, List, Optional, Tuple

from datakit.context import SourceData, BuildContext
from datakit.common import Camera, CameraKind, Limit, in_bbox
from datakit.sources._http import HTTP_TIMEOUT, UA, get_bytes, in_br, to_float

PAGE = "https://der.se.gov.br/localizacao-de-radares-fixos/"

_IFRAME = re.compile(r"<iframe[^>]*\btitle=\"radares\"[^>]*\bsrc=\"([^\"]+)\"", re.I)
_QUERY = re.compile(r"query=(-?\d{1,2}\.\d+),\s*(-?\d{2,3}\.\d+)")
_PLACE = re.compile(r"!3d(-?\d{1,2}\.\d+)!4d(-?\d{2,3}\.\d+)")
_DMS = re.compile(r"(\d{1,2})°\s*(\d{1,2})'\s*([\d.]+)\"*\s*([NS])\s+(\d{1,3})°\s*(\d{1,2})'\s*([\d.]+)\"*\s*([EWO])")
_SPEED = re.compile(r"(\d{2,3})\s*km", re.I)
_SHORT = re.compile(r"https://maps\.app\.goo\.gl/\w+")


def csv_url(page_html: str) -> str:
    """A planilha "radares" da página, como CSV (mesmo documento e aba, `pub?...&output=csv`)."""
    m = _IFRAME.search(page_html)
    if not m:
        raise RuntimeError("DER-SE: a página não tem mais a planilha \"radares\"")
    src = htmllib.unescape(m.group(1)).replace("/pubhtml", "/pub")
    return src + ("&" if "?" in src else "?") + "output=csv"


def _point(cells: List[str]) -> Optional[Tuple[float, float]]:
    text = " ".join(cells)
    for rx in (_QUERY, _PLACE):
        m = rx.search(text)
        if m:
            lat, lng = to_float(m.group(1)), to_float(m.group(2))
            if lat is not None and lng is not None:
                return lat, lng
    m = _DMS.search(text)
    if m:
        d1, m1, s1, h1, d2, m2, s2, h2 = m.groups()
        lat = (int(d1) + int(m1) / 60 + float(s1) / 3600) * (-1 if h1 == "S" else 1)
        lng = (int(d2) + int(m2) / 60 + float(s2) / 3600) * (-1 if h2 in "WO" else 1)
        return lat, lng
    return None


def resolve_short(url: str) -> Optional[str]:
    """Para onde o link curto do Google Maps redireciona (sem seguir; None se não redirecionar)."""
    import requests
    r = requests.get(url, headers=UA, timeout=HTTP_TIMEOUT, allow_redirects=False)
    return r.headers.get("Location")


def parse(text: str, bbox=None, resolve: Optional[Callable[[str], Optional[str]]] = None) -> List[Camera]:
    """CSV da planilha -> radares. Linha sem código "SEnnn" (cabeçalho, linha vazia) fica de fora.
    `resolve` abre o link curto (maps.app.goo.gl) da linha que não tem a coordenada escrita."""
    out: List[Camera] = []
    seen = set()
    for row in csv.reader(io.StringIO(text)):
        if not row or not re.match(r"\s*SE\d+", row[0]):
            continue
        p = _point(row[4:])
        short = _SHORT.search(" ".join(row[4:]))
        if p is None and short and resolve is not None:
            try:
                p = _point([resolve(short.group(0)) or ""])
            except Exception:  # noqa: BLE001 — um link curto que falha só tira aquele radar
                p = None
        if p is None or not in_br(*p) or not in_bbox(bbox, *p):
            continue
        key = (round(p[0], 6), round(p[1], 6))
        if key in seen:
            continue
        seen.add(key)
        m = _SPEED.search(row[3] if len(row) > 3 else "")
        limit = int(m.group(1)) if m and 20 <= int(m.group(1)) <= 130 else None
        out.append(Camera(key[0], key[1], CameraKind.FIXED, limit, "DER-SE", True,
                          source_ref=("DER-SE", row[0].strip())))
    return out


def load(raw_dir: str, bbox: Optional[Tuple[float, float, float, float]] = None
         ) -> Tuple[List[Camera], List[Limit]]:
    url = csv_url(get_bytes(PAGE).decode("utf-8", "replace"))
    cams = parse(get_bytes(url).decode("utf-8-sig", "replace"), bbox, resolve_short)
    if not cams:
        raise RuntimeError(f"DER-SE: nenhum radar lido de {url} (formato mudou?)")
    return cams, []


def fetch(ctx: BuildContext) -> SourceData:
    """Contrato das fontes (datakit/context.py)."""
    return SourceData(*load(ctx.raw_dir))
