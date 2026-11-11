"""O pacote de cada estado num banco SQLite: `pardal-<UF>.sqlite.zst`, só na release.

Os CSVs continuam iguais, byte a byte. O banco traz os mesmos registros de todos os arquivos do estado numa tabela só
(`event`), com:
- um id estável entre gerações (a chave de cada registro em Event.key, o número em stable_id);
- os campos de segurança que dá para tirar dos dados sem inventar: `direction_scope`,
  `position_accuracy_m`, `confidence`, `observed_at`, `valid_from`, `valid_until`;
- o id do registro na fonte que o publicou (`source_id`), onde o leitor da fonte o tem (common/model.py, source_ref);
- um índice espacial por célula do zoom 13 (`event_cell`), no piso técnico do Sabiá: SQLite 3.22 (Android 10), sem
  FTS5 e sem R-Tree, arquivo em modo rollback (journal DELETE, não WAL).

Coordenadas numa ordem só: lat e lng em colunas separadas, WGS84, inteiros em graus x 100.000 (a convenção do Sabiá);
as linhas (trechos) num blob de int32 little-endian lat, lng, lat, lng... na mesma escala, sem biblioteca de WKT. O
formato completo, com a regra do id e como consultar por proximidade, está em docs/FORMATO_SQLITE.md.

Duas entradas, o mesmo banco:
- no build, das listas do pacote (build_pack.py), com o source_id dos leitores que o têm;
- dos CSVs já publicados (`python run.py datakit.build_sqlite --states ../estados ...`), sem source_id (o CSV não o
  traz): serve para gerar o banco de uma edição publicada sem as fontes brutas.
Os dois caminhos formatam as coordenadas como o CSV antes de arredondar, e dão o mesmo banco para os registros sem
source_id (testado).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import sqlite3
import struct
import sys
import time
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from datakit.common.model import (AccidentZone, Bump, Camera, CameraKind, EnforcementCamera, Hazard, Limit, LimitLine,
                                  PotholeZone, RadarZone, Struct, Toll, parse_dir, source_parts)

# Sobe quando muda algo que um leitor feito para a versão anterior não entenderia (tabela ou coluna renomeada ou
# removida, valor que muda de significado, a regra do id). Tabela ou coluna nova não sobe.
SCHEMA_VERSION = 1
SCALE = 100_000        # graus x 100.000 (5 casas, ~1 m), como o Sabiá
CELL_ZOOM = 13         # o tile do zoom 13 (~4 a 5 km de lado no Brasil), como o Sabiá
SQLITE_FILE = "pardal.sqlite"   # dentro do pacote (data/packs/<UF>/); publicado compactado com o nome de release_name
ZSTD_LEVEL = 19
ATTRIBUTION = ("Pardal: © colaboradores do OpenStreetMap (ODbL 1.0) e as fontes abertas listadas no README "
               "(DNIT, ANTT, PRF, Inmetro, IBGE, DERs e prefeituras)")

# Os tipos de registro e o CSV do pacote que traz os mesmos registros (a conferência das contagens).
CAMERA = "CAMERA"
SPEED_LIMIT = "SPEED_LIMIT"
SPEED_LIMIT_LINE = "SPEED_LIMIT_LINE"
STRUCTURE = "STRUCTURE"
BUMP = "BUMP"
HAZARD = "HAZARD"
TOLL = "TOLL"
PORTABLE_RADAR_ZONE = "PORTABLE_RADAR_ZONE"
POTHOLE_ZONE = "POTHOLE_ZONE"
MOTO_ACCIDENT_ZONE = "MOTO_ACCIDENT_ZONE"
ENFORCEMENT_CAMERA = "ENFORCEMENT_CAMERA"
TYPE_FILES = {
    CAMERA: "radares.csv", SPEED_LIMIT: "limites.csv", SPEED_LIMIT_LINE: "limites_trechos.csv",
    STRUCTURE: "estruturas.csv", BUMP: "lombadas.csv", HAZARD: "pontos_atencao.csv", TOLL: "pedagios.csv",
    PORTABLE_RADAR_ZONE: "radar_portatil.csv", POTHOLE_ZONE: "buracos.csv", MOTO_ACCIDENT_ZONE: "acidentes_moto.csv",
    ENFORCEMENT_CAMERA: "cameras_fiscalizacao.csv",
}

SCHEMA = """
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE event(
  seq INTEGER PRIMARY KEY,
  id INTEGER NOT NULL,
  type TEXT NOT NULL,
  kind TEXT,
  lat INTEGER NOT NULL,
  lng INTEGER NOT NULL,
  end_lat INTEGER,
  end_lng INTEGER,
  coords BLOB,
  source TEXT NOT NULL,
  source_id TEXT,
  source_id_from TEXT,
  active INTEGER NOT NULL,
  limit_kmh INTEGER,
  limit_low_kmh INTEGER,
  estimated INTEGER,
  direction_deg INTEGER,
  direction_scope TEXT NOT NULL,
  position_accuracy_m INTEGER,
  confidence TEXT,
  observed_at TEXT,
  valid_from TEXT,
  valid_until TEXT,
  name TEXT,
  road TEXT,
  km_from REAL,
  km_to REAL,
  km_direction TEXT,
  highway TEXT,
  oneway INTEGER,
  accidents INTEGER,
  rider_deaths INTEGER,
  period TEXT,
  speed_fines_12m INTEGER
);
CREATE TABLE event_cell(cell INTEGER NOT NULL, seq INTEGER NOT NULL, PRIMARY KEY(cell, seq)) WITHOUT ROWID;
"""
COLUMNS = ("seq", "id", "type", "kind", "lat", "lng", "end_lat", "end_lng", "coords", "source", "source_id",
           "source_id_from", "active", "limit_kmh", "limit_low_kmh", "estimated", "direction_deg", "direction_scope",
           "position_accuracy_m", "confidence", "observed_at", "valid_from", "valid_until", "name", "road", "km_from",
           "km_to", "km_direction", "highway", "oneway", "accidents", "rider_deaths", "period", "speed_fines_12m")
VALUE_COLUMNS = COLUMNS[2:]
_VALUE_INDEX = {c: i for i, c in enumerate(VALUE_COLUMNS)}
# O que um banco do Pardal nunca pode usar: o SQLite do Android 10 (3.22) não tem.
NEWER_FEATURES = ("fts5", "rtree", "generated always", ") strict")


def release_name(uf: str) -> str:
    """O nome do arquivo na release: pardal-<UF>.sqlite.zst."""
    return f"pardal-{uf.upper()}.sqlite.zst"


@dataclass
class PackData:
    """As listas de um pacote de UF, as mesmas que viram os CSVs (já sem repetidos, na ordem do CSV)."""
    cameras: List[Camera] = field(default_factory=list)
    limits: List[Limit] = field(default_factory=list)
    limit_lines: List[LimitLine] = field(default_factory=list)
    structs: List[Struct] = field(default_factory=list)
    bumps: List[Bump] = field(default_factory=list)
    hazards: List[Hazard] = field(default_factory=list)
    tolls: List[Toll] = field(default_factory=list)
    radar_zones: List[RadarZone] = field(default_factory=list)
    potholes: List[PotholeZone] = field(default_factory=list)
    moto_accidents: List[AccidentZone] = field(default_factory=list)
    enforcement_cameras: List[EnforcementCamera] = field(default_factory=list)


@dataclass
class Dates:
    """A data do dado de cada fonte (`source_dates` do catálogo: {rótulo: AAAA-MM-DD}) e a do extrato do OSM."""
    sources: Dict[str, str] = field(default_factory=dict)
    osm: Optional[str] = None


# ── coordenadas e células ──────────────────────────────────────────────────────────────────────────────────────────

def e5(value: float, decimals: int = 6) -> int:
    """Graus -> inteiro x 100.000, a partir do número como o CSV o escreve (6 casas nos pontos, 5 nas linhas): o banco
    feito das listas do build e o feito dos CSVs publicados dão o mesmo inteiro."""
    return round(float(f"{value:.{decimals}f}") * SCALE)


def _tile(lat: float, lng: float) -> Tuple[float, float]:
    n = 1 << CELL_ZOOM
    lat_rad = math.radians(max(-85.05112878, min(85.05112878, lat)))
    return (lng + 180.0) / 360.0 * n, (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n


def cell(lat_e5: int, lng_e5: int) -> int:
    """A célula do ponto: o tile do zoom 13 como um número, x * 8192 + y (a mesma conta do Sabiá, sobre as coordenadas
    gravadas no banco, divididas por 100.000)."""
    n = 1 << CELL_ZOOM
    fx, fy = _tile(lat_e5 / SCALE, lng_e5 / SCALE)
    x = min(n - 1, max(0, int(fx)))
    y = min(n - 1, max(0, int(fy)))
    return x * n + y


def line_cells(points: Sequence[Tuple[int, int]]) -> Set[int]:
    """As células por onde a linha passa (pontos em inteiros x 100.000): cada segmento é amostrado a cada 1/4 de
    célula, e um passo em diagonal acrescenta as duas células do canto (a linha pode cortá-lo)."""
    n = 1 << CELL_ZOOM
    out: Set[int] = set()
    prev: Optional[Tuple[int, int]] = None

    def add(x: int, y: int) -> None:
        nonlocal prev
        x, y = min(n - 1, max(0, x)), min(n - 1, max(0, y))
        if prev is not None and prev[0] != x and prev[1] != y:
            out.add(prev[0] * n + y)
            out.add(x * n + prev[1])
        out.add(x * n + y)
        prev = (x, y)

    tiles = [_tile(lat / SCALE, lng / SCALE) for lat, lng in points]
    if not tiles:
        return out
    add(int(tiles[0][0]), int(tiles[0][1]))
    for (x0, y0), (x1, y1) in zip(tiles, tiles[1:]):
        steps = max(1, math.ceil(max(abs(x1 - x0), abs(y1 - y0)) * 4))
        for k in range(1, steps + 1):
            t = k / steps
            add(int(x0 + (x1 - x0) * t), int(y0 + (y1 - y0) * t))
    return out


def neighborhood(lat: float, lng: float) -> List[int]:
    """As 9 células em volta de um ponto (graus): a consulta por proximidade (docs/FORMATO_SQLITE.md)."""
    n = 1 << CELL_ZOOM
    c = cell(round(lat * SCALE), round(lng * SCALE))
    x, y = divmod(c, n)
    return sorted((x + dx) * n + (y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                  if 0 <= x + dx < n and 0 <= y + dy < n)


def encode_line(points: Sequence[Tuple[int, int]]) -> bytes:
    """int32 little-endian lat, lng, lat, lng... (x 100.000), na ordem da linha: o `street_line.coords` do Sabiá."""
    return struct.pack(f"<{2 * len(points)}i", *(v for p in points for v in p))


def decode_line(blob: bytes) -> List[Tuple[int, int]]:
    flat = struct.unpack(f"<{len(blob) // 4}i", blob)
    return list(zip(flat[0::2], flat[1::2]))


# ── id estável ─────────────────────────────────────────────────────────────────────────────────────────────────────

def stable_id(key: Sequence[str]) -> int:
    """Os 63 bits mais altos do sha256 da chave (partes unidas por U+001F): um inteiro positivo que cabe num Long."""
    digest = hashlib.sha256("\x1f".join(key).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") >> 1


def _km(v: float) -> str:
    return f"{v:.1f}"


# ── campos derivados (regras em docs/FORMATO_SQLITE.md) ──────────────────────────────────────────────────────────────

# Rótulo do `source_dates` de cada código de fonte, por tipo de registro. Radar: o código é o nome da fonte no
# build.OFFICIAL, menos estes (testado contra o build).
CAMERA_DATE_LABELS = {"PMJP": "capitais", "PMF": "capitais", "PCR": "capitais", "CURITIBA": "capitais",
                      "PRF": "PRF (radares das concessões)"}
LIMIT_DATE_LABELS = {"ANTT": "ANTT placas", "RIO": "Rio trechos", "CET-SP": "CET-SP limites"}
LINE_DATE_LABELS = {"ANTT": "ANTT placas (trechos)", "RIO": "Rio trechos (linhas)", "CET-SP": "CET-SP limites (linhas)"}
TOLL_DATE_LABELS = {"ANTT": "ANTT (pedágios)"}
ENFORCEMENT_DATE_LABELS = {"CET-SP:CAM": "CET-SP (outras câmeras)", "BHTRANS:CAM": "BHTRANS (outras câmeras)",
                           "CURITIBA:CAM": "Curitiba (outras câmeras)"}
ZONE_DATE_LABELS = {"PRF": "PRF (trechos de radar portátil)", "SIE-SC": "SIE-SC (radar portátil)"}

# position_accuracy_m: só onde a posição veio de um método indireto cujo erro foi medido (FONTES.md, README).
ACCURACY_INMETRO_ADDRESS_M = 100   # endereço do Inmetro no CNEFE: mediana 23 m, 89% a <= 100 m (5 capitais)
ACCURACY_SNV_KM_M = 900            # rodovia + km no SNV: mediana 226 m, p75 873 m (contra 1.774 radares do DNIT)
ACCURACY_OSM_MILESTONE_M = 200     # km entre marcos quilométricos do OSM: mediana 83 m, 25% acima de 200 m


def observed_at(source: str, dates: Dates, labels: Dict[str, str], same_name: bool = False) -> Optional[str]:
    """A data mais nova entre as fontes do registro que têm data: a do extrato para o OSM (OSM, OSM:zone, OSM:class);
    o `source_dates` pelo rótulo da fonte (labels; com same_name, o próprio código quando não está em labels); nada
    para o Inmetro (o catálogo não guarda a data dele)."""
    found = []
    for part in source_parts(source):
        if part == "OSM" or part.startswith("OSM:"):
            found.append(dates.osm)
        elif part in labels:
            found.append(dates.sources.get(labels[part]))
        elif same_name:
            found.append(dates.sources.get(part))
    known = [d for d in found if d]
    return max(known) if known else None


def confidence(source: str, estimated: bool = False) -> str:
    """LOW: valor estimado (não sinalizado). HIGH: duas ou mais fontes independentes (`+` na fonte), ou uma fonte
    oficial sozinha. MEDIUM: só o OSM (mapeamento colaborativo sem confirmação oficial), ou só o Inmetro (o medidor
    existe, mas a posição veio do endereço e ~1 em 10 é um radar já conhecido posto longe)."""
    if estimated:
        return "LOW"
    parts = source_parts(source)
    if len(parts) >= 2:
        return "HIGH"
    if not parts or parts[0] == "OSM" or parts[0].startswith("OSM:") or parts[0] == "INMETRO":
        return "MEDIUM"
    return "HIGH"


def camera_accuracy(source: str) -> Optional[int]:
    """Radar só do Inmetro: a posição é a do endereço. Radar do DER-MG (sem outra fonte com coordenada): posto por
    rodovia + km. O resto (coordenada publicada pelo órgão ou mapeada no OSM) não tem medida por registro: nulo."""
    parts = set(source_parts(source))
    if parts == {"INMETRO"}:
        return ACCURACY_INMETRO_ADDRESS_M
    if parts - {"INMETRO"} == {"DER-MG"}:
        return ACCURACY_SNV_KM_M
    return None


def _scope(direction: Optional[int], unknown: str = "UNKNOWN") -> str:
    return "ONE" if direction is not None else unknown


def _ref(obj) -> Tuple[Optional[str], Optional[str]]:
    ref = getattr(obj, "source_ref", None)
    return (ref[1], ref[0]) if ref else (None, None)


# ── registros ──────────────────────────────────────────────────────────────────────────────────────────────────────

class Event:
    """Um registro do banco: `values` na ordem de VALUE_COLUMNS, a chave do id (`key`), as células do índice (`cells`)
    e, depois de assign_ids, o id estável."""
    __slots__ = ("key", "cells", "values", "id")

    def __init__(self, key: Tuple[str, ...], cells: Iterable[int], fields: Dict[str, object]) -> None:
        self.key = key
        self.cells = tuple(sorted(set(cells)))
        self.values = tuple(fields.get(c) for c in VALUE_COLUMNS)
        self.id = 0

    def get(self, column: str):
        return self.values[_VALUE_INDEX[column]]


def _point_key(kind: str, source: str, ref, lat: int, lng: int, *extra: str) -> Tuple[str, ...]:
    if ref:
        return (kind, ref[0], "id", ref[1], *extra)
    return (kind, source, "pos", str(lat), str(lng), *extra)


def _dir_text(direction: Optional[int]) -> str:
    return "" if direction is None else str(direction)


def _camera(c: Camera, dates: Dates) -> Event:
    lat, lng = e5(c.lat), e5(c.lng)
    parts = source_parts(c.source)
    direction = None if c.direction_deg is None else int(c.direction_deg) % 360
    source_id, source_from = _ref(c)
    f: Dict[str, object] = {
        "type": CAMERA, "kind": c.kind.value, "lat": lat, "lng": lng, "source": c.source, "source_id": source_id,
        "source_id_from": source_from, "active": int(c.active), "limit_kmh": c.limit_kmh, "direction_deg": direction,
        "direction_scope": _scope(direction), "position_accuracy_m": camera_accuracy(c.source),
        "confidence": confidence(c.source), "observed_at": observed_at(c.source, dates, CAMERA_DATE_LABELS, True)}
    cells = [cell(lat, lng)]
    if c.end_lat is not None and c.end_lng is not None:
        f["end_lat"], f["end_lng"] = e5(c.end_lat), e5(c.end_lng)
        cells.append(cell(e5(c.end_lat), e5(c.end_lng)))
    return Event(_point_key(CAMERA, parts[0] if parts else "", c.source_ref, lat, lng), cells, f)


def _limit(x: Limit, dates: Dates) -> Event:
    lat, lng = e5(x.lat), e5(x.lng)
    direction = None if x.direction_deg is None else int(x.direction_deg) % 360
    f: Dict[str, object] = {
        "type": SPEED_LIMIT, "lat": lat, "lng": lng, "source": x.source, "active": 1, "limit_kmh": x.limit_kmh,
        "limit_low_kmh": x.low_kmh, "estimated": int(x.estimated), "direction_deg": direction,
        "direction_scope": _scope(direction, "BOTH"), "confidence": confidence(x.source, x.estimated),
        "observed_at": observed_at(x.source, dates, LIMIT_DATE_LABELS)}
    return Event((SPEED_LIMIT, x.source, "pos", str(lat), str(lng), _dir_text(direction)), [cell(lat, lng)], f)


def _line_points(points: Sequence[Tuple[float, float]]) -> List[Tuple[int, int]]:
    return [(e5(lat, 5), e5(lng, 5)) for lat, lng in points]


def _line_fields(kind: str, pts: List[Tuple[int, int]]) -> Dict[str, object]:
    """Os campos comuns de um trecho: o primeiro vértice como ponto e a linha inteira em `coords`."""
    return {"type": kind, "lat": pts[0][0], "lng": pts[0][1], "coords": encode_line(pts), "active": 1}


def geometry_digest(pts: Sequence[Tuple[int, int]]) -> str:
    """A geometria na chave do id do trecho de limite: sha256 de "lat,lng;lat,lng;..." (inteiros x 100.000)."""
    return hashlib.sha256(";".join(f"{a},{b}" for a, b in pts).encode()).hexdigest()


def _limit_line(ln: LimitLine, dates: Dates) -> Event:
    pts = _line_points(ln.points)
    direction = None if ln.direction_deg is None else int(ln.direction_deg) % 360
    f = _line_fields(SPEED_LIMIT_LINE, pts)
    f.update({"source": ln.source, "limit_kmh": ln.limit_kmh, "limit_low_kmh": ln.low_kmh,
              "estimated": int(ln.estimated), "direction_deg": direction, "direction_scope": _scope(direction, "BOTH"),
              "confidence": confidence(ln.source, ln.estimated), "highway": ln.highway or None,
              "observed_at": observed_at(ln.source, dates, LINE_DATE_LABELS),
              "oneway": None if ln.oneway is None else int(ln.oneway)})
    key = (SPEED_LIMIT_LINE, ln.source, "line", _dir_text(direction), geometry_digest(pts))
    return Event(key, line_cells(pts), f)


def _struct(s: Struct, dates: Dates) -> Event:
    a, b = (e5(s.lat1), e5(s.lng1)), (e5(s.lat2), e5(s.lng2))
    source_id, source_from = _ref(s)
    f: Dict[str, object] = {
        "type": STRUCTURE, "kind": s.kind, "lat": a[0], "lng": a[1], "end_lat": b[0], "end_lng": b[1],
        "source": "OSM", "source_id": source_id, "source_id_from": source_from, "active": 1,
        "direction_scope": "UNKNOWN", "confidence": confidence("OSM"), "observed_at": dates.osm}
    key = (STRUCTURE, "OSM", "id", s.source_ref[1]) if s.source_ref else \
        (STRUCTURE, "OSM", "pos", *(str(v) for v in (*a, *b)))
    return Event(key, line_cells([a, b]), f)


def _osm_point(kind: str, x, dates: Dates) -> Event:
    lat, lng = e5(x.lat), e5(x.lng)
    source_id, source_from = _ref(x)
    f: Dict[str, object] = {
        "type": kind, "kind": x.kind, "lat": lat, "lng": lng, "source": "OSM", "source_id": source_id,
        "source_id_from": source_from, "active": 1, "direction_scope": "UNKNOWN", "confidence": confidence("OSM"),
        "observed_at": dates.osm}
    return Event(_point_key(kind, "OSM", x.source_ref, lat, lng), [cell(lat, lng)], f)


def _toll(t: Toll, dates: Dates) -> Event:
    lat, lng = e5(t.lat), e5(t.lng)
    source_id, source_from = _ref(t)
    f: Dict[str, object] = {
        "type": TOLL, "kind": t.kind, "lat": lat, "lng": lng, "source": t.source, "source_id": source_id,
        "source_id_from": source_from, "active": 1, "direction_scope": "UNKNOWN", "confidence": confidence(t.source),
        "observed_at": observed_at(t.source, dates, TOLL_DATE_LABELS), "name": t.name or None}
    return Event(_point_key(TOLL, t.source, t.source_ref, lat, lng), [cell(lat, lng)], f)


def _enforcement(e: EnforcementCamera, dates: Dates) -> Event:
    lat, lng = e5(e.lat), e5(e.lng)
    source_id, source_from = _ref(e)
    f: Dict[str, object] = {
        "type": ENFORCEMENT_CAMERA, "kind": e.kind, "lat": lat, "lng": lng, "source": e.source,
        "source_id": source_id, "source_id_from": source_from, "active": int(e.active), "direction_scope": "UNKNOWN",
        "confidence": confidence(e.source), "observed_at": observed_at(e.source, dates, ENFORCEMENT_DATE_LABELS)}
    return Event(_point_key(ENFORCEMENT_CAMERA, e.source, e.source_ref, lat, lng, e.kind), [cell(lat, lng)], f)


def zone_source(road: str) -> str:
    """A fonte do trecho apto ao radar portátil: a PRF nas BRs, a SIE-SC nas SC (o radar_portatil.csv não traz a
    coluna; build.py junta as duas listas)."""
    return "SIE-SC" if road.upper().startswith("SC-") else "PRF"


def _radar_zone(z: RadarZone, dates: Dates) -> Event:
    source = zone_source(z.road)
    pts = _line_points(z.points)
    f = _line_fields(PORTABLE_RADAR_ZONE, pts)
    f.update({"source": source, "direction_scope": "UNKNOWN", "confidence": confidence(source),
              "position_accuracy_m": ACCURACY_OSM_MILESTONE_M if source == "SIE-SC" else ACCURACY_SNV_KM_M,
              "observed_at": observed_at(source, dates, ZONE_DATE_LABELS), "valid_from": z.valid_from or None,
              "road": z.road, "km_from": float(_km(z.km_from)), "km_to": float(_km(z.km_to)),
              "speed_fines_12m": z.speed_fines})
    return Event((PORTABLE_RADAR_ZONE, source, "km", z.road, _km(z.km_from), _km(z.km_to)), line_cells(pts), f)


def _pothole(z: PotholeZone, dates: Dates) -> Event:
    pts = _line_points(z.points)
    f = _line_fields(POTHOLE_ZONE, pts)
    f.update({"kind": z.level, "source": "DNIT", "direction_scope": "ONE", "confidence": confidence("DNIT"),
              "position_accuracy_m": ACCURACY_SNV_KM_M, "observed_at": z.month or None, "road": z.road,
              "km_from": float(_km(z.km_from)), "km_to": float(_km(z.km_to)), "km_direction": z.direction})
    key = (POTHOLE_ZONE, "DNIT", "km", z.road, z.direction, _km(z.km_from), _km(z.km_to))
    return Event(key, line_cells(pts), f)


def _accident(z: AccidentZone, dates: Dates) -> Event:
    pts = _line_points(z.points)
    f = _line_fields(MOTO_ACCIDENT_ZONE, pts)
    end = z.months.rsplit("/", 1)[-1].strip() if z.months else ""
    f.update({"source": "PRF", "direction_scope": "UNKNOWN", "confidence": confidence("PRF"),
              "position_accuracy_m": ACCURACY_SNV_KM_M, "observed_at": end or None, "road": z.road,
              "km_from": float(_km(z.km_from)), "km_to": float(_km(z.km_to)), "accidents": z.accidents,
              "rider_deaths": z.rider_deaths, "period": z.months or None})
    return Event((MOTO_ACCIDENT_ZONE, "PRF", "km", z.road, _km(z.km_from), _km(z.km_to)), line_cells(pts), f)


def events(data: PackData, dates: Optional[Dates] = None) -> List[Event]:
    """Os registros do banco, na ordem dos CSVs, com o id estável já atribuído."""
    dates = dates or Dates()
    out: List[Event] = []
    out += [_camera(c, dates) for c in data.cameras]
    out += [_limit(x, dates) for x in data.limits]
    out += [_limit_line(x, dates) for x in data.limit_lines if x.points]
    out += [_struct(x, dates) for x in data.structs]
    out += [_osm_point(BUMP, x, dates) for x in data.bumps]
    out += [_osm_point(HAZARD, x, dates) for x in data.hazards]
    out += [_toll(x, dates) for x in data.tolls]
    out += [_radar_zone(x, dates) for x in data.radar_zones if x.points]
    out += [_pothole(x, dates) for x in data.potholes if x.points]
    out += [_accident(x, dates) for x in data.moto_accidents if x.points]
    out += [_enforcement(x, dates) for x in data.enforcement_cameras]
    assign_ids(out)
    return out


def _content(ev: Event) -> str:
    return json.dumps([v.hex() if isinstance(v, bytes) else v for v in ev.values], ensure_ascii=False)


def assign_ids(evs: List[Event]) -> None:
    """id = stable_id(chave). Chave repetida (dois registros que a regra não separa, ex.: o mesmo trecho cortado em
    dois pedaços com os mesmos km): o primeiro na ordem do conteúdo fica com a chave e os outros ganham "#2", "#3"...
    Duas chaves diferentes com o mesmo id (63 bits: improvável) é erro."""
    groups: Dict[Tuple[str, ...], List[Event]] = {}
    for ev in evs:
        groups.setdefault(ev.key, []).append(ev)
    seen: Dict[int, Tuple[str, ...]] = {}
    for key, members in groups.items():
        if len(members) > 1:
            members.sort(key=_content)
        for n, ev in enumerate(members, 1):
            ev.key = key if n == 1 else (*key, f"#{n}")
            ev.id = stable_id(ev.key)
            other = seen.setdefault(ev.id, ev.key)
            if other != ev.key:
                raise ValueError(f"colisão de id estável: {other} x {ev.key}")


# ── banco ──────────────────────────────────────────────────────────────────────────────────────────────────────────

def write(path: str, uf: str, data: PackData, dates: Optional[Dates] = None, built_at: str = "") -> Dict[str, int]:
    """Grava o banco do estado (substitui um anterior) e devolve as contagens por tipo. Os registros vão em ordem de
    célula (a do ponto), tipo e id: `seq` segue essa ordem, e quem consulta uma região lê páginas vizinhas do arquivo.
    O mesmo conteúdo dá sempre o mesmo arquivo (no mesmo SQLite): sem data de gravação dentro."""
    evs = events(data, dates)
    lat_i, lng_i, type_i = _VALUE_INDEX["lat"], _VALUE_INDEX["lng"], _VALUE_INDEX["type"]
    evs.sort(key=lambda ev: (cell(ev.values[lat_i], ev.values[lng_i]), ev.values[type_i], ev.id))  # type: ignore[arg-type]
    partial = path + ".parcial"
    for p in (partial, partial + "-journal"):
        if os.path.exists(p):
            os.remove(p)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    db = sqlite3.connect(partial)
    try:
        db.executescript("PRAGMA page_size=4096; PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;")
        db.executescript(SCHEMA)
        meta = {"schema_version": str(SCHEMA_VERSION), "uf": uf.upper(), "built_at": built_at,
                "crs": "EPSG:4326", "coord_scale": str(SCALE), "cell_zoom": str(CELL_ZOOM), "attribution": ATTRIBUTION}
        db.executemany("INSERT INTO meta VALUES(?,?)", sorted(meta.items()))
        marks = ",".join("?" * len(COLUMNS))
        db.executemany(f"INSERT INTO event({','.join(COLUMNS)}) VALUES({marks})",
                       ((seq, ev.id, *ev.values) for seq, ev in enumerate(evs, 1)))
        db.executemany("INSERT INTO event_cell VALUES(?,?)",
                       sorted((c, seq) for seq, ev in enumerate(evs, 1) for c in ev.cells))
        db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        db.commit()
        db.execute("PRAGMA journal_mode=DELETE")
        db.execute("VACUUM")
    finally:
        db.close()
    os.replace(partial, path)
    counts = {t: 0 for t in TYPE_FILES}
    for ev in evs:
        counts[ev.values[type_i]] += 1  # type: ignore[index]
    return counts


def compress(src: str, dest: str) -> None:
    """zstd nível 19, com o tamanho original e o checksum no quadro, sem threads: o mesmo banco dá sempre o mesmo
    arquivo (como o Sabiá; o app já abre .sqlite.zst com o zstd-jni)."""
    import zstandard
    cctx = zstandard.ZstdCompressor(level=ZSTD_LEVEL, write_checksum=True, write_content_size=True)
    partial = dest + ".parcial"
    with open(src, "rb") as fin, open(partial, "wb") as fout:
        cctx.copy_stream(fin, fout, size=os.path.getsize(src))
    os.replace(partial, dest)


def decompress(src: str, dest: str) -> None:
    import zstandard
    with open(src, "rb") as fin, open(dest, "wb") as fout:
        zstandard.ZstdDecompressor().copy_stream(fin, fout)


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ── conferência ────────────────────────────────────────────────────────────────────────────────────────────────────

def csv_count(path: str) -> int:
    """Linhas de dado de um CSV (sem o cabeçalho); 0 se o arquivo não existe (o pacote não publica arquivo vazio)."""
    if not os.path.exists(path):
        return 0
    with open(path, newline="", encoding="utf-8") as f:
        return max(0, sum(1 for _ in csv.reader(f)) - 1)


def validate(path: str, csv_dir: str, csv_paths: Optional[Dict[str, str]] = None) -> Tuple[List[str], Dict[str, int]]:
    """(problemas, contagens por tipo) de um banco contra os CSVs da mesma geração em csv_dir: integrity_check,
    versão do esquema, modo rollback, nada que o SQLite 3.22 não tenha, todo registro no índice de células, e a
    contagem de cada tipo igual à de linhas do CSV correspondente (TYPE_FILES; `csv_paths` troca o caminho de algum
    tipo). Vazio = pode publicar."""
    problems: List[str] = []
    with open(path, "rb") as f:
        header = f.read(100)
    if header[18:20] != b"\x01\x01":
        problems.append(f"{os.path.basename(path)}: não está em modo rollback (bytes 18-19 = {header[18:20].hex()})")
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        check = db.execute("PRAGMA integrity_check").fetchall()
        if check != [("ok",)]:
            problems.append(f"integrity_check: {check[:3]}")
        meta = dict(db.execute("SELECT key, value FROM meta"))
        if meta.get("schema_version") != str(SCHEMA_VERSION):
            problems.append(f"schema_version {meta.get('schema_version')} (esperado {SCHEMA_VERSION})")
        for name, sql in db.execute("SELECT name, sql FROM sqlite_master WHERE sql IS NOT NULL"):
            text = " ".join(sql.lower().split())
            for needle in (*NEWER_FEATURES, "create virtual table"):
                if needle in text:
                    problems.append(f"{name} usa '{needle}', que o SQLite 3.22 do Android 10 não tem")
        counts = {t: 0 for t in TYPE_FILES}
        counts.update(dict(db.execute("SELECT type, count(*) FROM event GROUP BY type")))
        orphans = db.execute("SELECT count(*) FROM event WHERE seq NOT IN (SELECT seq FROM event_cell)").fetchone()[0]
        repeated = db.execute("SELECT count(*) - count(DISTINCT id) FROM event").fetchone()[0]
        if repeated:
            problems.append(f"{repeated} ids repetidos")
        if orphans:
            problems.append(f"{orphans} registros fora do índice de células")
    finally:
        db.close()
    for kind, name in TYPE_FILES.items():
        expected = csv_count((csv_paths or {}).get(kind) or os.path.join(csv_dir, name))
        if counts.get(kind, 0) != expected:
            problems.append(f"{kind}: {counts.get(kind, 0)} no banco, {expected} no {name}")
    unknown = set(counts) - set(TYPE_FILES)
    if unknown:
        problems.append(f"tipos desconhecidos: {sorted(unknown)}")
    return problems, counts


# ── a partir dos CSVs publicados ────────────────────────────────────────────────────────────────────────────────────

_WKT = re.compile(r"^\s*LINESTRING\s*\((.*)\)\s*$", re.I)


def parse_wkt(text: str) -> Tuple[Tuple[float, float], ...]:
    """LINESTRING(lng lat, ...) -> ((lat, lng), ...)."""
    m = _WKT.match(text or "")
    if not m:
        raise ValueError(f"WKT inesperado: {text[:60]!r}")
    out = []
    for pair in m.group(1).split(","):
        lng, lat = pair.split()
        out.append((float(lat), float(lng)))
    return tuple(out)


def _rows(folder: str, name: str) -> Iterable[Dict[str, str]]:
    path = os.path.join(folder, name)
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _int(v: Optional[str]) -> Optional[int]:
    v = (v or "").strip()
    return int(v) if v else None


def _float(v: Optional[str]) -> Optional[float]:
    v = (v or "").strip()
    return float(v) if v else None


def read_csv_dir(folder: str) -> PackData:
    """As listas de um pacote a partir dos CSVs de uma pasta de estado (estados/<UF>/ do repositório, mais o
    limites_trechos.csv do zip da release, se estiver lá). Cada objeto refaz exatamente a linha do CSV (testado)."""
    d = PackData()
    for r in _rows(folder, TYPE_FILES[CAMERA]):
        d.cameras.append(Camera(float(r["lat"]), float(r["lng"]), CameraKind(r["kind"]), _int(r.get("limit_kmh")),
                                r.get("source") or "", r.get("active", "1") != "0", _float(r.get("end_lat")),
                                _float(r.get("end_lng")), parse_dir(r.get("direction_deg"))))
    d.limits = [Limit.from_row(r) for r in _rows(folder, TYPE_FILES[SPEED_LIMIT])]
    for r in _rows(folder, TYPE_FILES[SPEED_LIMIT_LINE]):
        oneway = (r.get("oneway") or "").strip()
        d.limit_lines.append(LimitLine(parse_wkt(r["wkt"]), int(r["limit_kmh"]), r.get("source") or "",
                                       r.get("estimated") == "1", _int(r.get("limit_low_kmh")),
                                       parse_dir(r.get("direction_deg")), r.get("highway") or "",
                                       None if not oneway else oneway == "1"))
    d.structs = [Struct(float(r["lat1"]), float(r["lng1"]), float(r["lat2"]), float(r["lng2"]), r["kind"])
                 for r in _rows(folder, TYPE_FILES[STRUCTURE])]
    d.bumps = [Bump(float(r["lat"]), float(r["lng"]), r["kind"]) for r in _rows(folder, TYPE_FILES[BUMP])]
    d.hazards = [Hazard(float(r["lat"]), float(r["lng"]), r["kind"]) for r in _rows(folder, TYPE_FILES[HAZARD])]
    d.tolls = [Toll(float(r["lat"]), float(r["lng"]), r["kind"], r.get("name") or "", r.get("source") or "")
               for r in _rows(folder, TYPE_FILES[TOLL])]
    d.radar_zones = [RadarZone(r["road"], float(r["km_from"]), float(r["km_to"]), r.get("valid_from") or "",
                               parse_wkt(r["wkt"]), _int(r.get("speed_fines_12m")))
                     for r in _rows(folder, TYPE_FILES[PORTABLE_RADAR_ZONE])]
    d.potholes = [PotholeZone(r["road"], float(r["km_from"]), float(r["km_to"]), r["direction"], r["level"],
                              r.get("month") or "", parse_wkt(r["wkt"]))
                  for r in _rows(folder, TYPE_FILES[POTHOLE_ZONE])]
    d.moto_accidents = [AccidentZone(r["road"], float(r["km_from"]), float(r["km_to"]), int(r["accidents"]),
                                     int(r["rider_deaths"]), r.get("months") or "", parse_wkt(r["wkt"]))
                        for r in _rows(folder, TYPE_FILES[MOTO_ACCIDENT_ZONE])]
    d.enforcement_cameras = [EnforcementCamera(float(r["lat"]), float(r["lng"]), r["kind"], r.get("source") or "",
                                               r.get("active", "1") != "0")
                             for r in _rows(folder, TYPE_FILES[ENFORCEMENT_CAMERA])]
    return d


def osm_date(sources: Sequence[dict]) -> Optional[str]:
    """A data (AAAA-MM-DD) do extrato do OSM pelo `sources` do manifesto (Last-Modified da Geofabrik), ou None."""
    for s in sources:
        if str(s.get("name", "")).startswith("OSM/Geofabrik") and s.get("file_date"):
            try:
                return parsedate_to_datetime(str(s["file_date"])).date().isoformat()
            except (TypeError, ValueError):
                text = str(s["file_date"])
                return text[:10] if re.match(r"\d{4}-\d{2}-\d{2}", text) else None
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="datakit.build_sqlite",
                                 description="Gera os bancos SQLite por estado a partir dos CSVs já publicados.")
    ap.add_argument("--states", required=True, help="pasta estados/ (uma subpasta por UF, com os CSVs)")
    ap.add_argument("--lines", help="pasta com <UF>/limites_trechos.csv (extraídos dos zips da release); opcional")
    ap.add_argument("--catalog", help="catalogo.json da mesma edição (source_dates e built_at); opcional")
    ap.add_argument("--out", required=True, help="onde gravar pardal-<UF>.sqlite e pardal-<UF>.sqlite.zst")
    ap.add_argument("--uf", help="só estas UFs (GO,SP)")
    args = ap.parse_args(argv)

    catalog: dict = {}
    if args.catalog:
        with open(args.catalog, encoding="utf-8") as f:
            catalog = json.load(f)
    dates = Dates(sources=dict(catalog.get("source_dates") or {}))
    ufs = sorted(u for u in os.listdir(args.states) if os.path.isdir(os.path.join(args.states, u)))
    if args.uf:
        wanted = {u.strip().upper() for u in args.uf.split(",") if u.strip()}
        ufs = [u for u in ufs if u in wanted]
    os.makedirs(args.out, exist_ok=True)
    failed = 0
    for uf in ufs:
        folder = os.path.join(args.states, uf)
        data = read_csv_dir(folder)
        lines_csv = os.path.join(args.lines, uf, TYPE_FILES[SPEED_LIMIT_LINE]) if args.lines else ""
        overrides = {}
        if lines_csv and os.path.exists(lines_csv):
            data.limit_lines = read_csv_dir(os.path.dirname(lines_csv)).limit_lines
            overrides[SPEED_LIMIT_LINE] = lines_csv
        built_at = str(((catalog.get("ufs") or {}).get(uf) or {}).get("built_at") or catalog.get("built_at") or "")
        db_path = os.path.join(args.out, f"pardal-{uf}.sqlite")
        t0 = time.perf_counter()
        counts = write(db_path, uf, data, dates, built_at)
        t1 = time.perf_counter()
        compress(db_path, os.path.join(args.out, release_name(uf)))
        t2 = time.perf_counter()
        problems, _ = validate(db_path, folder, overrides)
        failed += bool(problems)
        size = os.path.getsize(db_path)
        zsize = os.path.getsize(os.path.join(args.out, release_name(uf)))
        print(f"[sqlite] {uf}: {sum(counts.values())} registros, {size / 1e6:.1f} MB, {zsize / 1e6:.1f} MB zst, "
              f"{t1 - t0:.1f} s + {t2 - t1:.1f} s zstd" + (f" — PROBLEMAS: {problems}" if problems else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
