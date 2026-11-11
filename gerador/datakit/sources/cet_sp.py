"""São Paulo (capital) — CET.

Limites: classificação viária da CET, camada do GeoSampa. Via de Trânsito Rápido -> 70,
Arterial -> 50; coletoras e locais ficam de fora. Cada segmento vira pontos a cada ~150 m.

Radares: "Locais fiscalizados" da página Fiscalização Eletrônica do Trânsito da CET, um
relatório Power BI público atualizado todo dia (lido por datakit/sources/_powerbi.py). Só os
ativos (sem data de desativação) e só os que fiscalizam velocidade (código V -> FIXED, com o
limite de veículo leve) ou avanço de sinal (A -> RED_LIGHT); rodízio, faixa exclusiva,
conversão proibida etc. ficam de fora. Reserva: a mesma base que a CET publica em CSV no GitHub
(cetsp-dados/dados-fiscalizacao-eletronica), usada quando o Power BI falha ou quando a última
ativação/desativação do CSV é mais nova que a do Power BI (ver _rows_with_fallback). Sentido: "(CENTRO/BAIRRO)" ou "(BAIRRO/CENTRO)" na
descrição vira o rumo que se afasta (ou se aproxima) do marco zero; sem isso (pares de lugares
como "RAPOSO/MARGINAL"), hint "*". Nos dois casos o build só publica o sentido quando o radar
está claramente sobre uma pista de mão única do OSM (osm_pbf.resolve_probes).
"""
from __future__ import annotations

import functools
import re
from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Tuple

from datakit import limit_lines
from datakit.context import SourceData, BuildContext
from datakit.common import Camera, CameraKind, in_bbox
from datakit.common.geo import bearing_deg, haversine_m, sample_polyline
from datakit.common.model import EnforcementCamera, Limit
from datakit.sources import _powerbi
from datakit.sources._http import get_json, in_br, to_float

WFS = "http://wms.geosampa.prefeitura.sp.gov.br/geoserver/geoportal/ows"
LAYER = "geoportal:classificacao_viaria_cet"
CLASS_LIMIT = {"VTR": 70, "Arterial": 50}
SAMPLE_M = 150.0
PAGE = 5000


def features_to_limits(features: list) -> List[Limit]:
    """GeoJSON (LineString/MultiLineString em lng,lat) -> pontos de limite. Puro, testado."""
    out: List[Limit] = []
    for f in features:
        kmh = CLASS_LIMIT.get(str((f.get("properties") or {}).get("dc_tipo_classificacao_viaria") or ""))
        geom = f.get("geometry") or {}
        if kmh is None:
            continue
        parts = geom.get("coordinates") or []
        if geom.get("type") == "LineString":
            parts = [parts]
        for line in parts:
            pts = [(lat, lng) for lng, lat in line]
            for lat, lng in sample_polyline(pts, SAMPLE_M):
                out.append(Limit(round(lat, 6), round(lng, 6), kmh, "CET-SP"))
    return out


PBI_VIEW = ("https://app.powerbi.com/view?r=eyJrIjoiZDhiOTU2NmMtMjVlMS00ZjY2LWE1NGItYWUzYjAyYmRhNmU3IiwidCI6"
            "ImIwODI2Nzg2LTZmNjktNGVjZC1iZmEyLTYyMmRhYTJiMTlhZCJ9")
PBI_API = "https://wabi-brazil-south-b-primary-api.analysis.windows.net"
PBI_TABLE = "tblFiscalizacaoEletronica"
PBI_COLS = ["CÓDIGO LOCAL", "LATITUDE", "LONGITUDE", "DESCRIÇÃO DO LOCAL", "ENQUADRAMENTOS",
            "VELOCIDADE", "ATIVAÇÃO", "DESATIVAÇÃO"]
# A mesma base, publicada pela CET em CSV no GitHub (conta cetsp-dados, desde 2026-10-27): campos
# com os mesmos nomes do Power BI, menos ENQUADRAMENTO (singular, códigos separados por ";") e as
# datas em AAAA-MM-DD (no Power BI, milissegundos desde 1970). Atualizada à mão: em 2026-11-08,
# 2.074 locais com a última mudança em 2026-10-20, contra 2.127 e 2026-11-04 no Power BI.
GITHUB_CSV = ("https://raw.githubusercontent.com/cetsp-dados/dados-fiscalizacao-eletronica/main/"
              "Base_Locais_Fiscalizados.csv")
