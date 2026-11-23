"""DER-GO / GOINFRA — lista oficial de equipamentos de fiscalização eletrônica ativos (rodovias
estaduais de Goiás); source="DER-GO".

* Radares: a página "Relatório de equipamentos de monitoramento da GOINFRA" liga o PDF da lista de
  equipamentos ativos (a edição de 03/11/2026 tem 1.102 linhas, uma por faixa: RADAR FIXO e LOMBADA
  ELET, com código, faixa, sentido Crescente/Decrescente, local "GO-xxx", km, código SRE, latitude,
  longitude e velocidade). O endereço do PDF muda a cada edição (a pasta tem o mês e o nome, a data):
  o link certo é o da lista "Equipamentos-Ativos" de data mais nova. O PDF avisa que coordenadas e km
  são referenciais.
  Substitui os FeatureServers ArcGIS da GOINFRA (`Controle_de_Subst_de_Radares` e `MalhaEstadual_gdb`),
  que passaram a exigir token (erro 499) em 19/11/2026. A camada pública `Pontos_REV_CEM_CEV` NÃO é
  fonte: 440 de 983 pontos dela são "Novo" (estudo, não equipamento instalado) e quase nenhum está na
  lista oficial.
* Leitura do PDF: texto no desenho da página (pypdf, extraction_mode="layout"), uma regex por linha.
  A tabela muda de um lote para outro (coordenada em inteiro de micrograus "-16412382" ou em decimal,
  com ou sem separador de milhar; SRE com 3 ou 4 dígitos finais; km sem "KM" ou ausente; série com
  letras), por isso a linha é lida pelas âncoras (tipo, código, faixa, sentido, local, SRE, latitude,
  longitude, velocidade) e não por colunas.
* O que é descartado (e contado no log, com o motivo): linha que não bate com o formato; coordenada
  ilegível ou fora da caixa de Goiás (a edição de 03/11/2026 tem 6 linhas, de 3 equipamentos, com a
  longitude sem sinal ou igual à latitude); ponto a mais de FAR_M do trecho do próprio SRE na malha e a
  mais de SNAP_M de qualquer outro SRE da mesma rodovia (9 pontos, de 7 equipamentos: 5 caem sobre o
  trecho de outra rodovia, com a rodovia ou o SRE trocado, e 2 longe de qualquer trecho, um deles com um
  grau de longitude a mais). Velocidade fora de
  20-120 km/h ou que não seja múltiplo de 10 (39, 1362) deixa o radar sem limite, como no resto do Pardal.
* Faixas: a lista traz uma linha por faixa de rolamento (às vezes mais de uma por equipamento
  substituído, com série nova). Linhas do mesmo local (rodovia), do mesmo sentido e a até JOIN_M metros
  uma da outra viram um radar só, na posição média. Um por sentido: os dois sentidos do mesmo local ficam
  separados (a mescla com o resto, em merge_cameras, junta os que caírem no mesmo ponto e apaga o sentido).
  Medido na edição de 03/11/2026: 1.096 linhas com coordenada válida viram 873 pontos (674 de uma faixa, 178
  de duas, 18 de três e 3 de quatro); as faixas de uma pista ficam a 1 a 15 m uma da outra, uma única a 33 m.
* Sentido (Crescente/Decrescente) vira direction_deg pela malha rodoviária estadual da GOINFRA: o
  KMZ do mapa rodoviário (SRE-GO_2025.kmz), trechos por SRE com km inicial/final. O km de cada vértice
  sai do comprimento acumulado; o km impresso no radar confirma se o trecho foi desenhado do km
  inicial para o final. Ver common/direction.py e FONTES.md. SRE que a malha não tem (29 dos 321 da
  lista): o radar fica sem sentido.
"""
from __future__ import annotations

import io
import re
import zipfile
from collections import Counter, defaultdict
from typing import Dict, Iterable, List, NamedTuple, Optional, Tuple
from urllib.parse import unquote, urljoin

from datakit.context import SourceData, BuildContext
from datakit.common import Camera, CameraKind, Limit, in_bbox
from datakit.common.geo import haversine_m
from datakit.common.lrs import MeasuredLine, parse_km
from datakit.common.direction import direction_on
from datakit.common.ufs import UF_BBOX
from datakit.sources._http import get_bytes, get_response
from datakit.sources._pdf import pdf_layout_text

