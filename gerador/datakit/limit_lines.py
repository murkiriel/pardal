"""Limites como trechos de via: juntar vias contíguas, tirar o que a fonte oficial já cobre e escrever o CSV.

O `limites.csv` guarda pontos: o valor vale até o próximo ponto, e o app precisa adivinhar em que via está (erra em
rua paralela, cruzamento, viaduto, marginal). O `limites_trechos.csv` guarda a via: cada linha é um trecho (WKT
`LINESTRING(lng lat, ...)`) com o limite que vale ao longo dele, para o app encaixar a posição na via mais perto, de
direção compatível.

Fluxo, por estado (build.py):
  1. OSM: cada via com limite (sinalizado ou estimado) vira um `Piece`, simplificada a LINE_EPSILON_M
     (osm_pbf.load, `lines_out`). Fontes oficiais com geometria de trecho (Rio, GeoSampa/CET, placas da ANTT sobre a
     rota do SNV) viram `Piece` do mesmo jeito.
  2. `join`: vias contíguas com os mesmos atributos viram uma linha só (até MAX_LINE_M).
  3. `cut`: do OSM sai o que um trecho oficial de direção compatível cobre (no espírito do override_limits dos pontos).
  4. `to_lines`: os `LimitLine` que o pacote escreve (common/model.py).

Memória: o extrato de uma região (sudeste) tem milhões de vias com limite. Cada `Piece` guarda a geometria como
`array('i')` de lat/lng em 1e-5° (5 casas, ~1,1 m; a mesma precisão que o CSV escreve), uns 8 bytes por vértice contra
~100 de uma tupla de floats; só o que vai ao pacote vira `LimitLine`.
"""
from __future__ import annotations

import functools
import math
from array import array
from collections import defaultdict
from typing import Dict, Hashable, Iterable, List, NamedTuple, Optional, Sequence, Tuple

from datakit.common.geo import angle_diff, bearing_deg, rdp
from datakit.common.model import LimitLine, to_dir
from datakit.common.spatial import Grid

Point = Tuple[float, float]

SCALE = 100_000            # coordenadas guardadas em 1e-5° (~1,1 m)
LINE_EPSILON_M = 3.0       # simplificação (Douglas-Peucker) da geometria de cada via
MAX_LINE_M = 5000.0        # uma linha juntada não passa disto (índice espacial do app, e erro de um casamento ruim)
CUT_RADIUS_M = 50.0        # o oficial cobre o OSM a até isto (o mesmo raio do override_limits dos pontos)
CUT_ANGLE_DEG = 30.0       # ...se a via do OSM tem a mesma orientação, até isto de diferença (módulo 180°)
SAMPLE_M = 20.0            # passo com que as linhas são medidas ao cortar
MIN_FRAGMENT_M = 40.0      # sobra de uma linha cortada menor que isto sai (resto de cruzamento, sem valor)
CUT_SIMPLIFY_M = 1.0       # os pontos intermediários do corte saem se estão a menos disto da reta


class Key(NamedTuple):
    """O que as vias precisam ter igual para virar uma linha só."""
    limit_kmh: int
    source: str
    estimated: bool
    low_kmh: Optional[int]
    directional: bool      # o limite vale para um sentido só (a linha vem no sentido do trânsito)
    highway: str
    oneway: Optional[bool]


@functools.lru_cache(maxsize=None)
def make_key(limit_kmh: int, source: str, estimated: bool, low_kmh: Optional[int], directional: bool,
             highway: str, oneway: Optional[bool]) -> Key:
    """Key única por combinação (poucas centenas): milhões de linhas dividem os mesmos objetos."""
    return Key(limit_kmh, source, estimated, low_kmh, directional, highway, oneway)


