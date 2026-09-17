"""Chronological benchmark: baselines vs learned models, ablations, breakdowns, calibration,
secondary tasks (severity bucket, cost bucket, withdrawal)."""
from __future__ import annotations
import json
import pickle
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import roc_auc_score, f1_score, accuracy_score
from .. import config as C
from ..features.pit import PublicData
from ..models import baselines as B
from ..models.latent import add_latent_feature
from ..models.tabular import MainRanker, feature_columns
from .metrics import rank_metrics, calibration, project_level_expected_count

FAMILIES = {
    "congestion": ["cong_hours_24m", "cong_mean_sp_24m", "cong_max_sp_24m", "cong_hours_all", "cong_years_all", "poi_cong_mean", "fac_cong_a",
                   "fac_cong_b", "fac_cong_gap", "fac_cong_vs_poi", "poi_lmp_p90"],
    "prior_studies": ["fac_n_named", "fac_mw_named", "fac_max_loading", "fac_mean_dfax", "fac_years_since_named", "fac_n_active", "fac_n_withdrawn",
                      "fac_n_inservice", "fac_cost_mean", "fac_n_named_near30", "fac_n_named_same_poi", "analog_wfrac", "analog_frac", "analog_n",
                      "analog_mean_dist", "analog_mean_nfac", "latent_score", "latent_seen_poi"],
    "topology": ["apx_dfax", "apx_dfax_missing", "apx_dfax_n1", "apx_contrib_mw", "hops", "end_degree_max"],
    "queue": ["queue_mw_active_25km", "queue_mw_active_50km", "queue_mw_all_50km", "queue_n_same_poi", "queue_mw_active_same_poi",
              "queue_withdraw_frac_50km", "fac_queue_mw_active_25km"],
    "outages_baseline": ["fac_outages_24m", "fac_baseline_upgraded_3y"],
    "latent": ["latent_score", "latent_seen_poi"],
}
COST_BINS = [-1, 1e3, 1e6, 1e7, 5e7, np.inf]
COST_LABELS = ["$0", "<$1M", "$1-10M", "$10-50M", ">$50M"]


def load_dataset(mode="queue"):
    pub = PublicData(verbose=False)
    X = pd.read_parquet(C.PROCESSED / f"features_{mode}.parquet")
    X["as_of"] = pd.to_datetime(X.as_of)
    q = pub.queue.set_index("project_id")
    si = pub.study_index.set_index("project_id")
    X["publication_date"] = X.project_id.map(si.publication_date)
    X["queue_date"] = X.project_id.map(q.queue_date)
    X["project_type"] = X.project_id.map(q.project_type)
    X["poi_sub_id"] = X.project_id.map(q.poi_sub_id)
    te, ve = pd.Timestamp(C.TRAIN_END), pd.Timestamp(C.VALID_END)
    X["split"] = np.where(X.publication_date <= te, "train", np.where(X.publication_date <= ve, "valid", np.where(X.as_of > ve, "test", "drop")))
    X = X[X.split != "drop"].reset_index(drop=True)
    return pub, X


def seen_poi_flags(pub, X):
    """Was there any *published* study (before as_of) for another project at the same POI?"""
    F = pub.meta[["project_id", "publication_date"]].merge(pub.queue[["project_id", "poi_sub_id"]], on="project_id")
    proj = X.groupby("project_id").agg(as_of=("as_of", "first"), poi=("poi_sub_id", "first"))
    seen = {}
    for pid, r in proj.iterrows():
        f = F[(F.poi_sub_id == r.poi) & (F.publication_date < r.as_of) & (F.project_id != pid)]
        seen[pid] = len(f) > 0
    return X.project_id.map(seen)


