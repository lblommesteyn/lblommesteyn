"""Point-in-time (PIT) public data access and the per-candidate feature builder.

Vintage rule: a feature for project X evaluated at `as_of` may use only records whose
public availability date is strictly before `as_of`:
  * queue entries with queue_date < as_of; status events with date < as_of
  * studies with publication_date < as_of (never X's own study)
  * market LMPs / constraints with datetime < as_of; outages with start < as_of
  * baseline upgrades with date < as_of; generators with online_year < as_of.year
`PITView` enforces this with assertions; `tests/test_vintage.py` proves invariance to
future rows (features computed from full tables == features from tables truncated at as_of).
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from .. import config as C
from ..extract.normalize import FacilityNormalizer
from ..sim.naming import to_xy_km
from .topology import PublicTopology


class PublicData:
    """All public tables, with free-text facility names resolved to canonical ids once."""

    def __init__(self, root=None, verbose=True):
        P = C.PUBLIC if root is None else root
        self.subs = pd.read_csv(P / "substations.csv")
        self.fac = pd.read_csv(P / "facilities.csv")
        self.queue = pd.read_csv(P / "queue.csv", parse_dates=["queue_date"])
        self.events = pd.read_csv(P / "queue_events.csv", parse_dates=["date"])
        self.study_index = pd.read_csv(P / "study_index.csv", parse_dates=["publication_date"])
        self.findings = pd.read_csv(C.STUDIES / "parsed_findings.csv", parse_dates=["publication_date"])
        self.meta = pd.read_csv(C.STUDIES / "parsed_meta.csv", parse_dates=["publication_date"])
        self.lmp = pd.read_parquet(P / "market_lmp.parquet")
        self.lmp["datetime"] = pd.to_datetime(self.lmp.datetime)
        self.constraints = pd.read_csv(P / "market_constraints.csv", parse_dates=["datetime"])
        self.outages = pd.read_csv(P / "outages.csv", parse_dates=["start", "end"])
        self.baseline = pd.read_csv(P / "baseline_upgrades.csv", parse_dates=["date"]) if (P / "baseline_upgrades.csv").exists() else pd.DataFrame(columns=["date", "facility_name"])
        self.generators = pd.read_csv(P / "generators.csv")
        self.load = pd.read_csv(P / "load_zonal_annual.csv")
        self.norm = FacilityNormalizer(self.subs, self.fac)
        self._resolve_names(verbose)
        self.topo = PublicTopology(self.subs, self.fac)
        # derived
        self.queue["xy"] = list(to_xy_km(self.queue.poi_sub_id.map(self.subs.set_index("sub_id").lat).values,
                                         self.queue.poi_sub_id.map(self.subs.set_index("sub_id").lon).values))
        self.queue_xy = np.vstack(self.queue.xy.values)
        self.q_by_pid = self.queue.set_index("project_id")
        self.lmp_hours = np.sort(self.lmp.datetime.unique())
        piv = self.lmp.pivot_table(index="datetime", columns="sub_id", values="congestion", aggfunc="mean")
        self.lmp_mat = piv.reindex(self.lmp_hours)
        self.findings = self.findings[self.findings.fid.notna()].copy()
        self.findings = self.findings.merge(self.queue[["project_id", "poi_sub_id", "mw", "project_type", "queue_date"]], on="project_id", how="left")
        self.findings["xy_idx"] = self.findings.project_id.map({p: i for i, p in enumerate(self.queue.project_id)})
        self.findings = self.findings.sort_values("publication_date").reset_index(drop=True)
        self.meta = self.meta.sort_values("publication_date").reset_index(drop=True)
        self.meta["xy_idx"] = self.meta.project_id.map({p: i for i, p in enumerate(self.queue.project_id)})
        self.events = self.events.sort_values("date").reset_index(drop=True)
        self.constraints = self.constraints.sort_values("datetime").reset_index(drop=True)
        self.outages = self.outages.sort_values("start").reset_index(drop=True)
        self.baseline = self.baseline.sort_values("date").reset_index(drop=True)
        self.fac_pos = {f: i for i, f in enumerate(self.fac.fid)}
        self.sub_xy = dict(zip(self.subs.sub_id, to_xy_km(self.subs.lat.values, self.subs.lon.values)))

    def _resolve_names(self, verbose):
        cache_path = C.PROCESSED / "name_map.csv"
        names = pd.unique(pd.concat([self.constraints.constraint_name, self.outages.facility_name, self.baseline.facility_name], ignore_index=True).dropna())
        if cache_path.exists():
            mp = pd.read_csv(cache_path)
            mp = dict(zip(mp.name, mp.fid.where(mp.fid.notna(), None)))
            if all(n in mp for n in names):
                self.name_map = mp
            else:
                self.name_map = None
        else:
            self.name_map = None
        if self.name_map is None:
            self.name_map = {n: self.norm.normalize(n)["fid"] for n in names}
            pd.DataFrame(dict(name=list(self.name_map), fid=list(self.name_map.values()))).to_csv(cache_path, index=False)
        self.constraints["fid"] = self.constraints.constraint_name.map(self.name_map)
        self.outages["fid"] = self.outages.facility_name.map(self.name_map)
        self.baseline["fid"] = self.baseline.facility_name.map(self.name_map)
        if verbose:
            print(f"name resolution: constraints {self.constraints.fid.notna().mean():.3f}, outages {self.outages.fid.notna().mean():.3f}, "
                  f"baseline {self.baseline.fid.notna().mean():.3f} resolved")

    def truncated(self, as_of: pd.Timestamp) -> "PublicData":
        """A copy with every dated table physically cut at as_of (used by the vintage test)."""
        import copy
        o = copy.copy(self)
        o.queue = self.queue[self.queue.queue_date < as_of].reset_index(drop=True); o.queue_xy = np.vstack(o.queue.xy.values) if len(o.queue) else np.zeros((0, 2))
        o.q_by_pid = o.queue.set_index("project_id")
        o.events = self.events[self.events.date < as_of].reset_index(drop=True)
        o.study_index = self.study_index[self.study_index.publication_date < as_of]
        o.findings = self.findings[self.findings.publication_date < as_of].reset_index(drop=True)
        o.meta = self.meta[self.meta.publication_date < as_of].reset_index(drop=True)
        o.lmp_hours = self.lmp_hours[self.lmp_hours < np.datetime64(as_of)]
        o.lmp_mat = self.lmp_mat.loc[o.lmp_hours]
        o.constraints = self.constraints[self.constraints.datetime < as_of].reset_index(drop=True)
        o.outages = self.outages[self.outages.start < as_of].reset_index(drop=True)
        o.baseline = self.baseline[self.baseline.date < as_of].reset_index(drop=True)
        o.generators = self.generators[self.generators.online_year < as_of.year]
        o.load = self.load[self.load.year < as_of.year]
        return o


class PITView:
    """Point-in-time slices with vintage assertions."""

    def __init__(self, pub: PublicData, as_of: pd.Timestamp):
        self.pub = pub
        self.as_of = pd.Timestamp(as_of)

    def _guard(self, df, col):
        if len(df):
            assert (df[col] < self.as_of).all(), f"vintage leak in {col}: max {df[col].max()} >= {self.as_of}"
        return df

    def queue(self):
        return self._guard(self.pub.queue[self.pub.queue.queue_date < self.as_of], "queue_date")

    def status_as_of(self) -> pd.Series:
        ev = self._guard(self.pub.events[self.pub.events.date < self.as_of], "date")
        last = ev.groupby("project_id").status.last()
        q = self.queue()
        st = pd.Series("active", index=q.project_id)
        st.update(last.reindex(st.index).dropna())
        return st

    def findings(self):
        return self._guard(self.pub.findings[self.pub.findings.publication_date < self.as_of], "publication_date")

    def meta(self):
        return self._guard(self.pub.meta[self.pub.meta.publication_date < self.as_of], "publication_date")

    def constraints(self, months: int | None = None):
        c = self.pub.constraints
        c = c[c.datetime < self.as_of]
        if months:
            c = c[c.datetime >= self.as_of - pd.DateOffset(months=months)]
        return self._guard(c, "datetime")

    def lmp_window(self, months: int = 24):
        h = self.pub.lmp_hours
        sel = (h < np.datetime64(self.as_of)) & (h >= np.datetime64(self.as_of - pd.DateOffset(months=months)))
        return self.pub.lmp_mat.loc[h[sel]]

    def outages(self, months: int = 24):
        o = self.pub.outages
        o = o[(o.start < self.as_of) & (o.start >= self.as_of - pd.DateOffset(months=months))]
        return self._guard(o, "start")

    def baseline(self, years: int = 3):
        b = self.pub.baseline
        b = b[(b.date < self.as_of) & (b.date >= self.as_of - pd.DateOffset(years=years))]
        return self._guard(b, "date")

    def generators(self):
        g = self.pub.generators
        return g[(g.online_year < self.as_of.year)]


class FeatureBuilder:
    def __init__(self, pub: PublicData):
        self.pub = pub
        self.topo = pub.topo
        self.fac = pub.fac
        self.fac_kv = pub.fac.kv.values.astype(float)
        self.fac_kind = pub.fac.kind.values
        self.fac_len = pub.fac.length_km.fillna(0).values
        self.fac_a = pub.fac.sub_a.values.astype(int)
        self.fac_b = pub.fac.sub_b.fillna(pub.fac.sub_a).values.astype(int)
        sub_pos = {int(s): i for i, s in enumerate(pub.subs.sub_id)}
        deg = pd.Series(np.r_[pub.fac[pub.fac.kind == "L"].sub_a.values, pub.fac[pub.fac.kind == "L"].sub_b.values]).value_counts()
        self.sub_deg = deg
        self.fac_xy_a = np.vstack([pub.sub_xy[s] for s in self.fac_a]); self.fac_xy_b = np.vstack([pub.sub_xy[s] for s in self.fac_b])
        # NOTE: generation features are computed per as_of inside build() (PIT); a class-level
        # aggregate over all generators leaked future in-service plants (caught by tests/test_vintage.py).

    # ---- candidate generation ---------------------------------------------------------
    def candidates(self, poi_sub: int, poi_kv: float, prior_findings: pd.DataFrame, radius_km=C.CANDIDATE_RADIUS_KM,
                   max_hops=C.CANDIDATE_MAX_HOPS, cap=C.CANDIDATE_CAP):
        dmin, dmax = self.topo.fac_dist_km(poi_sub)
        hops = self.topo.fac_hops(poi_sub)
        dfax = self.topo.apx_dfax(poi_sub, poi_kv)
        dfax_n1 = self.topo.apx_dfax_n1(poi_sub, poi_kv)
        sel = (dmin <= radius_km) | (hops <= max_hops) | (np.nan_to_num(dfax_n1, nan=0.0) >= C.CANDIDATE_MIN_APX_DFAX)
        # retrieval: facilities named by prior studies of projects within 60 km
        if len(prior_findings):
            pxy = self.pub.queue_xy[prior_findings.xy_idx.values.astype(int)]
            near = np.hypot(*(pxy - self.pub.sub_xy[int(poi_sub)]).T) <= 60
            for f in prior_findings.fid.values[near]:
                if f in self.pub.fac_pos:
                    sel[self.pub.fac_pos[f]] = True
        idx = np.where(sel)[0]
        if len(idx) > cap:
            score = np.nan_to_num(dfax_n1[idx], nan=0.0) * 1000 - dmin[idx]
            idx = idx[np.argsort(-score)[:cap]]
        return idx, dict(dmin=dmin, dmax=dmax, hops=hops, dfax=dfax, dfax_n1=dfax_n1)

    # ---- features ------------------------------------------------------------------------
    def build(self, project: pd.Series, as_of: pd.Timestamp, label_fids: dict | None = None) -> pd.DataFrame:
        pub = self.pub
        v = PITView(pub, as_of)
        poi_sub, poi_kv = int(project.poi_sub_id), float(project.poi_kv)
        pxy = pub.sub_xy[poi_sub]
        F = v.findings()
        F = F[F.project_id != project.project_id]
        idx, geo = self.candidates(poi_sub, poi_kv, F)
        fids = self.fac.fid.values[idx]
        n = len(idx)
        out = pd.DataFrame(dict(project_id=project.project_id, fid=fids))
        # --- project-level
        out["mw"] = project.mw; out["log_mw"] = np.log1p(project.mw)
        out["poi_kv"] = poi_kv
        for t in ("gen", "battery", "load"):
            out[f"type_{t}"] = float(project.project_type == t)
        for f in ("solar", "wind", "gas", "storage", "hybrid", "load", "other"):
            out[f"fuel_{f}"] = float(project.fuel == f)
        out["year"] = as_of.year + as_of.month / 12.0
        out["poi_degree"] = float(self.sub_deg.get(poi_sub, 0))
        G = v.generators()
        G = G[G.retire_year.isna() | (G.retire_year >= as_of.year)]
        gen_sub_mw = G.groupby("sub_id").mw.sum()
        out["poi_gen_mw"] = float(gen_sub_mw.get(poi_sub, 0.0))
        # --- geometry / topology
        out["dist_km"] = geo["dmin"][idx]; out["dist_far_km"] = geo["dmax"][idx]
        out["hops"] = np.where(np.isfinite(geo["hops"][idx]), geo["hops"][idx], 12.0)
        out["fac_kv"] = self.fac_kv[idx]; out["kv_ratio"] = self.fac_kv[idx] / poi_kv
        out["same_kv"] = (np.abs(self.fac_kv[idx] - poi_kv) < 1).astype(float)
        out["fac_len_km"] = self.fac_len[idx]
        for k in ("L", "X", "B"):
            out[f"kind_{k}"] = (self.fac_kind[idx] == k).astype(float)
        out["touches_poi"] = ((self.fac_a[idx] == poi_sub) | (self.fac_b[idx] == poi_sub)).astype(float)
        out["end_degree_max"] = np.maximum(self.sub_deg.reindex(self.fac_a[idx]).fillna(0).values, self.sub_deg.reindex(self.fac_b[idx]).fillna(0).values)
        d0 = geo["dfax"][idx]
        out["apx_dfax"] = np.nan_to_num(np.abs(d0), nan=0.0); out["apx_dfax_missing"] = np.isnan(d0).astype(float)
        d1 = geo["dfax_n1"][idx]
        out["apx_dfax_n1"] = np.nan_to_num(d1, nan=0.0)
        out["apx_contrib_mw"] = out.apx_dfax_n1 * project.mw
        # --- prior studies (facility history)
        if len(F):
            st = v.status_as_of()
            Fs = F.assign(status=F.project_id.map(st).fillna("active"))
            g = Fs.groupby("fid")
            agg = pd.DataFrame(dict(fac_n_named=g.size(), fac_mw_named=g.mw.sum(), fac_max_loading=g.loading_pct.max(),
                                    fac_mean_dfax=g.dfax_pct.mean(), fac_last_pub=g.publication_date.max(),
                                    fac_n_active=g.status.apply(lambda s: (s == "active").sum()),
                                    fac_n_withdrawn=g.status.apply(lambda s: (s == "withdrawn").sum()),
                                    fac_n_inservice=g.status.apply(lambda s: (s == "in_service").sum()),
                                    fac_cost_mean=g.cost_alloc_usd.mean() if "cost_alloc_usd" in Fs else 0.0))
            agg["fac_years_since_named"] = (as_of - agg.fac_last_pub).dt.days / 365.25
            agg = agg.drop(columns=["fac_last_pub"])
            pxy_all = pub.queue_xy[Fs.xy_idx.values.astype(int)]
            dist_p = np.hypot(*(pxy_all - pxy).T)
            Fs = Fs.assign(dist_p=dist_p)
            near = Fs[Fs.dist_p <= 30].groupby("fid").size().rename("fac_n_named_near30")
            same = Fs[Fs.poi_sub_id == poi_sub].groupby("fid").size().rename("fac_n_named_same_poi")
            agg = agg.join(near).join(same)
            out = out.merge(agg, left_on="fid", right_index=True, how="left")
        for c in ("fac_n_named", "fac_mw_named", "fac_max_loading", "fac_mean_dfax", "fac_n_active", "fac_n_withdrawn", "fac_n_inservice",
                  "fac_cost_mean", "fac_n_named_near30", "fac_n_named_same_poi"):
            if c not in out:
                out[c] = 0.0
            out[c] = out[c].fillna(0.0)
        if "fac_years_since_named" not in out:
            out["fac_years_since_named"] = 20.0
        out["fac_years_since_named"] = out.fac_years_since_named.fillna(20.0)
        # --- analog projects (retrieval)
        M = v.meta(); M = M[M.project_id != project.project_id]
        if len(M):
            mxy = pub.queue_xy[M.xy_idx.values.astype(int)]
            d = np.hypot(*(mxy - pxy).T)
            q = pub.q_by_pid.reindex(M.project_id)
            sim = np.exp(-d / 30.0) * np.where(q.project_type.values == project.project_type, 1.0, 0.5) * np.exp(-np.abs(np.log((q.mw.values + 1) / (project.mw + 1))))
            top = np.argsort(-sim)[:10]
            top = top[d[top] <= 80]
            if len(top):
                ana = M.iloc[top]; w = sim[top]
                named = F[F.project_id.isin(ana.project_id)]
                wmap = dict(zip(ana.project_id, w))
                named = named.assign(w=named.project_id.map(wmap))
                a1 = named.groupby("fid").w.sum() / w.sum()
                a2 = named.groupby("fid").project_id.nunique() / len(top)
                out["analog_wfrac"] = out.fid.map(a1).fillna(0.0); out["analog_frac"] = out.fid.map(a2).fillna(0.0)
                out["analog_n"] = float(len(top)); out["analog_mean_dist"] = float(d[top].mean())
                out["analog_mean_nfac"] = float(ana.n_fid_resolved.mean())
        for c, dflt in (("analog_wfrac", 0.0), ("analog_frac", 0.0), ("analog_n", 0.0), ("analog_mean_dist", 200.0), ("analog_mean_nfac", 0.0)):
            if c not in out:
                out[c] = dflt
        # --- congestion history
        Cw = v.constraints(months=24); Ca = v.constraints()
        if len(Cw):
            g = Cw.groupby("fid")
            out["cong_hours_24m"] = out.fid.map(g.size()).fillna(0.0)
            out["cong_mean_sp_24m"] = out.fid.map(g.shadow_price.mean()).fillna(0.0)
            out["cong_max_sp_24m"] = out.fid.map(g.shadow_price.max()).fillna(0.0)
        else:
            out["cong_hours_24m"] = 0.0; out["cong_mean_sp_24m"] = 0.0; out["cong_max_sp_24m"] = 0.0
        if len(Ca):
            out["cong_hours_all"] = out.fid.map(Ca.groupby("fid").size()).fillna(0.0)
            out["cong_years_all"] = out.fid.map(Ca.groupby("fid").datetime.apply(lambda s: s.dt.year.nunique())).fillna(0.0)
        else:
            out["cong_hours_all"] = 0.0; out["cong_years_all"] = 0.0
        Lw = v.lmp_window(24)
        if len(Lw):
            cong_mean = Lw.mean(axis=0)
            poi_c = float(cong_mean.get(poi_sub, np.nan))
            out["poi_cong_mean"] = 0.0 if np.isnan(poi_c) else poi_c
            ca = cong_mean.reindex(self.fac_a[idx]).values; cb = cong_mean.reindex(self.fac_b[idx]).values
            out["fac_cong_a"] = np.nan_to_num(ca, nan=0.0); out["fac_cong_b"] = np.nan_to_num(cb, nan=0.0)
            out["fac_cong_gap"] = np.nan_to_num(np.abs(ca - cb), nan=0.0)
            out["fac_cong_vs_poi"] = np.nan_to_num(np.maximum(ca, cb) - (0.0 if np.isnan(poi_c) else poi_c), nan=0.0)
            out["poi_lmp_p90"] = float(np.nanpercentile(Lw[poi_sub].values, 90)) if poi_sub in Lw.columns else 0.0
        else:
            for c in ("poi_cong_mean", "fac_cong_a", "fac_cong_b", "fac_cong_gap", "fac_cong_vs_poi", "poi_lmp_p90"):
                out[c] = 0.0
        # --- outages, baseline upgrades
        O = v.outages(24)
        out["fac_outages_24m"] = out.fid.map(O.groupby("fid").size()).fillna(0.0) if len(O) else 0.0
        B = v.baseline(3)
        out["fac_baseline_upgraded_3y"] = out.fid.isin(set(B.fid.dropna())).astype(float) if len(B) else 0.0
        # --- queue density (prior projects, status as of)
        Q = v.queue(); Q = Q[Q.project_id != project.project_id]
        if len(Q):
            st = v.status_as_of().reindex(Q.project_id).fillna("active").values
            qxy = np.vstack(Q.xy.values); dq = np.hypot(*(qxy - pxy).T)
            active = st == "active"
            out["queue_mw_active_25km"] = float(Q.mw.values[active & (dq <= 25)].sum())
            out["queue_mw_active_50km"] = float(Q.mw.values[active & (dq <= 50)].sum())
            out["queue_mw_all_50km"] = float(Q.mw.values[dq <= 50].sum())
            same = Q.poi_sub_id.values == poi_sub
            out["queue_n_same_poi"] = float(same.sum()); out["queue_mw_active_same_poi"] = float(Q.mw.values[same & active].sum())
            out["queue_withdraw_frac_50km"] = float((st[dq <= 50] == "withdrawn").mean()) if (dq <= 50).sum() else 0.0
            # active MW near each candidate facility's endpoints
            if active.sum():
                tree = cKDTree(qxy[active]); mw_act = Q.mw.values[active]
                near_a = tree.query_ball_point(self.fac_xy_a[idx], r=25); near_b = tree.query_ball_point(self.fac_xy_b[idx], r=25)
                out["fac_queue_mw_active_25km"] = [float(mw_act[list(set(a) | set(b))].sum()) if (a or b) else 0.0 for a, b in zip(near_a, near_b)]
            else:
                out["fac_queue_mw_active_25km"] = 0.0
        else:
            for c in ("queue_mw_active_25km", "queue_mw_active_50km", "queue_mw_all_50km", "queue_n_same_poi", "queue_mw_active_same_poi",
                      "queue_withdraw_frac_50km", "fac_queue_mw_active_25km"):
                out[c] = 0.0
        # --- generation near facility
        out["fac_gen_mw_ends"] = gen_sub_mw.reindex(self.fac_a[idx]).fillna(0).values + gen_sub_mw.reindex(self.fac_b[idx]).fillna(0).values
        # --- labels
        if label_fids is not None:
            out["y"] = out.fid.map(lambda f: 1.0 if f in label_fids else 0.0)
            out["y_loading"] = out.fid.map(lambda f: label_fids.get(f, np.nan))
        out["as_of"] = as_of
        return out


FEATURE_COLS = None  # filled by build script (all numeric columns except ids/labels)
