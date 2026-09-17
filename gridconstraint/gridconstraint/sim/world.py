"""The simulated ISO world.

Hidden state (never shown to models): the nodal planning case with reactances, ratings,
dispatch, and the exact study procedure. Public state: substations/lines geometry with
voltages (HIFLD-like), generators (EIA-like), queue entries and status events, published
study reports (PDF), market LMPs / binding constraints / shadow prices, outages, zonal load.
Everything public carries a date so that point-in-time views can be reconstructed.
"""
from __future__ import annotations
import json
import math
import numpy as np
import pandas as pd
import networkx as nx
from dataclasses import dataclass, field
from .. import config as C
from ..data import loaders as L
from .network import DCNetwork
from .naming import assign_substation_names, line_fid, xfmr_fid, noisy_facility_name, to_xy_km
from .study import LODFCache, select_contingencies, run_study, effective_dfax
from .market import solve_opf, _set_global_net, _opf_task
from multiprocessing import get_context

# ---------------------------------------------------------------------------------
# calibration tables (documented in REPORT.md)
ARRIVALS = {2011: 90, 2012: 100, 2013: 110, 2014: 120, 2015: 140, 2016: 160, 2017: 190, 2018: 220,
            2019: 240, 2020: 270, 2021: 330, 2022: 300, 2023: 100, 2024: 120, 2025: 150}
TYPE_MIX = {  # (project_type, fuel): share, by era
    2011: {("gen", "gas"): .32, ("gen", "wind"): .25, ("gen", "solar"): .25, ("gen", "other"): .08, ("battery", "storage"): .02, ("load", "load"): .08},
    2015: {("gen", "gas"): .20, ("gen", "wind"): .15, ("gen", "solar"): .48, ("gen", "other"): .04, ("battery", "storage"): .08, ("load", "load"): .05},
    2019: {("gen", "gas"): .07, ("gen", "wind"): .08, ("gen", "solar"): .52, ("gen", "hybrid"): .06, ("battery", "storage"): .22, ("load", "load"): .05},
    2022: {("gen", "gas"): .08, ("gen", "wind"): .04, ("gen", "solar"): .38, ("gen", "hybrid"): .10, ("battery", "storage"): .28, ("load", "load"): .12},
}
MW_LOGNORMAL = {"gas": (400, 0.9, 1500), "wind": (180, 0.5, 600), "solar": (120, 0.6, 700), "other": (60, 1.0, 500),
                "hybrid": (150, 0.5, 500), "storage": (100, 0.7, 500), "load": (150, 0.8, 1200)}
LINE_COST_PER_MILE = {500: 4.0e6, 345: 2.6e6, 230: 1.7e6, 161: 1.2e6, 138: 1.0e6, 115: 0.9e6, 100: 0.8e6, 69: 0.6e6}
XFMR_COST = {500: 30e6, 345: 16e6, 230: 9e6, 161: 6e6, 138: 5e6, 115: 4e6, 100: 3.5e6, 69: 2.5e6}
ZONE_SHAPE = {7: "PJME", 8: "PJME", 9: "PJME", 10: "PJME", 12: "PJME", 13: "PJME", 14: "PJME", 15: "PJME", 16: "PJME",
              11: "PJMW", 26: "PJMW", 27: "PJMW", 28: "PJMW", 29: "PJMW", 30: "PJMW", 32: "PJMW", 33: "PJMW",
              34: "COMED", 35: "COMED", 36: "COMED", 39: "COMED"}
FUEL_COST = {"ng": None, "coal": None, "nuclear": 8.0, "hydro": 2.0, "solar": 0.0, "wind": 0.0, "dfo": None, "other": 45.0,
             "storage": 28.0, "hybrid": 0.0, "gas": 34.0}


def kv_class(kv: float) -> int:
    return min(LINE_COST_PER_MILE, key=lambda k: abs(k - kv))


def kv_class_poi(kv: float) -> int:
    return min((69, 100, 115, 138, 161, 230, 345, 500, 765), key=lambda k: abs(k - kv))


@dataclass
class Project:
    pid: str
    queue_date: pd.Timestamp
    poi_sub: int
    poi_bus: int
    poi_kv: float
    ptype: str
    fuel: str
    mw: float
    state: str
    zone_id: int
    study_date: pd.Timestamp | None = None
    status: str = "active"           # active | withdrawn | in_service
    withdrawn_date: pd.Timestamp | None = None
    in_service_date: pd.Timestamp | None = None
    events: list = field(default_factory=list)
    study: dict | None = None
    source: str = "synthetic"


