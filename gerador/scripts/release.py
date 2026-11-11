"""Release de uma geração dos dados: pacotes zip + nota com as contagens, no GitHub.

    python scripts/release.py --previous catalogo_antes.json            # só monta (em data/release/)
    python scripts/release.py --previous catalogo_antes.json --create    # monta e cria a release (gh)
    ... --release-only --skip-if-same    # dia sem commit: só a release, e só se os dados mudaram

Os dados vão para a release todo dia que houver dado novo, e para o repositório só aos domingos
(.github/workflows/gerar-dados.yml). --skip-if-same compara os sha256 dos arquivos com os do
catálogo de --previous (o da última release) e não cria nada se forem os mesmos.

Roda depois do publish.py --commit: os pacotes saem dos arquivos já publicados (brasil/,
estados/, catalogo.json na raiz do repositório), mais os que vão só na release
(publish._RELEASE_ONLY_NAME: limites_trechos.csv), tirados do build (--dist, data/dist/estados/<UF>/). Uma release por geração, com a etiqueta
dados-AAAA-MM-DD (data de geração do catalogo.json, UTC) apontando para o commit dos dados.

Anexos:
    pardal-<UF>.zip               um estado: todos os arquivos dele, inclusive os limites em trechos
                                  (limites_trechos.csv, que só existe aqui)
    pardal-<UF>.sqlite.zst        o estado num banco SQLite compactado (zstd), tirado do build (--dist);
                                  formato em docs/FORMATO_SQLITE.md
    (cada zip leva o LICENCA-DADOS.txt: ODbL, © colaboradores do OpenStreetMap e as fontes)
    pardal-brasil.zip             o Brasil inteiro (os mesmos arquivos de brasil/)
    pardal-brasil-radares.zip     só os radares do Brasil, nos quatro formatos (para GPS e apps)
    catalogo.json                  o índice dos pacotes
    SHA256SUMS.txt                sha256 de cada anexo
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import zipfile
from typing import Dict, List, Optional, Set, Tuple

GENERATOR_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(GENERATOR_DIR)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from publish import _RELEASE_ASSET_NAME, _RELEASE_ONLY_NAME  # noqa: E402

CAMERA_FILES = ("radares.csv", "radares.geojson", "radares.kml", "radares.gpx")


def _catalog_path(repo: str) -> str:
    """O catálogo do repositório; o nome antigo (catalog.json) se o novo ainda não existir."""
    path = os.path.join(repo, "catalogo.json")
    return path if os.path.exists(path) else os.path.join(repo, "catalog.json")


def _fmt(n: Optional[int]) -> str:
    return "—" if n is None else f"{n:,}".replace(",", ".")


def _delta(new: Optional[int], before: Optional[int]) -> str:
    if new is None or before is None or new == before:
        return ""
    d = new - before
    return f" ({'+' if d > 0 else '−'}{_fmt(abs(d))})"


def _counts(cat: Optional[dict], uf: str) -> Dict[str, int]:
    return ((cat or {}).get("ufs", {}).get(uf) or {}).get("counts") or {}


LICENSE_FILE = "LICENCA-DADOS.txt"


def license_text(cat: dict, uf: Optional[str], repo_url: str) -> str:
    """O aviso de licença e atribuição que vai dentro de cada zip (quem baixa só o zip também precisa
    dele): ODbL, © colaboradores do OpenStreetMap e as fontes. `uf` None = o Brasil inteiro (as fontes
    de todos os estados). Puro, testado."""
    ufs = cat.get("ufs") or {}
    if uf is None:
        sources = sorted({s for k, e in ufs.items() if k != "BR"
                          for s in ((e.get("coverage") or {}).get("sources") or [])})
        where = "Brasil inteiro"
    else:
        sources = sorted((ufs.get(uf, {}).get("coverage") or {}).get("sources") or [])
        where = f"estado {uf}"
    built = str(cat.get("built_at", ""))
    return "\n".join([
        "Pardal: radares e limites de velocidade do Brasil",
        f"Pacote: {where}. Gerado em {built.replace('T', ' ').replace('Z', ' UTC')}.",
        "",
        "LICENÇA DOS DADOS: Open Database License (ODbL) 1.0",
        "https://opendatacommons.org/licenses/odbl/1-0/",
        "",
        "Base derivada do OpenStreetMap: © colaboradores do OpenStreetMap",
        "https://www.openstreetmap.org/copyright",
        "",
        "Ao usar ou redistribuir estes dados:",
        "- cite \"© colaboradores do OpenStreetMap\" e as fontes abaixo;",
        "- uma base derivada que você publicar precisa manter a ODbL 1.0.",
        "",
        f"Fontes dos radares deste pacote: {', '.join(sources) if sources else '(nenhuma informada)'}.",
        "Demais bases: limites, estruturas, lombadas, pedágios e pontos de atenção do OpenStreetMap;",
        "quilometragem das rodovias federais (SNV) e buracos (ICM) do DNIT; praças de pedágio e placas",
        "da ANTT; trechos de radar portátil, multas e acidentes da PRF; situação dos medidores do",
        "Inmetro; malha das UFs e endereços (CNEFE) do IBGE.",
        "",
        "Dados abertos de órgãos públicos (Lei 12.527/2011). Nenhum desses órgãos endossa este conjunto.",
        "Não é fonte oficial: a sinalização da via sempre prevalece.",
        "",
        f"Tabela completa das fontes e colunas: {repo_url} (README).",
        "",
    ])


def _zip(path: str, files: List[str], arcdir: str, license: Optional[str] = None) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in files:
            z.write(f, f"{arcdir}/{os.path.basename(f)}")
        if license is not None:
            z.writestr(f"{arcdir}/{LICENSE_FILE}", license)


def _sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _release_only(dist: Optional[str], uf: str) -> List[str]:
    """Os arquivos do estado que vão só na release, do build em dist (vazio sem dist)."""
    d = os.path.join(dist, "estados", uf) if dist else ""
    if not d or not os.path.isdir(d):
        return []
    return [os.path.join(d, f) for f in os.listdir(d) if _RELEASE_ONLY_NAME.match(f)]


def _sqlite_assets(catalog: dict, dist: Optional[str], out: str) -> List[str]:
    """Os bancos SQLite (pardal-<UF>.sqlite.zst) do build em `dist`, copiados para out/: só os que o catálogo lista
    (entrada `sqlite`, release_asset), e com o sha256 dele (outro arquivo é erro: o app recusaria o download)."""
    import shutil
    out_files: List[str] = []
    for uf, entry in sorted((catalog.get("ufs") or {}).items()):
        meta = (entry or {}).get("sqlite") if isinstance(entry, dict) else None
        name = (meta or {}).get("release_asset") or os.path.basename((meta or {}).get("file") or "")
        if not dist or not meta or not _RELEASE_ASSET_NAME.match(name):
            continue
        src = os.path.join(dist, "estados", uf, name)
        if not os.path.isfile(src) or _sha(src) != meta.get("sha256"):
            raise SystemExit(f"{name}: o arquivo do build ({src}) não é o que o catálogo lista")
        out_files.append(os.path.join(out, name))
        shutil.copyfile(src, out_files[-1])
    return out_files


def build_assets(repo: str, out: str, dist: Optional[str] = None,
                 repo_url: str = "https://github.com/murkiriel/pardal") -> List[str]:
    """Monta os zips em out/ a partir de brasil/ e estados/ do repositório, mais os arquivos de cada
    estado que vão só na release (do build em `dist`); cada zip leva o LICENCA-DADOS.txt. Os bancos SQLite
    dos estados (do build) vão como anexos próprios. Devolve os anexos."""
    os.makedirs(out, exist_ok=True)
    with open(_catalog_path(repo), encoding="utf-8") as f:
        catalog = json.load(f)
    assets: List[str] = []
    est = os.path.join(repo, "estados")
    for uf in sorted(os.listdir(est)):
        d = os.path.join(est, uf)
        files = sorted([os.path.join(d, f) for f in os.listdir(d) if os.path.isfile(os.path.join(d, f))]
                       + _release_only(dist, uf), key=os.path.basename)
        if files:
            assets.append(os.path.join(out, f"pardal-{uf}.zip"))
            _zip(assets[-1], files, uf, license_text(catalog, uf, repo_url))
    assets += _sqlite_assets(catalog, dist, out)
    br = os.path.join(repo, "brasil")
    files = sorted(os.path.join(br, f) for f in os.listdir(br) if os.path.isfile(os.path.join(br, f)))
    assets.append(os.path.join(out, "pardal-brasil.zip"))
    _zip(assets[-1], files, "brasil", license_text(catalog, None, repo_url))
    assets.append(os.path.join(out, "pardal-brasil-radares.zip"))
    _zip(assets[-1], [f for f in files if os.path.basename(f) in CAMERA_FILES], "brasil",
         license_text(catalog, None, repo_url))
    cat = os.path.join(out, "catalogo.json")
    with open(_catalog_path(repo), "rb") as fi, open(cat, "wb") as fo:
        fo.write(fi.read())
    assets.append(cat)
    sums = os.path.join(out, "SHA256SUMS.txt")
    with open(sums, "w", encoding="utf-8", newline="\n") as f:
        for a in assets:
            f.write(f"{_sha(a)}  {os.path.basename(a)}\n")
    assets.append(sums)
    return assets


def tag_for(cat: dict) -> str:
    return "dados-" + str(cat.get("built_at", ""))[:10]


def data_fingerprint(cat: Optional[dict]) -> set:
    """(arquivo, sha256) de cada arquivo de dado do catálogo (por estado e do Brasil), sem as datas:
    dois catálogos com a mesma impressão têm exatamente os mesmos dados. O banco SQLite (`sqlite`) fica de fora:
    é feito dos mesmos CSVs e traz as datas da geração (built_at, observed_at). Puro, testado."""
    out: Set[Tuple[str, str]] = set()
    if not cat:
        return out

    def add(value) -> None:
        if isinstance(value, dict) and value.get("sha256"):
            out.add((value.get("file") or value.get("asset_path") or "", value["sha256"]))
    for value in cat.values():
        add(value)
    for entry in (cat.get("ufs") or {}).values():
        if isinstance(entry, dict):
            for key, value in entry.items():
                if key != "sqlite":
                    add(value)
    return out


def release_notes(cat: dict, previous: Optional[dict], warnings: List[str], repo_url: str,
                  in_repo: bool = True) -> str:
    """Texto da release (Markdown): resumo do Brasil, downloads, tabela por estado com a
    diferença para a geração anterior, avisos. `in_repo`: os mesmos arquivos foram para o
    repositório nesta geração (domingo) ou só para a release (os outros dias). Puro, testado."""
    d = str(cat.get("built_at", ""))
    data = f"{d[8:10]}/{d[5:7]}/{d[0:4]}"
    br, br0 = _counts(cat, "BR"), _counts(previous, "BR")
    where = ("Os mesmos arquivos estão em `brasil/`, `estados/` e `catalogo.json` no commit desta versão."
             if in_repo else
             "Estes dados estão só nesta release: os arquivos do repositório (`brasil/`, `estados/`, "
             "`catalogo.json`) são atualizados aos domingos.")
    L = [f"Dados gerados em {data} ({d.replace('T', ' ').replace('Z', ' UTC')}) a partir das fontes "
         f"oficiais e do OpenStreetMap. {where}", "",
         "## Brasil", "",
         "| | Nesta versão |", "|---|---|"]
    for k, rot in (("cameras", "Radares"), ("limits", "Pontos de limite sinalizado"),
                   ("limits_estimated", "Pontos de limite estimado"), ("structs", "Pontes e túneis")):
        L.append(f"| {rot} | {_fmt(br.get(k))}{_delta(br.get(k), br0.get(k))} |")
    L += ["", "## Downloads", "",
          "- `pardal-<UF>.zip` — um estado: todos os arquivos dele, inclusive os limites em trechos "
          "(`limites_trechos.csv`, que só existe aqui, não no repositório)",
          "- `pardal-<UF>.sqlite.zst` — o mesmo estado num banco SQLite compactado (zstd), com id estável, "
          "índice por célula e os trechos sem WKT (formato em `docs/FORMATO_SQLITE.md`)",
          "- `pardal-brasil.zip` — o Brasil inteiro",
          "- `pardal-brasil-radares.zip` — só os radares do Brasil, nos quatro formatos (GPS e apps)",
          "- `catalogo.json` — índice dos pacotes; `SHA256SUMS.txt` — para conferir os arquivos",
          "",
          "Cada zip traz o `LICENCA-DADOS.txt`: os dados são ODbL 1.0 (© colaboradores do OpenStreetMap); "
          "cite as fontes e mantenha a licença em bases derivadas.",
          "",
          f"Link fixo para a versão mais recente: `{repo_url}/releases/latest/download/pardal-SP.zip` "
          "(troque a sigla do estado, ou use `pardal-brasil.zip`).",
          "", "## Por estado", ""]
    has_previous = bool(previous)
    L += ["| UF | Radares | Pontos de limite | Pontes e túneis |", "|---|---|---|---|"]
    for uf in sorted(u for u in cat.get("ufs", {}) if u != "BR"):
        c, c0 = _counts(cat, uf), _counts(previous, uf)
        L.append(f"| {uf} | {_fmt(c.get('cameras'))}{_delta(c.get('cameras'), c0.get('cameras'))} "
                 f"| {_fmt(c.get('limits'))}{_delta(c.get('limits'), c0.get('limits'))} "
                 f"| {_fmt(c.get('structs'))}{_delta(c.get('structs'), c0.get('structs'))} |")
    if has_previous:
        L += ["", "Entre parênteses, a diferença para a geração anterior."]
    if warnings:
        L += ["", "## Avisos", "",
              "Fontes que falharam nesta geração e foram lidas da cópia anterior guardada:", ""]
        L += [f"- {a}" for a in warnings]
    L += ["", "Dados sob a licença ODbL 1.0 (citar as fontes, manter a licença em bases derivadas); "
          "fontes e colunas no README do repositório."]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=REPO)
    ap.add_argument("--previous", help="catalogo.json publicado antes desta geração (para as diferenças)")
    ap.add_argument("--warnings", help="catalogo.json do build (data/dist), com a lista de avisos")
    ap.add_argument("--out", default=os.path.join(GENERATOR_DIR, "data", "release"))
    ap.add_argument("--dist", default=os.path.join(GENERATOR_DIR, "data", "dist"),
                    help="saída do build, de onde vêm os arquivos que vão só na release (limites_trechos.csv)")
    ap.add_argument("--create", action="store_true", help="cria a release no GitHub (gh)")
    ap.add_argument("--repo-url", default="https://github.com/murkiriel/pardal")
    ap.add_argument("--release-only", action="store_true",
                    help="dados só na release, sem commit no repositório (dias que não são domingo)")
    ap.add_argument("--skip-if-same", action="store_true",
                    help="não monta nem cria nada se os dados forem os mesmos do catálogo de --previous")
    args = ap.parse_args(argv)

    with open(_catalog_path(args.repo), encoding="utf-8") as f:
        cat = json.load(f)
    previous = None
    if args.previous and os.path.exists(args.previous):
        with open(args.previous, encoding="utf-8-sig") as f:
            previous = json.load(f)
    warnings: List[str] = []
    if args.warnings and os.path.exists(args.warnings):
        with open(args.warnings, encoding="utf-8-sig") as f:
            warnings = json.load(f).get("warnings") or []

    if args.skip_if_same and previous and data_fingerprint(cat) == data_fingerprint(previous):
        print("Os dados são os mesmos da geração anterior: sem release.")
        return 0
    assets = build_assets(args.repo, args.out, args.dist, args.repo_url)
    notes_path = os.path.join(args.out, "NOTAS.md")
    with open(notes_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(release_notes(cat, previous, warnings, args.repo_url, in_repo=not args.release_only))
    tag = tag_for(cat)
    d = str(cat.get("built_at", ""))
    title = f"Dados de {d[8:10]}/{d[5:7]}/{d[0:4]}"
    print(f"{len(assets)} anexos e a nota em {args.out}; etiqueta {tag}")
    if not args.create:
        return 0

    def gh(*a: str, check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(["gh", *a], cwd=args.repo, check=check, capture_output=True, text=True)

    if gh("release", "view", tag, check=False).returncode == 0:   # segunda geração no mesmo dia
        tag = f"{tag}-{d[11:13]}{d[14:16]}"
        title += f" ({d[11:16]} UTC)"
    sha = subprocess.run(["git", "-C", args.repo, "rev-parse", "HEAD"], check=True,
                         capture_output=True, text=True).stdout.strip()
    gh("release", "create", tag, *assets, "--title", title, "--notes-file", notes_path,
       "--target", sha, "--latest")
    print(f"release {tag} criada ({sha[:7]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