class Piece:
    """Um trecho antes de ir ao pacote. `start`/`end`: quem se encontra nas pontas (id do nó do OSM, ou a coordenada
    arredondada nas fontes oficiais); None quando a ponta não serve para juntar (sobra de um corte). `xy`: lat, lng,
    lat, lng... em 1e-5°."""
    __slots__ = ("start", "end", "xy", "key")

    def __init__(self, start: Optional[Hashable], end: Optional[Hashable], xy: "array[int]", key: Key):
        self.start, self.end, self.xy, self.key = start, end, xy, key

    @property
    def oriented(self) -> bool:
        """A linha vem desenhada no sentido do trânsito (mão única ou limite de um sentido só)."""
        return self.key.directional or self.key.oneway is True

    def first(self) -> Point:
        return self.xy[0] / SCALE, self.xy[1] / SCALE

    def middle(self) -> Point:
        k = (len(self.xy) // 4) * 2
        return self.xy[k] / SCALE, self.xy[k + 1] / SCALE

    def last(self) -> Point:
        return self.xy[-2] / SCALE, self.xy[-1] / SCALE

    def points(self) -> List[Point]:
        return decode(self.xy)

    def length_m(self) -> float:
        return _length_m(self.xy)


def encode(points: Iterable[Point]) -> "array[int]":
    """(lat, lng) -> array de inteiros em 1e-5°, sem vértice repetido em seguida."""
    out: "array[int]" = array("i")
    for lat, lng in points:
        y, x = round(lat * SCALE), round(lng * SCALE)
        if len(out) >= 2 and out[-2] == y and out[-1] == x:
            continue
        out.append(y)
        out.append(x)
    return out


def decode(xy: "array[int]") -> List[Point]:
    return [(xy[i] / SCALE, xy[i + 1] / SCALE) for i in range(0, len(xy), 2)]


def _reversed(xy: "array[int]") -> "array[int]":
    out: "array[int]" = array("i")
    for i in range(len(xy) - 2, -1, -2):
        out.append(xy[i])
        out.append(xy[i + 1])
    return out


def _length_m(xy: "array[int]") -> float:
    total = 0.0
    for i in range(0, len(xy) - 2, 2):
        total += _seg_m(xy[i], xy[i + 1], xy[i + 2], xy[i + 3])
    return total


def _seg_m(y0: int, x0: int, y1: int, x1: int) -> float:
    dy = (y1 - y0) / SCALE * 111_132.0
    dx = (x1 - x0) / SCALE * 111_320.0 * math.cos(math.radians((y0 + y1) / 2 / SCALE))
    return math.hypot(dx, dy)


def mean_bearing(xy: "array[int]") -> Optional[float]:
    """Rumo médio da linha: média circular dos rumos dos segmentos, ponderada pelo comprimento. Numa linha que faz
    curva é um resumo; o app compara com o rumo do segmento perto da posição."""
    sx = sy = 0.0
    for i in range(0, len(xy) - 2, 2):
        a, b = (xy[i] / SCALE, xy[i + 1] / SCALE), (xy[i + 2] / SCALE, xy[i + 3] / SCALE)
        w = _seg_m(xy[i], xy[i + 1], xy[i + 2], xy[i + 3])
        if w <= 0:
            continue
        r = math.radians(bearing_deg(a, b))
        sx += w * math.sin(r)
        sy += w * math.cos(r)
    if abs(sx) < 1e-9 and abs(sy) < 1e-9:
        return None
    return math.degrees(math.atan2(sx, sy)) % 360.0


def simplified(points: Sequence[Point], epsilon_m: Optional[float] = None) -> List[Point]:
    """Douglas-Peucker a epsilon_m (padrão: LINE_EPSILON_M); 0 deixa a geometria como está."""
    eps = LINE_EPSILON_M if epsilon_m is None else epsilon_m
    return rdp(list(points), eps) if eps > 0 else list(points)


# ── juntar vias contíguas ────────────────────────────────────────────────────

def join(pieces: Iterable[Piece], max_m: float = MAX_LINE_M) -> List[Piece]:
    """Vias que se encontram numa ponta, com os mesmos atributos, viram uma linha só. Só se junta onde exatamente duas
    pontas se encontram (num nó com três vias iguais não dá para saber qual segue). Linha de mão única ou de limite de
    um sentido só junta no sentido do trânsito (o fim de uma é o começo da outra); a de mão dupla junta em qualquer
    orientação. Nenhuma linha juntada passa de max_m (uma via sozinha pode passar)."""
    groups: Dict[Key, List[Piece]] = defaultdict(list)
    for p in pieces:
        groups[p.key].append(p)
    out: List[Piece] = []
    for key, group in groups.items():
        out.extend(_join_group(group, key.directional or key.oneway is True, max_m))
    return out


def _join_group(group: List[Piece], oriented: bool, max_m: float) -> List[Piece]:
    ends: Dict[Hashable, List[Tuple[int, int]]] = defaultdict(list)   # nó -> [(peça, 0 = começo | 1 = fim)]
    for i, p in enumerate(group):
        if p.start is not None and p.end is not None:
            ends[p.start].append((i, 0))
            ends[p.end].append((i, 1))
    link: Dict[Tuple[int, int], Tuple[int, int]] = {}
    for lst in ends.values():
        if len(lst) != 2:
            continue
        (i, e), (j, f) = lst
        if i == j or (oriented and e == f):
            continue
        link[(i, e)] = (j, f)
        link[(j, f)] = (i, e)
    if not link:
        return group

    out: List[Piece] = []
    done = [False] * len(group)
    for i in range(len(group)):
        if done[i]:
            continue
        # recua até a ponta livre da corrente (ou dá a volta, se for um laço)
        cur, seen = (i, 0), {i}
        while cur in link:
            j, f = link[cur]
            if j in seen:
                break
            seen.add(j)
            cur = (j, 1 - f)
        chain: List[Tuple[int, int]] = []   # (peça, ponta por onde se entra)
        while True:
            j, e = cur
            done[j] = True
            chain.append(cur)
            nxt = link.get((j, 1 - e))
            if nxt is None or done[nxt[0]]:
                break
            cur = nxt
        out.extend(_build_chain(group, chain, max_m))
    return out


def _build_chain(group: List[Piece], chain: List[Tuple[int, int]], max_m: float) -> List[Piece]:
    out: List[Piece] = []
    run: List[Tuple[int, int]] = []
    run_m = 0.0
    for item in chain:
        m = group[item[0]].length_m()
        if run and run_m + m > max_m:
            out.append(_merge_run(group, run))
            run, run_m = [], 0.0
        run.append(item)
        run_m += m
    if run:
        out.append(_merge_run(group, run))
    return out


def _merge_run(group: List[Piece], run: List[Tuple[int, int]]) -> Piece:
    if len(run) == 1 and run[0][1] == 0:
        return group[run[0][0]]
    xy: "array[int]" = array("i")
    for k, (j, e) in enumerate(run):
        seg = group[j].xy if e == 0 else _reversed(group[j].xy)
        xy.extend(seg if k == 0 else seg[2:])
    (j0, e0), (j1, e1) = run[0], run[-1]
    first, last = group[j0], group[j1]
    return Piece(first.start if e0 == 0 else first.end, last.end if e1 == 0 else last.start, xy, first.key)


# ── tirar do OSM o que o oficial cobre ───────────────────────────────────────

def _samples(xy: "array[int]", step_m: float) -> List[Tuple[float, float, float]]:
    """(lat, lng, rumo do segmento) ao longo da linha, a cada no máximo step_m, vértices incluídos."""
    pts = decode(xy)
    out: List[Tuple[float, float, float]] = []
    for a, b in zip(pts, pts[1:]):
        brg = bearing_deg(a, b)
        n = max(1, math.ceil(_seg_m(round(a[0] * SCALE), round(a[1] * SCALE),
                                    round(b[0] * SCALE), round(b[1] * SCALE)) / step_m))
        for k in range(n):
            t = k / n
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, brg))
    if len(pts) >= 2:
        out.append((pts[-1][0], pts[-1][1], out[-1][2]))
    return out