PAGE = "https://goias.gov.br/goinfra/relatorio-de-equipamentos-de-monitoramento-da-goinfra/"
MAP_PAGE = "https://goias.gov.br/goinfra/mapa-rodoviario-2025/"
# o KMZ que a página do mapa liga hoje; é o endereço de reserva se a página mudar
MAP_KMZ = "https://cdn.goinfra.go.gov.br/site/assets/paginas/images/SRE-GO_2025.kmz"

GO_BBOX = UF_BBOX["GO"]
SNAP_M = 150.0      # o radar a mais disso do trecho do SRE fica sem sentido
# O PDF diz que as coordenadas são referenciais: 98% dos radares ficam a até 250 m do trecho do próprio SRE
# na malha, 99% a até 700 m. Mais longe que FAR_M só vale se o ponto estiver sobre a mesma rodovia (outro
# SRE dela, a SNAP_M): é o SRE da lista que está errado, não a coordenada. Senão, a coordenada tem erro.
FAR_M = 1500.0
KM_TOLERANCE = 0.5  # km impresso x km na malha, quando o SRE da lista não é o do trecho
JOIN_M = 40.0       # faixas do mesmo local e sentido a até isto viram um radar
MIN_ROWS = 300      # a lista tem ~1.100 linhas; muito menos é formato que mudou, não lista curta
MAX_UNREAD = 0.10   # fração tolerada de linhas de equipamento que a regex não leu
LIMIT_RANGE = (20, 120)

_LINK = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.I)
_ROW = re.compile(
    r"^\s*(?P<tipo>RADAR\s+FIXO|LOMBADA\s+ELET\w*)\s+(?P<code>\S+)\s+(?P<lane>\d+)\s*(?P<side>[CD])\s+"
    r"(?P<cd>Crescente|Decrescente)\s+(?P<serial>\S+)\s+(?P<road>(?:GO|BR)\s*-?\s*\d{2,3})\s+(?P<middle>.*?)\s+"
    r"(?P<sre>\d{3}[A-Z]{2,3}\d{3,4})\s+(?P<lat>-?[\d.,]+)\s+(?P<lng>-?[\d.,]+)\s+(?P<kmh>\d+)(?:\s|$)",
    re.I)
_START = re.compile(r"^\s*(?:RADAR\s+FIXO|LOMBADA\s+ELET)", re.I)
_ISSUED = re.compile(r"Data de emiss[ãa]o:\s*(\d{2}/\d{2}/\d{4})", re.I)


# ── o link do PDF e do KMZ na página ─────────────────────────────────────────

def _edition_key(url: str) -> Tuple[Tuple[int, int, int], Tuple[int, int]]:
    """Ordem das edições da lista: a data que o nome do arquivo traz ("03_11_2026" ou "11_2025") e, de
    desempate, o mês da pasta de envio do WordPress (".../uploads/sites/77/2026/11/"). Sem data no nome,
    vale a da pasta."""
    folder = re.search(r"/(20\d{2})/(\d{2})/", url)
    month = (int(folder.group(1)), int(folder.group(2))) if folder else (0, 0)
    name = unquote(url.rsplit("/", 1)[-1])
    full = re.search(r"(?<!\d)(\d{1,2})[_.-](\d{1,2})[_.-](20\d{2})(?!\d)", name)
    if full:
        return (int(full.group(3)), int(full.group(2)), int(full.group(1))), month
    part = re.search(r"(?<!\d)(\d{1,2})[_.-](20\d{2})(?!\d)", name)
    if part:
        return (int(part.group(2)), int(part.group(1)), 0), month
    return (month[0], month[1], 0), month


def pdf_url(html: str, base: str = PAGE) -> Optional[str]:
    """O PDF mais novo da lista de equipamentos ativos na página, ou None. Só vale link .pdf cujo nome fala
    em "equipamento" e em "ativos" (a página liga também formulários e um despacho); entre eles, o de
    edição mais nova, e não o primeiro da página (a edição "vigentes até 30/05/2026" está ao lado da atual).
    Puro, testado."""
    cands = []
    for href in _LINK.findall(html):
        path = href.split("?", 1)[0].split("#", 1)[0]
        name = unquote(path.rsplit("/", 1)[-1]).lower()
        if name.endswith(".pdf") and "equipamento" in name and "ativo" in name:
            cands.append(urljoin(base, href.replace("&amp;", "&")))
    return max(cands, key=_edition_key) if cands else None


