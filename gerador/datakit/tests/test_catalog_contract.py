"""O bloco `contract` do catalogo.json publicado: o contrato de catálogo comum v1 (docs/CATALOGO.md).

Monta um build mínimo em data/dist, publica com scripts/publish.py (sem e com commit) e confere: o formato contra o
esquema (docs/catalogo-v1.schema.json), as regras que o esquema não expressa, as URLs absolutas, os sha256 iguais aos
das entradas antigas, a ordem do bbox, o build_id, e que os zips que o scripts/release.py monta são os que o catálogo
descreve.
"""
import copy
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from datakit import build_pack, build_sqlite, catalog_contract
from datakit.tests import contract_check

GENERATOR_DIR = Path(__file__).resolve().parent.parent.parent
REPO = GENERATOR_DIR.parent
DOCS = REPO / "docs"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pub = _load("publicar_contrato", GENERATOR_DIR / "scripts" / "publish.py")
sys.path.insert(0, str(GENERATOR_DIR / "scripts"))
rel = _load("release_contrato", GENERATOR_DIR / "scripts" / "release.py")

BUILT_AT = "2026-11-08T15:46:58Z"
FILES = {
    "estados/GO/radares.csv": "id,lat,lng,source\n1,-16.68,-49.27,DNIT\n",
    "estados/GO/radares.geojson": '{"type": "FeatureCollection", "features": []}\n',
    "estados/GO/radares.kml": "<kml/>\n",
    "estados/GO/radares.gpx": "<gpx/>\n",
    "estados/GO/limites.csv": "lat,lng,limit_kph\n-16.68,-49.27,60\n",
    "estados/GO/limites_trechos.csv": "wkt,limit_kph\nLINESTRING(-49.27 -16.68,-49.28 -16.69),60\n",
    "estados/DF/radares.csv": "id,lat,lng,source\n2,-15.79,-47.88,DETRAN-DF\n",
    "estados/DF/limites.csv": "lat,lng,limit_kph\n-15.79,-47.88,60\n",
    "brasil/radares.csv": "id,lat,lng,source\n1,-16.68,-49.27,DNIT\n2,-15.79,-47.88,DETRAN-DF\n",
    "brasil/radares.kml": "<kml/>\n",
    "brasil/limites.csv": "lat,lng,limit_kph\n-16.68,-49.27,60\n-15.79,-47.88,60\n",
    "brasil/ufs.geojson": '{"type": "FeatureCollection", "features": []}\n',
}
SQLITE = b"(\xb5/\xfd" + b"banco do GO" * 10   # o conteúdo não importa: só o sha256 e o tamanho
MANIFEST = {"sources": [{"name": "OSM/Geofabrik centro-oeste", "file_date": "Sat, 08 Nov 2026 21:21:36 GMT",
                         "sha256": "c" * 64, "bytes": 123},
                        {"name": "DNIT", "count": 10}]}


def _ref(dist, path, count=1):
    data = (Path(dist) / path).read_bytes()
    return {"file": path, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "count": count}