CITY_CENTER = (-23.550333, -46.633944)   # Praça da Sé
RADIAL_MIN_M = 1500.0                     # perto do centro, "sair do centro" não define rumo
_CB = re.compile(r"\(\s*(CENTRO|C)\s*/\s*(BAIRRO|B)\s*\)", re.I)
_BC = re.compile(r"\(\s*(BAIRRO|B)\s*/\s*(CENTRO|C)\s*\)", re.I)


def center_suburb_hint(desc: str, lat: float, lng: float) -> Optional[str]:
    """'(CENTRO/BAIRRO)' -> rumo que se afasta do marco zero; '(BAIRRO/CENTRO)' -> que se
    aproxima; como heading_hint '@<graus>'. None sem o par ou perto demais do centro."""
    out = _CB.search(desc or "")
    inn = _BC.search(desc or "")
    if bool(out) == bool(inn) or haversine_m(CITY_CENTER, (lat, lng)) < RADIAL_MIN_M:
        return None
    b = bearing_deg(CITY_CENTER, (lat, lng)) if out else bearing_deg((lat, lng), CITY_CENTER)
    return f"@{b:.0f}"


def _enforces(row: Dict) -> Optional[CameraKind]:
    codes = {c.strip().upper() for c in str(row.get("ENQUADRAMENTOS") or "").split(",")}
    if "V" in codes:
        return CameraKind.FIXED
    if "A" in codes:
        return CameraKind.RED_LIGHT
    return None


# Os códigos de ENQUADRAMENTO da CET (tabela "Enquadramentos" do mesmo relatório Power BI, lida em 2026-11-08) que NÃO
# são velocidade (V) nem avanço de sinal (A), os dois do radares.csv, e o tipo do cameras_fiscalizacao.csv de cada um.
# Todos os códigos da base tinham legenda; um código novo, sem legenda aqui, vira OTHER.
ENFORCEMENT_KINDS = {
    "EXD": "BUS_LANE", "EXE": "BUS_LANE",                       # faixa exclusiva direita / esquerda
    "CPD": "NO_TURN", "CPE": "NO_TURN",                         # conversão proibida à direita / esquerda
    "P": "STOP_ON_CROSSWALK",                                   # parada sobre a faixa de pedestres
    "R": "ROAD_ROTATION",                                       # rodízio
    "Z": "TRUCK_RESTRICTION", "VR": "TRUCK_RESTRICTION",        # ZMRC e VER (caminhão)
    "PR": "TRUCK_RESTRICTION",                                  # faixa proibida (caminhão à esquerda)
    "F": "CHARTER_RESTRICTION",                                 # ZMRF (fretado)
    "MT": "MOTORCYCLE_RESTRICTION",                             # motocicletas
    "S": "OTHER",                                               # trânsito seletivo
}
SOURCE_CAMERAS = "CET-SP:CAM"   # código próprio: a reserva pela edição busca radares pelas partes de `source` do radares.csv


def local_code(row: Dict) -> Optional[str]:
    """O "CÓDIGO LOCAL" da CET, como texto ("100"; o Power BI às vezes dá número), ou None. Vai para o SQLite como o id
    do registro na fonte (source_ref). Puro, testado."""
    v = row.get("CÓDIGO LOCAL")
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    text = str(v).strip() if v is not None else ""
    return text or None


def rows_to_enforcement_cameras(rows: List[Dict]) -> List[EnforcementCamera]:
    """Locais ativos que fiscalizam outra infração além de velocidade e avanço de sinal: uma linha por tipo de
    infração (conversão à direita e à esquerda são uma só). Puro, testado."""
    out: List[EnforcementCamera] = []
    for r in rows:
        if r.get("DESATIVAÇÃO"):
            continue
        lat, lng = to_float(r.get("LATITUDE")), to_float(r.get("LONGITUDE"))
        if lat is None or lng is None or not in_br(lat, lng):
            continue
        kinds = {ENFORCEMENT_KINDS.get(c, "OTHER") for c in
                 (c.strip().upper() for c in str(r.get("ENQUADRAMENTOS") or "").split(",")) if c and c not in ("V", "A")}
        code = local_code(r)
        ref = (SOURCE_CAMERAS, code) if code else None
        out.extend(EnforcementCamera(round(lat, 6), round(lng, 6), k, SOURCE_CAMERAS, source_ref=ref) for k in sorted(kinds))
    return out