def run(mode="queue", n_bags=3, out_prefix="", verbose=True, ablations=True):
    pub, X = load_dataset(mode)
    X = add_latent_feature(X, pub)
    X["seen_poi"] = seen_poi_flags(pub, X)
    tr, va, te = (X[X.split == s] for s in ("train", "valid", "test"))
    log = print if verbose else (lambda *a, **k: None)
    log(f"rows train/valid/test = {len(tr)}/{len(va)}/{len(te)}; projects = {tr.project_id.nunique()}/{va.project_id.nunique()}/{te.project_id.nunique()}")
    cov = pd.read_csv(C.PROCESSED / f"candidate_coverage_{mode}.csv").set_index("project_id")
    tp = te.project_id.unique()
    ceiling = cov.loc[tp].n_label_in_cand.sum() / max(1, cov.loc[tp].n_label.sum())
    log(f"test candidate ceiling (recall of true facilities inside candidate set): {ceiling:.3f}")
    scores = {}
    # ---- heuristics
    for name, fn in (("B1_nearest_projects", B.score_nearest_projects), ("B2_queue_density", B.score_queue_density),
                     ("B3_historical_congestion", B.score_historical_congestion), ("P0_public_topology_dfax", B.score_apx_dfax),
                     ("L0_latent_only", lambda d: d.latent_score.values)):
        scores[name] = {s: fn(d) for s, d in (("valid", va), ("test", te))}
    # ---- trained baselines
    gs = B.GeoSizeModel().fit(tr); scores["B4_geo_size_logit"] = dict(valid=gs.predict(va), test=gs.predict(te))
    st = B.SimpleTabular().fit(tr); scores["B5_simple_tabular_gbm"] = dict(valid=st.predict(va), test=st.predict(te))
    # ---- main model + ablations
    cols_all = feature_columns(X, exclude={"publication_date", "queue_date", "project_type", "poi_sub_id", "seen_poi"})
    main = MainRanker(cols_all, n_bags=n_bags).fit(tr, va)
    p_te, raw_te, sd_te = main.predict(te); p_va, raw_va, _ = main.predict(va)
    scores["MAIN_all_features"] = dict(valid=raw_va, test=raw_te)
    te = te.copy(); te["p_main"] = p_te; te["p_main_raw"] = raw_te; te["p_main_sd"] = sd_te
    ablations_out = {}
    for fam, cols in (FAMILIES.items() if ablations else []):
        keep = [c for c in cols_all if c not in set(cols)]
        m = MainRanker(keep, n_bags=1).fit(tr, va)
        pp, rr, _ = m.predict(te)
        scores[f"ABL_minus_{fam}"] = dict(test=rr); ablations_out[fam] = pp
    # ---- calibrate every score on validation for a fair calibration comparison
    results = []
    calib_tables = {}
    for name, sc in scores.items():
        d = te.assign(score=sc["test"])
        rm = rank_metrics(d, "score")
        row = dict(model=name, **{k: v for k, v in rm.items()})
        if "valid" in sc:
            iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(sc["valid"], va.y.values)
            d["prob"] = iso.predict(sc["test"])
        elif name == "MAIN_all_features":
            d["prob"] = p_te
        else:
            d["prob"] = np.clip(sc["test"], 0, 1)
        cal = calibration(d, "prob"); row.update(ece=cal["ece"], brier=cal["brier"], brier_skill=cal["brier_skill"])
        row.update({f"cnt_{k}": v for k, v in project_level_expected_count(d, "prob").items()})
        results.append(row); calib_tables[name] = cal["table"]
    # main model calibrated probabilities (isotonic fitted inside MainRanker)
    d = te.assign(prob=p_te); cal = calibration(d, "prob")
    for r in results:
        if r["model"] == "MAIN_all_features":
            r.update(ece=cal["ece"], brier=cal["brier"], brier_skill=cal["brier_skill"])
            r.update({f"cnt_{k}": v for k, v in project_level_expected_count(d, "prob").items()})
    res = pd.DataFrame(results).set_index("model")
    res["candidate_ceiling"] = ceiling
    res.to_csv(C.TABLES / f"{out_prefix}benchmark_{mode}.csv")
    pd.DataFrame(calib_tables["MAIN_all_features"]).to_csv(C.TABLES / f"{out_prefix}calibration_main_{mode}.csv", index=False)
    main.importance().to_csv(C.TABLES / f"{out_prefix}feature_importance_{mode}.csv", header=["gain"])
    # ---- breakdowns (main vs best baseline by hit@5)
    base_names = [n for n in res.index if n.startswith("B")]
    best_base = res.loc[base_names, "hit@5"].idxmax()
    te["mw_bucket"] = pd.cut(te.mw, [0, 50, 200, 1e5], labels=["<50MW", "50-200MW", ">200MW"])
    te["poi_seen"] = np.where(te.seen_poi, "seen_poi", "unseen_poi")
    bd = []
    for dim in ("poi_seen", "mw_bucket", "project_type"):
        for val, g in te.groupby(dim, observed=True):
            for name, sc in (("MAIN_all_features", te.p_main.values), (best_base, scores[best_base]["test"]), ("P0_public_topology_dfax", scores["P0_public_topology_dfax"]["test"])):
                gg = g.assign(score=sc[g.index.map(lambda i: te.index.get_loc(i))] if False else pd.Series(sc, index=te.index).loc[g.index].values)
                rm = rank_metrics(gg, "score")
                bd.append(dict(dimension=dim, value=str(val), model=name, n_projects=rm["n_projects"], **{k: rm[k] for k in ("hit@1", "hit@3", "hit@5", "hit@10", "recall@5", "recall@10", "precision@5", "mrr")}))
    pd.DataFrame(bd).to_csv(C.TABLES / f"{out_prefix}breakdowns_{mode}.csv", index=False)
    # ---- secondary tasks
    sec = secondary_tasks(pub, X, tr, va, te, main, cols_all, verbose=verbose, mode=mode)
    pd.DataFrame(sec).to_csv(C.TABLES / f"{out_prefix}secondary_{mode}.csv", index=False)
    # ---- persist predictions + model for case studies / UI
    te.to_parquet(C.PROCESSED / f"{out_prefix}test_predictions_{mode}.parquet", index=False)
    with open(C.PROCESSED / f"{out_prefix}main_model_{mode}.pkl", "wb") as fh:
        pickle.dump(dict(model=main, cols=cols_all, train_end=C.TRAIN_END, valid_end=C.VALID_END), fh)
    json.dump(dict(n_train_projects=int(tr.project_id.nunique()), n_valid_projects=int(va.project_id.nunique()), n_test_projects=int(te.project_id.nunique()),
                   n_test_projects_with_constraints=int(te.groupby("project_id").y.sum().gt(0).sum()), candidate_ceiling=float(ceiling), best_baseline=best_base),
              open(C.TABLES / f"{out_prefix}benchmark_meta_{mode}.json", "w"), indent=2)
    log(res[["hit@1", "hit@3", "hit@5", "hit@10", "recall@5", "recall@10", "precision@5", "mrr", "ece", "brier"]].round(3).to_string())
    return res, te


