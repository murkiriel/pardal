"""Prefeitura do Rio de Janeiro — limites por trecho de rua e radares da cidade.

* Limites: camada "Trechos de Logradouros" (IPP, CC-BY 4.0) com `velocidade_regulamentada`
  em ~85% dos 132 mil trechos. Cada trecho vira pontos nos vértices, com um ponto extra a
  cada 150 m em trecho longo, igual ao que o OSM faz.
* Radares: lista da SMTR/CET-Rio em PDF (endereço, código, limite), geocodificada pelo
  geocodificador de número de porta da própria prefeitura. Endereço sem número ("ACESSO AO
  MERGULHÃO…") não é geocodificado: sem número, o ponto cairia no meio da rua inteira.
  Se o geocodificador da prefeitura não responder (o servidor pgeo3 ficou fora do ar em
  novembro de 2026) e não houver cópia guardada da última leitura boa (datakit/source_cache.py),
  os mesmos endereços são localizados pelo cadastro de endereços do IBGE (sources/cnefe.py, como
  os medidores do Inmetro), com aviso. Medido em 2026-11-08 contra os 344 radares publicados em
  outubro pelo geocodificador da prefeitura: mediana de 19 m, 89% a até 100 m. Havendo cópia, ela
  vale mais que o CNEFE: a falha sobe e o build usa a cópia.
"""
from __future__ import annotations

import functools
import io
import re
from typing import Callable, Iterable, List, Optional, Tuple

from datakit import limit_lines
from datakit.context import SourceData, BuildContext
from datakit.common.geo import rdp, sample_polyline
from datakit.common.model import Camera, CameraKind, Limit
from datakit.sources._http import get_bytes, get_json, get_text

SEGMENTS_URL = ("https://pgeo3.rio.rj.gov.br/arcgis/rest/services/CadLog/"
                "Trechos_Logradouros/MapServer/0/query")
GEOCODE = ("https://pgeo3.rio.rj.gov.br/arcgis/rest/services/Geocode/Geocode_NP/"
           "GeocodeServer/findAddressCandidates")
LIST_PAGE = "https://cetrio.prefeitura.rio/fiscalizacao-eletronica/"
CITY = "RIO DE JANEIRO"
PAGE = 2000
MAX_GAP_M = 150.0
MIN_SCORE = 95.0


# ── limites ──────────────────────────────────────────────────────────────────

def segment_points(paths: List[List[List[float]]], kmh: int) -> List[Limit]:
    """Geometria ArcGIS (paths de [lng, lat]) -> pontos de limite. Puro, testado."""
    out: List[Limit] = []
    for path in paths:
        pts = [(y, x) for x, y in path]
        if len(pts) < 2:
            continue
        for lat, lng in sample_polyline(rdp(pts, 10.0), MAX_GAP_M) if len(pts) > 1 else pts:
            out.append(Limit(round(lat, 6), round(lng, 6), kmh, "RIO"))
    return out


def segment_lines(paths: List[List[List[float]]], kmh: int) -> List[limit_lines.Piece]:
    """Geometria ArcGIS (paths de [lng, lat]) -> trechos de limite (limites_trechos.csv). Puro, testado."""
    key = limit_lines.Key(kmh, "RIO", False, None, False, "", None)
    out = []
    for path in paths:
        piece = limit_lines.from_points([(y, x) for x, y in path], key)
        if piece is not None:
            out.append(piece)
    return out


@functools.lru_cache(maxsize=1)
def _segments() -> Tuple[Tuple[int, tuple], ...]:
    """(limite, paths) de cada trecho de logradouro com velocidade regulamentada. Lido uma vez por execução: os pontos
    (load_limits) e as linhas (load_limit_lines) saem da mesma leitura. Falha não fica guardada."""
    from datakit.sources._arcgis import query_all
    out = []
    for ft in query_all(SEGMENTS_URL, {"where": "velocidade_regulamentada > 0",
                                       "outFields": "velocidade_regulamentada", "outSR": 4326},
                        page=PAGE, order_by="objectid"):
        kmh = (ft.get("attributes") or {}).get("velocidade_regulamentada")
        paths = (ft.get("geometry") or {}).get("paths") or []
        if isinstance(kmh, int) and 10 <= kmh <= 130:
            out.append((kmh, tuple(map(tuple, paths))))
    return tuple(out)