def make_build(root, extra=""):
    """data/dist e data/packs mínimos, com o catálogo do build (o que o build_catalog e o build_brazil escrevem)."""
    dist, packs = os.path.join(root, "dist"), os.path.join(root, "packs")
    for path, text in FILES.items():
        os.makedirs(os.path.dirname(os.path.join(dist, path)), exist_ok=True)
        with open(os.path.join(dist, path), "w", encoding="utf-8", newline="") as f:
            f.write(text + (extra if path.endswith("radares.csv") else ""))
    with open(os.path.join(dist, "estados", "GO", "pardal-GO.sqlite.zst"), "wb") as f:
        f.write(SQLITE)
    sqlite = _ref(dist, "estados/GO/pardal-GO.sqlite.zst", 3)
    sqlite.update({"uncompressed_bytes": 4096, "uncompressed_sha256": "d" * 64, "schema_version": 1,
                   "counts": {"CAMERA": 1, "SPEED_LIMIT": 1, "SPEED_LIMIT_LINE": 1}})
    cat = {
        "schema": 2, "built_at": BUILT_AT, "base_url": "",
        "ufs": {
            "DF": {"name": "Distrito Federal", "bbox": [-16.06, -48.29, -15.5, -47.31], "built_at": BUILT_AT,
                   "cameras": _ref(dist, "estados/DF/radares.csv"), "limits": _ref(dist, "estados/DF/limites.csv"),
                   "counts": {"cameras": 1, "limits": 1}},
            "GO": {"name": "Goiás", "bbox": [-19.5, -53.25, -12.4, -45.9], "built_at": BUILT_AT,
                   "cameras": _ref(dist, "estados/GO/radares.csv"), "limits": _ref(dist, "estados/GO/limites.csv"),
                   "limit_lines": _ref(dist, "estados/GO/limites_trechos.csv"), "sqlite": sqlite,
                   "counts": {"cameras": 1, "limits": 1, "limit_lines": 1}},
            "BR": {"name": "Brasil (tudo)", "bbox": [-34.0, -74.5, 6.0, -32.0], "built_at": BUILT_AT,
                   "cameras": _ref(dist, "brasil/radares.csv", 2), "limits": _ref(dist, "brasil/limites.csv", 2),
                   "counts": {"cameras": 2, "limits": 2}},
        },
        "ufs_geojson": _ref(dist, "brasil/ufs.geojson"),
        "source_dates": {"DNIT": "2026-11-08", "RIO": "2026-10-06", "ANTT (pedágios)": "2026-11-08"},
    }
    with open(os.path.join(dist, "catalogo.json"), "w", encoding="utf-8") as f:
        json.dump(cat, f)
    os.makedirs(os.path.join(packs, "GO"))
    with open(os.path.join(packs, "GO", "manifesto.json"), "w", encoding="utf-8") as f:
        json.dump(MANIFEST, f)
    return dist, packs


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True, text=True).stdout.strip()


class PublishedTestCase(unittest.TestCase):
    commit = False

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.repo = os.path.join(self.root, "repo")
        os.makedirs(self.repo)
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.email", "teste@example.invalid")
        git(self.repo, "config", "user.name", "teste")
        with open(os.path.join(self.repo, "LEIAME.md"), "w", encoding="utf-8") as f:
            f.write("x\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "gerador")
        self.generator_commit = git(self.repo, "rev-parse", "HEAD")
        self.dist, self.packs = make_build(self.root)
        with open(os.path.join(self.dist, "catalogo.json"), encoding="utf-8") as f:
            self.build_cat = json.load(f)
        args = ["--repo", self.repo, "--dist", self.dist, "--packs", self.packs] + (["--commit"] if self.commit else [])
        self.assertEqual(0, pub.main(args))
        with open(os.path.join(self.repo, "catalogo.json"), encoding="utf-8") as f:
            self.cat = json.load(f)
        self.block = self.cat["contract"]
        self.files = {f["id"]: f for f in self.block["files"]}

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)


