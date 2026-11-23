"""Rotina da geração no GitHub Actions: o que publicar, limpeza das releases e aviso de falha.

    python scripts/routine.py mode --catalog ../catalogo.json --event schedule   # imprime commit|release|none
    python scripts/routine.py prune --repo murkiriel/pardal                       # apaga releases velhas
    python scripts/routine.py stale --catalog data/dist/catalogo.json            # imprime o JSON das fontes paradas
    python scripts/routine.py notify --repo murkiriel/pardal --failed --run-url URL [--stale JSON]

`mode`: o commit no repositório sai uma vez por semana. Na primeira geração agendada que passar a
partir do domingo (00:00 em Brasília), se o catalogo.json do repositório for de antes desse
domingo; se o domingo falhar, segunda tenta de novo, e assim por diante. Nos outros dias, só a
release (com dado novo). À mão com publish, sempre o commit.

`prune`: apaga as releases dados-* com mais de KEEP_DAYS dias, menos as que foram para o
repositório (as semanais, com "no commit desta versão" na nota) e a mais recente.

`stale`: do catalogo.json do build (data/dist), as fontes que usaram cópia antiga (campo `stale`, que
o datakit/failures.py preenche junto do aviso), com a idade da cópia na data da geração (`built_at`),
só as de STALE_DAYS dias ou mais. Sem catálogo, ou sem o campo, imprime [].

`notify`: issue fixa ISSUE_TITLE. Geração agendada que falhou, ou que passou mas deixou alguma fonte
parada há STALE_DAYS dias ou mais (`--stale`, a saída do `stale`), abre a issue (ou comenta nela, se
já estiver aberta), com a data e o link da execução e a lista das fontes; a primeira geração que passar
sem fonte parada comenta e fecha. As notas da release já listam os avisos, mas só nos dias em que há
release: a fonte parada precisa de um aviso que apareça todo dia.

O `gh` é injetado (`Gh`) para os testes usarem um falso (datakit/tests/test_routine.py).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from typing import Callable, List, Optional, Sequence

BRT = timezone(timedelta(hours=-3))   # Brasília, sem horário de verão desde 2019
KEEP_DAYS = 90
STALE_DAYS = 3   # fonte com cópia de 3 dias ou mais vira alerta (1 a 2 dias é a oscilação normal de um portal)
ISSUE_TITLE = "Geração falhando"
WEEKLY_MARK = "no commit desta versão"   # release.py: a nota das releases que foram para o repositório

Gh = Callable[[Sequence[str]], str]


def real_gh(args: Sequence[str]) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def week_start(now: datetime) -> datetime:
    """O último domingo, 00:00 em Brasília (o próprio dia, se hoje for domingo), em UTC."""
    local = now.astimezone(BRT)
    sunday = local.date() - timedelta(days=(local.weekday() + 1) % 7)
    return datetime(sunday.year, sunday.month, sunday.day, tzinfo=BRT).astimezone(timezone.utc)


def mode(published_built_at: Optional[str], event: str, publish: bool, now: datetime) -> str:
    """'commit' (repositório e release), 'release' (só a release) ou 'none' (só gera e confere)."""
    if not publish:
        return "none"
    if event != "schedule":
        return "commit"
    if not published_built_at:
        return "commit"
    return "commit" if _parse(published_built_at) < week_start(now) else "release"


def prune(repo: str, now: datetime, gh: Gh = real_gh, keep_days: int = KEEP_DAYS) -> List[str]:
    """Apaga as releases dados-* velhas (ver o topo). Devolve as etiquetas apagadas."""
    releases = json.loads(gh(["api", "--paginate", "--slurp", f"repos/{repo}/releases"]) or "[]")
    flat = [r for page in releases for r in (page if isinstance(page, list) else [page])]
    dados = sorted((r for r in flat if str(r.get("tag_name", "")).startswith("dados-")),
                   key=lambda r: r["created_at"])
    if not dados:
        return []
    newest = dados[-1]["tag_name"]
    limit = now - timedelta(days=keep_days)
    gone = []
    for r in dados:
        if r["tag_name"] == newest or _parse(r["created_at"]) >= limit or WEEKLY_MARK in (r.get("body") or ""):
            continue
        gh(["release", "delete", r["tag_name"], "--repo", repo, "--yes", "--cleanup-tag"])
        gone.append(r["tag_name"])
    return gone


def _open_issue(repo: str, gh: Gh) -> Optional[int]:
    found = json.loads(gh(["issue", "list", "--repo", repo, "--state", "open", "--search",
                           f'in:title "{ISSUE_TITLE}"', "--json", "number,title"]) or "[]")
    return next((i["number"] for i in found if i.get("title") == ISSUE_TITLE), None)


def stale_sources(catalog: dict, min_days: int = STALE_DAYS) -> List[dict]:
    """As fontes do campo `stale` do catálogo do build cuja cópia tem `min_days` dias ou mais na data da
    geração (`built_at`; sem ela, a de hoje), do mais velho ao mais novo, com `days`. Entrada ilegível
    (sem data, data inválida) fica de fora: sem a idade não há o que comparar."""
    try:
        built_on = _parse(catalog["built_at"]).date()
    except (KeyError, ValueError, TypeError, AttributeError):
        built_on = datetime.now(timezone.utc).date()
    found = []
    for entry in catalog.get("stale") or []:
        try:
            days = (built_on - datetime.fromisoformat(str(entry["copy_date"])[:10]).date()).days
            source = str(entry["source"])
        except (KeyError, ValueError, TypeError):
            continue
        if days >= min_days:
            found.append({"source": source, "copy_date": str(entry["copy_date"])[:10], "days": days,
                          "reason": str(entry.get("reason") or "")})
    return sorted(found, key=lambda e: (-e["days"], e["source"]))


def _stale_lines(stale: Sequence[dict]) -> str:
    return "\n".join(f"- {e['source']}: cópia de {e['copy_date']} ({e['days']} dias)"
                     + (f" — {e['reason']}" if e.get("reason") else "") for e in stale)


def notify(repo: str, failed: bool, run_url: str, now: datetime, gh: Gh = real_gh,
           stale: Optional[Sequence[dict]] = None) -> str:
    """Abre/comenta/fecha a issue de falha. `stale`: fontes paradas (stale_sources); com elas a issue abre
    ou recebe comentário mesmo que a geração tenha passado. Devolve o que fez:
    opened|commented|closed|nothing."""
    when = now.astimezone(BRT).strftime("%d/%m/%Y %H:%M")
    number = _open_issue(repo, gh)
    stale = [e for e in stale or [] if e.get("days", 0) >= STALE_DAYS]   # a lista pode vir de fora: confere o limite
    if failed or stale:
        text = (f"A geração agendada de {when} (Brasília) falhou: {run_url}" if failed
                else f"A geração agendada de {when} (Brasília) passou, mas há fonte parada: {run_url}")
        if stale:
            text += (f"\n\nFontes que usaram cópia de {STALE_DAYS} dias ou mais:\n" + _stale_lines(stale))
        if number is None:
            gh(["issue", "create", "--repo", repo, "--title", ISSUE_TITLE, "--body",
                text + "\n\nEsta issue é aberta e fechada pelo workflow Gerar dados "
                "(.github/workflows/gerar-dados.yml): fecha sozinha na primeira geração que passar "
                "sem fonte parada."])
            return "opened"
        gh(["issue", "comment", str(number), "--repo", repo, "--body", text])
        return "commented"
    if number is None:
        return "nothing"
    gh(["issue", "comment", str(number), "--repo", repo, "--body",
        f"A geração agendada de {when} (Brasília) passou, sem fonte parada: {run_url}"])
    gh(["issue", "close", str(number), "--repo", repo])
    return "closed"


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("mode")
    m.add_argument("--catalog", help="catalogo.json publicado no repositório")
    m.add_argument("--event", required=True)
    m.add_argument("--publish", default="true")
    p = sub.add_parser("prune")
    p.add_argument("--repo", required=True)
    p.add_argument("--keep-days", type=int, default=KEEP_DAYS)
    n = sub.add_parser("notify")
    n.add_argument("--repo", required=True)
    n.add_argument("--failed", action="store_true")
    n.add_argument("--run-url", required=True)
    n.add_argument("--stale", default="", help="JSON da saída do `stale` (lista de fontes paradas)")
    st = sub.add_parser("stale")
    st.add_argument("--catalog", required=True, help="catalogo.json do build (data/dist)")
    args = ap.parse_args(argv)
    now = datetime.now(timezone.utc)

    if args.cmd == "mode":
        built = None
        try:
            with open(args.catalog, encoding="utf-8") as f:
                built = json.load(f).get("built_at")
        except (OSError, ValueError, TypeError):
            pass
        print(mode(built, args.event, args.publish == "true", now))
    elif args.cmd == "prune":
        gone = prune(args.repo, now, keep_days=args.keep_days)
        print(f"releases apagadas: {', '.join(gone) if gone else 'nenhuma'}")
    elif args.cmd == "stale":
        try:
            with open(args.catalog, encoding="utf-8-sig") as f:
                found = stale_sources(json.load(f))
        except (OSError, ValueError, TypeError):
            found = []   # sem catálogo (o build nem chegou a gravá-lo): quem avisa é a falha do job
        print(json.dumps(found, ensure_ascii=False, separators=(",", ":")))
    else:
        try:
            stale = json.loads(args.stale) if args.stale.strip() else []
        except ValueError:
            stale = []
        print(f"issue: {notify(args.repo, args.failed, args.run_url, now, stale=stale if isinstance(stale, list) else [])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
