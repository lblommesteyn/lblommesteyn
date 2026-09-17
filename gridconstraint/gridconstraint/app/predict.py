"""Prediction service used by the CLI, the case studies and the static UI.

Given (POI substation, project type, MW) and an as-of date, build the point-in-time
candidate table, score it with the trained ranker, and assemble: ranked facilities with
calibrated probabilities and bag-spread uncertainty, difficulty summary, cost-bucket
probabilities, analog projects and per-facility evidence (top feature contributions).
"""
from __future__ import annotations
import pickle
import numpy as np
import pandas as pd
from .. import config as C
from ..features.pit import PublicData, FeatureBuilder, PITView
from ..models.latent import LatentModel
from ..sim.naming import canonical_display

EVIDENCE_TEXT = {
    "apx_dfax_n1": "public-topology distribution factor (N-1) {v:.2f}",
    "apx_dfax": "public-topology distribution factor {v:.2f}",
    "apx_contrib_mw": "estimated flow contribution {v:.0f} MW",
    "dist_km": "{v:.0f} km from POI", "hops": "{v:.0f} hops from POI", "touches_poi": "directly connected to POI",
    "fac_n_named": "named in {v:.0f} prior stud{ies}", "fac_n_named_near30": "named by {v:.0f} prior projects within 30 km",
    "fac_n_named_same_poi": "named by {v:.0f} prior projects at this POI", "fac_years_since_named": "last named {v:.1f} years ago",
    "fac_n_active": "{v:.0f} active queue projects already assigned this upgrade", "fac_n_withdrawn": "{v:.0f} earlier projects assigned it withdrew",
    "fac_n_inservice": "{v:.0f} projects assigned it went in service (upgrade likely built)",
    "cong_hours_24m": "bound {v:.0f} sampled market hours in last 24 months", "cong_hours_all": "bound {v:.0f} sampled market hours historically",
    "cong_mean_sp_24m": "mean shadow price ${v:.0f}/MWh when binding", "fac_cong_gap": "LMP congestion gap across facility ${v:.1f}/MWh",
    "fac_cong_vs_poi": "endpoint congestion vs POI ${v:.1f}/MWh", "poi_cong_mean": "POI congestion component ${v:.1f}/MWh",
    "fac_queue_mw_active_25km": "{v:.0f} MW active queue within 25 km of facility", "queue_mw_active_50km": "{v:.0f} MW active queue within 50 km of POI",
    "queue_mw_active_same_poi": "{v:.0f} MW active queue at this POI", "analog_wfrac": "named by {v:.0%} (similarity-weighted) of analog projects",
    "analog_frac": "named by {v:.0%} of the most similar prior projects", "latent_score": "latent-factor affinity {v:.2f}",
    "fac_kv": "{v:.0f} kV facility", "kv_ratio": "voltage ratio to POI {v:.2f}", "fac_baseline_upgraded_3y": "baseline upgrade within 3 years",
    "fac_outages_24m": "{v:.0f} outages in last 24 months", "fac_max_loading": "max prior study loading {v:.0f}%", "log_mw": "project size",
    "mw": "project size {v:.0f} MW", "fac_gen_mw_ends": "{v:.0f} MW existing generation at endpoints", "end_degree_max": "endpoint degree {v:.0f}",
}