def load_other_cameras(raw_dir: str) -> List[EnforcementCamera]:
    """As câmeras sem velocidade, da tabela que a leitura dos radares acabou de guardar em data/raw (CACHE_FILE):
    sem segunda consulta ao Power BI. Roda depois de fetch()."""
    import json
    import os
    with open(os.path.join(raw_dir, CACHE_FILE), encoding="utf-8") as f:
        return rows_to_enforcement_cameras(json.load(f))


def rows_to_deactivated(rows: List[Dict]) -> List[Tuple[float, float]]:
    """Locais desativados que fiscalizavam velocidade ou avanço de sinal. Puro, testado."""
    out = []
    for r in rows:
        lat, lng = to_float(r.get("LATITUDE")), to_float(r.get("LONGITUDE"))
        if r.get("DESATIVAÇÃO") and _enforces(r) and lat is not None and lng is not None and in_br(lat, lng):
            out.append((round(lat, 6), round(lng, 6)))
    return out


def rows_to_cameras(rows: List[Dict], bbox: Optional[Tuple[float, float, float, float]] = None
                    ) -> List[Camera]:
    """Linhas da tabela da CET -> radares ativos de velocidade/avanço de sinal. Puro, testado."""
    out: List[Camera] = []
    for r in rows:
        if r.get("DESATIVAÇÃO"):
            continue
        kind = _enforces(r)
        if kind is None:
            continue
        lat, lng = to_float(r.get("LATITUDE")), to_float(r.get("LONGITUDE"))
        if lat is None or lng is None or not in_br(lat, lng) or not in_bbox(bbox, lat, lng):
            continue
        m = re.match(r"\s*(\d{2,3})", str(r.get("VELOCIDADE") or ""))
        limit = int(m.group(1)) if kind == CameraKind.FIXED and m and 20 <= int(m.group(1)) <= 130 else None
        hint = center_suburb_hint(r.get("DESCRIÇÃO DO LOCAL") or "", lat, lng) or "*"
        code = local_code(r)
        out.append(Camera(round(lat, 6), round(lng, 6), kind, limit, "CET-SP", True, heading_hint=hint,
                          source_ref=("CET-SP", code) if code else None))
    return out


CACHE_FILE = "cet_sp_locais.json"


def csv_rows(text: str) -> List[Dict]:
    """CSV da CET no GitHub -> linhas com os campos do Power BI. Puro, testado."""
    import csv
    import io
    out = []
    for r in csv.DictReader(io.StringIO(text.lstrip("\ufeff"))):
        row = {k: (r.get(k) or None) for k in PBI_COLS if k != "ENQUADRAMENTOS"}
        row["ENQUADRAMENTOS"] = ",".join(c.strip() for c in (r.get("ENQUADRAMENTO") or "").split(";") if c.strip())
        out.append(row)
    return out


def _as_date(v) -> Optional[date]:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return datetime.fromtimestamp(v / 1000, tz=timezone.utc).date()
    try:
        return date.fromisoformat(str(v).strip()[:10]) if v else None
    except ValueError:
        return None


def last_change(rows: List[Dict]) -> Optional[date]:
    """A data mais recente de ativação ou desativação na base (o quanto ela está em dia)."""
    days = [d for r in rows for d in (_as_date(r.get("ATIVAÇÃO")), _as_date(r.get("DESATIVAÇÃO"))) if d]
    return max(days) if days else None


def choose(pbi: Optional[List[Dict]], github: Optional[List[Dict]]) -> Tuple[Optional[List[Dict]], str]:
    """Qual base usar: o Power BI, salvo quando ele falhou (None ou vazio) ou quando o CSV do GitHub
    tem uma ativação/desativação mais nova. Devolve (linhas, motivo de ter usado o GitHub ou "")."""
    if not github:
        return (pbi or None), ""
    if not pbi:
        return github, "Power BI falhou"
    p, g = last_change(pbi), last_change(github)
    if g is not None and (p is None or g > p):
        return github, f"Power BI desatualizado (última mudança {p}, a do CSV do GitHub é {g})"
    return pbi, ""


