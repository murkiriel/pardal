"""DNIT — Sistema Nacional de Viação: rotas com km (PolylineM) e base geométrica.

Compartilhamento público do DNIT (Nextcloud), lido por WebDAV. Baixa só a versão mais
nova de cada pasta, e só se ainda não estiver em raw_dir.
"""
from __future__ import annotations

import os
import re
from typing import Optional, Tuple

import requests

from datakit.sources._http import CONNECT_TIMEOUT, UA, guarded, session

SHARE = "https://servicos.dnit.gov.br/dnitcloud/public.php/webdav/"
TOKEN = "oTpPRmYs5AAdiNr"
ROUTES = "SNV Rotas (2015-Atual) (SHP)/"
BASES = "SNV Bases Geométricas (2013-Atual) (SHP)/"


def _latest(folder: str, pattern: str) -> str:
    return guarded(SHARE, lambda: _latest_once(folder, pattern))


def _latest_once(folder: str, pattern: str) -> str:
    r = session().request("PROPFIND", SHARE + requests.utils.quote(folder), auth=(TOKEN, ""),
                         headers={**UA, "Depth": "1"}, timeout=(CONNECT_TIMEOUT, 120))
    r.raise_for_status()
    names = re.findall(r"<d:href>[^<]*/([^/<]+\.zip)</d:href>", r.text)
    names = [requests.utils.unquote(n) for n in names if re.search(pattern, requests.utils.unquote(n))]
    if not names:
        raise RuntimeError(f"nenhum zip em {folder}")
    return max(names)


def _fetch(folder: str, name: str, dest: str) -> None:
    guarded(SHARE, lambda: _fetch_once(folder, name, dest))


def _fetch_once(folder: str, name: str, dest: str) -> None:
    with session().get(SHARE + requests.utils.quote(folder + name), auth=(TOKEN, ""), headers=UA,
                      stream=True, timeout=(CONNECT_TIMEOUT, 600)) as r:
        r.raise_for_status()
        tmp = dest + ".part"
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
        os.replace(tmp, dest)


def load_routes(raw_dir: str):
    """Rotas do SNV (SnvRoutes); None se o SNV falhar (registrado em falhas). Carrega a cada
    chamada: o build guarda o resultado no contexto (BuildContext.snv_routes)."""
    from datakit.common.lrs import SnvRoutes
    try:
        return SnvRoutes.from_zip(ensure(raw_dir)[0])
    except Exception as e:  # noqa: BLE001 — sem SNV, só fica sem o sentido
        from datakit import failures
        failures.record("SNV (rotas)", e)
        return None


def ensure(raw_dir: str) -> Tuple[str, str, str]:
    """(caminho do zip das rotas, caminho do zip da base, versão ex. '202607A'). Se a pasta do DNIT não
    responder, usa as versões mais novas já baixadas em raw_dir (aviso); sem elas, a falha sobe."""
    os.makedirs(raw_dir, exist_ok=True)
    try:
        route_zip = _latest(ROUTES, r"^rota_\d{6}[A-Z]\.zip$")
        base = _latest(BASES, r"^\d{6}[A-Z]\.zip$")
    except Exception as e:  # noqa: BLE001 — decide abaixo se há cópia guardada
        stored = _stored(raw_dir)
        if stored is None:
            raise
        from datakit import failures
        failures.warn("SNV", f"pasta do DNIT falhou ({type(e).__name__}); usada a versão guardada {stored[2]}")
        return stored
    version = route_zip[len("rota_"):-len(".zip")]
    paths = []
    for folder, name, local in ((ROUTES, route_zip, f"snv_rota_{version}.zip"),
                                (BASES, base, f"snv_base_{base[:-4]}.zip")):
        path = os.path.join(raw_dir, local)
        if not os.path.exists(path):
            print(f"[snv] baixando {name}")
            _fetch(folder, name, path)
        paths.append(path)
    return paths[0], paths[1], version


def _stored(raw_dir: str) -> Optional[Tuple[str, str, str]]:
    """As versões mais novas das rotas e da base do SNV já baixadas em raw_dir, ou None."""
    names = os.listdir(raw_dir)
    routes = sorted(n for n in names if re.fullmatch(r"snv_rota_\d{6}[A-Z]\.zip", n))
    bases = sorted(n for n in names if re.fullmatch(r"snv_base_\d{6}[A-Z]\.zip", n))
    if not routes or not bases:
        return None
    return (os.path.join(raw_dir, routes[-1]), os.path.join(raw_dir, bases[-1]),
            routes[-1][len("snv_rota_"):-len(".zip")])
