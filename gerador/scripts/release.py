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
from publish import _PUBLISHED_NAME, _RELEASE_ASSET_NAME, _RELEASE_ONLY_NAME  # noqa: E402

CAMERA_FILES = ("radares.csv", "radares.geojson", "radares.kml", "radares.gpx")
# O endereço do repositório escrito no LICENCA-DADOS.txt de cada zip (--repo-url muda; o publish.py usa este).
REPO_URL = "https://github.com/murkiriel/pardal"


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


# Data fixa de cada arquivo dentro dos zips: o mesmo conteúdo dá o mesmo zip, byte a byte, em qualquer montagem. É o que
# deixa o publish.py pôr no catálogo o sha256 do zip antes de o release.py montá-lo (contrato de catálogo,
# datakit/catalog_contract.py); o release.py confere os dois antes de criar a release.
ZIP_DATE = (1980, 1, 1, 0, 0, 0)


def _zip_entry(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, ZIP_DATE)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    return info


def _zip(path: str, files: List[str], arcdir: str, license: Optional[str] = None) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in files:
            with open(f, "rb") as fh:
                z.writestr(_zip_entry(f"{arcdir}/{os.path.basename(f)}"), fh.read(), compresslevel=9)
        if license is not None:
            z.writestr(_zip_entry(f"{arcdir}/{LICENSE_FILE}"), license, compresslevel=9)


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


def zip_inputs(root: str, catalog: dict, dist: Optional[str] = None, repo_url: str = REPO_URL,
               published_only: bool = False) -> List[Tuple[str, List[str], str, str]]:
    """[(nome do anexo, arquivos, pasta dentro do zip, LICENCA-DADOS.txt)] dos zips, a partir de root/estados e
    root/brasil (o repositório), mais os arquivos de cada estado que vão só na release (do build em `dist`).
    `published_only`: root é o próprio build (data/dist), e só entram os nomes publicados (publish._PUBLISHED_NAME),
    os mesmos que o publish.py copia para o repositório."""
    def keep(name: str) -> bool:
        return not published_only or bool(_PUBLISHED_NAME.match(name))
    out: List[Tuple[str, List[str], str, str]] = []
    est = os.path.join(root, "estados")
    for uf in sorted(os.listdir(est)) if os.path.isdir(est) else []:
        d = os.path.join(est, uf)
        files = sorted([os.path.join(d, f) for f in os.listdir(d) if os.path.isfile(os.path.join(d, f)) and keep(f)]
                       + _release_only(dist, uf), key=os.path.basename)
        if files:
            out.append((f"pardal-{uf}.zip", files, uf, license_text(catalog, uf, repo_url)))
    br = os.path.join(root, "brasil")
    if os.path.isdir(br):
        files = sorted(os.path.join(br, f) for f in os.listdir(br) if os.path.isfile(os.path.join(br, f)) and keep(f))
        brazil = license_text(catalog, None, repo_url)
        out.append(("pardal-brasil.zip", files, "brasil", brazil))
        out.append(("pardal-brasil-radares.zip", [f for f in files if os.path.basename(f) in CAMERA_FILES], "brasil",
                    brazil))
    return out


def predict_zips(dist: str, catalog: dict, repo_url: str = REPO_URL) -> Dict[str, Tuple[str, int]]:
    """{nome do zip: (sha256, bytes)} dos zips que build_assets vai montar do repositório depois que o publish.py copiar
    para lá o build em `dist`: montados aqui do próprio build, num diretório provisório, iguais byte a byte (ZIP_DATE)."""
    import tempfile
    out: Dict[str, Tuple[str, int]] = {}
    with tempfile.TemporaryDirectory() as tmp:
        for name, files, arcdir, license in zip_inputs(dist, catalog, dist, repo_url, published_only=True):
            path = os.path.join(tmp, name)
            _zip(path, files, arcdir, license)
            out[name] = (_sha(path), os.path.getsize(path))
            os.remove(path)
    return out


def build_assets(repo: str, out: str, dist: Optional[str] = None,
                 repo_url: str = REPO_URL) -> List[str]:
    """Monta os zips em out/ a partir de brasil/ e estados/ do repositório, mais os arquivos de cada
    estado que vão só na release (do build em `dist`); cada zip leva o LICENCA-DADOS.txt. Os bancos SQLite
    dos estados (do build) vão como anexos próprios. Devolve os anexos."""
    os.makedirs(out, exist_ok=True)
    with open(_catalog_path(repo), encoding="utf-8") as f:
        catalog = json.load(f)
    assets: List[str] = []
    inputs = zip_inputs(repo, catalog, dist, repo_url)
    for name, files, arcdir, license in inputs:
        if name.startswith("pardal-brasil"):
            continue
        assets.append(os.path.join(out, name))
        _zip(assets[-1], files, arcdir, license)
    assets += _sqlite_assets(catalog, dist, out)
    for name, files, arcdir, license in inputs:
        if name.startswith("pardal-brasil"):
            assets.append(os.path.join(out, name))
            _zip(assets[-1], files, arcdir, license)
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


def contract_mismatches(catalog: dict, assets: List[str]) -> List[str]:
    """Os anexos que o bloco `contract` do catálogo lista e que não saíram como ele diz (sha256 ou tamanho), ou que
    não saíram. Vazio = o catálogo descreve a release. Catálogo sem o bloco: nada a conferir."""
    block = catalog.get("contract")
    if not block:
        return []
    built = {os.path.basename(a): a for a in assets}
    prefix = block["release_url"]
    problems = []
    for f in block["files"]:
        if "member" in f or not f["url"].startswith(prefix):
            continue   # membro de um zip (conferido pelo zip) ou arquivo do repositório
        name = f["url"][len(prefix):]
        path = built.get(name)
        if path is None:
            problems.append(f"{name}: o catálogo lista, mas não foi montado")
        elif (_sha(path), os.path.getsize(path)) != (f["sha256"], f["bytes"]):
            problems.append(f"{name}: sha256 ou tamanho diferente do catálogo")
    return problems


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
    ap.add_argument("--repo-url", default=REPO_URL)
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

    # O catálogo com o bloco `contract` aponta os arquivos do repositório e os anexos para a etiqueta desta geração: no
    # commit semanal (sem --release-only) a release sai mesmo com os dados iguais aos da anterior, senão os endereços
    # do catálogo que acabou de ir para o repositório ficariam sem release.
    contract = cat.get("contract")
    if args.skip_if_same and previous and data_fingerprint(cat) == data_fingerprint(previous):
        if not contract or args.release_only:
            print("Os dados são os mesmos da geração anterior: sem release.")
            return 0
        print("Os dados são os mesmos da geração anterior, mas o catálogo do repositório aponta para esta release.")
    assets = build_assets(args.repo, args.out, args.dist, args.repo_url)
    problems = contract_mismatches(cat, assets)
    if problems:
        raise SystemExit("o catálogo (contract) não descreve os anexos montados; nada foi publicado:\n  "
                         + "\n  ".join(problems))
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
        if contract:
            raise SystemExit(f"a release {tag} já existe e o catálogo (contract) aponta para ela; apague a outra "
                             "release do dia ou gere de novo amanhã")
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
