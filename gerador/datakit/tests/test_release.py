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
                                 ["GO/estruturas.csv", "GO/limites.csv", "GO/radares.csv", "GO/radares.gpx"])
            with zipfile.ZipFile(os.path.join(out, "pardal-brasil-radares.zip")) as z:
                self.assertEqual(sorted(z.namelist()), ["brasil/radares.csv", "brasil/radares.kml"])
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
                self.assertEqual(sorted(z.namelist()), ["SP/limites_trechos.csv", "SP/radares.csv"])
                self.assertEqual(z.read("SP/radares.csv"), b"x")   # o publicado, não o do build


if __name__ == "__main__":
    unittest.main()
