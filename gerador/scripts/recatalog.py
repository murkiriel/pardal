"""Refaz o catalogo.json de uma geração já publicada com o bloco `contract` (docs/CATALOGO.md), sem refazer os dados.

    python scripts/recatalog.py --tag dados-2026-11-08 --out catalogo-refeito.json
    python scripts/recatalog.py --tag dados-2026-11-10 --release-only --out catalogo-refeito.json

Lê o catálogo da geração (o do repositório na etiqueta; com --release-only, o anexo catalogo.json da release), o
SHA256SUMS.txt e o tamanho dos anexos da release (pelo `gh`, só leitura) e acrescenta só a chave `contract`; as outras
saem iguais. Numa geração que foi para o repositório (o commit semanal), os arquivos de estados/ e brasil/ são lidos do
git na etiqueta; o commit do gerador é o pai do commit dos dados. Numa geração só da release, entram só os arquivos que
o catálogo lista com sha256 (os GeoJSON, KML e GPX ficam de fora: o sha256 deles só existe dentro do zip), e o commit
do gerador é o da etiqueta. Os extratos do OpenStreetMap não entram: os manifestos do build não são publicados. Não
publica nada: grava em --out.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from typing import Dict, Tuple

GENERATOR_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(GENERATOR_DIR)
sys.path.insert(0, GENERATOR_DIR)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from datakit import catalog_contract  # noqa: E402
from publish import _PUBLISHED_NAME  # noqa: E402


def _git(repo: str, *args: str) -> str:
    return subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True, text=True).stdout.strip()


def read_sums(path: str) -> Dict[str, str]:
    """{nome do anexo: sha256} de um SHA256SUMS.txt (`<sha256>  <nome>`)."""
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                sha, name = line.split(None, 1)
                out[name.strip()] = sha
    return out


def committed_files(repo: str, tag: str) -> Dict[str, Tuple[str, int]]:
    """{caminho: (sha256, bytes)} dos arquivos publicados de estados/ e brasil/ no commit da etiqueta."""
    out = {}
    for path in _git(repo, "ls-tree", "-r", "--name-only", tag, "--", "estados", "brasil").splitlines():
        if _PUBLISHED_NAME.match(path.rsplit("/", 1)[-1]):
            data = subprocess.run(["git", "-C", repo, "show", f"{tag}:{path}"], check=True,
                                  capture_output=True).stdout
            out[path] = (hashlib.sha256(data).hexdigest(), len(data))
    return out


def listed_files(cat: dict) -> Dict[str, Tuple[str, int]]:
    """{caminho: (sha256, bytes)} dos arquivos do repositório que o catálogo lista com sha256."""
    out = {}
    entries = [cat.get("ufs_geojson")] + [v for e in (cat.get("ufs") or {}).values() if isinstance(e, dict)
                                          for v in e.values()]
    for value in entries:
        if isinstance(value, dict) and value.get("file") and value.get("sha256"):
            out[value["file"]] = (value["sha256"], value["bytes"])
    return out


def rebuild(published: dict, *, repo: str, tag: str, sums: Dict[str, str], sizes: Dict[str, int],
            committed: bool, slug: str = catalog_contract.DEFAULT_REPO) -> dict:
    if catalog_contract.release_tag(published["built_at"]) != tag:
        raise SystemExit(f"o catálogo é de {published['built_at']}, que não dá a etiqueta {tag}")
    repo_files = committed_files(repo, tag) if committed else listed_files(published)
    for path, (sha, _) in listed_files(published).items():
        if path in repo_files and repo_files[path][0] != sha:
            raise SystemExit(f"{path}: o arquivo na etiqueta não é o que o catálogo lista")
    zips = {name: (sha, sizes[name]) for name, sha in sums.items() if name.endswith(".zip")}
    commit = _git(repo, "rev-parse", f"{tag}^" if committed else tag)
    out = {key: value for key, value in published.items() if key != "contract"}
    out["contract"] = catalog_contract.contract(out, repo_files=repo_files, zips=zips, committed=committed,
                                                generator_commit=commit, repo=slug)
    return out


def _gh_release(tag: str, slug: str, folder: str) -> Tuple[Dict[str, str], Dict[str, int], dict]:
    """O SHA256SUMS.txt, o tamanho de cada anexo e o catalogo.json da release, pelo `gh` (só leitura)."""
    subprocess.run(["gh", "release", "download", tag, "-R", slug, "-p", "SHA256SUMS.txt", "-p", "catalogo.json",
                    "-D", folder], check=True)
    assets = json.loads(subprocess.run(["gh", "release", "view", tag, "-R", slug, "--json", "assets"], check=True,
                                       capture_output=True, text=True).stdout)["assets"]
    with open(os.path.join(folder, "catalogo.json"), encoding="utf-8") as f:
        released = json.load(f)
    return read_sums(os.path.join(folder, "SHA256SUMS.txt")), {a["name"]: int(a["size"]) for a in assets}, released


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tag", required=True, help="a etiqueta da release da geração (dados-AAAA-MM-DD)")
    ap.add_argument("--release-only", action="store_true", help="a geração saiu só na release (não foi para o git)")
    ap.add_argument("--repo", default=REPO)
    ap.add_argument("--slug", default=catalog_contract.DEFAULT_REPO)
    ap.add_argument("--out", required=True, help="onde gravar o catálogo refeito")
    args = ap.parse_args(argv)
    with tempfile.TemporaryDirectory() as folder:
        sums, sizes, released = _gh_release(args.tag, args.slug, folder)
    if args.release_only:
        published = released
    else:
        published = json.loads(_git(args.repo, "show", f"{args.tag}:catalogo.json"))
        if catalog_contract.fingerprint(released) != catalog_contract.fingerprint(published):
            raise SystemExit("o catálogo da release não é o do repositório na etiqueta: use --release-only?")
    out = rebuild(published, repo=args.repo, tag=args.tag, sums=sums, sizes=sizes, committed=not args.release_only,
                  slug=args.slug)
    if os.path.abspath(args.out) == os.path.abspath(os.path.join(args.repo, "catalogo.json")):
        raise SystemExit("--out não pode ser o catálogo do repositório: confira antes e troque à mão")
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    block = out["contract"]
    print(f"{block['build_id']}: {len(block['files'])} arquivos, commit {block['generator']['commit']} -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
