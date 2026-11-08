"""O estado de uma execução do build num objeto só, e o contrato das fontes.

Antes, cada peça guardava o que já tinha carregado numa variável do próprio módulo (o extrato do
OSM da região e as fontes oficiais em build.py, os locais desativados em cet_sp, as rotas do SNV
em snv, os polígonos das UFs em ufpoly): duas execuções no mesmo processo (os testes) se
misturavam, e o que cada função usava não aparecia na assinatura. Agora vive tudo no `BuildContext`,
criado pelo build e passado adiante.

Contrato das fontes oficiais: cada módulo expõe `fetch(ctx) -> SourceData` (radares, limites e
locais que o órgão desativou). Toda fonte é lida por `source_cache.load`: atualiza quando dá e,
quando falha, usa a última leitura boa guardada em data/raw/fontes/ ou, sem ela, o que a fonte tinha
na edição publicada (datakit/edition.py; radares e limites oficiais) — vira aviso, não bloqueia a
publicação. Sem nenhum dos dois, a falha é registrada com o nome da fonte e o build segue sem ela;
fonte com várias bases (DER-SP, capitais) registra cada base que falhar. O código da fonte na
coluna `source` dos CSVs é o nome dela no OFFICIAL, ou os de `SOURCE_CODES` do módulo (capitais).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Mapping, Optional, Tuple

from datakit import failures, limit_lines, source_cache
from datakit.common.model import Camera, Limit

_NOT_LOADED = object()


@dataclass
class SourceData:
    """O que uma fonte devolve."""
    cameras: List[Camera] = field(default_factory=list)
    limits: List[Limit] = field(default_factory=list)
    deactivated: List[Tuple[float, float]] = field(default_factory=list)   # (lat, lng)


def _try(label: str, fn, default):
    try:
        return fn()
    except Exception as e:  # noqa: BLE001
        failures.record(label, e)
        return default


class BuildContext:
    """Uma execução do build. `sources`: {nome: módulo com fetch(ctx)}, na ordem do manifest."""

    def __init__(self, raw_dir: str, refresh_osm: bool = True, sources: Optional[dict] = None,
                 edition_dir: Optional[str] = None):
        from datakit.edition import Edition
        self.raw_dir = raw_dir
        self.refresh_osm = refresh_osm
        self.sources = sources or {}
        # a edição publicada, último recurso de cada fonte (None: sem edição, como nos testes)
        self.edition = Edition.open(edition_dir)
        self._polygons: Optional[dict] = None
        self._routes = _NOT_LOADED
        self._official: Optional[Dict[str, SourceData]] = None
        self._national: Optional[dict] = None
        self._osm_region: Optional[str] = None
        self._bumps_region: Optional[str] = None
        self._bumps: list = []
        self._hazards_region: Optional[str] = None
        self._hazards: list = []
        self._tolls_region: Optional[str] = None
        self._tolls: list = []
        self._antt_tolls: Optional[list] = None
        self._prf_radar: Optional[tuple] = None
        self._prf_fines: Optional[Mapping[Tuple[str, int, int], int]] = None
        self._prf_fines_read = False
        self._moto_accidents: Optional[tuple] = None
        self._prf_concessions: Optional[list] = None
        self._sc_portable: Optional[tuple] = None
        self._potholes: Optional[tuple] = None
        self._osm: Optional[tuple] = None
        self._osm_lines: list = []
        self._enforcement: Optional[list] = None
        self._inmetro_points: Dict[str, List[Camera]] = {}

    def _cached(self, label: str, fn, default, owns=(), cameras=(), limits=()):
        """fn() com a última leitura boa da fonte como reserva (datakit/source_cache.py) e, sem ela, as
        linhas da edição publicada com os códigos `cameras` (radares → SourceData) ou `limits` (limites →
        lista de Limit). Sem códigos, a fonte não tem reserva na edição (trechos da PRF, buracos…)."""
        ed = self.edition
        edition: Optional[Callable[[], Tuple[object, str]]] = None
        if ed is not None and cameras:
            edition = lambda: (SourceData(cameras=ed.cameras(cameras)), ed.source_date(label))  # noqa: E731
        elif ed is not None and limits:
            edition = lambda: (ed.limits(limits), ed.source_date(label))  # noqa: E731
        return source_cache.load(label, self.raw_dir, fn, default, owns=owns, edition=edition)

    def _cached_extra(self, label: str, fn, default, owns=()):
        """Como _cached, para o que só complementa uma fonte e não está na edição publicada (os trechos oficiais do
        limites_trechos.csv, as câmeras sem velocidade): sem cópia guardada, a falha vira aviso e fica `default` em vez
        de barrar a publicação."""
        mark = failures.mark()
        got = self._cached(label, fn, default, owns=owns)
        lost = [m for m in failures.since(mark) if m.startswith((label, *owns))]
        if lost:
            failures.discard(lost)
            # complementar: a linha "FALHOU" que o failures.record imprimiu acima fica só como aviso
            failures.warn(label, "falhou e não há cópia guardada da leitura anterior; fica sem ela (é complementar: "
                                 "aviso, não falha)")
        return got

    # ── bases carregadas uma vez por execução ──────────────────────────────────

    def polygons(self) -> dict:
        """{UF: polígono} da malha do IBGE; {} sem shapely ou sem a malha."""
        if self._polygons is None:
            from datakit.common import ufpoly
            self._polygons = ufpoly.polygons(self.raw_dir)
        return self._polygons

    def snv_routes(self):
        """Rotas do SNV (SnvRoutes), ou None se o SNV falhar (a falha é registrada uma vez)."""
        if self._routes is _NOT_LOADED:
            from datakit.sources import snv
            self._routes = snv.load_routes(self.raw_dir)
        return self._routes

    def official(self) -> Dict[str, SourceData]:
        """Carga nacional de cada fonte oficial (sem recorte)."""
        if self._official is None:
            self._official = {}
            for name, mod in self.sources.items():
                # as falhas por base que o módulo registra levam o nome dele (municipal → capitais)
                owns = (getattr(mod, "__name__", "").rsplit(".", 1)[-1],)
                codes = tuple(getattr(mod, "SOURCE_CODES", (name,)))
                try:
                    loaded = self._cached(name, lambda mod=mod: mod.fetch(self), SourceData(), owns=owns,
                                          cameras=codes)
                    print(f"[build] {name}: {len(loaded.cameras)} radares (nacional)")
                except NotImplementedError as e:
                    loaded = SourceData()
                    print(f"[build] {name}: pulado ({e})")
                self._official[name] = loaded
        return self._official

    def osm(self, region: str, probes=None):
        """(extrato, radares, limites, estruturas, sentidos das sondas) do OSM da região. Só a
        região atual fica em memória: as UFs saem agrupadas por região."""
        if self._osm_region != region:
            from datakit.sources import osm_pbf
            self._osm = None   # libera a região anterior antes de carregar a próxima
            ex = osm_pbf.ensure_extract(region, self.raw_dir, refresh=self.refresh_osm)
            print(f"[build] extrato {os.path.basename(ex.path)}  {ex.bytes/1e6:.1f} MB  ({ex.file_date})")
            probe_dirs: dict = {}
            self._osm_lines = []
            pieces: list = []
            cams, lims, structs = osm_pbf.load(ex.path, bbox=None, probes=probes, probe_out=probe_dirs,
                                               lines_out=pieces)
            print(f"[build] OSM/{region}: {len(cams)} radares, {len(lims)} limites, "
                  f"{len(structs)} pontes/túneis, {len(probe_dirs)} sentidos nominais resolvidos")
            self._osm_lines = limit_lines.join(pieces)
            print(f"[build] OSM/{region}: {len(pieces)} vias com limite viram {len(self._osm_lines)} trechos")
            self._osm_region, self._osm = region, (ex, cams, lims, structs, probe_dirs)
        return self._osm

    def osm_limit_lines(self, region: str) -> list:
        """Trechos de limite do OSM da região (`Piece`, já juntados), lidos na mesma passada que osm()."""
        self.osm(region)
        return self._osm_lines

    def osm_bumps(self, region: str) -> list:
        """Lombadas e quebra-molas do OSM da região (osm_pbf.load_bumps, uma passada a mais no extrato que osm()
        já baixou). Só a região atual fica em memória, como em osm()."""
        if self._bumps_region != region:
            from datakit.sources import osm_pbf
            self._bumps = []
            osm = self._osm if self._osm_region == region else None
            ex = osm[0] if osm is not None else osm_pbf.ensure_extract(region, self.raw_dir, refresh=False)
            self._bumps = osm_pbf.load_bumps(ex.path)
            self._bumps_region = region
            print(f"[build] OSM/{region}: {len(self._bumps)} lombadas e quebra-molas")
        return self._bumps

    def osm_hazards(self, region: str) -> list:
        """Pontos de atenção do OSM da região (osm_pbf.load_hazards), como osm_bumps."""
        if self._hazards_region != region:
            from datakit.sources import osm_pbf
            self._hazards = []
            osm = self._osm if self._osm_region == region else None
            ex = osm[0] if osm is not None else osm_pbf.ensure_extract(region, self.raw_dir, refresh=False)
            self._hazards = osm_pbf.load_hazards(ex.path)
            self._hazards_region = region
            print(f"[build] OSM/{region}: {len(self._hazards)} pontos de atenção")
        return self._hazards

    def osm_tolls(self, region: str) -> list:
        """Pedágios do OSM da região (osm_pbf.load_tolls), uma passada a mais no extrato que osm() já baixou."""
        if self._tolls_region != region:
            from datakit.sources import osm_pbf
            self._tolls = []
            osm = self._osm if self._osm_region == region else None
            ex = osm[0] if osm is not None else osm_pbf.ensure_extract(region, self.raw_dir, refresh=False)
            self._tolls = osm_pbf.load_tolls(ex.path)
            self._tolls_region = region
            print(f"[build] OSM/{region}: {len(self._tolls)} cabines e pórticos de pedágio")
        return self._tolls

    def enforcement_cameras(self) -> list:
        """As câmeras de fiscalização que não medem velocidade (CET de São Paulo, BHTrans, Setran de Curitiba), lidas uma
        vez por execução. Ficam FORA do SourceData.cameras: ali viram radar na mescla, contam como radar e vão para a
        cópia guardada da fonte. Cada fonte tem a sua cópia guardada (rótulo "<fonte> (outras câmeras)"); sem cópia, a
        falha vira aviso e o arquivo sai sem a fonte. Só as fontes ligadas no build (self.sources)."""
        if self._enforcement is None:
            from datakit.sources import bh, cet_sp, municipal
            self.official()   # as leituras que os radares já fizeram (a CET deixa a tabela em data/raw)
            active = list(self.sources.values())
            readers = ((cet_sp, "CET-SP (outras câmeras)", lambda: cet_sp.load_other_cameras(self.raw_dir)),
                       (bh, "BHTRANS (outras câmeras)", bh.load_other_cameras),
                       (municipal, "Curitiba (outras câmeras)", municipal.load_other_cameras))
            self._enforcement = []
            for mod, label, fn in readers:
                if mod in active:
                    self._enforcement += self._cached_extra(label, fn, [], owns=(mod.__name__.rsplit(".", 1)[-1],))
            print(f"[build] câmeras de fiscalização sem velocidade: {len(self._enforcement)} (nacional)")
        return self._enforcement

    def antt_tolls(self) -> list:
        """As praças de pedágio federais da ANTT, baixadas uma vez por execução; falha vira lista vazia, registrada."""
        if self._antt_tolls is None:
            from datakit.sources import antt_pedagio
            self._antt_tolls = self._cached("ANTT (pedágios)", antt_pedagio.load, [])
            print(f"[build] ANTT: {len(self._antt_tolls)} praças de pedágio")
        return self._antt_tolls

    def dnit_potholes(self) -> tuple:
        """(mês, km com buracos) do levantamento mais novo do ICM do DNIT, baixado uma vez por execução; falha vira
        ("", []), registrada."""
        if self._potholes is None:
            from datakit.sources import dnit_icm
            self._potholes = self._cached("DNIT (buracos, ICM)", dnit_icm.load, ("", []))
            print(f"[build] DNIT: {len(self._potholes[1])} km com buracos (ICM de {self._potholes[0] or '—'})")
        return self._potholes

    def sc_portable_radar(self, pbf: str) -> tuple:
        """(trechos, pontos de fora) do radar portátil de SC (sources/sc_portable_radar), com o extrato `pbf` da região
        sul; lidos uma vez por execução; falha vira ([], 0), registrada."""
        if self._sc_portable is None:
            from datakit.sources import sc_portable_radar
            self._sc_portable = self._cached("SIE-SC (radar portátil)", lambda: sc_portable_radar.zones(pbf), ([], 0))
            print(f"[build] SIE-SC: {len(self._sc_portable[0])} trechos de radar portátil "
                  f"({self._sc_portable[1]} pontos sem marcos do OSM em volta)")
        return self._sc_portable

    def prf_concessions(self) -> list:
        """Os equipamentos da planilha dos radares das concessões que a PRF mostra (sources/prf_concessions), lidos uma
        vez por execução; falha vira [], registrada (o Pardal segue com ANTT e DNIT)."""
        if self._prf_concessions is None:
            from datakit.sources import prf_concessions
            self._prf_concessions = self._cached("PRF (radares das concessões)", prf_concessions.load, [])
            print(f"[build] PRF: {len(self._prf_concessions)} equipamentos das concessões com coordenada")
        return self._prf_concessions

    def prf_moto_accidents(self) -> tuple:
        """((primeiro mês, último mês), trechos com muitos acidentes com moto no país) da PRF, lidos uma vez por
        execução; falha vira (("", ""), []), registrada."""
        if self._moto_accidents is None:
            from datakit import accident_spots
            from datakit.sources import prf_accidents

            def read() -> tuple:
                period, accidents = prf_accidents.load(self.raw_dir)
                return period, len(accidents), accident_spots.spots(accidents)

            period, n, spots = self._cached("PRF (acidentes com moto)", read, (("", ""), 0, []))
            self._moto_accidents = (period, spots)
            print(f"[build] PRF: {n} acidentes com moto de {period[0] or '—'} a {period[1] or '—'}, "
                  f"{len(spots)} trechos com {accident_spots.MIN_PER_KM} ou mais por km")
        return self._moto_accidents

    def prf_speed_fines(self) -> Optional[Mapping[Tuple[str, int, int], int]]:
        """Multas de velocidade da PRF por (UF, BR, km) nos 12 meses mais novos, lidas uma vez por execução; falha vira
        None, registrada (o radar_portatil.csv sai com a coluna vazia)."""
        if not self._prf_fines_read:
            from datakit.sources import prf_fines
            self._prf_fines_read = True
            loaded = self._cached("PRF (multas de velocidade)", lambda: prf_fines.load(self.raw_dir), None)
            if loaded is not None:
                (first, last), self._prf_fines = loaded
                print(f"[build] PRF: {sum(self._prf_fines.values())} multas de velocidade de {first} a {last}")
        return self._prf_fines

    def prf_portable_radar(self) -> tuple:
        """(início da validade, trechos) da lista vigente da PRF de trechos aptos ao radar portátil, baixada uma vez por
        execução; falha vira ("", []), registrada."""
        if self._prf_radar is None:
            from datakit.sources import prf_portable_radar
            valid_from, stretches, skipped = self._cached("PRF (trechos de radar portátil)",
                                                          prf_portable_radar.load, ("", [], 0))
            print(f"[build] PRF: {len(stretches)} trechos aptos ao radar portátil, lista de {valid_from or '—'} "
                  f"({skipped} linhas de fora)")
            self._prf_radar = (valid_from, stretches)
        return self._prf_radar

    def inmetro_points(self, uf: str) -> List[Camera]:
        """Locais do Inmetro só com endereço, localizados pelo cadastro do IBGE (inmetro_addresses.py),
        do arquivo do Inmetro que cobre a UF: o da própria UF, ou o de Goiás para o DF (os medidores
        de Brasília vêm nele). Um arquivo é geocodificado uma vez por execução."""
        file_uf = "GO" if uf == "DF" else uf
        if file_uf not in self._inmetro_points:
            from datakit import inmetro_addresses
            meters = [m for m in self.national()["meter_list"] if m.uf == file_uf]
            self._inmetro_points[file_uf] = _try(
                f"Inmetro {file_uf} (endereços)", lambda: inmetro_addresses.geocode(meters, file_uf, self.raw_dir), [])
        return self._inmetro_points[file_uf]

    def national(self) -> dict:
        """SNV (rotas + concessões), Inmetro e os limites oficiais. Cada base que falhar fica
        vazia — o pacote sai só sem aquela parte."""
        if self._national is None:
            from datakit import inmetro_status
            from datakit.common.lrs import load_concessions
            from datakit.sources import antt_placas, cet_sp, inmetro, rio, snv
            raw = self.raw_dir
            paths = _try("SNV", lambda: snv.ensure(raw), None)
            routes = self.snv_routes() if paths else None
            conc = _try("SNV concessões", lambda: load_concessions(paths[1]), {}) if paths else {}
            meters = _try("Inmetro", lambda: inmetro.load(raw), [])
            print(f"[build] Inmetro: {len(meters)} medidores; SNV {paths[2] if paths else '—'}")
            antt_l = self._cached("ANTT placas", lambda: antt_placas.load(raw, routes), [],
                                  limits=("ANTT",)) if routes else []
            rio_l = self._cached("Rio trechos", rio.load_limits, [], limits=("RIO",))
            cet_l = self._cached("CET-SP limites", cet_sp.load_limits, [], limits=("CET-SP",))
            print(f"[build] limites oficiais: ANTT {len(antt_l)}, Rio {len(rio_l)}, CET-SP {len(cet_l)} pontos")
            # os mesmos limites como trechos (limites_trechos.csv), com a geometria de cada fonte
            antt_t = self._cached_extra("ANTT placas (trechos)", lambda: antt_placas.load_lines(raw, routes),
                                        []) if routes else []
            rio_t = self._cached_extra("Rio trechos (linhas)", rio.load_limit_lines, [])
            cet_t = self._cached_extra("CET-SP limites (linhas)", cet_sp.load_limit_lines, [])
            print(f"[build] limites oficiais como trechos: ANTT {len(antt_t)}, Rio {len(rio_t)}, CET-SP {len(cet_t)}")
            self._national = dict(snv=routes, concessions=conc, snv_version=paths[2] if paths else None,
                                  meters=inmetro_status.index_meters(meters), n_meters=len(meters),
                                  meter_list=meters,
                                  official_limits={"ANTT": antt_l, "RIO": rio_l, "CET-SP": cet_l},
                                  official_lines={"ANTT": antt_t, "RIO": rio_t, "CET-SP": cet_t})
        return self._national