class ReleaseOnlyGenerationTest(PublishedTestCase):
    """Geração que sai só na release (publish.py sem --commit): os arquivos do repositório são membros dos zips."""

    def test_valid_against_the_schema_and_the_rules(self):
        self.assertEqual([], contract_check.problems(self.cat, DOCS))

    def test_the_checker_catches_a_broken_block(self):
        broken = copy.deepcopy(self.cat)
        broken["contract"]["files"][0]["container"] = "nao-existe.zip"
        self.assertTrue(contract_check.problems(broken, DOCS))

    def test_only_adds_to_the_published_catalog(self):
        self.assertEqual(pub.rewrite_catalog(self.build_cat), {k: v for k, v in self.cat.items() if k != "contract"})
        self.assertEqual(2, self.cat["schema"])
        self.assertEqual("", self.cat["base_url"])

    def test_identity_licences_and_coordinates(self):
        b = self.block
        self.assertEqual(("catalogo-comum", 1, 1, "pardal"), (b["name"], b["version"], b["min_reader_version"],
                                                              b["dataset"]))
        self.assertEqual(BUILT_AT, b["built_at"])
        self.assertEqual({"data": "ODbL-1.0", "code": "MIT", "attribution": build_sqlite.ATTRIBUTION}, b["license"])
        self.assertEqual({"crs": "EPSG:4326", "bbox_order": "lat_min,lon_min,lat_max,lon_max"}, b["coordinates"])
        self.assertEqual(self.generator_commit, b["generator"]["commit"])
        self.assertEqual("https://github.com/murkiriel/pardal", b["generator"]["repository"])

    def test_build_id_is_the_date_and_the_hash_of_the_data(self):
        published = pub.rewrite_catalog(self.build_cat)
        self.assertEqual(catalog_contract.build_id(published), self.block["build_id"])
        self.assertRegex(self.block["build_id"], r"^2026-11-08-[0-9a-f]{8}$")
        self.assertEqual(rel.data_fingerprint(self.cat), catalog_contract.fingerprint(self.cat))
        later = {**published, "built_at": "2026-11-08T23:00:00Z"}
        self.assertEqual(self.block["build_id"], catalog_contract.build_id(later))   # mesmos dados, mesmo id
        other = copy.deepcopy(published)
        other["ufs"]["GO"]["cameras"]["sha256"] = "e" * 64
        self.assertNotEqual(self.block["build_id"], catalog_contract.build_id(other))

    def test_every_published_file_is_listed_once(self):
        expected = set(FILES) | {"pardal-GO.zip", "pardal-DF.zip", "pardal-GO.sqlite.zst", "pardal-brasil.zip",
                                 "pardal-brasil-radares.zip"}
        self.assertEqual(expected, set(self.files))

    def test_absolute_urls_on_the_release_of_the_generation(self):
        release_url = "https://github.com/murkiriel/pardal/releases/download/dados-2026-11-08/"
        self.assertEqual(release_url, self.block["release_url"])
        self.assertEqual(rel.tag_for(self.cat), catalog_contract.release_tag(BUILT_AT))
        for f in self.files.values():
            self.assertTrue(f["url"].startswith(release_url), f["url"])
        go = self.files["estados/GO/radares.csv"]
        self.assertEqual((release_url + "pardal-GO.zip", "pardal-GO.zip", "GO/radares.csv"),
                         (go["url"], go["container"], go["member"]))
        self.assertEqual((release_url + "pardal-brasil.zip", "brasil/radares.csv"),
                         (self.files["brasil/radares.csv"]["url"], self.files["brasil/radares.csv"]["member"]))

    def test_sha256_and_sizes_are_the_legacy_ones(self):
        ufs = self.cat["ufs"]
        for uf, key in (("GO", "cameras"), ("GO", "limits"), ("DF", "cameras"), ("BR", "cameras"), ("BR", "limits")):
            old = ufs[uf][key]
            f = self.files[old["file"]]
            self.assertEqual((old["sha256"], old["bytes"], key), (f["sha256"], f["bytes"], f["content"]))
        lines = ufs["GO"]["limit_lines"]
        f = self.files["estados/GO/limites_trechos.csv"]
        self.assertEqual((lines["sha256"], lines["bytes"], lines["release_asset"], lines["asset_path"]),
                         (f["sha256"], f["bytes"], f["container"], f["member"]))
        sqlite = ufs["GO"]["sqlite"]
        f = self.files[sqlite["release_asset"]]
        self.assertEqual((sqlite["sha256"], sqlite["bytes"], sqlite["uncompressed_bytes"]),
                         (f["sha256"], f["bytes"], f["bytes_unpacked"]))
        geo = self.cat["ufs_geojson"]
        self.assertEqual((geo["sha256"], "auxiliary", None), (self.files[geo["file"]]["sha256"],
                                                            self.files[geo["file"]]["kind"],
                                                            self.files[geo["file"]]["coverage_level"]))

    def test_files_without_a_legacy_entry_get_their_own_sha256(self):
        for path in ("estados/GO/radares.geojson", "estados/GO/radares.kml", "brasil/radares.kml"):
            data = (Path(self.dist) / path).read_bytes()
            self.assertEqual((hashlib.sha256(data).hexdigest(), len(data)),
                             (self.files[path]["sha256"], self.files[path]["bytes"]), path)
        self.assertEqual(("geojson", "application/geo+json"), (self.files["estados/GO/radares.geojson"]["format"],
                                                               self.files["estados/GO/radares.geojson"]["media_type"]))
        self.assertEqual(("gpx", "application/gpx+xml"), (self.files["estados/GO/radares.gpx"]["format"],
                                                         self.files["estados/GO/radares.gpx"]["media_type"]))

    def test_bbox_latitude_first_from_the_legacy_entries(self):
        self.assertEqual(self.cat["ufs"]["GO"]["bbox"], self.files["pardal-GO.zip"]["bbox"])
        self.assertEqual(self.cat["ufs"]["GO"]["bbox"], self.files["estados/GO/limites.csv"]["bbox"])
        self.assertEqual(self.cat["ufs"]["BR"]["bbox"], self.files["brasil/radares.csv"]["bbox"])
        lat_min, lon_min, lat_max, lon_max = self.files["pardal-GO.zip"]["bbox"]
        self.assertTrue(-20 < lat_min < lat_max < -12 and -54 < lon_min < lon_max < -45)

    def test_kinds_levels_and_formats(self):
        expected = {"pardal-GO.zip": ("uf", "GO", "DETAILED", "pardal-bundle", ["zip"]),
                    "pardal-GO.sqlite.zst": ("uf", "GO", "DETAILED", "sqlite", ["zstd"]),
                    "estados/GO/radares.csv": ("uf", "GO", "DETAILED", "csv", []),
                    "pardal-brasil.zip": ("national", "BR", "DETAILED", "pardal-bundle", ["zip"]),
                    "brasil/limites.csv": ("national", "BR", "DETAILED", "csv", [])}
        for file_id, values in expected.items():
            f = self.files[file_id]
            self.assertEqual(values, (f["kind"], f["region"], f["coverage_level"], f["format"], f["unpack"]), file_id)
            self.assertEqual([], f["requires"])

    def test_sources_and_osm_snapshot(self):
        sources = {s["id"]: s for s in self.block["sources"]}
        osm = sources["openstreetmap-geofabrik-centro-oeste"]
        self.assertEqual(({"sha256": "c" * 64}, "2026-11-08T21:21:36Z"), (osm["checksums"], osm["date"]))
        self.assertEqual({"date": "2026-11-08T21:21:36Z", "md5": None}, self.block["osm_snapshot"])
        self.assertEqual(("2026-10-06", {}), (sources["rio"]["date"], sources["rio"]["checksums"]))
        self.assertIn("antt-pedagios", sources)

    def test_compatibility_block_tied_to_the_build(self):
        compat = self.block["compatibility"]
        pardal = compat["pardal"]
        self.assertTrue(compat["mix_generations"])
        self.assertEqual({"name": "pardal", "version": str(build_pack.SCHEMA)}, compat["data_format"])
        self.assertEqual(build_pack.SCHEMA, pardal["pack_schema"])
        self.assertEqual(build_sqlite.SCHEMA_VERSION, pardal["sqlite_schema_version"])
        self.assertEqual(catalog_contract.SQLITE_SCHEMA_VERSION, build_sqlite.SCHEMA_VERSION)
        self.assertEqual(catalog_contract.ATTRIBUTION, build_sqlite.ATTRIBUTION)
        self.assertEqual("3.22.0", pardal["sqlite_min_version"])
        self.assertIn("SQLite 3.22.0", (DOCS / "FORMATO_SQLITE.md").read_text(encoding="utf-8"))
        self.assertEqual(f"https://github.com/murkiriel/pardal/blob/{self.generator_commit}/docs/FORMATO_SQLITE.md",
                         pardal["sqlite_spec"])
        self.assertEqual("lat,lng", pardal["coordinate_order"]["csv"])
        self.assertEqual("lng,lat", pardal["coordinate_order"]["geojson"])

    def test_release_builds_exactly_the_zips_the_catalog_describes(self):
        out = os.path.join(self.root, "release")
        assets = rel.build_assets(self.repo, out, self.dist)
        self.assertEqual([], rel.contract_mismatches(self.cat, assets))
        with zipfile.ZipFile(os.path.join(out, "pardal-GO.zip")) as z:
            names = set(z.namelist())
        members = {f["member"] for f in self.files.values() if f.get("container") == "pardal-GO.zip"}
        self.assertEqual(members | {"GO/LICENCA-DADOS.txt"}, names)
        with open(os.path.join(out, "catalogo.json"), encoding="utf-8") as f:
            self.assertEqual(self.cat, json.load(f))   # a release leva o mesmo catálogo

    def test_a_zip_that_is_not_the_described_one_stops_the_release(self):
        out = os.path.join(self.root, "release")
        assets = rel.build_assets(self.repo, out, self.dist)
        with open(os.path.join(out, "pardal-DF.zip"), "ab") as f:
            f.write(b"mudou")
        self.assertEqual(["pardal-DF.zip: sha256 ou tamanho diferente do catálogo"],
                         rel.contract_mismatches(self.cat, assets))
        self.assertIn("pardal-GO.sqlite.zst: o catálogo lista, mas não foi montado",
                      rel.contract_mismatches(self.cat, [a for a in assets if not a.endswith(".sqlite.zst")]))

    def test_zips_are_the_same_byte_for_byte(self):
        first = rel.predict_zips(self.dist, self.cat)
        os.utime(os.path.join(self.dist, "estados", "GO", "radares.csv"), (1, 1))   # outra data no arquivo
        self.assertEqual(first, rel.predict_zips(self.dist, self.cat))