class Predictor:
    def __init__(self, mode: str = "queue", pub: PublicData | None = None):
        self.pub = pub or PublicData(verbose=False)
        with open(C.PROCESSED / f"main_model_{mode}.pkl", "rb") as fh:
            d = pickle.load(fh)
        self.model, self.cols = d["model"], d["cols"]
        self.fb = FeatureBuilder(self.pub)
        self.names = dict(zip(self.pub.subs.sub_id.astype(int), self.pub.subs.name))
        self._latent_cache: dict[int, LatentModel] = {}
        cost_path = C.PROCESSED / f"cost_model_{mode}.pkl"
        self.cost_model = pickle.load(open(cost_path, "rb")) if cost_path.exists() else None

    def latent(self, as_of: pd.Timestamp) -> LatentModel:
        y = as_of.year
        if y not in self._latent_cache:
            self._latent_cache[y] = LatentModel(self.pub).fit(pd.Timestamp(year=y, month=1, day=1))
        return self._latent_cache[y]

    def display(self, fid: str) -> str:
        try:
            return canonical_display(fid, self.names) if not fid.startswith("B:") else f"{self.names[int(fid.split(':')[1])]} {fid.split(':')[2]} kV bus"
        except Exception:
            return fid

    def predict(self, poi_sub: int, project_type: str, mw: float, as_of: pd.Timestamp, fuel: str | None = None, project_id: str = "NEW",
                top_k: int = 10, n_analogs: int = 5) -> dict:
        as_of = pd.Timestamp(as_of)
        fuel = fuel or {"gen": "solar", "battery": "storage", "load": "load"}[project_type]
        sub = self.pub.subs.set_index("sub_id").loc[int(poi_sub)]
        kvs = [k for (s, k) in self.pub.topo.nodes if s == int(poi_sub)] or [sub.max_kv]
        poi_kv = float(max(kvs)) if mw > 300 else float(min(kvs, key=lambda k: abs(np.log((mw + 1) / {69: 20, 100: 60, 115: 80, 138: 90, 161: 150, 230: 260, 345: 550, 500: 900, 765: 1200}.get(int(k), 100)))))
        proj = pd.Series(dict(project_id=project_id, poi_sub_id=int(poi_sub), poi_kv=poi_kv, project_type=project_type, fuel=fuel, mw=float(mw)))
        X = self.fb.build(proj, as_of)
        lm = self.latent(as_of)
        X["latent_score"] = lm.score(int(poi_sub), X.fid.values) if lm.V is not None else 0.0
        e = lm.poi_embedding(int(poi_sub)) if lm.V is not None else None
        X["latent_seen_poi"] = float(e is not None and e[1])
        for c in self.cols:
            if c not in X:
                X[c] = 0.0
        p, raw, sd = self.model.predict(X)
        X["p"] = p; X["raw"] = raw; X["sd"] = sd
        top = X.sort_values("p", ascending=False).head(top_k)
        # evidence via per-feature contributions of the first bag
        contrib = self.model.models[0].predict(top[self.cols].fillna(0), pred_contrib=True)
        ev = []
        for i, (_, r) in enumerate(top.iterrows()):
            c = pd.Series(contrib[i][:-1], index=self.cols).sort_values(ascending=False)
            items = []
            for f in c.index[:4]:
                if c[f] <= 0:
                    break
                v = float(r[f]); t = EVIDENCE_TEXT.get(f)
                if t:
                    items.append(t.format(v=v, ies="y" if abs(v - 1) < 1e-9 else "ies"))
            ev.append(items)
        top = top.assign(evidence=ev, display=[self.display(f) for f in top.fid])
        # difficulty
        p_all = X.p.values
        exp_n = float(p_all.sum()); p_none = float(np.exp(np.sum(np.log1p(-np.clip(p_all, 0, 0.999)))))
        difficulty = "low" if exp_n < 1.0 else ("moderate" if exp_n < 3 else ("high" if exp_n < 7 else "very high"))
        # analogs
        v = PITView(self.pub, as_of); M = v.meta(); M = M[M.project_id != project_id]
        analogs = []
        if len(M):
            mxy = self.pub.queue_xy[M.xy_idx.values.astype(int)]
            d = np.hypot(*(mxy - self.pub.sub_xy[int(poi_sub)]).T)
            q = self.pub.q_by_pid.reindex(M.project_id)
            sim = np.exp(-d / 30.0) * np.where(q.project_type.values == project_type, 1.0, 0.5) * np.exp(-np.abs(np.log((q.mw.values + 1) / (mw + 1))))
            for j in np.argsort(-sim)[:n_analogs]:
                r = M.iloc[j]; qq = q.iloc[j]
                F = v.findings(); F = F[F.project_id == r.project_id]
                analogs.append(dict(project_id=r.project_id, distance_km=round(float(d[j]), 1), mw=float(qq.mw), project_type=qq.project_type, fuel=qq.fuel,
                                    poi=self.names.get(int(qq.poi_sub_id), ""), published=str(r.publication_date.date()), n_facilities=int(r.n_fid_resolved),
                                    cost_usd=float(r.total_cost_usd) if pd.notna(r.total_cost_usd) else None,
                                    facilities=[self.display(f) for f in F.fid.head(5)]))
        # cost buckets
        cost = None
        if self.cost_model is not None:
            feats = dict(p_sum=exp_n, p_max=float(p_all.max()), p_top10=float(np.sort(p_all)[-10:].sum()), n_gt05=float((p_all > 0.5).sum()), mw=mw, poi_kv=poi_kv,
                         type_gen=float(project_type == "gen"), type_battery=float(project_type == "battery"), type_load=float(project_type == "load"),
                         q25=float(X.queue_mw_active_25km.iloc[0]), q50=float(X.queue_mw_active_50km.iloc[0]), qsame=float(X.queue_mw_active_same_poi.iloc[0]),
                         apx_top=float(X.apx_contrib_mw.max()), analog_nfac=float(X.analog_mean_nfac.iloc[0]), poi_cong=float(X.poi_cong_mean.iloc[0]),
                         year=as_of.year + as_of.month / 12)
            pr = self.cost_model["model"].predict_proba(pd.DataFrame([feats])[self.cost_model["feats"]])[0]
            cost = {lab: float(pv) for lab, pv in zip(self.cost_model["labels"], pr)}
        return dict(project=dict(poi_sub_id=int(poi_sub), poi_name=self.names.get(int(poi_sub), ""), poi_kv=poi_kv, project_type=project_type, fuel=fuel, mw=mw,
                                 as_of=str(as_of.date()), seen_poi=bool(X.latent_seen_poi.iloc[0]) if "latent_seen_poi" in X else False, n_candidates=int(len(X))),
                    ranked=top[["fid", "display", "p", "sd", "evidence", "dist_km", "fac_kv"]].to_dict("records"),
                    difficulty=dict(expected_constraints=exp_n, p_no_constraint=p_none, label=difficulty, mean_bag_sd_top10=float(top.sd.mean())),
                    cost_bucket_probs=cost, analogs=analogs)