def kmz_urls(html: str, base: str = MAP_PAGE) -> List[str]:
    """Links .kmz da página do mapa rodoviário (o do mapa mais novo primeiro, pelo ano no nome), seguidos do
    endereço de reserva. Puro, testado."""
    found = [urljoin(base, h.replace("&amp;", "&")) for h in _LINK.findall(html)
             if h.split("?", 1)[0].lower().endswith(".kmz")]
    found.sort(key=lambda u: max((int(y) for y in re.findall(r"20\d{2}", u.rsplit("/", 1)[-1])), default=0),
               reverse=True)
    return list(dict.fromkeys(found + [MAP_KMZ]))


# ── a lista ──────────────────────────────────────────────────────────────────

class Row(NamedTuple):
    code: str
    lane: str
    road: str                 # "GO-060"
    sre: str
    lat: float
    lng: float
    limit: Optional[int]
    increasing: Optional[bool]    # Crescente/Decrescente; None se a faixa contradiz o sentido
    km_text: str              # o que vem entre o local e o SRE: km, sentido por extenso e município


Discard = Tuple[str, str]    # (motivo, código e faixa da linha)

UNREAD = "linha fora do formato"
BAD_COORD = "coordenada ilegível"
OUTSIDE = "coordenada fora de Goiás"
FAR = "longe do trecho do SRE"


def parse_coordinate(text: str) -> Optional[float]:
    """"-16412382" -> -16,412382 (inteiro em micrograus, a edição de 11/2026); "-16.412382" e "-16,412382"
    (decimal, a de 11/2025) ficam como estão; "-16.791.786" (ponto de milhar) é micrograus. None se não for
    número. Puro, testado."""
    t = (text or "").strip()
    neg = t.startswith("-")
    t = t.lstrip("+-")
    if not re.fullmatch(r"\d[\d.,]*", t):
        return None
    seps = re.findall(r"[.,]", t)
    if len(seps) == 1 and len(re.split(r"[.,]", t)[0]) <= 3:
        v = float(t.replace(",", "."))
    else:
        v = int(re.sub(r"[.,]", "", t)) / 1e6
    return -v if neg else v


def parse_limit(text: str) -> Optional[int]:
    """Limite em km/h: 20 a 120 e múltiplo de 10 (a lista tem 39 e 1362, erros de digitação)."""
    try:
        v = int(text)
    except ValueError:
        return None
    return v if LIMIT_RANGE[0] <= v <= LIMIT_RANGE[1] and v % 10 == 0 else None


def normalize_sre(sre: str) -> str:
    """"221EGO095" -> "221EGO0095": a lista às vezes perde o zero à esquerda do trecho (3 dígitos em vez de 4)."""
    m = re.fullmatch(r"(\d{3}[A-Z]{2,3})(\d{3})", sre)
    return f"{m.group(1)}0{m.group(2)}" if m else sre


def parse_list(lines: Iterable[str]) -> Tuple[List[Row], List[Discard], int]:
    """Linhas do PDF -> (linhas válidas, descartes com o motivo, quantas linhas de equipamento havia).
    Uma linha de equipamento começa com RADAR FIXO ou LOMBADA ELET. Puro, testado."""
    rows: List[Row] = []
    discards: List[Discard] = []
    total = 0
    for line in lines:
        if not _START.match(line):
            continue
        total += 1
        m = _ROW.match(line)
        if m is None:
            parts = line.split()
            discards.append((UNREAD, " ".join(parts[2:5]) if len(parts) > 4 else line.strip()[:40]))
            continue
        ref = f"{m['code']} {m['lane']}{m['side'].upper()}"
        lat, lng = parse_coordinate(m["lat"]), parse_coordinate(m["lng"])
        if lat is None or lng is None:
            discards.append((BAD_COORD, ref))
            continue
        if not in_bbox(GO_BBOX, lat, lng):
            discards.append((OUTSIDE, f"{ref} ({m['lat']} {m['lng']})"))
            continue
        # a lista traz o sentido duas vezes (faixa "1D" e "Decrescente"); se discordam, não há como saber
        by_name = m["cd"].lower() == "crescente"
        increasing: Optional[bool] = by_name if (m["side"].upper() == "C") == by_name else None
        rows.append(Row(m["code"], f"{m['lane']}{m['side'].upper()}", re.sub(r"[\s-]+", "-", m["road"].upper()),
                        normalize_sre(m["sre"].upper()), lat, lng, parse_limit(m["kmh"]), increasing,
                        m["middle"]))
    return rows, discards, total


