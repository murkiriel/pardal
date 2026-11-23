"""Fontes que falharam nesta execução do build.

Uma fonte fora do ar é pulada e o resto do build segue; o que foi pulado fica registrado aqui,
vai para o campo `failures` do data/dist/catalogo.json e o scripts/publish.py se recusa a montar
os arquivos enquanto a lista não estiver vazia (ou com --accept-failures).

Avisos são o caso mais brando: a fonte falhou, mas havia uma cópia anterior guardada em data/raw/
e ela foi usada (dado da última leitura boa ou da edição publicada, não dado faltando; ver
datakit/source_cache.py e datakit/edition.py), ou o dado veio por outro caminho (o extrato datado da Geofabrik, quando o -latest falha). Vão para o campo `warnings`, aparecem no
fim do build e no publish.py, e não bloqueiam a publicação.
"""
from __future__ import annotations

from typing import Dict, List, Optional

_FAILURES: List[str] = []


def record(source: str, error: BaseException) -> None:
    msg = f"{source}: {type(error).__name__}: {error}"[:300]
    print(f"[build] {source}: FALHOU, pulando ({type(error).__name__}: {error})")
    if msg not in _FAILURES:
        _FAILURES.append(msg)


def recorded() -> List[str]:
    return list(_FAILURES)


def mark() -> int:
    """Posição atual da lista de falhas, para since()."""
    return len(_FAILURES)


def since(position: int) -> List[str]:
    """Falhas registradas depois de mark()."""
    return list(_FAILURES[position:])


def discard(messages: List[str]) -> None:
    """Tira da lista falhas que deixaram de valer (a fonte usou a cópia guardada; vira aviso)."""
    for m in messages:
        if m in _FAILURES:
            _FAILURES.remove(m)


_WARNINGS: List[str] = []
_STALE: Dict[str, Dict[str, str]] = {}


def warn(source: str, message: str, copy_date: Optional[str] = None, reason: str = "") -> None:
    """Aviso (campo `warnings`). Quando a fonte caiu numa cópia antiga, `copy_date` (AAAA-MM-DD, o dia
    do dado) também a põe em `stale`, com o `reason` curto: o notify do workflow lê a lista para avisar de
    fonte parada nos dias em que não sai release, que é quando ninguém lê as notas."""
    msg = f"{source}: {message}"[:300]
    print(f"[build] {source}: AVISO — {message}")
    if msg not in _WARNINGS:
        _WARNINGS.append(msg)
    if copy_date:
        _STALE[source] = {"source": source, "copy_date": copy_date[:10], "reason": reason[:200]}


def stale() -> List[Dict[str, str]]:
    """Fontes que usaram cópia antiga nesta execução, uma entrada por fonte (a idade se calcula depois,
    com a data da geração)."""
    return sorted(_STALE.values(), key=lambda s: s["source"])


def warnings() -> List[str]:
    return list(_WARNINGS)
