"""Rio: geocodificador da prefeitura com o CNEFE de reserva (sources/rio.py: locate e fetch)."""
import os
import tempfile
import unittest
from unittest import mock

from datakit import source_cache
from datakit.common.model import CameraKind
from datakit.context import BuildContext
from datakit.sources import rio

ITEMS = [
    ("AVENIDA AREIA BRANCA,PROXIMO AO Nº 1672 - SENTIDO SANTA CRUZ", CameraKind.FIXED, 60),
    ("AVENIDA AREIA BRANCA,PROXIMO AO Nº 1672 - SENTIDO CENTRO", CameraKind.FIXED, 60),   # mesma consulta
    ("RUA JARDIM BOTANICO, OPOSTO AO Nº 1008", CameraKind.RED_LIGHT, None),
    ("ACESSO AO MERGULHAO - SENTIDO BARRA", CameraKind.FIXED, 50),                         # sem número
]


class Locate(unittest.TestCase):
    def test_city_geocoder_up_is_used_once_per_query(self):
        calls = []

        def city(q):
            calls.append(q)
            return (-22.9, -43.5) if "AREIA" in q else None

        def backup(addrs):
            raise AssertionError("o CNEFE não deve ser usado com o geocodificador no ar")
        cams, error = rio.locate(ITEMS, city, backup)
        self.assertIsNone(error)
        self.assertEqual(calls, ["AVENIDA AREIA BRANCA 1672", "RUA JARDIM BOTANICO 1008"])
        self.assertEqual([(c.lat, c.kind, c.limit_kmh) for c in cams],
                         [(-22.9, CameraKind.FIXED, 60), (-22.9, CameraKind.FIXED, 60)])

    def test_city_geocoder_down_moves_every_address_to_the_backup(self):
        def city(q):
            raise TimeoutError("pgeo3 fora")
        asked = []

        def backup(addrs):
            asked.extend(addrs)
            return lambda addr: (-22.97, -43.22) if "JARDIM" in addr else (-22.91, -43.56)
        cams, error = rio.locate(ITEMS, city, backup)
        self.assertIsInstance(error, TimeoutError)
        self.assertEqual(len(asked), 3)    # só os que têm número de porta
        self.assertEqual(sorted((c.lat, c.kind) for c in cams),
                         [(-22.97, CameraKind.RED_LIGHT), (-22.91, CameraKind.FIXED), (-22.91, CameraKind.FIXED)])
        self.assertTrue(all(c.source == "RIO" and c.active for c in cams))

    def test_backup_that_refuses_lets_the_failure_rise(self):
        def city(q):
            raise TimeoutError("pgeo3 fora")

        def backup(addrs):
            raise RuntimeError("há cópia guardada")
        with self.assertRaises(RuntimeError):
            rio.locate(ITEMS, city, backup)


class FetchUsesCnefeOnlyWithoutCopy(unittest.TestCase):
    def _fetch(self, raw):
        with mock.patch.object(rio, "load", return_value=([], [])) as load:
            rio.fetch(BuildContext(raw))
        return load.call_args.kwargs["cnefe_backup"]

    def test_without_copy_cnefe_is_allowed(self):
        self.assertTrue(self._fetch(tempfile.mkdtemp()))

    def test_with_copy_the_failure_rises_to_use_it(self):
        raw = tempfile.mkdtemp()
        path = source_cache.path_for(raw, "RIO")
        os.makedirs(os.path.dirname(path))
        open(path, "wb").close()
        self.assertFalse(self._fetch(raw))


if __name__ == "__main__":
    unittest.main()