def secondary_tasks(pub, X, tr, va, te, main, cols_all, verbose=True, mode="queue"):
    out = []
    # (a) severity bucket among true constrained facilities
    def sev(v):
        return np.where(v <= 105, 0, np.where(v <= 120, 1, 2))
    trp, tep = tr[tr.y == 1], te[te.y == 1]
    if len(trp) > 50 and len(tep) > 10:
        m = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=31, min_child_samples=20, verbose=-1, random_state=0)
        m.fit(trp[cols_all].fillna(0), sev(trp.y_loading.values))
        pred = m.predict(tep[cols_all].fillna(0)); truth = sev(tep.y_loading.values)
        maj = np.bincount(sev(trp.y_loading.values)).argmax()
        out.append(dict(task="severity_bucket(<=105,105-120,>120)", model="gbm", n=len(tep), accuracy=accuracy_score(truth, pred), macro_f1=f1_score(truth, pred, average="macro")))
        out.append(dict(task="severity_bucket(<=105,105-120,>120)", model="majority", n=len(tep), accuracy=accuracy_score(truth, np.full_like(truth, maj)), macro_f1=f1_score(truth, np.full_like(truth, maj), average="macro")))
    # project-level table
    meta = pub.meta.set_index("project_id")
    def proj_table(d, probs):
        g = d.assign(p=probs).groupby("project_id")
        t = pd.DataFrame(dict(p_sum=g.p.sum(), p_max=g.p.max(), p_top10=g.p.apply(lambda s: np.sort(s.values)[-10:].sum()), n_gt05=g.p.apply(lambda s: (s > 0.5).sum()),
                              mw=g.mw.first(), poi_kv=g.poi_kv.first(), type_gen=g.type_gen.first(), type_battery=g.type_battery.first(), type_load=g.type_load.first(),
                              q25=g.queue_mw_active_25km.first(), q50=g.queue_mw_active_50km.first(), qsame=g.queue_mw_active_same_poi.first(),
                              apx_top=g.apx_contrib_mw.max(), analog_nfac=g.analog_mean_nfac.first(), poi_cong=g.poi_cong_mean.first(), year=g.year.first()))
        t["cost"] = t.index.map(meta.total_cost_usd).fillna(0.0)
        t["cost_bucket"] = pd.cut(t.cost, COST_BINS, labels=range(len(COST_LABELS))).astype(int)
        return t
    p_tr = main.predict(tr)[0]; p_va = main.predict(va)[0]; p_te = te.p_main.values
    Ptr, Pva, Pte = proj_table(tr, p_tr), proj_table(va, p_va), proj_table(te, p_te)
    # NOTE: training-row probabilities are in-sample (optimistic); acceptable for a bucket model, flagged in report.
    feats = ["p_sum", "p_max", "p_top10", "n_gt05", "mw", "poi_kv", "type_gen", "type_battery", "type_load", "q25", "q50", "qsame", "apx_top", "analog_nfac", "poi_cong", "year"]
    Pall = pd.concat([Ptr, Pva])
    m = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=15, min_child_samples=20, verbose=-1, random_state=0)
    m.fit(Pall[feats], Pall.cost_bucket)
    with open(C.PROCESSED / f"cost_model_{mode}.pkl", "wb") as fh:
        pickle.dump(dict(model=m, feats=feats, labels=[COST_LABELS[i] for i in m.classes_]), fh)
    pred = m.predict(Pte[feats]); truth = Pte.cost_bucket.values
    out.append(dict(task="upgrade_cost_bucket", model="gbm(project-level, uses ranker probs)", n=len(Pte), accuracy=accuracy_score(truth, pred),
                    macro_f1=f1_score(truth, pred, average="macro"), adjacent_accuracy=float(np.mean(np.abs(pred - truth) <= 1))))
    maj = np.bincount(Pall.cost_bucket).argmax()
    out.append(dict(task="upgrade_cost_bucket", model="majority", n=len(Pte), accuracy=accuracy_score(truth, np.full_like(truth, maj)),
                    macro_f1=f1_score(truth, np.full_like(truth, maj), average="macro"), adjacent_accuracy=float(np.mean(np.abs(maj - truth) <= 1))))
    g2 = lgb.LGBMClassifier(n_estimators=200, learning_rate=0.05, num_leaves=15, verbose=-1, random_state=0).fit(Pall[["mw", "poi_kv", "type_gen", "type_battery", "type_load", "q50", "year"]], Pall.cost_bucket)
    pg = g2.predict(Pte[["mw", "poi_kv", "type_gen", "type_battery", "type_load", "q50", "year"]])
    out.append(dict(task="upgrade_cost_bucket", model="geo+size+queue only", n=len(Pte), accuracy=accuracy_score(truth, pg), macro_f1=f1_score(truth, pg, average="macro"),
                    adjacent_accuracy=float(np.mean(np.abs(pg - truth) <= 1))))
    # (c) withdrawal prediction (label: project eventually withdrawn; unresolved excluded)
    ev = pub.events
    final = ev.sort_values("date").groupby("project_id").status.last()
    for P in (Pall, Pte):
        P["withdrawn"] = P.index.map(final).map({"withdrawn": 1, "in_service": 0}).astype(float)
    trw = Pall[Pall.withdrawn.notna()]; tew = Pte[Pte.withdrawn.notna()]
    if len(trw) > 50 and tew.withdrawn.nunique() == 2:
        m = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=15, min_child_samples=20, verbose=-1, random_state=0).fit(trw[feats], trw.withdrawn)
        pw = m.predict_proba(tew[feats])[:, 1]
        out.append(dict(task="withdrawal", model="gbm(project-level)", n=len(tew), auc=roc_auc_score(tew.withdrawn, pw), base_rate=float(tew.withdrawn.mean())))
        m2 = lgb.LGBMClassifier(n_estimators=200, learning_rate=0.05, num_leaves=15, verbose=-1, random_state=0).fit(trw[["mw", "poi_kv", "type_gen", "type_battery", "type_load", "q50", "year"]], trw.withdrawn)
        pw2 = m2.predict_proba(tew[["mw", "poi_kv", "type_gen", "type_battery", "type_load", "q50", "year"]])[:, 1]
        out.append(dict(task="withdrawal", model="geo+size+queue only", n=len(tew), auc=roc_auc_score(tew.withdrawn, pw2), base_rate=float(tew.withdrawn.mean())))
    Pte.to_csv(C.PROCESSED / f"test_project_level_{mode}.csv")
    if verbose:
        print(pd.DataFrame(out).round(3).to_string())
    return out