def main():
    import argparse, json
    ap = argparse.ArgumentParser(description="Rank likely limiting facilities for a proposed project (research prototype; NOT an ISO study).")
    ap.add_argument("--sub", required=True, help="substation name (fuzzy) or sub_id")
    ap.add_argument("--type", default="gen", choices=["gen", "battery", "load"])
    ap.add_argument("--mw", type=float, default=100.0)
    ap.add_argument("--as-of", default="2026-01-01")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    P = Predictor()
    if a.sub.isdigit():
        sid = int(a.sub)
    else:
        c = P.pub.norm.match_sub(a.sub)
        if not c:
            raise SystemExit("no substation matched")
        sid = c[0][0]
    r = P.predict(sid, a.type, a.mw, pd.Timestamp(a.as_of))
    if a.json:
        print(json.dumps(r, indent=1, default=str)); return
    print(f"POI {r['project']['poi_name']} ({sid}) {r['project']['poi_kv']:.0f} kV | {a.type} {a.mw:.0f} MW | as of {a.as_of} | seen POI: {r['project']['seen_poi']}")
    print(f"difficulty: {r['difficulty']['label']} (expected constrained facilities {r['difficulty']['expected_constraints']:.1f}, P(none) {r['difficulty']['p_no_constraint']:.2f})")
    for i, x in enumerate(r["ranked"], 1):
        print(f"{i:2d}. {x['display']:55s} p={x['p']:.2f} ±{x['sd']:.2f}  | " + "; ".join(x["evidence"][:3]))
    if r["cost_bucket_probs"]:
        print("cost bucket probs:", {k: round(v, 2) for k, v in r["cost_bucket_probs"].items()})
    print("analogs:", [(x["project_id"], x["distance_km"], x["n_facilities"]) for x in r["analogs"]])
    print("NOTE: research prototype on a simulated ISO over public topology; not an interconnection study.")


if __name__ == "__main__":
    main()
