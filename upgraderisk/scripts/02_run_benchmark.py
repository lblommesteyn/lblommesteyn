"""Rolling-origin chronological benchmark.

For each test month (observation dates after the first cutoff), every baseline and model is re-fitted on all
examples observed before that month using only labels that were KNOWABLE by then (pit.known_by), and scores the
month's examples. Predictions are pooled over months for the metrics. This is the deployment-faithful protocol:
nothing published after an observation, and no outcome that had not yet happened, reaches the model.

Outputs (outputs/tables): benchmark.json, benchmark_main.md, reliability_*.csv, predictions_test.parquet
"""
from __future__ import annotations
import argparse, json, sys, time, warnings
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from upgraderisk import features, baselines, models, metrics, pit
from upgraderisk.config import PROCESSED, TABLES, SEED

warnings.filterwarnings("ignore")


def model_zoo(num, cat, n_bags):
    zoo = [baselines.AlwaysOnTime(), baselines.BaseRate(), baselines.ProjectAgeHeuristic(), baselines.GroupRate("to"), baselines.GroupRate("voltage_class"),
           baselines.GroupRate("equipment"), baselines.SmallLogistic(["voltage_kv", "log_cost", "months_to_expected_isd"], "logit_voltage_cost_duration"),
           baselines.SmallLogistic([c for c in num if not c.startswith(("rate_", "n_", "global_"))], "logit_numeric"),
           BaggedGBM(num, cat, n_bags), models.DiscreteTimeSurvival(num, cat, seed=SEED), Blend(num, cat, n_bags)]
    return zoo


class Blend:
    """Average of the survival model's and the calibrated classifier's slip probabilities; survival quantiles for
    completion; classifier for cost and cancellation."""
    name = "blend"

    def __init__(self, num, cat, n_bags):
        self.g = BaggedGBM(num, cat, n_bags); self.s = models.DiscreteTimeSurvival(num, cat, seed=SEED)

    def fit(self, tr):
        self.g.fit(tr); self.s.fit(tr); return self

    def predict(self, te):
        pg, ps = self.g.predict(te), self.s.predict(te)
        return dict(p_delay=0.5 * (pg["p_delay"] + ps["p_delay"]), p_over=pg["p_over"], p_cancel=pg.get("p_cancel", np.full(len(te), np.nan)), q_late=ps["q_late"], q_over=pg["q_over"],
                    q_capped=ps["q_capped"], horizon_beyond_followup=ps["horizon_beyond_followup"], max_followup_months=ps["max_followup_months"])


class BaggedGBM:
    name = "gbm"

    def __init__(self, num, cat, n_bags):
        self.num, self.cat = num, cat
        self.members = [models.GBMRisk(num, cat, seed=SEED + i) for i in range(n_bags)]

    def fit(self, tr):
        for m in self.members:
            m.fit(tr)
        return self

    def predict(self, te):
        ps = [m.predict(te) for m in self.members]
        return {k: np.nanmean([p[k] for p in ps], axis=0) for k in ps[0]}

    def contributions(self, te, lab="delay_12m"):
        cols = self.num + self.cat
        c = np.mean([m.clf_[lab].predict(m._X(te), pred_contrib=True)[:, :-1] for m in self.members if lab in m.clf_], axis=0)
        return cols, c

    def importance(self):
        return sum(m.importance() for m in self.members) / len(self.members)


def evaluate(te, p):
    r = dict(delay=metrics.classification(te["delay_12m"], p["p_delay"]), overrun=metrics.classification(te["cost_overrun_25"], p["p_over"]),
             cancel=(metrics.classification(te["cancelled"], p["p_cancel"]) if "p_cancel" in p and not np.all(np.isnan(p["p_cancel"])) else None),
             months_late=metrics.quantiles(te["months_late"], p["q_late"]), pct_overrun=metrics.quantiles(te["pct_overrun"].clip(-1, 5), p["q_over"]))
    done = te["months_late"].notna()
    if done.sum() >= 5:
        r["cod_mae_months_iso"] = float(np.abs(te.loc[done, "months_late"]).mean())
        r["cod_mae_months_model"] = float(np.abs(te.loc[done, "months_late"] - p["q_late"][done.values, 1]).mean())
    return r


def breakdowns(te, p, keys):
    out = {}
    for k in keys:
        out[k] = {}
        for g, idx in te.groupby(k).indices.items():
            if len(idx) < 40:
                continue
            sub = te.iloc[idx]; pp = {kk: np.asarray(v)[idx] for kk, v in p.items()}
            out[k][str(g)] = dict(n=int(len(idx)), delay=metrics.classification(sub["delay_12m"], pp["p_delay"]), overrun=metrics.classification(sub["cost_overrun_25"], pp["p_over"]),
                                  months_late=metrics.quantiles(sub["months_late"], pp["q_late"]))
    return out


