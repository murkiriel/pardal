"""Rotina da geração no GitHub Actions: o que publicar, limpeza das releases e aviso de falha.

    python scripts/routine.py mode --catalog ../catalogo.json --event schedule   # imprime commit|release|none
    python scripts/routine.py prune --repo murkiriel/pardal                       # apaga releases velhas
    python scripts/routine.py notify --repo murkiriel/pardal --failed --run-url URL

`mode`: o commit no repositório sai uma vez por semana. Na primeira geração agendada que passar a
partir do domingo (00:00 em Brasília), se o catalogo.json do repositório for de antes desse
domingo; se o domingo falhar, segunda tenta de novo, e assim por diante. Nos outros dias, só a
release (com dado novo). À mão com publish, sempre o commit.

`prune`: apaga as releases dados-* com mais de KEEP_DAYS dias, menos as que foram para o
repositório (as semanais, com "no commit desta versão" na nota) e a mais recente.

`notify`: issue fixa ISSUE_TITLE. Geração agendada que falhou abre a issue (ou comenta nela, se
já estiver aberta), com a data e o link da execução; a primeira que passar comenta e fecha.

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


def notify(repo: str, failed: bool, run_url: str, now: datetime, gh: Gh = real_gh) -> str:
    """Abre/comenta/fecha a issue de falha. Devolve o que fez: opened|commented|closed|nothing."""
    when = now.astimezone(BRT).strftime("%d/%m/%Y %H:%M")
    number = _open_issue(repo, gh)
    if failed:
        text = f"A geração agendada de {when} (Brasília) falhou: {run_url}"
        if number is None:
            gh(["issue", "create", "--repo", repo, "--title", ISSUE_TITLE, "--body",
                text + "\n\nEsta issue é aberta e fechada pelo workflow Gerar dados "
                "(.github/workflows/gerar-dados.yml): fecha sozinha na primeira geração que passar."])
            return "opened"
        gh(["issue", "comment", str(number), "--repo", repo, "--body", text])
        return "commented"
    if number is None:
        return "nothing"
    gh(["issue", "comment", str(number), "--repo", repo, "--body",
        f"A geração agendada de {when} (Brasília) passou: {run_url}"])
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
    else:
        print(f"issue: {notify(args.repo, args.failed, args.run_url, now)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