class _Coverage:
    """Onde os trechos oficiais estão: amostras (lat, lng, rumo, sentido único?) numa grade de CUT_RADIUS_M."""

    def __init__(self, official: Iterable[Piece], radius_m: float, angle_deg: float, step_m: float):
        self.angle = angle_deg
        self.grid: Grid[Tuple[float, bool]] = Grid(radius_m)
        self.cells: set = set()
        for p in official:
            oriented = p.oriented
            for lat, lng, brg in _samples(p.xy, step_m):
                self.grid.add(lat, lng, (brg, oriented))
                self.cells.add((int(lat // 0.01), int(lng // 0.01)))

    def near(self, xy: "array[int]") -> bool:
        """A caixa da linha toca alguma célula (0,01°) com trecho oficial? Descarte barato."""
        ys, xs = xy[0::2], xy[1::2]
        for cy in range(int((min(ys) / SCALE - 0.002) // 0.01), int((max(ys) / SCALE + 0.002) // 0.01) + 1):
            for cx in range(int((min(xs) / SCALE - 0.002) // 0.01), int((max(xs) / SCALE + 0.002) // 0.01) + 1):
                if (cy, cx) in self.cells:
                    return True
        return False

    def covers(self, lat: float, lng: float, brg: float, oriented: bool) -> bool:
        """Há um trecho oficial a até o raio, de orientação compatível? Oficial sem sentido cobre a via inteira. Oficial
        de um sentido só cobre a via de mão única do mesmo sentido, e a de mão dupla só quando os dois sentidos têm
        trecho oficial ali."""
        same = opposite = False
        for _d, (ob, o_oriented) in self.grid.within(lat, lng):
            diff = angle_diff(brg, ob)
            if diff <= self.angle:
                if not o_oriented:
                    return True
                if oriented:
                    return True
                same = True
            elif diff >= 180.0 - self.angle:
                if not o_oriented:
                    return True
                opposite = True
            if same and opposite:
                return True
        return False


def cut(pieces: Iterable[Piece], official: Sequence[Piece], radius_m: float = CUT_RADIUS_M,
        angle_deg: float = CUT_ANGLE_DEG, step_m: float = SAMPLE_M) -> Tuple[List[Piece], Dict[str, float]]:
    """Os trechos do OSM sem o que um trecho oficial de direção compatível cobre (a até radius_m, orientação até
    angle_deg de diferença): os pontos da linha são medidos a cada step_m e as sequências sem cobertura viram linhas
    novas. Devolve (linhas, medidas: `lines` testadas, `cut` quantas perderam um pedaço, `dropped` quantas sumiram,
    `km_before`, `km_after`). Sem trecho oficial, devolve tudo como veio."""
    pieces = list(pieces)
    if not official:
        return pieces, {}
    cov = _Coverage(official, radius_m, angle_deg, step_m)
    out: List[Piece] = []
    stats = {"lines": 0.0, "cut": 0.0, "dropped": 0.0, "km_before": 0.0, "km_after": 0.0}
    for p in pieces:
        if not cov.near(p.xy):
            out.append(p)
            continue
        stats["lines"] += 1
        samples = _samples(p.xy, step_m)
        flags = [cov.covers(lat, lng, brg, p.oriented) for lat, lng, brg in samples]
        before = p.length_m()
        stats["km_before"] += before / 1000
        if not any(flags):
            out.append(p)
            stats["km_after"] += before / 1000
            continue
        kept = _runs(samples, flags, p)
        stats["cut"] += 1
        if not kept:
            stats["dropped"] += 1
        stats["km_after"] += sum(q.length_m() for q in kept) / 1000
        out.extend(kept)
    return out, stats


def _runs(samples: List[Tuple[float, float, float]], flags: List[bool], proto: Piece) -> List[Piece]:
    out: List[Piece] = []
    run: List[Point] = []
    for (lat, lng, _brg), covered in zip(samples, flags):
        if covered:
            _close_run(run, proto, out)
            run = []
        else:
            run.append((lat, lng))
    _close_run(run, proto, out)
    return out


def _close_run(run: List[Point], proto: Piece, out: List[Piece]) -> None:
    if len(run) < 2:
        return
    xy = encode(simplified(run, CUT_SIMPLIFY_M))
    if len(xy) < 4:
        return
    piece = Piece(None, None, xy, proto.key)
    if piece.length_m() >= MIN_FRAGMENT_M:
        out.append(piece)


# ── para o pacote ────────────────────────────────────────────────────────────

def to_lines(pieces: Iterable[Piece]) -> List[LimitLine]:
    """Os `LimitLine` do pacote. `direction_deg`: o rumo médio, só nos limites de um sentido só."""
    out: List[LimitLine] = []
    for p in pieces:
        if len(p.xy) < 4:
            continue
        k = p.key
        direction = to_dir(mean_bearing(p.xy)) if k.directional else None
        out.append(LimitLine(tuple(decode(p.xy)), k.limit_kmh, k.source, k.estimated, k.low_kmh, direction,
                             k.highway, k.oneway))
    return out


def from_points(points: Sequence[Point], key: Key, start: Optional[Hashable] = None,
                end: Optional[Hashable] = None, epsilon_m: Optional[float] = None) -> Optional[Piece]:
    """Piece de uma geometria (lat, lng), simplificada. Sem `start`/`end`, as pontas são as coordenadas arredondadas
    (fontes oficiais, que não têm nó). None se a geometria degenera num ponto."""
    xy = encode(simplified(points, epsilon_m))
    if len(xy) < 4:
        return None
    if start is None:
        start, end = (xy[0], xy[1]), (xy[-2], xy[-1])
    return Piece(start, end, xy, key)