def read_list(text: str) -> Tuple[List[Row], List[Discard]]:
    """parse_list com a conferência de formato: muito pouca linha lida (ou muita linha de equipamento que a
    regex não leu) é lista com outro desenho, e a fonte falha em vez de publicar um pedaço."""
    rows, discards, total = parse_list(text.splitlines())
    unread = sum(1 for reason, _ in discards if reason == UNREAD)
    if len(rows) < MIN_ROWS or unread > MAX_UNREAD * max(total, 1):
        raise RuntimeError(f"lista de equipamentos da GOINFRA com outro formato: {total} linhas de equipamento, "
                           f"{len(rows)} lidas, {unread} fora do formato")
    return rows, discards


class Point(NamedTuple):
    lat: float
    lng: float
    limit: Optional[int]
    increasing: Optional[bool]
    sre: str
    km_text: str
    lanes: int


def join_lanes(rows: List[Row], radius_m: float = JOIN_M) -> List[Point]:
    """Junta as faixas: mesmo local (rodovia), mesmo sentido e a até radius_m uma da outra (encadeadas) viram
    um ponto, na posição média. Limite: o mais comum entre as faixas, e o menor no empate. Puro, testado."""
    groups: Dict[Tuple[str, Optional[bool]], List[Row]] = defaultdict(list)
    for r in rows:
        groups[(r.road, r.increasing)].append(r)
    out: List[Point] = []
    for members in groups.values():
        clusters: List[List[Row]] = []
        for r in members:
            near = [c for c in clusters if any(haversine_m((r.lat, r.lng), (q.lat, q.lng)) <= radius_m for q in c)]
            merged = [r]
            for c in near:
                merged += c
                clusters.remove(c)
            clusters.append(merged)
        for c in clusters:
            limits = Counter(r.limit for r in c if r.limit is not None)
            top = max(limits.values()) if limits else 0
            first = c[0]
            out.append(Point(round(sum(r.lat for r in c) / len(c), 6), round(sum(r.lng for r in c) / len(c), 6),
                              min(k for k, n in limits.items() if n == top) if limits else None,
                              first.increasing, first.sre, next((r.km_text for r in c if r.km_text), ""), len(c)))
    return sorted(out, key=lambda p: (p.lat, p.lng, p.increasing is not False))


# ── a malha (KMZ do mapa rodoviário) ─────────────────────────────────────────

_PLACEMARK = re.compile(r"<Placemark\b.*?</Placemark>", re.S)
_DATA = re.compile(r'<Data name="(sre|km_inicial|km_final)">\s*<value>([^<]*)</value>')
_COORDS = re.compile(r"<coordinates>(.*?)</coordinates>", re.S)


def _path(text: str) -> List[Tuple[float, float]]:
    """"lng,lat,alt lng,lat,alt ..." (KML) -> [(lat, lng)]."""
    pts = []
    for tok in text.split():
        xy = tok.split(",")
        if len(xy) >= 2:
            pts.append((float(xy[1]), float(xy[0])))
    return pts


def parse_network(kml: str) -> Dict[str, List[MeasuredLine]]:
    """KML do mapa rodoviário -> {SRE: trechos com km em cada vértice}. Cada Placemark traz sre, km_inicial e
    km_final e uma ou mais linhas; o km de cada vértice sai do comprimento acumulado, do km inicial ao final.
    Placemark com mais de uma linha (48 em 2.065) reparte o intervalo de km entre elas pelo comprimento, na ordem
    em que vêm. Puro, testado."""
    lines: Dict[str, List[MeasuredLine]] = defaultdict(list)
    for pm in _PLACEMARK.findall(kml):
        a = dict(_DATA.findall(pm))
        try:
            k0, k1 = float(a["km_inicial"]), float(a["km_final"])
        except (KeyError, ValueError):
            continue
        sre = a.get("sre", "").strip()
        paths = [p for p in (_path(c) for c in _COORDS.findall(pm)) if len(p) >= 2]
        if not sre or k0 == k1 or not paths:
            continue
        if len(paths) == 1:
            lines[sre].append(MeasuredLine.from_extent(paths[0], k0, k1))
            continue
        sizes = [sum(haversine_m(p, q) for p, q in zip(path, path[1:])) for path in paths]
        total = sum(sizes) or 1.0
        done = 0.0
        for path, size in zip(paths, sizes):
            lines[sre].append(MeasuredLine.from_extent(
                path, k0 + (k1 - k0) * done / total, k0 + (k1 - k0) * (done + size) / total))
            done += size
    return dict(lines)