def load_limits() -> List[Limit]:
    out: List[Limit] = []
    for kmh, paths in _segments():
        out.extend(segment_points([list(p) for p in paths], kmh))
    return out


def load_limit_lines() -> List[limit_lines.Piece]:
    """Os trechos de logradouro com limite como linhas, juntados quando seguidos e de mesmo limite."""
    out: List[limit_lines.Piece] = []
    for kmh, paths in _segments():
        out.extend(segment_lines([list(p) for p in paths], kmh))
    return limit_lines.join(out)


# ── radares ──────────────────────────────────────────────────────────────────

_SECTIONS = (
    ("lombada eletr", CameraKind.FIXED),
    ("medidor velocidade", CameraKind.FIXED),
    ("avanço de sinal", CameraKind.RED_LIGHT),
)
_LINE = re.compile(r"^(?P<addr>.+?)\s*\((?P<code>\d{6,})\)\s*(?:(?P<kmh>\d{2,3})\s+(?!HORAS))?")
_HOURS = re.compile(r"^(\d{1,2}H\b|AS \d|DIAS UTEIS|DE \d|SABADO|DOMINGO|E \d)")
_LABELS = ("sexta", "segunda", "terça", "quarta", "quinta", "sábado", "domingo",
           "pontos fiscalizados", "permitida", "horário", "funcionamento", "velocidade")


def parse_list(lines: Iterable[str]) -> List[Tuple[str, CameraKind, Optional[int]]]:
    """Texto do PDF -> (endereço, tipo, limite). Títulos de seção são as únicas linhas fora
    de maiúsculas; seções que não são de velocidade nem de avanço de sinal (faixa exclusiva,
    carga, conversão…) ficam de fora. Linha de endereço quebrada é juntada até o
    "(código)"; sobras de horário ("21H, SABADO 6H") são ignoradas. Puro, testado."""
    out = []
    kind: Optional[CameraKind] = None
    buf = ""
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        low = line.lower()
        if line != line.upper():
            if not low.startswith(_LABELS):
                kind = next((k for n, k in _SECTIONS if low.startswith(n)), None)
                buf = ""
            continue
        if not buf and _HOURS.match(line):
            continue
        buf = f"{buf} {line}".strip()
        m = _LINE.match(buf)
        if m is None:
            if len(buf) > 400:
                buf = ""
            continue
        if kind is not None:
            kmh = int(m.group("kmh")) if m.group("kmh") else None
            out.append((m.group("addr").strip(), kind, kmh if kmh and 20 <= kmh <= 130 else None))
        buf = ""
    return out


def geocode_query(addr: str) -> Optional[str]:
    """'AVENIDA AREIA BRANCA,PROXIMO AO Nº 1672 - SENTIDO X' -> 'AVENIDA AREIA BRANCA 1672'.
    None se não houver número de porta. Puro, testado."""
    street = addr.split(",")[0].strip()
    m = re.search(r"N[º°O]?\.?\s*(\d{1,5})", addr, re.I)
    if not street or not m:
        return None
    return f"{street} {m.group(1)}"


def _geocode(q: str) -> Optional[Tuple[float, float]]:
    j = get_json(GEOCODE, params={"SingleLine": q, "outSR": 4326, "f": "json", "maxLocations": 1}, timeout=60)
    cands = j.get("candidates") or []
    if not cands or cands[0].get("score", 0) < MIN_SCORE:
        return None
    loc = cands[0]["location"]
    return loc["y"], loc["x"]


