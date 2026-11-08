"""A edição publicada (brasil/, catalogo.json na raiz do repositório) como último recurso de cada fonte.

Quando uma fonte falha e não há cópia guardada da última leitura boa (datakit/source_cache.py), o
build usa as linhas daquela fonte na edição publicada: os radares de brasil/radares.csv e os
limites de brasil/limites.csv cuja coluna `source` traz o código da fonte. O workflow do GitHub já
tem a edição no checkout (o build roda antes de o publish.py trocar os arquivos), e ela nunca some
como o cache do Actions.

A edição já passou pela mescla, então a reconstrução é aproximada: um radar do OSM juntado a um
oficial aparece como "RIO+OSM" e volta como radar RIO (a mescla junta de novo com o OSM do dia).
Os limites oficiais voltam exatos, porque o oficial sempre ganha do OSM. Ficam de fora o que não
vai para os CSVs: os locais desativados da CET e o km do cadastro de cada radar (road_km).

A data do dado de cada fonte segue no campo `source_dates` do catálogo: uma fonte que fica meses
caindo na edição continua com a data da última leitura boa, e não com a data de cada edição.
"""
from __future__ import annotations

import csv
import json
import os
from typing import Dict, Iterable, List, Optional

from datakit.common.model import Camera, CameraKind, Limit, source_parts

CATALOG = "catalogo.json"


def default_root() -> str:
    """A raiz do repositório (gerador/datakit/edition.py → ../..)."""
    return os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))


def _opt_float(v: str) -> Optional[float]:
    return float(v) if v else None


def _opt_int(v: str) -> Optional[int]:
    return int(v) if v else None


class Edition:
    """A edição publicada em `root`. Os CSVs só são lidos se alguma fonte precisar deles."""

    def __init__(self, root: str):
        self.root = root
        with open(os.path.join(root, CATALOG), encoding="utf-8") as f:
            self.catalog = json.load(f)
        self._cameras: Optional[Dict[str, List[Camera]]] = None
        self._limits: Optional[Dict[str, List[Limit]]] = None

    @classmethod
    def open(cls, root: Optional[str]) -> Optional["Edition"]:
        """A edição em `root`, ou None se não houver uma (sem catalogo.json ou sem brasil/)."""
        if not root or not os.path.exists(os.path.join(root, CATALOG)) \
                or not os.path.isdir(os.path.join(root, "brasil")):
            return None
        try:
            return cls(root)
        except (OSError, ValueError):
            return None

    @property
    def built_at(self) -> str:
        return str(self.catalog.get("built_at") or "")[:10]

    def source_date(self, label: str) -> str:
        """Data do dado da fonte nesta edição: a gravada em `source_dates`, ou a data da edição."""
        return str((self.catalog.get("source_dates") or {}).get(label) or self.built_at)

    def cameras(self, codes: Iterable[str]) -> List[Camera]:
        """Radares da edição com algum dos códigos na fonte, com a fonte reduzida a esse código."""
        if self._cameras is None:
            self._cameras = {}
            for r in self._rows("radares.csv"):
                for part in source_parts(r["source"]):
                    if part == "OSM" or part.startswith("OSM:"):
                        continue
                    self._cameras.setdefault(part, []).append(Camera(
                        float(r["lat"]), float(r["lng"]), CameraKind(r["kind"]), _opt_int(r["limit_kmh"]),
                        part, r["active"] == "1", _opt_float(r["end_lat"]), _opt_float(r["end_lng"]),
                        _opt_int(r["direction_deg"])))
        return [c for code in codes for c in self._cameras.get(code, [])]

    def limits(self, codes: Iterable[str]) -> List[Limit]:
        """Limites sinalizados da edição com o código na fonte (os do OSM nunca precisam daqui)."""
        if self._limits is None:
            self._limits = {}
            for r in self._rows("limites.csv"):
                if r["source"].startswith("OSM") or r["estimated"] == "1":
                    continue
                self._limits.setdefault(r["source"], []).append(Limit.from_row(r))
        return [lim for code in codes for lim in self._limits.get(code, [])]

    def _rows(self, name: str):
        """Linhas de brasil/<name>, ou de brasil/<name>.gz quando o arquivo passou do teto e foi
        publicado compactado (build_brazil.compress_oversized)."""
        path = os.path.join(self.root, "brasil", name)
        if os.path.exists(path):
            with open(path, encoding="utf-8", newline="") as f:
                yield from csv.DictReader(f)
        elif os.path.exists(path + ".gz"):
            import gzip
            with gzip.open(path + ".gz", "rt", encoding="utf-8", newline="") as f:
                yield from csv.DictReader(f)