def kml_from_kmz(data: bytes) -> str:
    """O texto do KML dentro do KMZ (ou o próprio KML, se não for zip)."""
    if data[:2] != b"PK":
        return data.decode("utf-8", "replace")
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return z.read(next(n for n in z.namelist() if n.lower().endswith(".kml"))).decode("utf-8", "replace")


def load_network() -> Dict[str, List[MeasuredLine]]:
    """Trechos da malha estadual por SRE (ex. '070EGO0170'), com km em cada vértice. Tenta o KMZ que a página do
    mapa liga e, se falhar, o endereço de reserva."""
    try:
        urls = kmz_urls(get_response(MAP_PAGE, timeout=60).text)
    except Exception as e:  # noqa: BLE001 — a página do mapa fora do ar: vale o endereço conhecido
        print(f"[DER-GO] página do mapa rodoviário: {type(e).__name__}: {e}"[:300])
        urls = [MAP_KMZ]
    errors = []
    for url in urls:
        try:
            net = parse_network(kml_from_kmz(get_bytes(url, timeout=300)))
        except Exception as e:  # noqa: BLE001 — tenta o próximo endereço
            errors.append(f"{url}: {type(e).__name__}: {e}")
            continue
        if net:
            return net
        errors.append(f"{url}: sem trechos com sre e km")
    raise RuntimeError("malha estadual (KMZ) não lida: " + "; ".join(errors))


def nearest(lines: Iterable[MeasuredLine], lat: float, lng: float, max_m: float
            ) -> Optional[Tuple[MeasuredLine, float, float]]:
    """(trecho, km, distância em m) do trecho mais perto do ponto, se a menos de max_m."""
    best = None
    for line in lines:
        if not line.near_bbox((lat, lng), max_m):
            continue
        km, d = line.project((lat, lng), max_m)
        if d <= max_m and (best is None or d < best[2]):
            best = (line, km, d)
    return best


def road_lines(network: Dict[str, List[MeasuredLine]], sre: str) -> List[MeasuredLine]:
    """Trechos dos outros SREs da mesma rodovia (o SRE começa pelo número dela: "164EGO0540" é da GO-164)."""
    return [ln for other, lines in network.items() if other[:3] == sre[:3] and other != sre for ln in lines]


def printed_km(text: str) -> Optional[float]:
    """O km impresso na lista: "KM 225+332M", "km89+469m", "KM 000+941 m" ou só "406+080M" (sem o "KM")."""
    km = parse_km(text or "")
    if km is None:
        m = re.search(r"(?<!\d)(\d{1,3})\s*\+\s*(\d{3})(?!\d)", text or "")
        km = int(m.group(1)) + int(m.group(2)) / 1000.0 if m else None
    return km


def heading(best: Optional[Tuple[MeasuredLine, float, float]], increasing: Optional[bool], km_text: str,
            strict: bool = False) -> Optional[int]:
    """Rumo do trânsito no ponto `best` (de nearest), ou None sem trecho a até SNAP_M ou sem sentido. `strict`
    (trecho de outro SRE da mesma rodovia): só vale se o km impresso bater com o da malha."""
    if increasing is None or best is None or best[2] > SNAP_M:
        return None
    line, km, _ = best
    printed = printed_km(km_text)
    if strict and (printed is None or min(abs(km - printed), abs(line.m_min + line.m_max - km - printed))
                   > KM_TOLERANCE):
        return None
    # O km impresso no radar confirma o sentido em que o trecho foi desenhado: o trecho vem do km inicial ao
    # final (599 de 604 pontos, em que o km impresso cai a até 500 m de um dos dois lados); se o km impresso
    # só bate com a posição espelhada (trecho desenhado ao contrário), inverte. Km que não bate com nenhuma das
    # duas fica com a regra geral (o km é referencial: 51 pontos a mais de 500 m).
    if printed is not None:
        mirrored = line.m_min + line.m_max - km
        if abs(mirrored - printed) <= KM_TOLERANCE < abs(km - printed):
            increasing = not increasing
    return direction_on(line, km, increasing)