def main(processed: Path, out: Path, cutoff: str, n_bags: int):
    out.mkdir(parents=True, exist_ok=True)
    ex = pd.read_parquet(processed / "examples.parquet")
    f, num, cat = features.design(ex)
    f["cost_bucket"] = pd.cut(f["est_cost_musd"].fillna(0), [-1, 1, 5, 20, 100, 1e9], labels=["<1M", "1-5M", "5-20M", "20-100M", ">100M"]).astype(str)
    f["horizon_bucket"] = pd.cut(f["months_to_expected_isd"].fillna(0), [-1e9, 0, 6, 12, 24, 1e9], labels=["past due", "0-6m", "6-12m", "12-24m", ">24m"]).astype(str)
    f["type"] = f["upgrade_type"].astype(str)
    test = f[f["obs_date"] > cutoff].copy()
    test["origin"] = test["obs_date"].dt.to_period("M").dt.to_timestamp()      # retrain once per test month
    origins = sorted(test["origin"].unique())
    print(f"{len(origins)} origins: {[str(pd.Timestamp(o).date()) for o in origins]}; test {len(test)} examples, {test.upgrade_id.nunique()} upgrades", flush=True)
    preds = {}; contribs = []; importance = None; pieces = []; origin_stats = []
    zoo_names = [m.name for m in model_zoo(num, cat, 1)]
    for o in origins:
        o = pd.Timestamp(o)
        te = test[test["origin"] == o].copy()
        first_obs = te["obs_date"].min()
        tr = pit.known_by(f[f["obs_date"] < first_obs], first_obs)
        te["new_upgrade"] = ~te["upgrade_id"].isin(set(tr["upgrade_id"]))
        st = dict(origin=str(first_obs.date()), n_train=int(len(tr)), n_test=int(len(te)), delay_labels_train=int(tr.delay_12m.notna().sum()), overrun_labels_train=int(tr.cost_overrun_25.notna().sum()),
                  cancel_labels_train=int(tr.cancelled.notna().sum()), train_delay_rate=float(tr.delay_12m.mean()) if tr.delay_12m.notna().any() else None, events_train=int(tr.event_done.sum()))
        t0 = time.time()
        for m in model_zoo(num, cat, n_bags):
            try:
                p = m.fit(tr).predict(te)
            except Exception as e:
                print(f"  {m.name} failed at {st['origin']}: {e}", flush=True); continue
            preds.setdefault(m.name, []).append(pd.DataFrame({"idx": te.index, "p_delay": p["p_delay"], "p_over": p["p_over"], "p_cancel": p.get("p_cancel", np.full(len(te), np.nan)),
                                                             "late_p10": p["q_late"][:, 0], "late_p50": p["q_late"][:, 1], "late_p90": p["q_late"][:, 2],
                                                             "over_p10": p["q_over"][:, 0], "over_p50": p["q_over"][:, 1], "over_p90": p["q_over"][:, 2],
                                                             "p50_capped": (p["q_capped"][:, 1] if "q_capped" in p else np.zeros(len(te), bool)), "p90_capped": (p["q_capped"][:, 2] if "q_capped" in p else np.zeros(len(te), bool)),
                                                             "beyond_followup": (p["horizon_beyond_followup"] if "horizon_beyond_followup" in p else np.zeros(len(te), bool)),
                                                             "max_followup": (p["max_followup_months"] if "max_followup_months" in p else np.full(len(te), np.nan))}))
            if m.name == "gbm":
                cols, c = m.contributions(te)
                order = np.argsort(-np.abs(c), axis=1)[:, :5]
                contribs.append(pd.DataFrame({"idx": te.index, "drivers": [json.dumps([dict(f=cols[j], v=(None if pd.isna(te.iloc[i][cols[j]]) else (round(float(te.iloc[i][cols[j]]), 1) if cols[j] in num else str(te.iloc[i][cols[j]])[:24])), c=round(float(c[i, j]), 2)) for j in order[i]]) for i in range(len(te))]}))
                importance = m.importance() if importance is None else importance + m.importance()
        st["seconds"] = round(time.time() - t0, 1); origin_stats.append(st); pieces.append(te)
        print(f"  origin {st['origin']}: train {st['n_train']} (delay labels {st['delay_labels_train']}, rate {st['train_delay_rate']}), test {st['n_test']}, {st['seconds']}s", flush=True)
    test = pd.concat(pieces).sort_index()
    results = {}
    for name, parts in preds.items():
        pp = pd.concat(parts).set_index("idx").loc[test.index]
        p = dict(p_delay=pp["p_delay"].values, p_over=pp["p_over"].values, p_cancel=pp["p_cancel"].values, q_late=pp[["late_p10", "late_p50", "late_p90"]].values, q_over=pp[["over_p10", "over_p50", "over_p90"]].values)
        nw = test["new_upgrade"].values
        results[name] = dict(all=evaluate(test, p), new_upgrades=evaluate(test[nw], {k: np.asarray(v)[nw] for k, v in p.items()}),
                             by_origin={str(o.date()): evaluate(test[test.origin == o], {k: np.asarray(v)[(test.origin == o).values] for k, v in p.items()}) for o in origins})
        if name in ("gbm", "blend", "dt_survival"):
            results[name]["breakdowns"] = breakdowns(test, p, ["to", "voltage_class", "type", "equipment", "cost_bucket", "horizon_bucket", "status"])
            for lab, key in (("delay_12m", "p_delay"), ("cost_overrun_25", "p_over")):
                metrics.reliability(test[lab], p[key]).to_csv(out / f"reliability_{name}_{lab}.csv", index=False)
        d, o_ = results[name]["all"]["delay"], results[name]["all"]["overrun"]
        print(f"{name:28s} delay AUROC {d.get('auroc', float('nan')):.3f} Brier {d.get('brier', float('nan')):.3f} | overrun AUROC {o_.get('auroc', float('nan')):.3f} Brier {o_.get('brier', float('nan')):.3f} | "
              f"COD MAE model {results[name]['all'].get('cod_mae_months_model', float('nan')):.1f} vs ISO {results[name]['all'].get('cod_mae_months_iso', float('nan')):.1f} months", flush=True)
    summary = dict(protocol="rolling-origin: refit each test month on examples observed earlier with labels knowable by then", first_cutoff=cutoff, origins=origin_stats,
                   n_test=int(len(test)), n_test_new=int(test.new_upgrade.sum()), test_upgrades=int(test.upgrade_id.nunique()), n_train=origin_stats[0]["n_train"], n_train_last=origin_stats[-1]["n_train"],
                   train_upgrades=int(f.loc[f.obs_date <= cutoff, "upgrade_id"].nunique()), test_obs_dates=sorted(test.obs_date.dt.date.astype(str).unique().tolist()),
                   delay_rate_test=float(test.delay_12m.mean()), overrun_rate_test=float(test.cost_overrun_25.mean()), n_delay_labels_test=int(test.delay_12m.notna().sum()),
                   n_overrun_labels_test=int(test.cost_overrun_25.notna().sum()), results=results,
                   feature_importance=(importance.sort_values("delay_12m", ascending=False).head(25).round(1).to_dict() if importance is not None else None))
    json.dump(summary, open(out / "benchmark.json", "w"), indent=1, default=float)
    rows = []
    for name, r in results.items():
        a = r["all"]; nw = r["new_upgrades"]
        rows.append(dict(model=name, delay_auroc=a["delay"].get("auroc"), delay_brier=a["delay"].get("brier"), delay_ece=a["delay"].get("ece"), delay_prauc=a["delay"].get("pr_auc"),
                         over_auroc=a["overrun"].get("auroc"), over_brier=a["overrun"].get("brier"), over_prauc=a["overrun"].get("pr_auc"), cancel_auroc=(a["cancel"] or {}).get("auroc"),
                         cod_mae=a.get("cod_mae_months_model"), p50_cov=a["months_late"].get("cov_p50"), p90_cov=a["months_late"].get("cov_p90"),
                         new_delay_auroc=nw["delay"].get("auroc"), new_over_auroc=nw["overrun"].get("auroc")))
    tab = pd.DataFrame(rows)
    with open(out / "benchmark_main.md", "w") as fh:
        fh.write(f"Rolling-origin chronological benchmark: {len(origins)} test months from {origin_stats[0]['origin']} to {origin_stats[-1]['origin']}; at each, models are refitted on examples observed earlier "
                 f"({origin_stats[0]['n_train']}–{origin_stats[-1]['n_train']} rows) using only labels knowable by then, and score that month's {'/'.join(str(s['n_test']) for s in origin_stats)} examples "
                 f"(pooled: {len(test)} examples, {test.upgrade_id.nunique()} upgrades, {int(test.new_upgrade.sum())} examples of upgrades unseen before their origin).\n\n")
        fh.write(tab.round(3).to_markdown(index=False))
    pt = test[["upgrade_id", "obs_date", "origin", "to", "voltage_kv", "voltage_class", "equipment", "task", "status", "scope", "est_cost_musd", "expected_isd", "required_date", "age_months", "slip_so_far_months",
               "n_isd_revisions", "cost_growth_so_far", "pct_complete", "months_to_expected_isd", "delay_12m", "cost_overrun_25", "cancelled", "months_late", "pct_overrun", "resolved_done", "resolved_cancel",
               "actual_isd", "final_cost_musd", "last_obs", "new_upgrade"]].copy()
    for name, parts in preds.items():
        pp = pd.concat(parts).set_index("idx").loc[test.index]
        for c in pp.columns:
            pt[f"{name}_{c}"] = pp[c].values
    if contribs:
        pt["gbm_drivers"] = pd.concat(contribs).set_index("idx").loc[test.index, "drivers"].values
    pt.to_parquet(out / "predictions_test.parquet", index=False)
    print(tab.round(3).to_string(index=False))
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--processed", default=str(PROCESSED))
    ap.add_argument("--out", default=str(TABLES))
    ap.add_argument("--cutoff", default="2017-12-31", help="observations after this date form the test period")
    ap.add_argument("--n-bags", type=int, default=2)
    a = ap.parse_args()
    main(Path(a.processed), Path(a.out), a.cutoff, a.n_bags)
