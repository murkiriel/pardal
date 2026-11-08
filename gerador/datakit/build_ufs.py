"""Contorno de cada UF para o app escolher o pacote pela posição: brasil/ufs.geojson.

Um GeoJSON FeatureCollection com uma feição por UF (`properties`: `uf`, `name`; geometria Polygon ou MultiPolygon),
a malha oficial do IBGE (common/ufpoly.py) simplificada a TOLERANCE_DEG. O contorno cheio tem ~1 MB; o simplificado
cabe em ~130 KB, que o app baixa uma vez. Medido em 2026-11-08 (FONTES.md): o desvio máximo para o contorno do IBGE é
de ~3 km, então perto da divisa (e fora de todos os contornos, no mar) o app deve olhar também os pacotes vizinhos.

Entra no catalogo.json como `ufs_geojson` (chave de nível superior; o `schema` do catálogo não muda, quem não conhece
a chave a ignora). Sem `shapely` ou sem a malha das UFs, o arquivo simplesmente não sai.
"""
from __future__ import annotations

import json
import os
from typing import Dict, Optional

from datakit.build_catalog import _sha256
from datakit.common.ufs import uf_name

FILE = "ufs.geojson"
TOLERANCE_DEG = 0.02   # Douglas-Peucker em graus (~2,2 km na latitude): 132 KB; 0,01 daria 250 KB e 0,005 daria 457 KB
DECIMALS = 4           # ~11 m, bem abaixo da tolerância


def feature_collection(polygons: Dict[str, object], tolerance: float = TOLERANCE_DEG, decimals: int = DECIMALS) -> dict:
    """{UF: geometria shapely} -> FeatureCollection, as UFs em ordem de sigla."""
    from shapely.geometry import mapping

    def rounded(coords):
        if coords and isinstance(coords[0], (int, float)):
            return [round(coords[0], decimals), round(coords[1], decimals)]
        return [rounded(c) for c in coords]

    features = []
    for uf in sorted(polygons):
        geom = mapping(polygons[uf].simplify(tolerance, preserve_topology=True))   # type: ignore[attr-defined]
        features.append({"type": "Feature", "properties": {"uf": uf, "name": uf_name(uf)},
                         "geometry": {"type": geom["type"], "coordinates": rounded(geom["coordinates"])}})
    return {"type": "FeatureCollection", "features": features}


def build(polygons: Dict[str, object], dist_dir: str) -> Optional[dict]:
    """Escreve dist/brasil/ufs.geojson e a chave `ufs_geojson` do catalogo.json; devolve a entrada do catálogo, ou
    None (e apaga um arquivo velho) se não há contornos."""
    path = os.path.join(dist_dir, "brasil", FILE)
    cat_path = os.path.join(dist_dir, "catalogo.json")
    catalog: dict = {}
    if os.path.exists(cat_path):
        with open(cat_path, encoding="utf-8") as f:
            catalog = json.load(f)
    if not polygons:
        if os.path.exists(path):
            os.remove(path)
        if catalog.pop("ufs_geojson", None) is not None:
            _write_catalog(cat_path, catalog)
        return None
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(feature_collection(polygons), f, ensure_ascii=False, separators=(",", ":"))
    entry = {"file": f"brasil/{FILE}", "bytes": os.path.getsize(path), "sha256": _sha256(path)}
    if os.path.exists(cat_path):
        catalog["ufs_geojson"] = entry
        _write_catalog(cat_path, catalog)
    return entry


def _write_catalog(path: str, catalog: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)
