"""O bloco `contract` do catalogo.json publicado: o contrato de catálogo comum aos quatro geradores (docs/CATALOGO.md).

Só acrescenta: nenhuma chave antiga do catálogo muda (o `schema` 2, o `base_url`, as entradas de cada estado seguem
iguais). O scripts/publish.py monta o bloco no catálogo que vai para o repositório e para a release; este módulo é só
a parte pura (biblioteca padrão e a tabela de UFs), testada sem rede nem git.

O que entra em `files`:
- por estado: os arquivos do repositório (estados/<UF>/*.csv, .geojson, .kml, .gpx), o `limites_trechos.csv` (só no
  zip), o zip da release (`pardal-<UF>.zip`) e o banco (`pardal-<UF>.sqlite.zst`);
- o Brasil (`BR`): os arquivos de brasil/, os dois zips do Brasil e os polígonos das UFs (`ufs.geojson`).

URLs: os anexos apontam para a release da geração (`dados-AAAA-MM-DD`, a etiqueta que o scripts/release.py cria). Um
arquivo do repositório aponta para o mesmo nome de etiqueta no raw.githubusercontent.com quando a geração vai para o
repositório (`committed`); senão, a URL é a do zip que o contém (`container` + `member`).
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import timezone
from email.utils import parsedate_to_datetime
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from datakit.common.ufs import UF_BBOX

CONTRACT_NAME = "catalogo-comum"
CONTRACT_VERSION = 1
CONTRACT_MIN_READER_VERSION = 1
DATASET = "pardal"
BBOX_ORDER = "lat_min,lon_min,lat_max,lon_max"
DATA_LICENSE = "ODbL-1.0"
CODE_LICENSE = "MIT"
# O crédito dos dados (o mesmo da tabela `meta` dos bancos, datakit/build_sqlite.py ATTRIBUTION; um teste confere).
ATTRIBUTION = ("Pardal: © colaboradores do OpenStreetMap (ODbL 1.0) e as fontes abertas listadas no README "
               "(DNIT, ANTT, PRF, Inmetro, IBGE, DERs e prefeituras)")
# A versão do formato dos CSVs (datakit/build_pack.py SCHEMA) e do banco (datakit/build_sqlite.py SCHEMA_VERSION):
# repetidas aqui porque o publish.py não importa o build; os testes conferem que são as mesmas.
PACK_SCHEMA = 12
SQLITE_SCHEMA_VERSION = 1
SQLITE_MIN_VERSION = "3.22.0"
SQLITE_SPEC = "docs/FORMATO_SQLITE.md"
DEFAULT_REPO = "Murkiriel/pardal"
BR = "BR"
BRAZIL_BBOX = [-34.0, -74.5, 6.0, -32.0]   # o mesmo da entrada BR do catálogo (datakit/build_brazil.py)
UFS_GEOJSON = "brasil/ufs.geojson"

# A ordem das coordenadas em cada formato publicado (docs/CATALOGO.md, Pardal). "named": colunas ou atributos com nome.
COORDINATE_ORDER = {"csv": "lat,lng", "wkt": "lng,lat", "geojson": "lng,lat", "kml": "lng,lat", "gpx": "named",
                    "sqlite": "named"}

# Extensão -> (format, media_type). O `.gz` de um arquivo grande (build_brazil.compress_oversized) vira unpack gzip.
FORMATS = {"csv": ("csv", "text/csv"), "geojson": ("geojson", "application/geo+json"),
           "kml": ("kml", "application/vnd.google-earth.kml+xml"), "gpx": ("gpx", "application/gpx+xml")}
# Nome do arquivo (sem extensão) -> a chave da entrada antiga do catálogo que o descreve.
CONTENT = {"radares": "cameras", "limites": "limits", "limites_estimados": "limits_estimated", "estruturas": "structs",
           "lombadas": "bumps", "pontos_atencao": "hazards", "pedagios": "tolls", "radar_portatil": "portable_radar",
           "buracos": "potholes", "acidentes_moto": "moto_accidents", "limites_trechos": "limit_lines",
           "cameras_fiscalizacao": "enforcement_cameras", "ufs": "ufs"}
BUNDLE_FORMAT = "pardal-bundle"
BRAZIL_ZIP = "pardal-brasil.zip"
BRAZIL_CAMERAS_ZIP = "pardal-brasil-radares.zip"


def release_tag(built_at: str) -> str:
    """A etiqueta da release da geração: a mesma de scripts/release.py (tag_for)."""
    return "dados-" + str(built_at)[:10]


def fingerprint(cat: Mapping) -> Set[Tuple[str, str]]:
    """(arquivo, sha256) de cada arquivo de dado do catálogo, sem o banco SQLite (que traz as datas da geração): a
    mesma regra de scripts/release.py (data_fingerprint). Dados iguais, impressão igual."""
    out: Set[Tuple[str, str]] = set()

    def add(value) -> None:
        if isinstance(value, dict) and value.get("sha256"):
            out.add((value.get("file") or value.get("asset_path") or "", value["sha256"]))
    for key, value in cat.items():
        if key != "contract":
            add(value)
    for entry in (cat.get("ufs") or {}).values():
        if isinstance(entry, dict):
            for key, value in entry.items():
                if key != "sqlite":
                    add(value)
    return out


def build_id(cat: Mapping) -> str:
    """AAAA-MM-DD (do built_at, UTC) + os 8 primeiros do sha256 da impressão dos dados (linhas `arquivo  sha256`
    ordenadas): o formato dos outros geradores, com o hash do conteúdo no lugar do md5 do extrato."""
    lines = "".join(f"{path}  {sha}\n" for path, sha in sorted(fingerprint(cat)))
    return f"{str(cat['built_at'])[:10]}-{hashlib.sha256(lines.encode('utf-8')).hexdigest()[:8]}"


def _slug(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", plain).strip("-") or "fonte"


def _iso(http_date: str) -> Optional[str]:
    """`Sat, 08 Nov 2026 21:21:36 GMT` (o Last-Modified da Geofabrik) -> `2026-11-08T21:21:36Z`; None se não der."""
    try:
        when = parsedate_to_datetime(http_date)
    except (TypeError, ValueError, IndexError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def osm_extracts(manifests: Iterable[Mapping]) -> List[dict]:
    """Os extratos regionais do OpenStreetMap (Geofabrik) dos manifestos dos pacotes, um por região:
    {name, file_date, sha256, bytes}."""
    found: Dict[str, dict] = {}
    for manifest in manifests:
        for source in manifest.get("sources") or []:
            name = str(source.get("name") or "")
            if name.startswith("OSM/Geofabrik ") and source.get("sha256"):
                found[name] = {k: source.get(k) for k in ("name", "file_date", "sha256", "bytes")}
    return [found[name] for name in sorted(found)]


def _sources(cat: Mapping, extracts: Sequence[Mapping]) -> List[dict]:
    sources: List[dict] = []
    for extract in extracts:
        region = str(extract["name"]).split(" ", 1)[1]
        sources.append({"id": "openstreetmap-geofabrik-" + _slug(region), "name": str(extract["name"]),
                        "url": f"https://download.geofabrik.de/south-america/brazil/{region}-latest.osm.pbf",
                        "date": _iso(str(extract.get("file_date") or "")), "license": "ODbL-1.0",
                        "checksums": {"sha256": extract["sha256"]}})
    seen = {s["id"] for s in sources}
    for name, date in sorted((cat.get("source_dates") or {}).items()):
        source_id = _slug(name)
        while source_id in seen:
            source_id += "-2"
        seen.add(source_id)
        sources.append({"id": source_id, "name": name, "date": date, "checksums": {}})
    return sources


def _osm_snapshot(extracts: Sequence[Mapping]) -> dict:
    """A data do extrato mais antigo (a idade dos dados é a do pedaço mais velho); md5 não há (a Geofabrik dá sha256,
    que vai em `sources`)."""
    dates = sorted(d for d in (_iso(str(e.get("file_date") or "")) for e in extracts) if d)
    return {"date": dates[0] if dates else None, "md5": None}


def _bbox(cat: Mapping, region: str) -> List[float]:
    entry = (cat.get("ufs") or {}).get(region) or {}
    if isinstance(entry.get("bbox"), list) and len(entry["bbox"]) == 4:
        return [float(x) for x in entry["bbox"]]
    if region == BR:
        return list(BRAZIL_BBOX)
    return [float(x) for x in UF_BBOX[region]]


def _format(name: str) -> Tuple[str, str, List[str]]:
    """(format, media_type, unpack) de um arquivo pelo nome."""
    unpack: List[str] = []
    if name.endswith(".gz"):
        name, unpack = name[:-3], ["gzip"]
    fmt, media = FORMATS[name.rsplit(".", 1)[1]]
    return fmt, ("application/gzip" if unpack else media), unpack


def _content(name: str) -> str:
    stem = name.split(".", 1)[0]
    return CONTENT.get(stem, stem)


def contract(cat: Mapping, *, repo_files: Mapping[str, Tuple[str, int]], zips: Mapping[str, Tuple[str, int]],
             committed: bool, generator_commit: Optional[str], repo: str = DEFAULT_REPO,
             extracts: Sequence[Mapping] = ()) -> dict:
    """O bloco `contract` do catálogo publicado `cat` (o de scripts/publish.py rewrite_catalog).

    `repo_files`: {caminho no repositório (estados/GO/radares.csv, brasil/...): (sha256, bytes)}, tudo o que vai para
    brasil/ e estados/. `zips`: {nome do anexo: (sha256, bytes)} dos zips que o scripts/release.py monta.
    `committed`: os arquivos do repositório vão para o commit desta geração (a etiqueta aponta para ele).
    `extracts`: os extratos do OpenStreetMap (osm_extracts)."""
    tag = release_tag(cat["built_at"])
    release_url = f"https://github.com/{repo}/releases/download/{tag}/"
    files: List[dict] = []

    def add(file_id: str, kind: str, region: Optional[str], url: str, sha: str, size: int, media: str,
            unpack: List[str], fmt: str, coverage: Optional[str], **extra) -> None:
        files.append({"id": file_id, "kind": kind, "region": region, "url": url, "sha256": sha, "bytes": size,
                      "bytes_unpacked": extra.pop("bytes_unpacked", None), "media_type": media, "unpack": unpack,
                      "format": fmt, "bbox": None if region is None else _bbox(cat, region),
                      "coverage_level": coverage, "requires": [], **extra})

    def add_zip(name: str, kind: str, region: str, **extra) -> None:
        sha, size = zips[name]
        add(name, kind, region, release_url + name, sha, size, "application/zip", ["zip"], BUNDLE_FORMAT, "DETAILED",
            **extra)

    def add_member(path: str, kind: str, region: str, box: str, member: str, sha: str, size: int,
                   in_repo: bool) -> None:
        name = path.rsplit("/", 1)[1]
        fmt, media, unpack = _format(name)
        url = f"https://raw.githubusercontent.com/{repo}/{tag}/{path}" if in_repo else release_url + box
        coverage = None if _content(name) == "ufs" else "DETAILED"
        add(path, "auxiliary" if coverage is None else kind, region, url, sha, size, media, unpack, fmt, coverage,
            container=box, member=member, content=_content(name))

    ufs = cat.get("ufs") or {}
    for uf in sorted(u for u in ufs if u != BR):
        entry = ufs[uf]
        box = f"pardal-{uf}.zip"
        if box in zips:
            add_zip(box, "uf", uf)
        for path in sorted(p for p in repo_files if p.startswith(f"estados/{uf}/")):
            sha, size = repo_files[path]
            add_member(path, "uf", uf, box, f"{uf}/{path.rsplit('/', 1)[1]}", sha, size, committed)
        for value in entry.values():   # o que vai só no zip (limites_trechos.csv: release_asset + asset_path)
            if isinstance(value, dict) and value.get("asset_path") and value.get("release_asset") == box:
                name = value["asset_path"].rsplit("/", 1)[1]
                add_member(f"estados/{uf}/{name}", "uf", uf, box, value["asset_path"], value["sha256"],
                           value["bytes"], False)
        sqlite = entry.get("sqlite")
        if isinstance(sqlite, dict) and sqlite.get("release_asset"):
            name = sqlite["release_asset"]
            add(name, "uf", uf, release_url + name, sqlite["sha256"], sqlite["bytes"], "application/zstd", ["zstd"],
                "sqlite", "DETAILED", bytes_unpacked=sqlite.get("uncompressed_bytes"))
    if BRAZIL_ZIP in zips:
        add_zip(BRAZIL_ZIP, "national", BR)
    if BRAZIL_CAMERAS_ZIP in zips:
        add_zip(BRAZIL_CAMERAS_ZIP, "national", BR, content="cameras")
    for path in sorted(p for p in repo_files if p.startswith("brasil/")):
        sha, size = repo_files[path]
        add_member(path, "national", BR, BRAZIL_ZIP, path, sha, size, committed)

    versions = {e["sqlite"].get("schema_version") for e in ufs.values()
                if isinstance(e, dict) and isinstance(e.get("sqlite"), dict)}
    sqlite_version = versions.pop() if len(versions) == 1 else SQLITE_SCHEMA_VERSION
    return {
        "name": CONTRACT_NAME,
        "version": CONTRACT_VERSION,
        "min_reader_version": CONTRACT_MIN_READER_VERSION,
        "dataset": DATASET,
        "build_id": build_id(cat),
        "built_at": cat["built_at"],
        "release_url": release_url,
        "generator": {"repository": f"https://github.com/{repo}", "commit": generator_commit},
        "license": {"data": DATA_LICENSE, "code": CODE_LICENSE, "attribution": ATTRIBUTION},
        "coordinates": {"crs": "EPSG:4326", "bbox_order": BBOX_ORDER},
        "osm_snapshot": _osm_snapshot(extracts),
        "sources": _sources(cat, extracts),
        "compatibility": {
            "mix_generations": True,
            "data_format": {"name": "pardal", "version": str(PACK_SCHEMA)},
            DATASET: {
                "pack_schema": PACK_SCHEMA,
                "sqlite_schema_version": sqlite_version,
                "sqlite_min_version": SQLITE_MIN_VERSION,
                "sqlite_spec": f"https://github.com/{repo}/blob/{generator_commit or 'main'}/{SQLITE_SPEC}",
                "coordinate_order": dict(COORDINATE_ORDER),
            },
        },
        "files": files,
    }