def _cnefe_geocoder(addrs: List[str], raw_dir: str) -> Callable[[str], Optional[Tuple[float, float]]]:
    """Geocodificador de reserva: "rua + número" pelo CNEFE do município do Rio (sources/cnefe.py)."""
    from datakit.common.address import parse_number
    from datakit.sources import cnefe
    href = cnefe.file_for(CITY, cnefe.municipality_files("RJ", raw_dir))
    if href is None:
        raise RuntimeError(f"CNEFE sem arquivo para {CITY}")
    wanted = [n[0] for n in (parse_number(a) for a in addrs) if n]
    streets = cnefe.read_streets(cnefe.ensure("RJ", href, raw_dir), wanted)

    def geocode(addr: str) -> Optional[Tuple[float, float]]:
        numbered = parse_number(addr)
        street = cnefe.match_street(numbered[0], streets) if numbered else None
        return cnefe.locate_number(streets[street], numbered[1]) if numbered and street else None
    return geocode


def locate(items: List[Tuple[str, CameraKind, Optional[int]]],
           primary: Callable[[str], Optional[Tuple[float, float]]],
           fallback: Callable[[List[str]], Callable[[str], Optional[Tuple[float, float]]]],
           ) -> Tuple[List[Camera], Optional[BaseException]]:
    """(radares, erro do geocodificador da prefeitura ou None). `primary(consulta)` é o da prefeitura;
    no primeiro erro dele (servidor fora, não "endereço não achado"), todos os endereços passam para
    `fallback(endereços)(endereço)`. Puro dado os geocodificadores, testado."""
    usable = [(addr, kind, kmh, q) for addr, kind, kmh in items if (q := geocode_query(addr)) is not None]
    seen: dict = {}
    error: Optional[BaseException] = None
    for _addr, _kind, _kmh, q in usable:
        if q in seen:
            continue
        try:
            seen[q] = primary(q)
        except Exception as e:  # noqa: BLE001 — servidor fora: decide abaixo
            error = e
            break
    if error is not None:
        backup = fallback([addr for addr, _k, _l, _q in usable])
        points = {addr: backup(addr) for addr, _k, _l, _q in usable}
    else:
        points = {addr: seen[q] for addr, _k, _l, q in usable}
    out: List[Camera] = []
    for addr, kind, kmh, _q in usable:
        p = points[addr]
        if p is not None:
            out.append(Camera(round(p[0], 6), round(p[1], 6), kind, kmh, "RIO", True))
    return out, error


def _latest_pdf_url() -> str:
    html = get_text(LIST_PAGE, timeout=60)
    urls = re.findall(r"https?://[^\"'<> ]+ListagemSMTR\.pdf", html)
    if not urls:
        raise RuntimeError("lista de radares do Rio não encontrada")
    return max(urls)


def load_cameras(raw_dir: str = "data/raw", cnefe_backup: bool = True) -> List[Camera]:
    """Radares da lista da CET-Rio. `cnefe_backup`: com o geocodificador da prefeitura fora, localiza
    pelo CNEFE (True) ou deixa a falha subir (False, quando há cópia guardada melhor que o CNEFE)."""
    import pypdf

    pdf = pypdf.PdfReader(io.BytesIO(get_bytes(_latest_pdf_url())))
    lines = [ln for page in pdf.pages for ln in (page.extract_text() or "").splitlines()]

    def backup(addrs: List[str]) -> Callable[[str], Optional[Tuple[float, float]]]:
        if not cnefe_backup:
            raise RuntimeError("geocodificador da prefeitura fora do ar")
        return _cnefe_geocoder(addrs, raw_dir)
    cams, error = locate(parse_list(lines), _geocode, backup)
    if error is not None:
        from datakit import failures
        failures.warn("RIO", f"geocodificador da prefeitura falhou ({type(error).__name__}); "
                             f"{len(cams)} endereços localizados pelo CNEFE do IBGE")
    return cams


def load(raw_dir: str, bbox=None, cnefe_backup: bool = True):
    """Interface das fontes oficiais de radar (build.OFFICIAL)."""
    return load_cameras(raw_dir, cnefe_backup), []


def fetch(ctx: BuildContext) -> SourceData:
    """Contrato das fontes (datakit/context.py). O CNEFE só entra sem cópia guardada da fonte."""
    import os
    from datakit import source_cache
    has_copy = os.path.exists(source_cache.path_for(ctx.raw_dir, "RIO"))
    return SourceData(*load(ctx.raw_dir, cnefe_backup=not has_copy))
