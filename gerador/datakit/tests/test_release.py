"""Release de uma geração (scripts/release.py): pacotes e nota."""
import importlib.util
import json
import os
import tempfile
import unittest
import zipfile

_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "release.py"))
_spec = importlib.util.spec_from_file_location("release", _PATH)
assert _spec is not None and _spec.loader is not None
rel = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rel)


def _cat(built, **ufs):
    return {"built_at": built, "ufs": {uf: {"counts": c} for uf, c in ufs.items()}}


class Notes(unittest.TestCase):
    def test_counts_differences_and_warnings(self):
        before = _cat("2026-09-30T12:13:21Z", BR={"cameras": 17798, "limits": 100, "limits_estimated": 5, "structs": 9},
                      GO={"cameras": 1428, "limits": 125500, "structs": 4929})
        new = _cat("2026-10-01T06:40:00Z", BR={"cameras": 17810, "limits": 100, "limits_estimated": 4, "structs": 9},
                   GO={"cameras": 1431, "limits": 125500, "structs": 4929})
        n = rel.release_notes(new, before, ["Inmetro GO: usada a cópia de 2026-09-30"], "https://github.com/x/y")
        self.assertIn("Dados gerados em 01/10/2026", n)
        self.assertIn("| Radares | 17.810 (+12) |", n)
        self.assertIn("| Pontos de limite estimado | 4 (−1) |", n)
        self.assertIn("| Pontos de limite sinalizado | 100 |", n)          # sem mudança: sem parênteses
        self.assertIn("| GO | 1.431 (+3) | 125.500 | 4.929 |", n)
        self.assertIn("## Avisos", n)
        self.assertIn("https://github.com/x/y/releases/latest/download/pardal-SP.zip", n)
        self.assertNotIn("| BR |", n)
        self.assertEqual(rel.tag_for(new), "dados-2026-10-01")

    def test_first_release_has_no_differences(self):
        n = rel.release_notes(_cat("2026-10-01T06:40:00Z", BR={"cameras": 1}, GO={"cameras": 1}), None, [], "u")
        self.assertNotIn("(+", n)
        self.assertNotIn("diferença para a geração anterior", n)
        self.assertNotIn("## Avisos", n)


class Assets(unittest.TestCase):
    def test_zips_per_state_brazil_and_cameras_only(self):
        with tempfile.TemporaryDirectory() as repo:
            for uf in ("GO", "SP"):
                os.makedirs(os.path.join(repo, "estados", uf))
                for f in ("radares.csv", "radares.gpx", "limites.csv", "estruturas.csv"):
                    with open(os.path.join(repo, "estados", uf, f), "w") as fh:
                        fh.write("x")
            os.makedirs(os.path.join(repo, "brasil"))
            for f in ("radares.csv", "radares.kml", "limites.csv", "limites_estimados.csv", "estruturas.csv"):
                with open(os.path.join(repo, "brasil", f), "w") as fh:
                    fh.write("x")
            with open(os.path.join(repo, "catalogo.json"), "w") as fh:
                json.dump(_cat("2026-10-01T06:40:00Z"), fh)
            out = os.path.join(repo, "_out")
            assets = [os.path.basename(a) for a in rel.build_assets(repo, out)]
            self.assertEqual(assets, ["pardal-GO.zip", "pardal-SP.zip", "pardal-brasil.zip",
                                      "pardal-brasil-radares.zip", "catalogo.json", "SHA256SUMS.txt"])
            with zipfile.ZipFile(os.path.join(out, "pardal-GO.zip")) as z:
                self.assertEqual(sorted(z.namelist()),
                                 ["GO/LICENCA-DADOS.txt", "GO/estruturas.csv", "GO/limites.csv", "GO/radares.csv",
                                  "GO/radares.gpx"])
            with zipfile.ZipFile(os.path.join(out, "pardal-brasil-radares.zip")) as z:
                self.assertEqual(sorted(z.namelist()),
                                 ["brasil/LICENCA-DADOS.txt", "brasil/radares.csv", "brasil/radares.kml"])
            with open(os.path.join(out, "SHA256SUMS.txt"), encoding="utf-8") as fh:
                self.assertEqual(len(fh.read().splitlines()), 5)


    def test_release_only_lines_go_into_the_state_zip_from_the_build(self):
        with tempfile.TemporaryDirectory() as repo, tempfile.TemporaryDirectory() as dist:
            os.makedirs(os.path.join(repo, "estados", "SP"))
            os.makedirs(os.path.join(repo, "brasil"))
            with open(os.path.join(repo, "estados", "SP", "radares.csv"), "w") as fh:
                fh.write("x")
            with open(os.path.join(repo, "catalogo.json"), "w") as fh:
                json.dump(_cat("2026-11-08T06:40:00Z"), fh)
            os.makedirs(os.path.join(dist, "estados", "SP"))
            for f in ("limites_trechos.csv", "radares.csv", "rascunho.txt"):   # só o trecho vem do build
                with open(os.path.join(dist, "estados", "SP", f), "w") as fh:
                    fh.write("do build")
            out = os.path.join(repo, "_out")
            rel.build_assets(repo, out, dist)
            with zipfile.ZipFile(os.path.join(out, "pardal-SP.zip")) as z:
                self.assertEqual(sorted(z.namelist()),
                                 ["SP/LICENCA-DADOS.txt", "SP/limites_trechos.csv", "SP/radares.csv"])
                self.assertEqual(z.read("SP/radares.csv"), b"x")   # o publicado, não o do build



