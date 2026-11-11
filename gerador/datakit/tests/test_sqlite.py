"""O banco SQLite por estado (datakit/build_sqlite.py): esquema, id estável entre gerações, regras de
precisão, confiança, sentido e data, índice por célula, conferência contra os CSVs, catálogo, publicação e release.

    python -m unittest discover -s datakit/tests -t .     # de dentro de gerador/

O banco também abre no SQLite 3.22 (o do Android 10) quando PARDAL_SQLITE_322 aponta para a biblioteca (a do Sabiá:
sabia/gerador/scripts/install_sqlite.py); sem ela, esse teste é pulado.
"""
import csv
import ctypes
import importlib.util
import json
import math
import os
import sqlite3
import tempfile
import unittest
from dataclasses import replace

from datakit import build_sqlite as bs
from datakit import failures
from datakit.common import (AccidentZone, Bump, Camera, CameraKind, EnforcementCamera, Hazard, Limit, LimitLine,
                            PotholeZone, RadarZone, Struct, Toll)


def _script(name):
    path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scripts", f"{name}.py"))
    spec = importlib.util.spec_from_file_location(f"_{name}_sqlite", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _data(**over):
    """Um pacote com um registro de cada tipo (Goiânia e arredores)."""
    d = bs.PackData(
        cameras=[Camera(-16.680001, -49.250002, CameraKind.FIXED, 60, "DER-GO+OSM", True, direction_deg=92),
                 Camera(-16.700000, -49.260000, CameraKind.SECTION, 80, "OSM", True, end_lat=-16.71, end_lng=-49.26,
                        source_ref=("OSM", "node/7")),
                 Camera(-16.690000, -49.270000, CameraKind.FIXED, 50, "INMETRO", False)],
        limits=[Limit(-16.68, -49.25, 60, "OSM"), Limit(-16.68, -49.25, 40, "OSM:class", True, 30, 180)],
        limit_lines=[LimitLine(((-16.68, -49.25), (-16.681, -49.248)), 60, "ANTT", direction_deg=90, highway="",
                               oneway=None)],
        structs=[Struct(-16.6, -49.2, -16.601, -49.2, "BRIDGE")],
        bumps=[Bump(-16.62, -49.22, "BUMP")],
        hazards=[Hazard(-16.63, -49.23, "LEVEL_CROSSING", source_ref=("OSM", "node/9"))],
        tolls=[Toll(-16.64, -49.24, "PLAZA", "Praça 1", "ANTT")],
        radar_zones=[RadarZone("BR-060", 120.0, 130.5, "2026-01-01", ((-16.5, -49.1), (-16.6, -49.0)), 12)],
        potholes=[PotholeZone("BR-153", 10.0, 12.0, "DECREASING", "VERY_BAD", "2026-09", ((-16.4, -49.3), (-16.41, -49.3)))],
        moto_accidents=[AccidentZone("BR-153", 1.0, 3.0, 9, 2, "2025-08/2026-07", ((-16.3, -49.3), (-16.31, -49.3)))],
        enforcement_cameras=[EnforcementCamera(-16.65, -49.25, "BUS_LANE", "CET-SP:CAM")])
    for k, v in over.items():
        setattr(d, k, v)
    return d


DATES = bs.Dates({"DER-GO": "2026-11-08", "ANTT placas (trechos)": "2026-11-07", "ANTT (pedágios)": "2026-11-06",
                  "PRF (trechos de radar portátil)": "2026-11-05", "CET-SP (outras câmeras)": "2026-11-04"},
                 osm="2026-11-09")


def _query(path, sql, args=()):
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return db.execute(sql, args).fetchall()
    finally:
        db.close()


def _by_type(path):
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        return {r["type"]: dict(r) for r in db.execute("SELECT * FROM event ORDER BY seq")}
    finally:
        db.close()


class Schema(unittest.TestCase):
    def test_tables_columns_meta_and_rollback_mode(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "x.sqlite")
            counts = bs.write(path, "go", _data(), DATES, "2026-11-08T00:00:00Z")
            self.assertEqual(counts, {t: (3 if t == bs.CAMERA else 2 if t == bs.SPEED_LIMIT else 1)
                                      for t in bs.TYPE_FILES})
            names = {r[0] for r in _query(path, "SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertEqual(names, {"meta", "event", "event_cell"})
            cols = [r[1] for r in _query(path, "PRAGMA table_info(event)")]
            self.assertEqual(tuple(cols), bs.COLUMNS)
            meta = dict(_query(path, "SELECT key, value FROM meta"))
            self.assertEqual((meta["schema_version"], meta["uf"], meta["coord_scale"], meta["cell_zoom"], meta["crs"]),
                             (str(bs.SCHEMA_VERSION), "GO", "100000", "13", "EPSG:4326"))
            self.assertEqual(_query(path, "PRAGMA user_version"), [(bs.SCHEMA_VERSION,)])
            with open(path, "rb") as f:
                self.assertEqual(f.read(20)[18:20], b"\x01\x01")   # rollback (legado), não WAL
            sql = " ".join(r[0].lower() for r in _query(path, "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL"))
            for needle in ("fts", "rtree", "virtual"):
                self.assertNotIn(needle, sql)
            self.assertFalse(os.path.exists(path + ".parcial"))
            problems = bs.validate(path, d)[0]   # os CSVs não estão aqui: só as contagens acusam
            self.assertTrue(problems and all(p.endswith(".csv") and " no banco, 0 no " in p for p in problems), problems)

    def test_same_content_same_file(self):
        """Sem data de gravação dentro e em ordem fixa: duas gravações do mesmo pacote dão o mesmo arquivo."""
        with tempfile.TemporaryDirectory() as d:
            a, b = os.path.join(d, "a.sqlite"), os.path.join(d, "b.sqlite")
            bs.write(a, "GO", _data(), DATES, "t")
            shuffled = _data(cameras=list(reversed(_data().cameras)), limits=list(reversed(_data().limits)))
            bs.write(b, "GO", shuffled, DATES, "t")
            self.assertEqual(bs.sha256(a), bs.sha256(b))

    def test_coordinates_lines_and_fields(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "x.sqlite")
            bs.write(path, "GO", _data(), DATES)
            ev = _by_type(path)
            cam = ev[bs.CAMERA]
            line = ev[bs.SPEED_LIMIT_LINE]
            self.assertEqual(bs.decode_line(line["coords"]), [(-1668000, -4925000), (-1668100, -4924800)])
            self.assertEqual((line["lat"], line["lng"], line["direction_scope"], line["oneway"]),
                             (-1668000, -4925000, "ONE", None))
            rows = _query(path, "SELECT lat, lng, end_lat, end_lng, kind FROM event WHERE type='CAMERA' ORDER BY lat")
            self.assertIn((-1670000, -4926000, -1671000, -4926000, "SECTION"), rows)
            self.assertIn(cam["source"], {"DER-GO+OSM", "OSM", "INMETRO"})
            zone = ev[bs.PORTABLE_RADAR_ZONE]
            self.assertEqual((zone["road"], zone["km_from"], zone["km_to"], zone["valid_from"], zone["speed_fines_12m"],
                              zone["source"]), ("BR-060", 120.0, 130.5, "2026-01-01", 12, "PRF"))
            hole = ev[bs.POTHOLE_ZONE]
            self.assertEqual((hole["kind"], hole["km_direction"], hole["observed_at"], hole["direction_scope"]),
                             ("VERY_BAD", "DECREASING", "2026-09", "ONE"))
            acc = ev[bs.MOTO_ACCIDENT_ZONE]
            self.assertEqual((acc["accidents"], acc["rider_deaths"], acc["period"], acc["observed_at"]),
                             (9, 2, "2025-08/2026-07", "2026-07"))
            self.assertEqual((ev[bs.TOLL]["name"], ev[bs.TOLL]["observed_at"]), ("Praça 1", "2026-11-06"))
            self.assertEqual((ev[bs.HAZARD]["source_id"], ev[bs.HAZARD]["source_id_from"]), ("node/9", "OSM"))
            self.assertIsNone(ev[bs.BUMP]["source_id"])
            self.assertTrue(all(r["valid_until"] is None for r in ev.values()))


class StableId(unittest.TestCase):
    """O id não muda entre gerações enquanto o objeto não muda (regra em docs/FORMATO_SQLITE.md)."""

    def _ids(self, data):
        return {(ev.get("type"), ev.get("lat"), ev.get("lng"), ev.get("source")): ev.id for ev in bs.events(data, DATES)}

    def test_two_generations(self):
        gen1 = _data()
        # a segunda geração: outra ordem, um radar novo, o limite e a situação de um radar mudaram, o radar do OSM
        # (com o nó) moveu 2 m, o radar do Inmetro (sem id da fonte) moveu 2 m
        cams = gen1.cameras
        gen2 = _data(cameras=[
            Camera(-16.75, -49.30, CameraKind.FIXED, 40, "DNIT", True),
            replace(cams[2], lat=cams[2].lat + 0.00002),
            replace(cams[1], lat=cams[1].lat + 0.00002),
            replace(cams[0], limit_kmh=50, active=False),
        ], limits=list(reversed(gen1.limits)))
        a = {ev.key: ev.id for ev in bs.events(gen1, DATES)}
        b_events = bs.events(gen2, DATES)
        b = {ev.key: ev.id for ev in b_events}
        same = set(a) & set(b)
        self.assertTrue(all(a[k] == b[k] for k in same))
        by_id = {ev.id: ev for ev in b_events}
        first = [ev for ev in bs.events(gen1, DATES) if ev.get("type") == bs.CAMERA]
        ids1 = {ev.get("source"): ev.id for ev in first}
        ids2 = {ev.get("source"): ev.id for ev in b_events if ev.get("type") == bs.CAMERA}
        self.assertEqual(ids1["DER-GO+OSM"], ids2["DER-GO+OSM"])   # limite e situação mudaram: mesmo objeto
        self.assertEqual(by_id[ids2["DER-GO+OSM"]].get("limit_kmh"), 50)
        self.assertEqual(ids1["OSM"], ids2["OSM"])                 # o nó do OSM é o mesmo, mesmo movido
        self.assertNotEqual(ids1["INMETRO"], ids2["INMETRO"])      # sem id da fonte: posição nova, id novo
        self.assertIn("DNIT", ids2)
        # todo o resto (limites em outra ordem, trechos, pedágios...) igual
        rest1 = {k: v for k, v in self._ids(gen1).items() if k[0] != bs.CAMERA}
        rest2 = {k: v for k, v in self._ids(gen2).items() if k[0] != bs.CAMERA}
        self.assertEqual(rest1, rest2)

    def test_merged_source_keeps_the_id_of_the_first(self):
        """O radar do órgão que ganhou a confirmação do OSM (DNIT -> DNIT+OSM) ou do Inmetro fica com o id."""
        base = [ev.id for ev in bs.events(bs.PackData(cameras=[Camera(-16.0, -49.0, source="DNIT")]))]
        for source in ("DNIT+OSM", "DNIT+INMETRO", "DNIT+OSM+INMETRO"):
            got = [ev.id for ev in bs.events(bs.PackData(cameras=[Camera(-16.0, -49.0, source=source)]))]
            self.assertEqual(got, base, source)
        other = [ev.id for ev in bs.events(bs.PackData(cameras=[Camera(-16.0, -49.0, source="ANTT")]))]
        self.assertNotEqual(other, base)

    def test_rule_is_the_documented_hash(self):
        ev = bs.events(bs.PackData(cameras=[Camera(-16.0, -49.0, source="DNIT")]))[0]
        self.assertEqual(ev.key, ("CAMERA", "DNIT", "pos", "-1600000", "-4900000"))
        self.assertEqual(ev.id, int.from_bytes(__import__("hashlib").sha256(
            "CAMERA\x1fDNIT\x1fpos\x1f-1600000\x1f-4900000".encode()).digest()[:8], "big") >> 1)
        self.assertTrue(0 < ev.id < 2 ** 63)
        osm = bs.events(bs.PackData(bumps=[Bump(-16.0, -49.0, "HUMP", source_ref=("OSM", "way/5"))]))[0]
        self.assertEqual(osm.key, ("BUMP", "OSM", "id", "way/5"))
        zone = bs.events(bs.PackData(radar_zones=[RadarZone("SC-401", 1.04, 2.0, "", ((-27.5, -48.5), (-27.4, -48.5)))]))
        self.assertEqual(zone[0].key, ("PORTABLE_RADAR_ZONE", "SIE-SC", "km", "SC-401", "1.0", "2.0"))

    def test_repeated_key_gets_a_suffix_whatever_the_order(self):
        """Dois pedaços do mesmo trecho com os mesmos km: o primeiro pelo conteúdo fica com a chave, o outro com #2."""
        a = RadarZone("BR-060", 1.0, 2.0, "", ((-16.0, -49.0), (-16.1, -49.0)))
        b = RadarZone("BR-060", 1.0, 2.0, "", ((-16.5, -49.0), (-16.6, -49.0)))
        one = {ev.get("lat"): (ev.key[-1], ev.id) for ev in bs.events(bs.PackData(radar_zones=[a, b]))}
        two = {ev.get("lat"): (ev.key[-1], ev.id) for ev in bs.events(bs.PackData(radar_zones=[b, a]))}
        self.assertEqual(one, two)
        self.assertEqual(sorted(k for k, _ in one.values()), ["#2", "2.0"])

    def test_limit_line_key_uses_the_geometry(self):
        ln = LimitLine(((-16.68, -49.25), (-16.681, -49.248)), 60, "OSM")
        k1 = bs.events(bs.PackData(limit_lines=[ln]))[0]
        k2 = bs.events(bs.PackData(limit_lines=[replace(ln, limit_kmh=80)]))[0]
        k3 = bs.events(bs.PackData(limit_lines=[replace(ln, points=((-16.68, -49.25), (-16.682, -49.248)))]))[0]
        self.assertEqual(k1.id, k2.id)       # o valor mudou na mesma via: mesmo trecho
        self.assertNotEqual(k1.id, k3.id)    # a geometria mudou: trecho novo


class DerivedFields(unittest.TestCase):
    def test_confidence(self):
        self.assertEqual(bs.confidence("OSM"), "MEDIUM")
        self.assertEqual(bs.confidence("INMETRO"), "MEDIUM")
        self.assertEqual(bs.confidence("DNIT"), "HIGH")
        self.assertEqual(bs.confidence("DNIT+OSM"), "HIGH")
        self.assertEqual(bs.confidence("OSM+INMETRO"), "HIGH")
        self.assertEqual(bs.confidence("OSM", estimated=True), "LOW")
        self.assertEqual(bs.confidence("OSM:class", estimated=True), "LOW")
        self.assertEqual(bs.confidence("ANTT"), "HIGH")

    def test_position_accuracy(self):
        self.assertEqual(bs.camera_accuracy("INMETRO"), 100)
        self.assertEqual(bs.camera_accuracy("DER-MG"), 900)
        self.assertEqual(bs.camera_accuracy("DER-MG+INMETRO"), 900)
        self.assertIsNone(bs.camera_accuracy("DER-MG+OSM"))
        self.assertIsNone(bs.camera_accuracy("OSM+INMETRO"))
        self.assertIsNone(bs.camera_accuracy("DNIT"))
        evs = {ev.get("type"): ev for ev in bs.events(_data(), DATES)}
        self.assertEqual(evs[bs.PORTABLE_RADAR_ZONE].get("position_accuracy_m"), 900)
        self.assertEqual(evs[bs.POTHOLE_ZONE].get("position_accuracy_m"), 900)
        self.assertEqual(evs[bs.MOTO_ACCIDENT_ZONE].get("position_accuracy_m"), 900)
        self.assertIsNone(evs[bs.SPEED_LIMIT].get("position_accuracy_m"))
        sc = bs.events(bs.PackData(radar_zones=[RadarZone("SC-401", 1, 2, "", ((-27.5, -48.5), (-27.4, -48.5)))]))
        self.assertEqual(sc[0].get("position_accuracy_m"), 200)

    def test_direction_scope(self):
        evs = bs.events(_data(), DATES)
        scopes = {(ev.get("type"), ev.get("direction_deg")): ev.get("direction_scope") for ev in evs}
        self.assertEqual(scopes[(bs.CAMERA, 92)], "ONE")
        self.assertEqual(scopes[(bs.CAMERA, None)], "UNKNOWN")      # vazio: os dois sentidos OU desconhecido
        self.assertEqual(scopes[(bs.SPEED_LIMIT, None)], "BOTH")    # limite sem sentido vale para os dois (README)
        self.assertEqual(scopes[(bs.SPEED_LIMIT, 180)], "ONE")
        self.assertEqual(scopes[(bs.POTHOLE_ZONE, None)], "ONE")    # o sentido avaliado, a linha desenhada nele
        self.assertEqual(scopes[(bs.BUMP, None)], "UNKNOWN")

    def test_observed_at(self):
        self.assertEqual(bs.observed_at("DER-GO+OSM", DATES, bs.CAMERA_DATE_LABELS, True), "2026-11-09")
        self.assertEqual(bs.observed_at("DER-GO", DATES, bs.CAMERA_DATE_LABELS, True), "2026-11-08")
        self.assertIsNone(bs.observed_at("INMETRO", DATES, bs.CAMERA_DATE_LABELS, True))
        self.assertIsNone(bs.observed_at("DNIT", DATES, bs.CAMERA_DATE_LABELS, True))   # sem data no catálogo
        self.assertEqual(bs.observed_at("OSM:class", DATES, bs.LIMIT_DATE_LABELS), "2026-11-09")
        self.assertIsNone(bs.observed_at("OSM", bs.Dates(), bs.LIMIT_DATE_LABELS))
        dates = bs.Dates({"capitais": "2026-10-01", "PRF (radares das concessões)": "2026-10-02"})
        self.assertEqual(bs.observed_at("PMF", dates, bs.CAMERA_DATE_LABELS, True), "2026-10-01")
        self.assertEqual(bs.observed_at("PRF", dates, bs.CAMERA_DATE_LABELS, True), "2026-10-02")

    def test_osm_date_from_the_manifest(self):
        self.assertEqual(bs.osm_date([{"name": "OSM/Geofabrik centro-oeste",
                                       "file_date": "Sat, 08 Nov 2026 21:23:05 GMT"}]), "2026-11-08")
        self.assertIsNone(bs.osm_date([{"name": "teste"}]))

    def test_date_labels_are_the_ones_the_build_uses(self):
        """Os rótulos de `source_dates` são os do build: os nomes do OFFICIAL e os de context.py."""
        from datakit import build, context
        for name, mod in build.OFFICIAL.items():
            for code in getattr(mod, "SOURCE_CODES", (name,)):
                self.assertEqual(bs.CAMERA_DATE_LABELS.get(code, code), name, code)
        with open(context.__file__, encoding="utf-8") as f:
            text = f.read()
        for labels in (bs.LIMIT_DATE_LABELS, bs.LINE_DATE_LABELS, bs.TOLL_DATE_LABELS, bs.ENFORCEMENT_DATE_LABELS,
                       bs.ZONE_DATE_LABELS):
            for label in labels.values():
                self.assertIn(f'"{label}"', text, label)
        self.assertIn('"PRF (radares das concessões)"', text)


class Cells(unittest.TestCase):
    def test_cell_is_the_sabia_one(self):
        """x * 8192 + y do tile do zoom 13 (docs/FORMATO.md do Sabiá)."""
        lat, lng = -16.6869, -49.2648
        n = 8192
        x = int((lng + 180) / 360 * n)
        y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
        self.assertEqual(bs.cell(bs.e5(lat), bs.e5(lng)), x * n + y)
        self.assertEqual(len(bs.neighborhood(lat, lng)), 9)
        self.assertIn(x * n + y, bs.neighborhood(lat, lng))

    def test_a_long_line_is_found_anywhere_along_it(self):
        """Um trecho de 60 km com só as duas pontas: a consulta pelo meio dele o acha."""
        zone = RadarZone("BR-060", 0, 60, "", ((-16.0, -49.0), (-16.0, -48.44)))
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "x.sqlite")
            bs.write(path, "GO", bs.PackData(radar_zones=[zone], cameras=[Camera(-15.0, -47.0)]))
            for lng in (-49.0, -48.8, -48.72, -48.6, -48.44):
                cells = bs.neighborhood(-16.001, lng)
                got = _query(path, f"SELECT type FROM event WHERE seq IN (SELECT seq FROM event_cell WHERE cell IN "
                                   f"({','.join('?' * len(cells))}))", cells)
                self.assertEqual(got, [(bs.PORTABLE_RADAR_ZONE,)], lng)

    def test_diagonal_step_adds_the_corner_cells(self):
        n = 8192
        a = (bs.e5(-16.0), bs.e5(-49.0))
        b = (bs.e5(-16.2), bs.e5(-48.8))
        cells = bs.line_cells([a, b])
        xs = {c // n for c in cells}
        ys = {c % n for c in cells}
        self.assertGreater(len(cells), len(xs))
        for c in cells:   # contíguo: cada célula tem vizinha (lado) no conjunto, menos se for a única
            x, y = divmod(c, n)
            self.assertTrue(any((x + dx) * n + (y + dy) in cells for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))))
        self.assertTrue(min(xs) <= bs.cell(*a) // n <= max(xs) and min(ys) <= bs.cell(*b) % n <= max(ys))


class FromCsv(unittest.TestCase):
    """O banco tirado dos CSVs publicados é o mesmo do build, para os registros sem id da fonte."""

    def _pack(self, d, data):
        from datakit.build_pack import build as build_pack
        return build_pack("GO", d, data.cameras, data.limits, data.structs, sources=[], bumps=data.bumps,
                          tolls=data.tolls, radar_zones=data.radar_zones, potholes=data.potholes,
                          moto_accidents=data.moto_accidents, hazards=data.hazards, limit_lines=data.limit_lines,
                          enforcement_cameras=data.enforcement_cameras)

    def test_csv_round_trip_and_same_database(self):
        data = _data(cameras=[replace(c, source_ref=None) for c in _data().cameras],
                     hazards=[Hazard(-16.63, -49.23, "LEVEL_CROSSING")])
        with tempfile.TemporaryDirectory() as d:
            m = self._pack(d, data)
            folder = os.path.join(d, "GO")
            back = bs.read_csv_dir(folder)
            for name, attr in (("radares.csv", "cameras"), ("limites.csv", "limits"),
                               ("limites_trechos.csv", "limit_lines"), ("estruturas.csv", "structs"),
                               ("lombadas.csv", "bumps"), ("pontos_atencao.csv", "hazards"), ("pedagios.csv", "tolls"),
                               ("radar_portatil.csv", "radar_zones"), ("buracos.csv", "potholes"),
                               ("acidentes_moto.csv", "moto_accidents"),
                               ("cameras_fiscalizacao.csv", "enforcement_cameras")):
                with open(os.path.join(folder, name), newline="", encoding="utf-8") as f:
                    rows = list(csv.reader(f))[1:]
                self.assertEqual([x.row() for x in getattr(back, attr)], rows, name)
            again = os.path.join(d, "de_novo.sqlite")
            bs.write(again, "GO", back, bs.Dates(), m["built_at"])
            self.assertEqual(bs.sha256(again), m["sqlite"]["sha256"])
            self.assertEqual(bs.validate(again, folder)[0], [])

    def test_validate_catches_a_count_that_does_not_match(self):
        with tempfile.TemporaryDirectory() as d:
            self._pack(d, _data())
            folder = os.path.join(d, "GO")
            path = os.path.join(folder, bs.SQLITE_FILE)
            problems, counts = bs.validate(path, folder)
            self.assertEqual(problems, [])
            self.assertEqual(counts[bs.CAMERA], 3)
            with open(os.path.join(folder, "radares.csv"), "a", encoding="utf-8") as f:
                f.write("-16.000000,-49.000000,FIXED,,OSM,1,,,\n")
            problems, _ = bs.validate(path, folder)
            self.assertEqual(problems, ["CAMERA: 3 no banco, 4 no radares.csv"])

    def test_cli_builds_from_a_published_folder(self):
        with tempfile.TemporaryDirectory() as d:
            self._pack(os.path.join(d, "estados"), _data())
            os.remove(os.path.join(d, "estados", "GO", bs.SQLITE_FILE))
            lines = os.path.join(d, "trechos", "GO")
            os.makedirs(lines)
            os.replace(os.path.join(d, "estados", "GO", "limites_trechos.csv"), os.path.join(lines, "limites_trechos.csv"))
            cat = os.path.join(d, "catalogo.json")
            with open(cat, "w", encoding="utf-8") as f:
                json.dump({"built_at": "2026-11-08T00:00:00Z", "source_dates": {"DER-GO": "2026-11-08"},
                           "ufs": {"GO": {"built_at": "2026-11-08T01:00:00Z"}}}, f)
            out = os.path.join(d, "out")
            code = bs.main(["--states", os.path.join(d, "estados"), "--lines", os.path.join(d, "trechos"),
                            "--catalog", cat, "--out", out])
            self.assertEqual(code, 0)
            path = os.path.join(out, "pardal-GO.sqlite")
            self.assertEqual(dict(_query(path, "SELECT key, value FROM meta"))["built_at"], "2026-11-08T01:00:00Z")
            self.assertEqual(_query(path, "SELECT count(*) FROM event WHERE type='SPEED_LIMIT_LINE'"), [(1,)])
            unpacked = os.path.join(d, "unpacked.sqlite")
            bs.decompress(os.path.join(out, "pardal-GO.sqlite.zst"), unpacked)
            self.assertEqual(bs.sha256(unpacked), bs.sha256(path))


class Catalog(unittest.TestCase):
    """A entrada `sqlite` do catálogo: nova, ao lado das outras, sem mudar nenhuma chave existente."""

    def _build(self, d, keep_sqlite=True):
        from datakit import build_catalog
        from datakit.build_pack import build as build_pack
        data = _data()
        packs, dist = os.path.join(d, "packs"), os.path.join(d, "dist")
        build_pack("GO", packs, data.cameras, data.limits, data.structs, sources=[], bumps=data.bumps,
                   tolls=data.tolls, limit_lines=data.limit_lines, potholes=data.potholes)
        if not keep_sqlite:
            os.remove(os.path.join(packs, "GO", bs.SQLITE_FILE))
        return build_catalog.build(packs, dist), dist

    def test_entry_and_file(self):
        with tempfile.TemporaryDirectory() as d:
            cat, dist = self._build(d)
            entry = cat["ufs"]["GO"]["sqlite"]
            self.assertEqual(set(entry), {"file", "bytes", "sha256", "uncompressed_bytes", "uncompressed_sha256",
                                          "schema_version", "count", "counts"})
            self.assertEqual(entry["file"], "estados/GO/pardal-GO.sqlite.zst")
            path = os.path.join(dist, entry["file"])
            self.assertEqual((entry["bytes"], entry["sha256"]), (os.path.getsize(path), bs.sha256(path)))
            unpacked = os.path.join(d, "x.sqlite")
            bs.decompress(path, unpacked)
            self.assertEqual((entry["uncompressed_bytes"], entry["uncompressed_sha256"]),
                             (os.path.getsize(unpacked), bs.sha256(unpacked)))
            self.assertEqual(entry["schema_version"], bs.SCHEMA_VERSION)
            self.assertEqual(entry["counts"][bs.CAMERA], cat["ufs"]["GO"]["cameras"]["count"])
            self.assertEqual(entry["counts"][bs.SPEED_LIMIT_LINE], cat["ufs"]["GO"]["limit_lines"]["count"])
            self.assertEqual(entry["count"], sum(entry["counts"].values()))

    def test_no_existing_key_changes(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            with_db, _ = self._build(a)
            without, _ = self._build(b, keep_sqlite=False)
            for cat in (with_db, without):
                cat.pop("built_at")
                for e in cat["ufs"].values():
                    e.pop("built_at")
                    e.pop("artifact_built_at")
            with_db["ufs"]["GO"].pop("sqlite")
            self.assertEqual(with_db, without)

    def test_a_database_that_does_not_match_is_a_failure_and_stays_out(self):
        from datakit import build_catalog
        from datakit.build_pack import build as build_pack
        before = list(failures._FAILURES)
        try:
            with tempfile.TemporaryDirectory() as d:
                packs, dist = os.path.join(d, "packs"), os.path.join(d, "dist")
                build_pack("GO", packs, [Camera(-16.0, -49.0)], [], [], sources=[])
                with open(os.path.join(packs, "GO", "radares.csv"), "a", encoding="utf-8") as f:
                    f.write("-16.100000,-49.000000,FIXED,,OSM,1,,,\n")
                cat = build_catalog.build(packs, dist)
                self.assertNotIn("sqlite", cat["ufs"]["GO"])
                self.assertFalse(os.path.exists(os.path.join(dist, "estados", "GO", "pardal-GO.sqlite.zst")))
                self.assertTrue(any(m.startswith("sqlite GO") for m in failures.since(len(before))))
        finally:
            failures._FAILURES[:] = before

    def test_the_app_reader_ignores_the_new_key(self):
        """O leitor do app (RadarPackManager.parseCatalog/parseDownloadPlan) lê só chaves conhecidas de cada UF e exige
        que cada uma seja um objeto com "file": a entrada nova é um objeto e não troca nenhuma delas."""
        with tempfile.TemporaryDirectory() as d:
            cat, _ = self._build(d)
            pub = _script("publish")
            published = pub.rewrite_catalog(cat)
            go = published["ufs"]["GO"]
            for key in ("cameras", "limits", "structs", "bumps", "tolls", "potholes"):
                if key in go:
                    self.assertIn("file", go[key], key)
            self.assertEqual(go["sqlite"]["release_asset"], "pardal-GO.sqlite.zst")
            self.assertNotIn("file", go["sqlite"])
            self.assertIsInstance(go["counts"]["cameras"], int)


class Publish(unittest.TestCase):
    def setUp(self):
        self.pub = _script("publish")

    def test_release_asset_name(self):
        self.assertTrue(self.pub._RELEASE_ASSET_NAME.match("pardal-SP.sqlite.zst"))
        self.assertIsNone(self.pub._PUBLISHED_NAME.match("pardal-SP.sqlite.zst"))
        self.assertIsNone(self.pub._RELEASE_ONLY_NAME.match("pardal-SP.sqlite.zst"))
        self.assertIsNone(self.pub._PUBLISHED_NAME.match(bs.SQLITE_FILE))
        self.assertTrue(self.pub._RELEASE_ASSET_NAME.match(bs.release_name("sp")))

    def test_published_catalog_points_to_the_release_asset(self):
        entry = {"file": "estados/SP/pardal-SP.sqlite.zst", "bytes": 5, "sha256": "ab", "uncompressed_bytes": 9,
                 "uncompressed_sha256": "cd", "schema_version": 1, "count": 2, "counts": {"CAMERA": 2}}
        out = self.pub.rewrite_catalog({"ufs": {"SP": {"sqlite": dict(entry)}}})
        expected = dict(entry)
        expected.pop("file")
        expected["release_asset"] = "pardal-SP.sqlite.zst"
        self.assertEqual(out["ufs"]["SP"]["sqlite"], expected)

    def test_a_database_that_disappears_is_a_drop(self):
        old = {"ufs": {"SP": {"counts": {"cameras": 10}, "sqlite": {"sha256": "x"}}}}
        self.assertEqual(self.pub.drops(old, {"ufs": {"SP": {"counts": {"cameras": 10}}}}),
                         ["SP: banco SQLite sumiu do catálogo"])
        self.assertEqual(self.pub.drops(old, old), [])
        self.assertEqual(self.pub.drops({"ufs": {"SP": {"counts": {}}}}, old), [])   # o primeiro banco não é queda

    def _dist(self, d, payload=b"zst"):
        dist = os.path.join(d, "dist")
        os.makedirs(os.path.join(dist, "estados", "SP"))
        path = os.path.join(dist, "estados", "SP", "pardal-SP.sqlite.zst")
        with open(path, "wb") as f:
            f.write(payload)
        cat = {"ufs": {"SP": {"counts": {}, "sqlite": {"file": "estados/SP/pardal-SP.sqlite.zst",
                                                        "sha256": bs.sha256(path), "bytes": len(payload)}}}}
        with open(os.path.join(dist, "catalogo.json"), "w", encoding="utf-8") as f:
            json.dump(cat, f)
        repo = os.path.join(d, "repo")
        os.makedirs(repo)
        return dist, repo, path

    def test_publish_checks_size_and_sha_and_never_copies_the_database(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            dist, repo, path = self._dist(d)
            self.assertEqual(self.pub.release_assets(dist), ["estados/SP/pardal-SP.sqlite.zst"])
            with mock.patch.object(self.pub, "MAX_FILE_BYTES", 2):
                with self.assertRaises(SystemExit) as cm:
                    self.pub.main(["--repo", repo, "--dist", dist])
                self.assertIn("pardal-SP.sqlite.zst", str(cm.exception.code))
            with open(path, "wb") as f:
                f.write(b"outro")
            with self.assertRaises(SystemExit) as cm:
                self.pub.main(["--repo", repo, "--dist", dist])
            self.assertIn("sha256", str(cm.exception.code))
        with tempfile.TemporaryDirectory() as d:
            dist, repo, _ = self._dist(d)
            self.assertEqual(self.pub.main(["--repo", repo, "--dist", dist]), 0)
            self.assertEqual(sorted(os.listdir(repo)), ["catalogo.json"])
            with open(os.path.join(repo, "catalogo.json"), encoding="utf-8") as f:
                self.assertEqual(json.load(f)["ufs"]["SP"]["sqlite"]["release_asset"], "pardal-SP.sqlite.zst")


class Release(unittest.TestCase):
    def setUp(self):
        self.rel = _script("release")

    def _repo(self, d, sha):
        repo, dist = os.path.join(d, "repo"), os.path.join(d, "dist")
        os.makedirs(os.path.join(repo, "estados", "SP"))
        os.makedirs(os.path.join(repo, "brasil"))
        os.makedirs(os.path.join(dist, "estados", "SP"))
        with open(os.path.join(repo, "estados", "SP", "radares.csv"), "w") as f:
            f.write("x")
        with open(os.path.join(dist, "estados", "SP", "pardal-SP.sqlite.zst"), "wb") as f:
            f.write(b"banco")
        cat = {"built_at": "2026-11-08T00:00:00Z",
               "ufs": {"SP": {"sqlite": {"release_asset": "pardal-SP.sqlite.zst", "sha256": sha}}}}
        with open(os.path.join(repo, "catalogo.json"), "w", encoding="utf-8") as f:
            json.dump(cat, f)
        return repo, dist

    def test_database_is_its_own_asset_with_the_catalog_sha(self):
        import hashlib
        with tempfile.TemporaryDirectory() as d:
            repo, dist = self._repo(d, hashlib.sha256(b"banco").hexdigest())
            out = os.path.join(d, "out")
            assets = [os.path.basename(a) for a in self.rel.build_assets(repo, out, dist)]
            self.assertIn("pardal-SP.sqlite.zst", assets)
            with open(os.path.join(out, "SHA256SUMS.txt"), encoding="utf-8") as f:
                self.assertIn("pardal-SP.sqlite.zst", f.read())
            import zipfile
            with zipfile.ZipFile(os.path.join(out, "pardal-SP.zip")) as z:
                self.assertNotIn("SP/pardal-SP.sqlite.zst", z.namelist())   # fora do zip
        with tempfile.TemporaryDirectory() as d:
            repo, dist = self._repo(d, "outro")
            with self.assertRaises(SystemExit):
                self.rel.build_assets(repo, os.path.join(d, "out"), dist)

    def test_fingerprint_ignores_the_database(self):
        a = {"ufs": {"SP": {"cameras": {"file": "estados/SP/radares.csv", "sha256": "x"},
                            "sqlite": {"release_asset": "pardal-SP.sqlite.zst", "sha256": "1"}}}}
        b = json.loads(json.dumps(a))
        b["ufs"]["SP"]["sqlite"]["sha256"] = "2"
        self.assertEqual(self.rel.data_fingerprint(a), self.rel.data_fingerprint(b))

    def test_notes_list_the_database(self):
        self.assertIn("pardal-<UF>.sqlite.zst", self.rel.release_notes({"built_at": "2026-11-08T00:00:00Z"}, None,
                                                                      [], "u"))


class SourceRefs(unittest.TestCase):
    """O id da fonte nos leitores que o têm (o resto fica nulo: docs/FORMATO_SQLITE.md)."""

    def test_der_se_detran_ma_and_cet(self):
        from datakit.sources import cet_sp, der_se, detran_ma
        from datakit.tests.test_state_sources import CetGithubBackup, DerSe, DetranMa
        self.assertEqual([c.source_ref for c in der_se.parse(DerSe.CSV)][:2],
                         [("DER-SE", "SE001R"), ("DER-SE", "SE348L")])
        self.assertEqual([c.source_ref for c in detran_ma.parse(DetranMa.TEXT)],
                         [("DETRAN-MA", "MA301R"), ("DETRAN-MA", "MA349R")])
        rows = cet_sp.csv_rows(CetGithubBackup.CSV)
        self.assertEqual([c.source_ref for c in cet_sp.rows_to_cameras(rows)], [("CET-SP", "100"), ("CET-SP", "200")])
        self.assertEqual({c.source_ref for c in cet_sp.rows_to_enforcement_cameras(rows)}, {("CET-SP:CAM", "200")})
        self.assertEqual(cet_sp.local_code({"CÓDIGO LOCAL": 2400.0}), "2400")
        self.assertIsNone(cet_sp.local_code({"CÓDIGO LOCAL": " "}))

    def test_ref_is_not_part_of_the_comparison(self):
        a = Camera(-16.0, -49.0, source="OSM", source_ref=("OSM", "node/1"))
        self.assertEqual(a, Camera(-16.0, -49.0, source="OSM"))
        self.assertEqual(a.row(), Camera(-16.0, -49.0, source="OSM").row())


@unittest.skipUnless(os.environ.get("PARDAL_SQLITE_322"), "PARDAL_SQLITE_322 não aponta para o SQLite 3.22")
class OldSqlite(unittest.TestCase):
    def test_opens_checks_and_queries_in_3_22(self):
        lib = ctypes.CDLL(os.environ["PARDAL_SQLITE_322"])
        lib.sqlite3_libversion.restype = ctypes.c_char_p
        self.assertEqual(lib.sqlite3_libversion().decode(), "3.22.0")
        vp, cp = ctypes.c_void_p, ctypes.c_char_p
        lib.sqlite3_open_v2.argtypes = [cp, ctypes.POINTER(vp), ctypes.c_int, cp]
        lib.sqlite3_prepare_v2.argtypes = [vp, cp, ctypes.c_int, ctypes.POINTER(vp), ctypes.POINTER(vp)]
        lib.sqlite3_step.argtypes = [vp]
        lib.sqlite3_finalize.argtypes = [vp]
        lib.sqlite3_close.argtypes = [vp]
        lib.sqlite3_column_text.argtypes = [vp, ctypes.c_int]
        lib.sqlite3_column_text.restype = ctypes.c_char_p
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "x.sqlite")
            bs.write(path, "GO", _data(), DATES)
            db = vp()
            self.assertEqual(lib.sqlite3_open_v2(path.encode(), ctypes.byref(db), 1, None), 0)
            cells = ",".join(map(str, bs.neighborhood(-16.68, -49.25)))
            got = []
            for sql in ("PRAGMA integrity_check",
                        f"SELECT group_concat(type) FROM (SELECT type FROM event WHERE seq IN "
                        f"(SELECT seq FROM event_cell WHERE cell IN ({cells})) ORDER BY type)"):
                st = vp()
                self.assertEqual(lib.sqlite3_prepare_v2(db, sql.encode(), -1, ctypes.byref(st), None), 0, sql)
                self.assertEqual(lib.sqlite3_step(st), 100)
                got.append(lib.sqlite3_column_text(st, 0).decode())
                lib.sqlite3_finalize(st)
            lib.sqlite3_close(db)
            self.assertEqual(got[0], "ok")
            self.assertIn("CAMERA", got[1].split(","))


if __name__ == "__main__":
    unittest.main()