class World:
    def __init__(self, seed: int = C.SEED, start_year: int = C.SIM_START_YEAR, end_year: int = C.SIM_END_YEAR,
                 arrival_scale: float = 1.0, market_hours_per_year: int = 12, verbose: bool = True, n_workers: int = 4,
                 harden_every: int = 1):
        self.rng = np.random.default_rng(seed)
        self.n_workers = n_workers
        self.harden_every = harden_every      # 1 = baseline reliability pass every year (headroom re-randomised yearly);
                                              # k = only every k years (facility headroom persists, as in a real grid)
        self.start_year, self.end_year = start_year, end_year
        self.arrival_scale = arrival_scale
        self.market_hours_per_year = market_hours_per_year
        self.verbose = verbose
        self._build_case()
        self._build_public_graph()
        self.projects: list[Project] = []
        self.studies: list[dict] = []
        self.market_rows: list = []
        self.lmp_rows: list = []
        self.outage_rows: list = []
        self.load_rows: list = []
        self.upgrade_log: list = []
        self.rating_history: list = []

    # ------------------------------------------------------------------ case
    def _log(self, *a):
        if self.verbose:
            print(*a, flush=True)

    def _build_case(self):
        bus, br, pl = L.load_bus(), L.load_branch(), L.load_plant()
        self.bus, self.branch = bus, br
        self.net = DCNetwork(bus, br)
        net = self.net
        zone = L.load_zone().set_index("zone_id")
        self.zone_state = zone.state.to_dict()
        # substations
        subs = bus.groupby("sub_id").agg(lat=("lat", "first"), lon=("lon", "first"), zone_id=("zone_id", "first"),
                                         max_kv=("baseKV", "max"), min_kv=("baseKV", "min"), external=("external", "max"),
                                         load_mw=("Pd", lambda s: s[s > 0].sum())).reset_index()
        subs["state"] = subs.zone_id.map(self.zone_state)
        subs = assign_substation_names(subs, L.load_hifld_substations(), self.rng)
        self.subs = subs.set_index("sub_id")
        self.sub_names = self.subs.name.to_dict()
        self.bus_sub = bus.sub_id.values
        self.bus_ext = bus.external.values.astype(bool)
        # facilities (branch -> canonical public facility id)
        sub_f = self.bus_sub[net.f]; sub_t = self.bus_sub[net.t]
        fids, kinds = [], []
        for i in range(net.m):
            if net.is_xfmr[i]:
                fids.append(xfmr_fid(sub_f[i], max(net.kv_from[i], net.kv_to[i]), min(net.kv_from[i], net.kv_to[i]))); kinds.append("X")
            elif sub_f[i] == sub_t[i]:
                fids.append(f"B:{int(sub_f[i])}:{int(round(net.kvmax[i]))}"); kinds.append("B")
            else:
                fids.append(line_fid(sub_f[i], sub_t[i], net.kvmax[i])); kinds.append("L")
        fac = pd.DataFrame(dict(branch=np.arange(net.m), fid=fids, kind=kinds, sub_a=sub_f, sub_b=sub_t,
                                kv=net.kvmax, rate=net.rate, touches_external=self.bus_ext[net.f] | self.bus_ext[net.t]))
        xy_f = to_xy_km(bus.lat.values[net.f], bus.lon.values[net.f]); xy_t = to_xy_km(bus.lat.values[net.t], bus.lon.values[net.t])
        fac["length_km"] = np.hypot(*(xy_f - xy_t).T) * 1.2
        fac["circuit"] = fac.groupby("fid").cumcount() + 1
        self.fac = fac
        self.monitored = ((net.rate > 0) & (net.kvmax >= C.MONITORED_MIN_KV) & ~fac.touches_external.values)
        # non-radial (bridge) test for contingency eligibility
        G = nx.Graph()
        mult = {}
        for i in range(net.m):
            e = (min(net.f[i], net.t[i]), max(net.f[i], net.t[i]))
            mult[e] = mult.get(e, 0) + 1
        G.add_edges_from(mult.keys())
        bridges = set(nx.bridges(G))
        is_bridge = np.array([((min(net.f[i], net.t[i]), max(net.f[i], net.t[i])) in bridges) and
                              mult[(min(net.f[i], net.t[i]), max(net.f[i], net.t[i]))] == 1 for i in range(net.m)])
        self.eligible_cont = self.monitored & ~is_bridge & (net.kvmax >= C.CONTINGENCY_MIN_KV)
        self.rate = net.rate.copy()
        self.rate0 = net.rate.copy()
        # plants
        pl = pl[pl.status == 1].reset_index(drop=True)
        pl["bus_idx"] = pl.bus_id.map(net.bus_idx)
        pl["sub_id"] = self.bus_sub[pl.bus_idx.values]
        cost = pl.c1.values + 0.5 * pl.c2.values * pl.Pmax.values
        pl["mcost"] = [FUEL_COST[t] if FUEL_COST.get(t) is not None else c for t, c in zip(pl.type, cost)]
        pl["online_year"] = self.rng.integers(1960, 2011, len(pl))
        pl["retire_year"] = np.nan
        pl["pid"] = ""
        self.plants = pl
        self.Pd0 = bus.Pd.values.astype(float)
        self.lodf = LODFCache(net, np.where(self.monitored)[0])
        self.hops_cache: dict = {}
        self.ptdf_store: dict[str, np.ndarray] = {}
        self._log(f"case: {net.n} buses, {net.m} branches, monitored {self.monitored.sum()}, contingency-eligible {self.eligible_cont.sum()}, plants {len(pl)}")

    def _build_public_graph(self):
        """What a HIFLD-like public layer would show: corridors (collapsed circuits) with kV and length."""
        f = self.fac[~self.fac.touches_external]
        pub = f.groupby("fid").agg(kind=("kind", "first"), sub_a=("sub_a", "first"), sub_b=("sub_b", "first"),
                                   kv=("kv", "max"), length_km=("length_km", "mean"), n_circuits=("branch", "size")).reset_index()
        # HIFLD is incomplete: hide 3% of line corridors from the public layer (still monitored by the ISO)
        hide = (pub.kind == "L") & (self.rng.random(len(pub)) < 0.03)
        pub["public_visible"] = ~hide
        self.public_fac = pub.set_index("fid")
        self.fid_to_branches = self.fac.groupby("fid").branch.apply(list).to_dict()

    # ------------------------------------------------------------------ queue generation
    def _era_mix(self, year):
        keys = sorted(TYPE_MIX)
        k = max([y for y in keys if y <= year] or [keys[0]])
        return TYPE_MIX[k]

    def build_queue(self):
        rng = self.rng
        subs = self.subs[(~self.subs.external.astype(bool)) & (self.subs.max_kv >= 69)].copy()
        subs["attract"] = rng.normal(0, 0.8, len(subs))          # persistent site attractiveness (land, resource, TO)
        tc2 = L.load_pjm_tc2_projects()
        tc2 = tc2[tc2.ProjectType.str.contains("Generation", na=False) & tc2.MW_Energy.notna()]
        state_w = tc2.State.value_counts(normalize=True)
        st_map = {"IL": "Illinois", "KY": "Kentucky", "PA": "Pennsylvania", "OH": "Ohio", "VA": "Virginia", "NJ": "New Jersey",
                  "MD": "Maryland", "WV": "West Virginia", "IN": "Indiana", "NC": "North Carolina", "DE": "Delaware",
                  "MI": "Michigan", "TN": "Tennessee", "DC": "Maryland", "WI": "Wisconsin", "IA": "Iowa"}
        sub_states = subs.state.value_counts()
        state_p = {st_map.get(k, k): v for k, v in state_w.items() if st_map.get(k, k) in sub_states.index}
        # blend with substation-count prior so every state gets some projects
        pri = (sub_states / sub_states.sum()).to_dict()
        states = sorted(set(state_p) | set(pri))
        sp_ = np.array([0.7 * state_p.get(s, 0) + 0.3 * pri.get(s, 0) for s in states]); sp_ /= sp_.sum()
        queue_mw_at_sub: dict[int, float] = {}
        pid_counter = 0
        tc2_pool = tc2.sample(frac=1.0, random_state=int(rng.integers(1e9))).reset_index(drop=True)
        tc2_i = 0
        fuel_map = {"Solar": "solar", "Storage": "storage", "Natural Gas": "gas", "Wind": "wind", "Offshore Wind": "wind",
                    "Solar; Storage": "hybrid", "Nuclear": "other", "Hydro": "other", "Methane": "other", "Other": "other",
                    "Wind; Storage": "hybrid", "Solar; Wind": "hybrid"}
        for year in range(self.start_year, self.end_year + 1):
            n_arr = int(round(ARRIVALS[year] * self.arrival_scale))
            mix = self._era_mix(year)
            keys = list(mix); probs = np.array([mix[k] for k in keys]); probs /= probs.sum()
            days = np.sort(rng.integers(0, 365, n_arr))
            for d in days:
                qd = pd.Timestamp(year=year, month=1, day=1) + pd.Timedelta(days=int(d))
                source = "synthetic"
                if year >= 2024 and tc2_i < len(tc2_pool) and rng.random() < 0.8:
                    row = tc2_pool.iloc[tc2_i]; tc2_i += 1
                    fuel = fuel_map.get(str(row.FuelPrimary), "other")
                    ptype = "battery" if fuel == "storage" else "gen"
                    mw = float(max(5.0, row.MW_Energy))
                    state = st_map.get(row.State, row.State)
                    if state not in states:
                        state = states[rng.choice(len(states), p=sp_)]
                    source = f"pjm_tc2:{row.ProjectID}"
                else:
                    ptype, fuel = keys[rng.choice(len(keys), p=probs)]
                    med, sig, cap = MW_LOGNORMAL[fuel]
                    mw = float(np.clip(np.exp(np.log(med) + sig * rng.normal()), 5.0, cap))
                    mw = float(round(mw, 1))
                    state = states[rng.choice(len(states), p=sp_)]
                cand = subs[subs.state == state]
                if len(cand) == 0:
                    cand = subs
                w = cand.attract.values.copy()
                w += 0.9 * (cand.max_kv.values >= 230) + 0.4 * (cand.max_kv.values >= 138)
                w += 0.5 * np.log1p(np.array([queue_mw_at_sub.get(s, 0.0) for s in cand.index]) / 100.0)   # herding
                if fuel in ("solar", "wind", "hybrid"):
                    w -= 0.5 * np.log1p(cand.load_mw.values / 50.0)
                elif ptype in ("battery", "load"):
                    w += 0.4 * np.log1p(cand.load_mw.values / 50.0)
                if mw > 300:
                    w += 1.0 * (cand.max_kv.values >= 345) - 1.5 * (cand.max_kv.values < 138)
                p = np.exp(w - w.max()); p /= p.sum()
                sub_id = int(cand.index[rng.choice(len(cand), p=p)])
                # POI voltage & bus
                sb = self.bus[(self.bus.sub_id == sub_id) & (self.bus.baseKV >= 69)]
                kvs = np.sort(sb.baseKV.unique())
                typical = np.array([{69: 20, 100: 60, 115: 80, 138: 90, 161: 150, 230: 260, 345: 550, 500: 900, 765: 1200}[kv_class_poi(k)] for k in kvs])
                lw = -((np.log(mw) - np.log(typical)) ** 2) / (2 * 0.8 ** 2)
                pk = np.exp(lw - lw.max()); pk /= pk.sum()
                kv = kvs[rng.choice(len(kvs), p=pk)]
                bus_row = sb[sb.baseKV == kv].iloc[0]
                pid_counter += 1
                pid = f"Q{year % 100:02d}-{pid_counter:04d}"
                lag = rng.uniform(*C.STUDY_LAG_MONTHS)
                pr = Project(pid=pid, queue_date=qd, poi_sub=sub_id, poi_bus=int(self.net.bus_idx[int(bus_row.bus_id)]), poi_kv=float(kv),
                             ptype=ptype, fuel=fuel, mw=mw, state=state, zone_id=int(bus_row.zone_id),
                             study_date=qd + pd.DateOffset(days=int(lag * 30.4)), source=source)
                pr.events.append((qd, "queued"))
                # some projects withdraw before any study is published
                if rng.random() < 0.12:
                    wd = qd + pd.Timedelta(days=int(rng.uniform(90, max(120, (pr.study_date - qd).days))))
                    pr.status = "withdrawn"; pr.withdrawn_date = wd; pr.study_date = None
                    pr.events.append((wd, "withdrawn"))
                queue_mw_at_sub[sub_id] = queue_mw_at_sub.get(sub_id, 0.0) + mw
                self.projects.append(pr)
        self.projects.sort(key=lambda p: p.queue_date)
        self._log(f"queue: {len(self.projects)} projects {self.start_year}-{self.end_year}; "
                  f"{sum(p.source != 'synthetic' for p in self.projects)} carry real PJM TC2 characteristics")

    # ------------------------------------------------------------------ load & fleet evolution
    def zone_growth(self, year: int, zone_id: int) -> float:
        g = 1.0 + 0.003 * (year - 2016)
        if year > 2020:
            g *= (1.02 ** (year - 2020))
            if zone_id in (14, 15):          # Virginia data-centre growth
                g *= (1.05 ** (year - 2020))
            if zone_id in (13, 29, 30, 34):  # MD / OH / ComEd
                g *= (1.015 ** (year - 2020))
        return g

    def load_vector(self, year: int, shape: float = 1.0) -> np.ndarray:
        Pd = self.Pd0.copy()
        zid = self.bus.zone_id.values
        g = np.array([self.zone_growth(year, int(z)) for z in zid])
        internal = ~self.bus_ext & (Pd > 0)
        Pd[internal] = Pd[internal] * g[internal] * shape
        # in-service large loads
        for p in self.projects:
            if p.ptype == "load" and p.status == "in_service" and p.in_service_date.year <= year:
                Pd[p.poi_bus] += p.mw * (0.9 if shape >= 0.9 else 0.6)
        return Pd

    def apply_retirements(self, year: int):
        pl = self.plants
        rng = self.rng
        cand = pl[(pl.type.isin(["coal", "dfo"])) & pl.retire_year.isna() & (pl.pid == "")]
        n_ret = int(round(0.045 * len(cand)))
        if n_ret > 0 and len(cand):
            idx = rng.choice(cand.index, size=n_ret, replace=False)
            pl.loc[idx, "retire_year"] = year

    def fleet(self, year: int):
        pl = self.plants
        act = pl[pl.retire_year.isna() | (pl.retire_year > year)]
        return act

    # ------------------------------------------------------------------ market snapshots
    def _load_shapes(self):
        z = L.load_pjm_zonal_load()
        shapes = {}
        for col in ("PJME", "PJMW", "COMED"):
            s = z[col].dropna()
            s = s[s.index.year >= 2012]
            shapes[col] = s / s.groupby(s.index.year).transform("max")
        self._shape_df = pd.DataFrame(shapes).dropna()
        return self._shape_df

    def market_year(self, year: int):
        """Run representative-hour OPFs; record LMPs, binding constraints, outages. Returns summer-peak dispatch."""
        if not hasattr(self, "_shape_df"):
            self._load_shapes()
        rng = self.rng
        sdf = self._shape_df
        ref_year = year if year in sdf.index.year else 2016
        sy = sdf[sdf.index.year == ref_year]
        # monthly peak hours (by PJME shape) -> 12 snapshots; ensure the July/Aug peak is included
        hours = sy.groupby(sy.index.month).PJME.idxmax().tolist()
        if self.market_hours_per_year < 12:
            hours = [h for h in hours if h.month in (1, 4, 7, 8, 10, 12)][:self.market_hours_per_year]
        peak_hour = sy.PJME.idxmax()
        if peak_hour not in hours:
            hours.append(peak_hour)
        fleet = self.fleet(year)
        gb = fleet.bus_idx.values.astype(int)
        base_pmax = fleet.Pmax.values.astype(float)
        cost = fleet.mcost.values.astype(float)
        mon = self.monitored
        dispatch = None
        zid = self.bus.zone_id.values
        internal = ~self.bus_ext & (self.Pd0 > 0)
        tasks, meta = [], []
        for h in hours:
            shape_by_zone = {z: float(sy.loc[h, ZONE_SHAPE.get(z, "PJME")]) for z in np.unique(zid)}
            shp = np.array([shape_by_zone[int(z)] for z in zid])
            Pd = self.Pd0.copy()
            g = np.array([self.zone_growth(year, int(z)) for z in zid])
            Pd[internal] = Pd[internal] * g[internal] * shp[internal]
            ts = pd.Timestamp(h.replace(tzinfo=None))
            for p in self.projects:
                if p.ptype == "load" and p.status == "in_service" and p.in_service_date <= ts:
                    Pd[p.poi_bus] += p.mw * 0.85
            # renewable availability
            pmax = base_pmax.copy()
            hr = h.hour; is_solar = fleet.type.values == "solar"; is_wind = fleet.type.values == "wind"; is_hydro = fleet.type.values == "hydro"
            solar_cf = max(0.0, math.sin(math.pi * (hr - 6) / 13)) * (0.75 if h.month in (5, 6, 7, 8) else 0.55) if 6 <= hr <= 19 else 0.0
            pmax[is_solar] *= solar_cf * rng.uniform(0.7, 1.0)
            pmax[is_wind] *= np.clip(rng.normal(0.35 if h.month in (11, 12, 1, 2, 3) else 0.22, 0.12, is_wind.sum()), 0.02, 0.9)
            pmax[is_hydro] *= 0.55
            # outages (0.2-0.6 % of eligible >=200 kV-or-local lines), recorded publicly
            elig = np.where(self.eligible_cont & ~self.net.is_xfmr)[0]
            n_out = int(len(elig) * rng.uniform(0.002, 0.006))
            outs = rng.choice(elig, size=n_out, replace=False)
            out_mask = np.zeros(self.net.m, bool); out_mask[outs] = True
            for k in outs:
                start = ts - pd.Timedelta(days=int(rng.integers(0, 10)))
                self.outage_rows.append(dict(branch=int(k), fid=self.fac.fid.values[k], start=start,
                                             end=start + pd.Timedelta(days=int(rng.integers(1, 21))), reason="planned"))
            tasks.append((Pd, gb, pmax, cost, self.rate.copy(), mon, out_mask)); meta.append((h, ts, Pd))
        _set_global_net(self.net)
        with get_context("fork").Pool(self.n_workers) as pool:
            results = pool.map(_opf_task, tasks)
        for (h, ts, Pd), res in zip(meta, results):
            if res["status"] != 0:
                self._log("  OPF failed", h, res.get("message"))
                if h == peak_hour:   # retry without outages
                    res = solve_opf(self.net, Pd, gb, tasks[meta.index((h, ts, Pd))][2], cost, self.rate, mon)
                    if res["status"] != 0:
                        raise RuntimeError("peak OPF infeasible")
                else:
                    continue
            lmp = res["lmp"]; sysavg = float(np.average(lmp[internal], weights=Pd[internal]))
            sub_lmp = pd.DataFrame(dict(sub_id=self.bus_sub, lmp=lmp)).groupby("sub_id").lmp.mean()
            self.lmp_rows.append(pd.DataFrame(dict(datetime=ts, sub_id=sub_lmp.index.values, lmp=sub_lmp.values.round(2),
                                                   congestion=(sub_lmp.values - sysavg).round(2))))
            sh = res["shadow"]
            for k in np.where(sh > 0.5)[0]:
                self.market_rows.append(dict(datetime=ts, branch=int(k), fid=self.fac.fid.values[k], shadow_price=round(float(sh[k]), 2),
                                             flow_mw=round(float(abs(res["flow"][k])), 1)))
            if h == peak_hour:
                dispatch = np.zeros(self.net.n); np.add.at(dispatch, gb, res["pg"])
                dispatch -= res["shed"]
                self._peak_Pd = Pd.copy()
        # zonal load publication
        for z in np.unique(zid):
            mask = (zid == z) & internal
            self.load_rows.append(dict(year=year, zone_id=int(z), peak_mw=float(self._peak_Pd[mask].sum())))
        if dispatch is None:
            raise RuntimeError("no peak dispatch")
        return dispatch

    # ------------------------------------------------------------------ studies
    def _withdraw_vec(self, dispatch: np.ndarray) -> np.ndarray:
        w = np.clip(dispatch, 0, None); w = w * (~self.bus_ext)
        return w / w.sum()

    def project_ptdf(self, p: Project, w: np.ndarray) -> np.ndarray:
        if p.pid not in self.ptdf_store:
            self.ptdf_store[p.pid] = self.net.project_ptdf(p.poi_bus, w).astype(np.float32)
        return self.ptdf_store[p.pid]

    def queue_ahead(self, p: Project, date: pd.Timestamp) -> list[Project]:
        out = []
        for q in self.projects:
            if q.queue_date >= p.queue_date:
                break
            if q.status == "withdrawn" and q.withdrawn_date is not None and q.withdrawn_date <= date:
                continue
            if q.status == "in_service" and q.in_service_date is not None and q.in_service_date <= date:
                continue   # already in the base case as a plant / load
            out.append(q)
        return out

    def base_flow(self, dispatch: np.ndarray, Pd: np.ndarray, ahead: list[Project], w: np.ndarray) -> np.ndarray:
        inj = dispatch - Pd
        inj -= inj.sum() * w             # balance mismatch via the dispatch distribution
        tot = 0.0
        for q in ahead:
            s = -1.0 if q.ptype == "load" else 1.0
            inj[q.poi_bus] += s * q.mw; tot += s * q.mw
        inj -= tot * w
        return self.net.flows(inj)

    def upgrade_cost(self, branch: int, loading: float, rng) -> tuple[str, float]:
        f = self.fac.iloc[branch]
        kvc = kv_class(f.kv)
        if f.kind == "X":
            return "replace transformer", XFMR_COST[kvc] * np.exp(rng.normal(0, 0.25))
        if f.kind == "B":
            return "upgrade bus/terminal equipment", 1.5e6 * (1 + kvc / 200) * np.exp(rng.normal(0, 0.3))
        miles = max(0.5, f.length_km / 1.609)
        if loading <= 1.10:
            return "reconductor", 0.35 * LINE_COST_PER_MILE[kvc] * miles * np.exp(rng.normal(0, 0.25))
        return "rebuild", LINE_COST_PER_MILE[kvc] * miles * np.exp(rng.normal(0, 0.25))

    def study_project(self, p: Project, date: pd.Timestamp, dispatch: np.ndarray, Pd: np.ndarray, w: np.ndarray):
        rng = self.rng
        ahead = self.queue_ahead(p, date)
        bf = self.base_flow(dispatch, Pd, ahead, w)
        ptdf = self.project_ptdf(p, w).astype(float)
        # PJM practice: upgrades already assigned to earlier-queued (still active) projects are
        # assumed in service for this study, even though physically unbuilt.
        rate_plan = self.rate.copy()
        for q in ahead:
            if q.study:
                for r in q.study["rows"]:
                    b = r["branch"]
                    rate_plan[b] = max(rate_plan[b], 1.15 * r["flow_post"])
        dirs = [1.0] if p.ptype == "gen" else ([-1.0] if p.ptype == "load" else [1.0, -1.0])
        found: dict[int, dict] = {}
        for s in dirs:
            cont = select_contingencies(self.net, ptdf * s, p.poi_bus, self.eligible_cont, self.hops_cache)
            res = run_study(self.net, rate_plan, bf, ptdf, s * p.mw, self.monitored, cont, self.lodf)
            for r in res:
                r["direction"] = "injection" if s > 0 else "withdrawal"
                if r["branch"] not in found or r["loading_post"] > found[r["branch"]]["loading_post"]:
                    found[r["branch"]] = r
        rows = []
        near = [q for q in ahead if abs(self.subs.lat[q.poi_sub] - self.subs.lat[p.poi_sub]) < 1.5
                and abs(self.subs.lon[q.poi_sub] - self.subs.lon[p.poi_sub]) < 2.0]
        for r in sorted(found.values(), key=lambda d: -d["loading_post"]):
            b = r["branch"]
            utype, cost = self.upgrade_cost(b, r["loading_post"], rng)
            # cost sharing with contributing queue-ahead projects (>= 5 % DFAX, aggravating)
            own = r["contrib_mw"]; tot = own
            contributors = []
            for q in near:
                dq = effective_dfax(self.ptdf_store[q.pid].astype(float), b, r["cont"], self.lodf) if q.pid in self.ptdf_store else 0.0
                sq = -1.0 if q.ptype == "load" else 1.0
                if abs(dq) >= C.DFAX_THRESHOLD:
                    c = abs(dq * q.mw * sq)
                    tot += c; contributors.append(q.pid)
            share = own / tot if tot > 0 else 1.0
            fid = self.fac.fid.values[b]
            rows.append(dict(project_id=p.pid, branch=b, fid=fid, circuit=int(self.fac.circuit.values[b]),
                             cont_branch=r["cont"], cont_fid=(self.fac.fid.values[r["cont"]] if r["cont"] >= 0 else ""),
                             cont_circuit=(int(self.fac.circuit.values[r["cont"]]) if r["cont"] >= 0 else 0),
                             direction=r["direction"], loading_post=round(r["loading_post"] * 100, 1), loading_pre=round(r["loading_pre"] * 100, 1),
                             dfax=round(r["dfax"] * 100, 1), contrib_mw=round(r["contrib_mw"], 1), rating_mva=round(r["rating"], 0),
                             flow_post=round(r["flow_post"], 1), upgrade=utype, cost_total=round(cost, -3), cost_share=round(share, 3),
                             cost_alloc=round(cost * share, -3), contributors=";".join(contributors)))
        total = sum(r["cost_alloc"] for r in rows)
        study = dict(project_id=p.pid, study_date=date, n_facilities=len(rows), cost_alloc_total=total,
                     cost_per_kw=total / (p.mw * 1000.0), rows=rows, n_queue_ahead=len(ahead))
        p.study = study
        self.studies.append(study)
        # fate
        cpk = study["cost_per_kw"]
        z = -0.6 + 1.1 * (np.log10(cpk + 1.0) - 2.0) + {"battery": 0.5, "load": -0.6, "gen": 0.0}[p.ptype]
        z += {"solar": 0.3, "gas": -0.4}.get(p.fuel, 0.0)
        pw = 1 / (1 + np.exp(-z))
        if rng.random() < pw:
            wd = date + pd.Timedelta(days=int(rng.uniform(30, 540)))
            p.status = "withdrawn"; p.withdrawn_date = wd; p.events.append((wd, "withdrawn"))
        else:
            isd = date + pd.Timedelta(days=int(rng.uniform(540, 1460)))
            p.in_service_date = isd; p.events.append((isd, "in_service"))
            p.status = "pending_in_service"

    def commission(self, p: Project, date: pd.Timestamp):
        """Project enters service: add plant/load; build its network upgrades (ratings rise)."""
        p.status = "in_service"
        if p.ptype != "load":
            fuel = {"gas": "gas", "solar": "solar", "wind": "wind", "hybrid": "hybrid", "storage": "storage", "other": "other"}[p.fuel]
            row = dict(plant_id=900000 + len(self.plants), bus_id=int(self.bus.bus_id.values[p.poi_bus]), Pg=0.0, status=1,
                       Pmax=p.mw, Pmin=0.0, type=fuel, GenFuelCost=0.0, c2=0.0, c1=FUEL_COST.get(fuel, 30.0) or 30.0, c0=0.0,
                       bus_idx=p.poi_bus, sub_id=p.poi_sub, mcost=FUEL_COST.get(fuel, 30.0) if FUEL_COST.get(fuel) is not None else 34.0,
                       online_year=date.year, retire_year=np.nan, pid=p.pid)
            self.plants = pd.concat([self.plants, pd.DataFrame([row])], ignore_index=True)
        if p.study:
            for r in p.study["rows"]:
                b = r["branch"]
                new = max(self.rate[b], 1.15 * r["flow_post"])
                if new > self.rate[b] + 1:
                    self.upgrade_log.append(dict(date=date, project_id=p.pid, branch=b, fid=r["fid"], old_rating=self.rate[b], new_rating=new))
                    self.rate[b] = new

    # ------------------------------------------------------------------ baseline reliability (RTEP-like)
    def harden_n1(self, year: int, dispatch: np.ndarray, Pd: np.ndarray, w: np.ndarray, chunk: int = 400):
        """Yearly baseline reliability pass (RTEP-like): raise ratings of facilities that would be
        overloaded under any eligible single contingency in the *pre-queue* planning case, with a
        random headroom margin (2-30 %) as real upgrades do not size exactly to the violation.
        Published as baseline upgrades."""
        bf = self.base_flow(dispatch, Pd, [], w)
        Mi = self.lodf.M
        worst = np.abs(bf[Mi])
        conts = np.where(self.eligible_cont)[0]
        for i in range(0, len(conts), chunk):
            L, ks = self.lodf.stack(conts[i:i + chunk], cache=False)
            if len(ks) == 0:
                continue
            Fpost = np.abs(bf[Mi][:, None] + L * bf[ks][None, :])
            worst = np.maximum(worst, Fpost.max(axis=1))
        margin = np.clip(1.0 + np.abs(self.rng.normal(0.08, 0.07, len(Mi))), 1.02, 1.30)
        new = np.maximum(self.rate[Mi], margin * worst)
        changed = np.where(new > self.rate[Mi] + 1)[0]
        for j in changed:
            b = int(Mi[j])
            self.upgrade_log.append(dict(date=pd.Timestamp(year=year, month=1, day=1), project_id="BASELINE", branch=b,
                                         fid=self.fac.fid.values[b], old_rating=self.rate[b], new_rating=new[j]))
        self.rate[Mi] = new
        return len(changed)

    # ------------------------------------------------------------------ main loop
    def run(self):
        if not self.projects:
            self.build_queue()
        for year in range(self.start_year, self.end_year + 1):
            self.apply_retirements(year)
            self._log(f"== {year}: market snapshots ...")
            dispatch = self.market_year(year)
            Pd = self._peak_Pd
            w = self._withdraw_vec(dispatch)
            if (year - self.start_year) % self.harden_every == 0:
                nb = self.harden_n1(year, dispatch, Pd, w)
            else:
                nb = 0
            self.rate0 = self.rate.copy() if year == self.start_year else self.rate0
            self._log(f"   baseline (N-1) upgrades: {nb}")
            n_stud = 0
            for month in range(1, 13):
                date = pd.Timestamp(year=year, month=month, day=15)
                # fate events
                for p in self.projects:
                    if p.status == "pending_in_service" and p.in_service_date <= date:
                        self.commission(p, date)
                due = [p for p in self.projects if p.study_date is not None and p.study is None and p.status == "active"
                       and p.study_date.year == year and p.study_date.month == month]
                for p in due:
                    self.study_project(p, date, dispatch, Pd, w); n_stud += 1
            self.rating_history.append(dict(year=year, n_upgraded=int((self.rate > self.rate0 + 1).sum())))
            self._log(f"   {year}: {n_stud} studies, cumulative upgrades {self.rating_history[-1]['n_upgraded']}, "
                      f"withdrawn {sum(p.status=='withdrawn' for p in self.projects)}, in-service {sum(p.status=='in_service' for p in self.projects)}")

    # ------------------------------------------------------------------ export
    def export(self):
        W, P = C.WORLD, C.PUBLIC
        subs = self.subs.reset_index()
        subs.to_csv(W / "substations.csv", index=False)
        pub_subs = subs[~subs.external.astype(bool)][["sub_id", "name", "lat", "lon", "state", "zone_id", "max_kv", "min_kv"]]
        pub_subs.to_csv(P / "substations.csv", index=False)
        self.fac.to_csv(W / "branches.csv", index=False)
        pf = self.public_fac.reset_index()
        pf[pf.public_visible].drop(columns=["public_visible", "n_circuits"]).to_csv(P / "facilities.csv", index=False)
        pf.to_csv(W / "facilities_all.csv", index=False)
        # projects & events
        rows, ev = [], []
        for p in self.projects:
            rows.append(dict(project_id=p.pid, queue_date=p.queue_date.date(), poi_sub_id=p.poi_sub, poi_kv=p.poi_kv,
                             poi_name=f"{self.sub_names[p.poi_sub]} {int(p.poi_kv)} kV", project_type=p.ptype, fuel=p.fuel, mw=p.mw,
                             state=p.state, zone_id=p.zone_id, source=p.source))
            for d, e in p.events:
                ev.append(dict(project_id=p.pid, date=d.date(), status=e))
        pd.DataFrame(rows).to_csv(P / "queue.csv", index=False)
        pd.DataFrame(ev).sort_values(["date", "project_id"]).to_csv(P / "queue_events.csv", index=False)
        # hidden truth: study rows + summary
        srows, ssum = [], []
        for s in self.studies:
            ssum.append({k: v for k, v in s.items() if k != "rows"})
            srows.extend(s["rows"])
        pd.DataFrame(srows).to_csv(W / "study_rows.csv", index=False)
        pd.DataFrame(ssum).to_csv(W / "study_summary.csv", index=False)
        ul = pd.DataFrame(self.upgrade_log)
        ul.to_csv(W / "upgrades.csv", index=False)
        if len(ul):
            style_rng = np.random.default_rng(13)
            bl = ul[ul.project_id == "BASELINE"].copy()
            bl["facility_name"] = [noisy_facility_name(f, self.sub_names, style_rng, circuit=int(self.fac.circuit.values[b]),
                                                       style=dict(kv_fmt="{kv} kV", case="title", sep=" - ")) for f, b in zip(bl.fid, bl.branch)]
            bl[["date", "facility_name"]].assign(upgrade="baseline reliability upgrade").to_csv(P / "baseline_upgrades.csv", index=False)
        # market
        if self.lmp_rows:
            lmp = pd.concat(self.lmp_rows, ignore_index=True)
            hv = set(pub_subs[pub_subs.max_kv >= 100].sub_id)
            lmp = lmp[lmp.sub_id.isin(hv)]
            lmp.to_parquet(P / "market_lmp.parquet", index=False)
        mc = pd.DataFrame(self.market_rows)
        if len(mc):
            style_rng = np.random.default_rng(7)
            names = {}
            for b in mc.branch.unique():
                fid = self.fac.fid.values[b]
                names[b] = noisy_facility_name(fid, self.sub_names, style_rng, circuit=int(self.fac.circuit.values[b]) if self.public_fac.n_circuits.get(fid, 1) > 1 else None,
                                               style=dict(kv_fmt="{kv} KV", case="upper", sep=" - "))
            mc["constraint_name"] = mc.branch.map(names)
            mc[["datetime", "constraint_name", "shadow_price", "flow_mw"]].to_csv(P / "market_constraints.csv", index=False)
            mc.to_csv(W / "market_constraints_truth.csv", index=False)
        ot = pd.DataFrame(self.outage_rows)
        if len(ot):
            style_rng = np.random.default_rng(11)
            ot["facility_name"] = [noisy_facility_name(f, self.sub_names, style_rng, circuit=int(self.fac.circuit.values[b]),
                                                       style=dict(kv_fmt="{kv} kV", case="title", sep=" - ")) for f, b in zip(ot.fid, ot.branch)]
            ot[["facility_name", "start", "end", "reason"]].to_csv(P / "outages.csv", index=False)
            ot.to_csv(W / "outages_truth.csv", index=False)
        pd.DataFrame(self.load_rows).to_csv(P / "load_zonal_annual.csv", index=False)
        # generators (EIA-like)
        g = self.plants[["plant_id", "sub_id", "type", "Pmax", "online_year", "retire_year", "pid"]].rename(
            columns={"type": "fuel", "Pmax": "mw", "pid": "queue_project_id"})
        g.to_csv(P / "generators.csv", index=False)
        json.dump(dict(seed=int(self.rng.bit_generator.state["state"]["state"]) if False else C.SEED, start=self.start_year, end=self.end_year,
                       n_projects=len(self.projects), n_studies=len(self.studies)), open(W / "meta.json", "w"), indent=2)
        self._log("exported world + public data")
