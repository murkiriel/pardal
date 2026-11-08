"""Cópia da última leitura boa de cada fonte: atualiza quando dá; quando falha, fica como estava.

Cada fonte é lida por `load()`. Leitura boa: o resultado é guardado em data/raw/fontes/<nome>.pickle
e segue para o build. Leitura que falha — exceção, uma base interna da fonte que falhou (DER-SP,
capitais, malha do DER-GO) ou resultado vazio quando a cópia tinha dados — usa essa cópia: a falha
vira aviso (`failures.warn`, com a data da cópia), as outras fontes seguem normalmente e a
publicação não é barrada. Sem cópia (fonte que nunca foi lida com sucesso nesta máquina, ou cache do
Actions apagado), vale o que a fonte tinha na edição publicada (`edition`, datakit/edition.py), também
como aviso. Sem os dois, a falha fica registrada como sempre (`failures.record`) e o build segue sem
a fonte.

Cada fonte tem a data do seu dado (`dates()`, campo `source_dates` do catálogo): a de hoje na leitura
boa, a da cópia ou a que a edição publicada registrou. Dado com mais de STALE_DAYS dias vira um aviso
com "ATENÇÃO" — não barra, mas não passa despercebido.

A cópia é um pickle do que a fonte devolve (radares, limites, trechos), gravada pelo próprio build
em data/raw/ — nunca um arquivo de fora. Se o formato das classes mudar e a cópia não puder ser lida,
vale a falha original.
"""
from __future__ import annotations

import os
import pickle
import re
import unicodedata
from datetime import date, datetime
from typing import Any, Callable, Dict, Iterable, Optional, Tuple

from datakit import failures

CACHE_DIR = "fontes"
FORMAT = 1   # sobe quando o envelope abaixo muda
# Fonte que fica isto sem leitura boa: o aviso ganha "ATENÇÃO" (a fonte pode ter mudado de endereço)
STALE_DAYS = 60

_DATES: Dict[str, str] = {}


def dates() -> Dict[str, str]:
    """{fonte: data do dado (AAAA-MM-DD)} desta execução, para o campo source_dates do catálogo."""
    return dict(sorted(_DATES.items()))


def _age_note(when: str, today: Optional[date] = None) -> str:
    try:
        days = ((today or date.today()) - date.fromisoformat(when[:10])).days
    except ValueError:
        return ""
    return f" — ATENÇÃO: dado de {days} dias" if days > STALE_DAYS else ""


def path_for(raw_dir: str, label: str) -> str:
    plain = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode().lower()
    slug = re.sub(r"[^a-z0-9]+", "_", plain).strip("_")
    return os.path.join(raw_dir, CACHE_DIR, f"{slug}.pickle")


def _empty(value: Any) -> Optional[bool]:
    """True se não veio nada, False se veio algo, None se o valor não é uma coleção (texto, número)."""
    from datakit.context import SourceData
    if isinstance(value, SourceData):
        return not (value.cameras or value.limits or value.deactivated)
    if isinstance(value, (list, dict, set)) or hasattr(value, "keys"):
        return len(value) == 0
    if isinstance(value, tuple):
        inner = [e for e in (_empty(x) for x in value) if e is not None]
        return all(inner) if inner else None
    return None


def _read(path: str) -> Optional[Tuple[Any, str]]:
    """(valor, data da cópia) ou None se não há cópia legível."""
    try:
        with open(path, "rb") as f:
            env = pickle.load(f)
        if not isinstance(env, dict) or env.get("format") != FORMAT:
            return None
        return env["value"], env["saved_at"][:10]
    except Exception:  # noqa: BLE001 — cópia ausente, corrompida ou de outra versão das classes
        return None


def _write(path: str, value: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        pickle.dump({"format": FORMAT, "saved_at": datetime.now().isoformat(timespec="seconds"),
                     "value": value}, f, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, path)


def load(label: str, raw_dir: str, fn: Callable[[], Any], default: Any,
         owns: Iterable[str] = (), edition: Optional[Callable[[], Optional[Tuple[Any, str]]]] = None) -> Any:
    """fn() com a cópia guardada como reserva e, sem cópia, a edição publicada. `owns`: prefixos (além
    de `label`) das falhas que a própria fonte registra por dentro, por base (ex.: "municipal" para as
    capitais). Falhas de outras bases chamadas por dentro (as rotas do SNV, no DER-MG) não são da fonte
    e ficam como estão. `edition()`: (valor, data do dado) da fonte na edição publicada, ou None se ela
    não tem nada da fonte. NotImplementedError (fonte desligada de propósito) sobe sem tocar na cópia."""
    prefixes = (label, *owns)
    mark = failures.mark()
    error: Optional[BaseException] = None
    value = default
    try:
        value = fn()
    except NotImplementedError:
        raise
    except Exception as e:  # noqa: BLE001 — uma fonte fora do ar não derruba a geração
        error = e
    partial = [m for m in failures.since(mark) if m.startswith(prefixes)]
    path = path_for(raw_dir, label)

    if error is None and not partial:
        if not _empty(value):
            _write(path, value)
            _DATES[label] = date.today().isoformat()
            return value
        cached = _read(path)
        if cached is None or _empty(cached[0]):
            _write(path, value)
            _DATES[label] = date.today().isoformat()
            return value
        reason = "veio vazia"
    else:
        cached = _read(path)
        reason = (f"{type(error).__name__}" if error is not None
                  else "falhou: " + "; ".join(m.split(":", 1)[0] for m in partial))

    if cached is None:
        published = _from_edition(label, edition)
        if published is None:
            if error is not None:
                failures.record(label, error)
            return value   # sem cópia nem edição: o que veio (parcial), com as falhas já registradas
        failures.discard(partial)
        if error is not None:
            print(f"[build] {label}: {type(error).__name__}: {error}"[:300])
        _DATES[label] = published[1]
        failures.warn(label, f"atualização {reason}; sem cópia guardada, usados os dados da edição "
                             f"publicada (dado de {published[1]}){_age_note(published[1])}")
        return published[0]
    failures.discard(partial)
    if error is not None:
        print(f"[build] {label}: {type(error).__name__}: {error}"[:300])
    _DATES[label] = cached[1]
    failures.warn(label, f"atualização {reason}; usada a cópia de {cached[1]}{_age_note(cached[1])}")
    return cached[0]


def _from_edition(label: str, edition: Optional[Callable[[], Optional[Tuple[Any, str]]]]
                  ) -> Optional[Tuple[Any, str]]:
    """(valor, data) da edição publicada, ou None se não há edição, ela não tem a fonte ou não abre."""
    if edition is None:
        return None
    try:
        got = edition()
    except Exception as e:  # noqa: BLE001 — edição ilegível: vale a falha original
        print(f"[build] {label}: edição publicada ilegível ({type(e).__name__}: {e})"[:300])
        return None
    if got is None or _empty(got[0]):
        return None
    return got
