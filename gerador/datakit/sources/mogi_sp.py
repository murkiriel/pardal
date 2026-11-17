"""MOGI-SP — radares, lombadas eletrônicas e detectores de avanço de sinal de Mogi das Cruzes/SP.

O portal de dados abertos da Prefeitura (CKAN, conjunto "Dados sobre radar", da Secretaria Municipal de
Mobilidade Urbana) publica a lista dos equipamentos em `localizacao_radares2.csv`: Latin-1, separador ";",
CRLF e campos entre aspas que quebram linha (a coluna `justificativa`, um texto longo). Colunas:
id_radar, logradouro2, numero, Logradouro, subtipo, latitude, longitude, Localizacao ("lat, lng"), Sentido,
Faixas, Velocidade, Status, justificativa. Uma linha por equipamento e por ponto, sem repetição.

Tipos (`subtipo`): FIXO e REDUTOR DE VELOCIDADE (a lombada eletrônica mede velocidade) -> FIXED, com a
`Velocidade` (40, 50 ou 60; vazia em alguns) como limite; AVANÇO DE SINAL -> RED_LIGHT, sem limite (como o
BHTRANS, o limite só vale para o radar de velocidade; nenhuma linha de avanço de sinal tem velocidade).
Subtipo que não é nenhum dos dois fica de fora. `Status` "Inativo" -> inativo; "Em operação" (ou qualquer
outro valor) -> ativo. O sentido é só nominal ("Centro-Bairro", "Bairro-Centro e Centro-Bairro"): não vira
rumo, como na Transalvador.

Medido em 2026-11-17: 39 linhas, 39 pontos únicos; 33 em operação e 6 inativos; 17 fixos, 16 redutores e
6 de avanço de sinal; 18 dos 33 ativos já no pacote a <= 50 m, 11 novos (> 200 m). O arquivo é um upload
de 2023-12-28 (o portal não renova o recurso): a lista pode estar atrás do que a cidade tem hoje.
"""
from __future__ import annotations

import csv
import io
import unicodedata
from typing import Dict, List, Optional, Tuple

from datakit.context import SourceData, BuildContext
from datakit.common import Camera, CameraKind, Limit, in_bbox
from datakit.sources._http import get_bytes, in_br, to_float

CODE = "MOGI-SP"
PAGE = "https://dados.mogidascruzes.sp.gov.br/dataset/b93af036-8ed9-4442-82e4-7bc8c3d6c64f"
CSV_URL = (PAGE + "/resource/822a6c76-4c9b-413b-8299-abd40f903bf4/download/localizacao_radares2.csv")
AREA = (-23.8, -46.4, -23.3, -45.9)   # município de Mogi das Cruzes, com folga

_INACTIVE = ("INATIV", "DESATIV", "INOPERANTE", "SUSPENS")


def _norm(s: Optional[str]) -> str:
    """Maiúsculas e sem acento, para não depender de a prefeitura trocar a codificação do arquivo."""
    return "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c)).strip().upper()


def decode(raw: bytes) -> str:
    """UTF-8 se o arquivo for UTF-8 (a prefeitura pode corrigir); senão Latin-1, como é hoje."""
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def _kind(subtype: str) -> Optional[CameraKind]:
    t = _norm(subtype)
    if "AVANC" in t or "SEMAFORO" in t or "SINAL" in t:
        return CameraKind.RED_LIGHT
    if "FIXO" in t or "REDUTOR" in t or "LOMBADA" in t or "VELOCIDADE" in t or "RADAR" in t:
        return CameraKind.FIXED
    return None


def _point(row: Dict[str, str]) -> Optional[Tuple[float, float]]:
    lat, lng = to_float(row.get("latitude")), to_float(row.get("longitude"))
    if lat is None or lng is None:   # a coluna Localizacao traz "lat, lng"
        parts = (row.get("localizacao") or "").split(",")
        if len(parts) == 2:
            lat, lng = to_float(parts[0]), to_float(parts[1])
    if lat is None or lng is None:
        return None
    return lat, lng


def parse(text: str, bbox=None) -> List[Camera]:
    """CSV da lista -> radares, um por ponto. Linha sem coordenada, de subtipo que não é radar nem avanço de sinal
    ou fora de Mogi das Cruzes fica de fora."""
    found: Dict[Tuple[float, float], Camera] = {}
    for raw in csv.DictReader(io.StringIO(text), delimiter=";"):
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
        kind = _kind(row.get("subtipo", ""))
        p = _point(row)
        if kind is None or p is None or not in_br(*p) or not in_bbox(AREA, *p) or not in_bbox(bbox, *p):
            continue
        status = _norm(row.get("status"))
        active = not any(w in status for w in _INACTIVE)
        v = row.get("velocidade", "")
        limit = int(v) if kind == CameraKind.FIXED and v.isdigit() and 20 <= int(v) <= 130 else None
        key = (round(p[0], 6), round(p[1], 6))
        ref = (CODE, row["id_radar"]) if row.get("id_radar") else None
        cam = Camera(key[0], key[1], kind, limit, CODE, active, source_ref=ref)
        old = found.get(key)
        if old is None or (cam.active and not old.active):   # dois equipamentos no ponto: vale o que está ativo
            found[key] = cam
    return list(found.values())


def load(raw_dir: str, bbox: Optional[Tuple[float, float, float, float]] = None
         ) -> Tuple[List[Camera], List[Limit]]:
    cams = parse(decode(get_bytes(CSV_URL)), bbox)
    if not cams:
        raise RuntimeError(f"{CODE}: nenhum radar lido de {CSV_URL} (formato mudou?)")
    return cams, []


def fetch(ctx: BuildContext) -> SourceData:
    """Contrato das fontes (datakit/context.py)."""
    return SourceData(*load(ctx.raw_dir))