def _rows_with_fallback(raw_dir: str) -> List[Dict]:
    """A tabela da CET pelo Power BI ou, se ele falhar ou estiver mais velho, pelo CSV que a CET
    publica no GitHub (choose). Guarda a leitura boa em data/raw/; se as duas falharem, usa essa
    cópia e avisa (failures.warn). Sem cópia, a falha sobe."""
    import json
    import os
    from datakit import failures
    from datakit.sources._http import get_bytes
    path = os.path.join(raw_dir, CACHE_FILE)
    pbi: Optional[List[Dict]] = None
    pbi_error: Optional[Exception] = None
    try:
        key = _powerbi.resource_key(PBI_VIEW)
        pbi = _powerbi.query_table(PBI_API, key, _powerbi.model_id(PBI_API, key), PBI_TABLE, PBI_COLS)
        if not pbi:
            raise RuntimeError("tabela da CET veio vazia")
    except Exception as e:  # noqa: BLE001
        pbi, pbi_error = None, e
    github: Optional[List[Dict]] = None
    try:
        github = csv_rows(get_bytes(GITHUB_CSV).decode("utf-8-sig", "replace"))
    except Exception as e:  # noqa: BLE001 — o CSV é só reserva: sem ele, vale o Power BI
        if pbi_error is None:
            failures.warn("CET-SP (radares)", f"CSV do GitHub (reserva) falhou ({type(e).__name__})")
    rows, why = choose(pbi, github)
    if rows is None:
        if not os.path.exists(path):
            raise pbi_error or RuntimeError("CET-SP: Power BI e CSV do GitHub sem dados")
        when = date.fromtimestamp(os.path.getmtime(path)).isoformat()
        failures.warn("CET-SP (radares)", f"Power BI e CSV do GitHub falharam ({type(pbi_error).__name__}); "
                      f"usada a cópia de {when}")
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    if why:
        failures.warn("CET-SP (radares)", f"{why}; usado o CSV do GitHub")
    os.makedirs(raw_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False)
    return rows


def load(raw_dir: str, bbox: Optional[Tuple[float, float, float, float]] = None
         ) -> Tuple[List[Camera], List[Limit]]:
    return rows_to_cameras(_rows_with_fallback(raw_dir), bbox), []


def fetch(ctx: BuildContext) -> SourceData:
    """Contrato das fontes (datakit/context.py). Vão junto os locais que a CET desativou: o
    build marca inativo o radar do OSM que ficou num deles (model.deactivate_near)."""
    rows = _rows_with_fallback(ctx.raw_dir)
    return SourceData(rows_to_cameras(rows), [], rows_to_deactivated(rows))


def features_to_lines(features: list) -> List[limit_lines.Piece]:
    """GeoJSON (LineString/MultiLineString em lng,lat) -> trechos de limite (limites_trechos.csv). Puro, testado."""
    out: List[limit_lines.Piece] = []
    for f in features:
        kmh = CLASS_LIMIT.get(str((f.get("properties") or {}).get("dc_tipo_classificacao_viaria") or ""))
        geom = f.get("geometry") or {}
        if kmh is None:
            continue
        parts = geom.get("coordinates") or []
        if geom.get("type") == "LineString":
            parts = [parts]
        key = limit_lines.Key(kmh, "CET-SP", False, None, False, "", None)
        for line in parts:
            piece = limit_lines.from_points([(lat, lng) for lng, lat in line], key)
            if piece is not None:
                out.append(piece)
    return out


@functools.lru_cache(maxsize=1)
def _classified_features() -> tuple:
    """As feições VTR e Arterial da classificação viária, lidas uma vez por execução (pontos e linhas saem da mesma
    leitura). Falha não fica guardada."""
    out: list = []
    start = 0
    while True:
        gj = get_json(WFS, params={
            "service": "WFS", "version": "2.0.0", "request": "GetFeature",
            "typeNames": LAYER, "outputFormat": "application/json", "srsName": "EPSG:4326",
            "count": PAGE, "startIndex": start,
            "CQL_FILTER": "dc_tipo_classificacao_viaria IN ('VTR','Arterial')",
        })
        feats = gj.get("features", [])
        out.extend(feats)
        if len(feats) < PAGE:
            break
        start += PAGE
    return tuple(out)


def load_limits() -> List[Limit]:
    return features_to_limits(list(_classified_features()))


def load_limit_lines() -> List[limit_lines.Piece]:
    """As vias de trânsito rápido e arteriais como linhas, juntadas quando seguidas e de mesmo limite."""
    return limit_lines.join(features_to_lines(list(_classified_features())))