def direction(network: Dict[str, List[MeasuredLine]], sre: str, direction_text: str, km_text: str,
              lat: float, lng: float) -> Optional[int]:
    from datakit.common.direction import parse_increasing
    return heading(nearest(network.get((sre or "").strip(), []), lat, lng, SNAP_M),
                   parse_increasing(direction_text), km_text)


# ── a fonte ──────────────────────────────────────────────────────────────────

def cameras_from(rows: List[Row], network: Dict[str, List[MeasuredLine]],
                 bbox: Optional[Tuple[float, float, float, float]] = None
                 ) -> Tuple[List[Camera], List[Discard]]:
    """Radares a partir das linhas lidas e da malha ({} = sem sentido e sem a conferência de distância).
    Com a malha: o SRE que ela não tem deixa o radar sem sentido e sem conferência; o SRE que ela tem confere a
    distância (FAR_M do próprio SRE, ou SNAP_M de outro SRE da mesma rodovia) e dá o sentido. Devolve também o
    que a conferência descartou. Puro, testado."""
    out: List[Camera] = []
    discards: List[Discard] = []
    for p in join_lanes(rows):
        if not in_bbox(bbox, p.lat, p.lng):
            continue
        best, strict = None, False
        if p.sre in network:
            best = nearest(network[p.sre], p.lat, p.lng, FAR_M)
            if best is None:
                best, strict = nearest(road_lines(network, p.sre), p.lat, p.lng, SNAP_M), True
                if best is None:
                    discards.append((FAR, f"{p.sre} ({p.lat:.6f}, {p.lng:.6f})"))
                    continue
        out.append(Camera(p.lat, p.lng, CameraKind.FIXED, p.limit, "DER-GO", True,
                          direction_deg=heading(best, p.increasing, p.km_text, strict)))
    return out, discards


def _report(discards: List[Discard], unit: str) -> None:
    for reason, n in Counter(r for r, _ in discards).most_common():
        shown = [what for r, what in discards if r == reason][:8]
        print(f"[DER-GO] descartad{'as' if unit == 'linhas' else 'os'} {n} {unit}: {reason} "
              f"({'; '.join(shown)}{'; ...' if n > len(shown) else ''})")


def load(raw_dir: str, bbox: Optional[Tuple[float, float, float, float]] = None
         ) -> Tuple[List[Camera], List[Limit]]:
    page = get_response(PAGE, timeout=60)
    url = pdf_url(page.text, page.url)
    if url is None:
        raise RuntimeError(f"lista de equipamentos ativos da GOINFRA não encontrada na página ({page.url}, "
                           f"{len(page.text)} bytes, HTTP {page.status_code})")
    text = pdf_layout_text(get_bytes(url))
    rows, discards = read_list(text)
    issued = _ISSUED.search(text)
    try:
        network = load_network()
    except Exception as e:  # noqa: BLE001 — sem a malha, os radares saem sem sentido
        from datakit import failures
        failures.record("DER-GO (malha estadual, sentido)", e)
        network = {}
    cams, far = cameras_from(rows, network, bbox)
    _report(discards, "linhas")
    _report(far, "pontos")
    print(f"[DER-GO] lista de {issued.group(1) if issued else 'data desconhecida'} ({url.rsplit('/', 1)[-1]}): "
          f"{len(rows) + len(discards)} linhas de equipamento, {len(rows)} lidas, {len(cams)} radares "
          f"({sum(1 for c in cams if c.direction_deg is not None)} com sentido em graus, "
          f"{sum(1 for c in cams if c.limit_kmh is None)} sem limite)")
    return cams, []


def fetch(ctx: BuildContext) -> SourceData:
    """Contrato das fontes (datakit/context.py)."""
    return SourceData(*load(ctx.raw_dir))