class LicenseInEveryZip(unittest.TestCase):
    """Quem baixa só o zip recebe a licença e a atribuição (ODbL, OpenStreetMap, fontes)."""

    CAT = {"built_at": "2026-11-08T15:46:58Z",
           "ufs": {"GO": {"coverage": {"sources": ["OSM", "DNIT", "DER-GO"]}},
                   "SE": {"coverage": {"sources": ["DER-SE", "OSM"]}},
                   "BR": {"coverage": {"sources": ["GO+SE"]}}}}

    def test_state_text_names_its_sources_and_the_license(self):
        t = rel.license_text(self.CAT, "GO", "https://github.com/x/y")
        for must in ("ODbL 1.0", "© colaboradores do OpenStreetMap", "openstreetmap.org/copyright",
                     "DER-GO, DNIT, OSM", "estado GO", "2026-11-08 15:46:58 UTC", "https://github.com/x/y"):
            self.assertIn(must, t)
        self.assertNotIn("DER-SE", t)

    def test_brazil_text_joins_the_sources_of_every_state(self):
        t = rel.license_text(self.CAT, None, "u")
        self.assertIn("DER-GO, DER-SE, DNIT, OSM", t)
        self.assertNotIn("GO+SE", t)   # a entrada BR não é fonte


class DailyRelease(unittest.TestCase):
    """Release todo dia com dado novo; repositório só aos domingos."""

    def _cat(self, built, sha):
        return {"built_at": built, "source_dates": {"DNIT": built[:10]},
                "ufs_geojson": {"file": "brasil/ufs.geojson", "sha256": "u"},
                "ufs": {"SP": {"built_at": built, "counts": {"cameras": 1},
                               "cameras": {"file": "estados/SP/radares.csv", "sha256": sha},
                               "limit_lines": {"asset_path": "SP/limites_trechos.csv", "sha256": "t"}}}}

    def test_same_data_on_another_day_has_the_same_fingerprint(self):
        a, b = self._cat("2026-11-09T06:40:00Z", "x"), self._cat("2026-11-10T06:40:00Z", "x")
        self.assertEqual(rel.data_fingerprint(a), rel.data_fingerprint(b))
        self.assertNotEqual(rel.data_fingerprint(a), rel.data_fingerprint(self._cat("2026-11-10T06:40:00Z", "y")))
        self.assertIn(("SP/limites_trechos.csv", "t"), rel.data_fingerprint(a))
        self.assertEqual(rel.data_fingerprint(None), set())

    def test_skip_if_same_builds_nothing(self):
        with tempfile.TemporaryDirectory() as repo:
            with open(os.path.join(repo, "catalogo.json"), "w") as fh:
                json.dump(self._cat("2026-11-10T06:40:00Z", "x"), fh)
            prev = os.path.join(repo, "anterior.json")
            with open(prev, "w") as fh:
                json.dump(self._cat("2026-11-09T06:40:00Z", "x"), fh)
            out = os.path.join(repo, "_out")
            self.assertEqual(rel.main(["--repo", repo, "--previous", prev, "--out", out, "--skip-if-same"]), 0)
            self.assertFalse(os.path.exists(out))

    def test_release_only_notes_say_the_repository_is_weekly(self):
        cat = self._cat("2026-11-10T06:40:00Z", "x")
        self.assertIn("só nesta release", rel.release_notes(cat, None, [], "u", in_repo=False))
        self.assertIn("no commit desta versão", rel.release_notes(cat, None, [], "u"))


if __name__ == "__main__":
    unittest.main()
