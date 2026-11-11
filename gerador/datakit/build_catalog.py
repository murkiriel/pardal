"""data/packs/<UF>/  ->  data/dist/  (arquivos publicáveis por estado + catalogo.json).

data/dist tem a mesma estrutura do que é publicado na raiz do repositório:
  data/dist/estados/<UF>/radares.csv, limites.csv, estruturas.csv
  data/dist/catalogo.json            (com os caminhos já como no repositório)

Quem consome os pacotes lê o catalogo.json da raiz do repositório e baixa os arquivos que ele
lista; scripts/publish.py só copia data/dist para lá.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from typing import Optional

from datakit.build_pack import (ACCIDENTS_FILE, BUMPS_FILE, CAMERAS_FILE, ENFORCEMENT_FILE, HAZARDS_FILE, LIMIT_LINES_FILE, LIMITS_FILE,
                                 MANIFEST_FILE, POTHOLES_FILE, RADAR_ZONES_FILE, STRUCTS_FILE, TOLLS_FILE)
from datakit.common import AccidentZone, EnforcementCamera, LimitLine, PotholeZone, RadarZone
from datakit.common.ufs import SOURCE_HOME_UF, uf_name

# Versão do formato do catálogo. 2 (2026-09-30): nome catalogo.json e etiquetas em inglês (name,
# coverage, cameras, limits, limits_estimated, structs, included_ufs); a 1 era catalog.json com
# nome, cobertura, radares, limites, limites_estimados, estruturas, ufs_incluidas.
SCHEMA = 2

_FEDERAL = {"DNIT", "ANTT"}
_MUNICIPAL = {"PMF", "PCR", "PMJP", "CET-SP", "RIO", "BHTRANS", "CURITIBA", "EPTC", "TRANSALVADOR", "SEMTRAN-PVH"}
# Órgãos estaduais que não se chamam DER-*.
_STATE = {"DETRAN-DF", "AGETO-TO", "DETRAN-MA", "SEINFRA-BA"}


def _coverage(cameras_csv: str, uf: str) -> dict:
    """Que tipo de fonte de radar entrou nesta UF — pra UI ser honesta. `sources` lista todas;
    `level` só conta órgão estadual ou municipal da própria UF: um radar do DER-SP colado na
    divisa aparece no pacote de MG, mas não faz de MG um estado com cobertura estadual. O
    Detran-DF conta como estadual (era a maior fonte oficial e o DF saía só como "federal"), como
    os outros órgãos estaduais que não se chamam DER-* (_STATE)."""
    srcs: set = set()
    try:
        with open(cameras_csv, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                srcs.update(p for p in (r.get("source") or "").split("+") if p)
    except OSError:
        pass
    local = {s for s in srcs if SOURCE_HOME_UF.get(s, uf) == uf}
    parts = []
    if srcs & _FEDERAL:
        parts.append("federal")
    if any(s.startswith("DER-") or s in _STATE for s in local):
        parts.append("state")
    if local & _MUNICIPAL:
        parts.append("municipal")
    if "OSM" in srcs and not parts:
        parts.append("osm")
    return {"level": "+".join(parts) or "none", "sources": sorted(srcs)}


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _file_ref(path: str, count: Optional[int], dist_dir: str) -> dict:
    return {
        "file": os.path.relpath(path, dist_dir).replace(os.sep, "/"),
        "bytes": os.path.getsize(path),
        "sha256": _sha256(path),
        "count": count,
    }


def _sqlite_ref(uf: str, pack_dir: str, out: str, manifest: dict, dist_dir: str) -> Optional[dict]:
    """A entrada `sqlite` do estado: o banco do pacote conferido contra os CSVs que acabaram de ir para `out` (mesma
    geração: contagem por tipo, integrity_check, esquema; build_sqlite.validate) e compactado em
    out/pardal-<UF>.sqlite.zst. O arquivo não vai para o repositório (scripts/publish.py, _RELEASE_ASSET_NAME): a
    entrada publicada troca "file" por "release_asset". Problema na conferência ou banco acima do teto de 95 MB por
    arquivo: falha registrada (o publish.py não monta) e o estado sai sem o banco. Sem banco no pacote: None."""
    from datakit import build_sqlite, failures
    from datakit.build_brazil import MAX_FILE_BYTES
    src = os.path.join(pack_dir, build_sqlite.SQLITE_FILE)
    if not manifest.get("sqlite") or not os.path.isfile(src):
        return None
    try:
        problems, counts = build_sqlite.validate(src, out)
        if problems:
            raise ValueError("; ".join(problems))
        dst = os.path.join(out, build_sqlite.release_name(uf))
        build_sqlite.compress(src, dst)
        if os.path.getsize(dst) > MAX_FILE_BYTES:
            os.remove(dst)
            raise ValueError(f"{os.path.getsize(src) / 1e6:.1f} MB passa do teto de {MAX_FILE_BYTES / 1e6:.0f} MB "
                             "por arquivo mesmo compactado")
    except Exception as e:  # noqa: BLE001
        failures.record(f"sqlite {uf}", e)
        return None
    return {
        "file": os.path.relpath(dst, dist_dir).replace(os.sep, "/"),
        "bytes": os.path.getsize(dst),
        "sha256": _sha256(dst),
        "uncompressed_bytes": os.path.getsize(src),
        "uncompressed_sha256": _sha256(src),
        "schema_version": build_sqlite.SCHEMA_VERSION,
        "count": sum(counts.values()),
        "counts": counts,
    }


def build(packs_dir: str, dist_dir: str, base_url: str = "") -> dict:
    os.makedirs(dist_dir, exist_ok=True)
    states_dir = os.path.join(dist_dir, "estados")
    shutil.rmtree(states_dir, ignore_errors=True)   # refeito inteiro: nada de um build anterior fica
    ufs: dict = {}
    for uf in sorted(os.listdir(packs_dir)):
        pdir = os.path.join(packs_dir, uf)
        man_path = os.path.join(pdir, MANIFEST_FILE)
        if not os.path.isfile(man_path):
            continue
        with open(man_path, encoding="utf-8") as f:
            man = json.load(f)

        out = os.path.join(states_dir, uf)
        os.makedirs(out, exist_ok=True)
        rad_dst = os.path.join(out, CAMERAS_FILE)
        lim_dst = os.path.join(out, LIMITS_FILE)
        shutil.copyfile(os.path.join(pdir, CAMERAS_FILE), rad_dst)
        shutil.copyfile(os.path.join(pdir, LIMITS_FILE), lim_dst)

        counts = man.get("counts", {})
        entry = {
            "name": uf_name(uf),
            "bbox": man.get("bbox", []),
            "built_at": man.get("built_at"),
            "artifact_built_at": man.get("artifact_built_at"),
            "coverage": _coverage(os.path.join(pdir, CAMERAS_FILE), uf),
            "cameras": _file_ref(rad_dst, counts.get("cameras"), dist_dir),
            "limits": _file_ref(lim_dst, counts.get("limits"), dist_dir),
            "counts": counts,
        }
        struct_src = os.path.join(pdir, STRUCTS_FILE)
        if os.path.exists(struct_src) and os.path.getsize(struct_src) > 40:  # > só o cabeçalho
            struct_dst = os.path.join(out, STRUCTS_FILE)
            shutil.copyfile(struct_src, struct_dst)
            entry["structs"] = _file_ref(struct_dst, counts.get("structs"), dist_dir)
        # lombadas e quebra-molas (pacote schema 3): só a UF que tem alguma; chave nova, quem não a conhece a ignora
        bump_src = os.path.join(pdir, BUMPS_FILE)
        if os.path.exists(bump_src) and os.path.getsize(bump_src) > len("lat,lng,kind\n"):
            bump_dst = os.path.join(out, BUMPS_FILE)
            shutil.copyfile(bump_src, bump_dst)
            entry["bumps"] = _file_ref(bump_dst, counts.get("bumps"), dist_dir)
        # pontos de atenção (pacote schema 9): só a UF que tem algum
        hazard_src = os.path.join(pdir, HAZARDS_FILE)
        if os.path.exists(hazard_src) and os.path.getsize(hazard_src) > len("lat,lng,kind\n"):
            hazard_dst = os.path.join(out, HAZARDS_FILE)
            shutil.copyfile(hazard_src, hazard_dst)
            entry["hazards"] = _file_ref(hazard_dst, counts.get("hazards"), dist_dir)
        # pedágios (pacote schema 4): só a UF que tem algum
        toll_src = os.path.join(pdir, TOLLS_FILE)
        if os.path.exists(toll_src) and os.path.getsize(toll_src) > len("lat,lng,kind,name,source\n"):
            toll_dst = os.path.join(out, TOLLS_FILE)
            shutil.copyfile(toll_src, toll_dst)
            entry["tolls"] = _file_ref(toll_dst, counts.get("tolls"), dist_dir)
        # trechos aptos ao radar portátil (pacote schema 5): só a UF que tem algum
        zone_src = os.path.join(pdir, RADAR_ZONES_FILE)
        if os.path.exists(zone_src) and os.path.getsize(zone_src) > len(",".join(RadarZone.HEADER)) + 1:
            zone_dst = os.path.join(out, RADAR_ZONES_FILE)
            shutil.copyfile(zone_src, zone_dst)
            entry["portable_radar"] = _file_ref(zone_dst, counts.get("portable_radar"), dist_dir)
        # trechos com buracos (pacote schema 6): só a UF que tem algum
        hole_src = os.path.join(pdir, POTHOLES_FILE)
        if os.path.exists(hole_src) and os.path.getsize(hole_src) > len(",".join(PotholeZone.HEADER)) + 1:
            hole_dst = os.path.join(out, POTHOLES_FILE)
            shutil.copyfile(hole_src, hole_dst)
            entry["potholes"] = _file_ref(hole_dst, counts.get("potholes"), dist_dir)
        # trechos com muitos acidentes com moto (pacote schema 8): só a UF que tem algum
        acc_src = os.path.join(pdir, ACCIDENTS_FILE)
        if os.path.exists(acc_src) and os.path.getsize(acc_src) > len(",".join(AccidentZone.HEADER)) + 1:
            acc_dst = os.path.join(out, ACCIDENTS_FILE)
            shutil.copyfile(acc_src, acc_dst)
            entry["moto_accidents"] = _file_ref(acc_dst, counts.get("moto_accidents"), dist_dir)
        # limites como trechos de via (pacote schema 10): só a UF que tem algum
        lt_src = os.path.join(pdir, LIMIT_LINES_FILE)
        if os.path.exists(lt_src) and os.path.getsize(lt_src) > len(",".join(LimitLine.HEADER)) + 1:
            lt_dst = os.path.join(out, LIMIT_LINES_FILE)
            shutil.copyfile(lt_src, lt_dst)
            entry["limit_lines"] = _file_ref(lt_dst, counts.get("limit_lines"), dist_dir)
        # câmeras de fiscalização que não medem velocidade (pacote schema 11): só a UF que tem alguma
        enf_src = os.path.join(pdir, ENFORCEMENT_FILE)
        if os.path.exists(enf_src) and os.path.getsize(enf_src) > len(",".join(EnforcementCamera.HEADER)) + 1:
            enf_dst = os.path.join(out, ENFORCEMENT_FILE)
            shutil.copyfile(enf_src, enf_dst)
            entry["enforcement_cameras"] = _file_ref(enf_dst, counts.get("enforcement_cameras"), dist_dir)
        # o banco SQLite do estado (build_sqlite.py): conferido contra os CSVs acima e compactado; vai só na release
        sqlite_entry = _sqlite_ref(uf, pdir, out, man, dist_dir)
        if sqlite_entry is not None:
            entry["sqlite"] = sqlite_entry
        ufs[uf] = entry

    catalog = {
        "schema": SCHEMA,
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "base_url": base_url,  # dica; quem consome pode sobrescrever
        "ufs": ufs,
    }
    with open(os.path.join(dist_dir, "catalogo.json"), "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)
    return catalog


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="datakit.build_catalog")
    ap.add_argument("--packs", default="data/packs")
    ap.add_argument("--dist", default="data/dist")
    ap.add_argument("--base-url", default="", help="URL base pública dos arquivos (opcional)")
    args = ap.parse_args(argv)
    cat = build(args.packs, args.dist, args.base_url)
    tot_r = sum(u["cameras"]["count"] or 0 for u in cat["ufs"].values())
    tot_l = sum(u["limits"]["count"] or 0 for u in cat["ufs"].values())
    print(f"[catalog] {len(cat['ufs'])} UF(s), {tot_r} radares, {tot_l} limites -> {args.dist}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