class WeeklyCommitGenerationTest(PublishedTestCase):
    """Geração que vai para o repositório (publish.py --commit): os arquivos têm URL própria, pela etiqueta."""
    commit = True

    def test_valid_and_repository_files_point_to_the_tag(self):
        self.assertEqual([], contract_check.problems(self.cat, DOCS))
        go = self.files["estados/GO/radares.csv"]
        self.assertEqual("https://raw.githubusercontent.com/murkiriel/pardal/dados-2026-11-08/estados/GO/radares.csv",
                         go["url"])
        self.assertEqual(("pardal-GO.zip", "GO/radares.csv"), (go["container"], go["member"]))
        # o que só existe no zip continua apontando para o zip
        lines = self.files["estados/GO/limites_trechos.csv"]
        self.assertEqual(self.block["release_url"] + "pardal-GO.zip", lines["url"])

    def test_the_generator_commit_is_the_parent_of_the_data_commit(self):
        self.assertEqual(self.generator_commit, git(self.repo, "rev-parse", "HEAD^"))
        self.assertEqual(self.generator_commit, self.block["generator"]["commit"])
        committed = json.loads(git(self.repo, "show", "HEAD:catalogo.json"))
        self.assertEqual(self.cat, committed)

    def test_the_raw_url_path_is_the_committed_file(self):
        for f in self.files.values():
            if f["url"].startswith("https://raw.githubusercontent.com/"):
                path = f["url"].split("/dados-2026-11-08/", 1)[1]
                data = subprocess.run(["git", "-C", self.repo, "show", f"HEAD:{path}"], check=True,
                                      capture_output=True).stdout
                self.assertEqual(f["sha256"], hashlib.sha256(data).hexdigest(), path)

    def test_same_data_as_the_last_release_still_makes_the_weekly_release(self):
        previous = os.path.join(self.root, "anterior.json")
        with open(previous, "w", encoding="utf-8") as f:
            json.dump(self.cat, f)
        out = os.path.join(self.root, "release")
        argv = ["--repo", self.repo, "--dist", self.dist, "--out", out, "--previous", previous, "--skip-if-same"]
        self.assertEqual(0, rel.main(argv))
        self.assertTrue(os.path.exists(os.path.join(out, "pardal-GO.zip")))
        shutil.rmtree(out)
        self.assertEqual(0, rel.main(argv + ["--release-only"]))   # só a release: dado igual, nada
        self.assertFalse(os.path.exists(out))


class SharedDocumentsTest(unittest.TestCase):
    def test_spec_and_schema_are_the_shared_ones(self):
        self.assertEqual({}, contract_check.doc_mismatches(DOCS))

    def test_the_readme_points_to_the_spec(self):
        self.assertIn("docs/CATALOGO.md", (REPO / "README.md").read_text(encoding="utf-8"))

    def test_the_pack_schema_mirror_is_the_build_one(self):
        self.assertEqual(build_pack.SCHEMA, catalog_contract.PACK_SCHEMA)


class RecatalogTest(unittest.TestCase):
    """scripts/recatalog.py: o bloco de uma geração já publicada, a partir do catálogo e do SHA256SUMS.txt da release."""

    def setUp(self):
        self.recatalog = _load("recatalogo", GENERATOR_DIR / "scripts" / "recatalog.py")

    def test_rebuilds_a_committed_generation_from_the_repository_and_the_sums(self):
        with tempfile.TemporaryDirectory() as root:
            repo = os.path.join(root, "repo")
            os.makedirs(repo)
            git(repo, "init", "-q")
            git(repo, "config", "user.email", "teste@example.invalid")
            git(repo, "config", "user.name", "teste")
            with open(os.path.join(repo, "LEIAME.md"), "w", encoding="utf-8") as f:
                f.write("x\n")
            git(repo, "add", "-A")
            git(repo, "commit", "-q", "-m", "gerador")
            generator = git(repo, "rev-parse", "HEAD")
            dist, packs = make_build(root)
            self.assertEqual(0, pub.main(["--repo", repo, "--dist", dist, "--packs", packs, "--commit"]))
            git(repo, "tag", "dados-2026-11-08")
            out = os.path.join(root, "release")
            assets = rel.build_assets(repo, out, dist)
            with open(os.path.join(repo, "catalogo.json"), encoding="utf-8") as f:
                published = json.load(f)
            old = {k: v for k, v in published.items() if k != "contract"}   # como era antes do contrato
            sums = self.recatalog.read_sums(os.path.join(out, "SHA256SUMS.txt"))
            sizes = {os.path.basename(a): os.path.getsize(a) for a in assets}
            rebuilt = self.recatalog.rebuild(old, repo=repo, tag="dados-2026-11-08", sums=sums, sizes=sizes,
                                             committed=True)
            self.assertEqual(generator, rebuilt["contract"]["generator"]["commit"])
            # sem os manifestos do build não há os extratos do OSM; o resto é igual ao da publicação
            expected = copy.deepcopy(published["contract"])
            expected["sources"] = [s for s in expected["sources"] if not s["id"].startswith("openstreetmap-")]
            expected["osm_snapshot"] = {"date": None, "md5": None}
            self.assertEqual(expected, rebuilt["contract"])
            self.assertEqual([], contract_check.problems(rebuilt, DOCS))


if __name__ == "__main__":
    unittest.main()
