"""Chronological benchmark: train on examples observed up to a cutoff, test on examples observed after it,
for every baseline and model. Also a stricter test on upgrades never seen before the cutoff, and breakdowns.

Outputs (outputs/tables): benchmark.json, benchmark_main.md, reliability_*.csv, breakdowns.json, predictions_test.parquet
"""
from __future__ import annotations
import argparse, json, sys, time, warnings
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from upgraderisk import features, baselines, models, metrics
from upgraderisk.config import PROCESSED, TABLES, SEED

warnings.filterwarnings("ignore")


def model_zoo(num, cat, n_bags):
    zoo = [baselines.AlwaysOnTime(), baselines.BaseRate(), baselines.ProjectAgeHeuristic(), baselines.GroupRate("to"), baselines.GroupRate("voltage_class"),
           baselines.GroupRate("equipment"), baselines.SmallLogistic(["voltage_kv", "log_cost", "months_to_expected_isd"], "logit_voltage_cost_duration"),
           baselines.SmallLogistic([c for c in num if not c.startswith(("rate_", "n_", "global_"))], "logit_numeric")]
    zoo.append(BaggedGBM(num, cat, n_bags))
    try:
        import lifelines  # noqa
        zoo.append(models.CoxSurvival(num))
    except ImportError:
        pass
    return zoo


class BaggedGBM:
    name = "gbm"

    def __init__(self, num, cat, n_bags):
        self.members = [models.GBMRisk(num, cat, seed=SEED + i) for i in range(n_bags)]

    def fit(self, tr):
        for m in self.members:
            m.fit(tr)
        return self

    def predict(self, te):
        ps = [m.predict(te) for m in self.members]
        return {k: np.mean([p[k] for p in ps], axis=0) for k in ps[0]}

    def importance(self):
        return sum(m.importance() for m in self.members) / len(self.members)


def evaluate(te, p):
    r = dict(delay=metrics.classification(te["delay_12m"], p["p_delay"]), overrun=metrics.classification(te["cost_overrun_25"], p["p_over"]),
             months_late=metrics.quantiles(te["months_late"], p["q_late"]), pct_overrun=metrics.quantiles(te["pct_overrun"].clip(-1, 5), p["q_over"]))
    # completion-month error: predicted COD = expected_isd_t + P50 months late vs actual
    done = te["months_late"].notna()
    if done.sum() >= 5:
        r["cod_mae_months_iso"] = float(np.abs(te.loc[done, "months_late"]).mean())          # error of the ISO's own date
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
    tr = f[f["obs_date"] <= cutoff].copy(); te = f[f["obs_date"] > cutoff].copy()
    seen_before = set(tr["upgrade_id"]); te["new_upgrade"] = ~te["upgrade_id"].isin(seen_before)
    print(f"train {len(tr)} examples ({tr.upgrade_id.nunique()} upgrades, obs {tr.obs_date.min().date()}..{tr.obs_date.max().date()}); "
          f"test {len(te)} ({te.upgrade_id.nunique()} upgrades, obs {te.obs_date.min().date()}..{te.obs_date.max().date()}); new-in-test {int(te.new_upgrade.sum())}", flush=True)
    results, preds, importance = {}, {}, None
    for m in model_zoo(num, cat, n_bags):
        t0 = time.time()
        try:
            p = m.fit(tr).predict(te)
        except Exception as e:
            print(f"{m.name}: failed {e}"); continue
        results[m.name] = dict(all=evaluate(te, p), new_upgrades=evaluate(te[te.new_upgrade], {k: np.asarray(v)[te.new_upgrade.values] for k, v in p.items()}),
                               seconds=round(time.time() - t0, 1))
        preds[m.name] = p
        if m.name == "gbm":
            importance = m.importance()
            results[m.name]["breakdowns"] = breakdowns(te, p, ["to", "voltage_class", "type", "equipment", "cost_bucket", "horizon_bucket", "status"])
            for lab, key in (("delay_12m", "p_delay"), ("cost_overrun_25", "p_over")):
                metrics.reliability(te[lab], p[key]).to_csv(out / f"reliability_gbm_{lab}.csv", index=False)
        d, o = results[m.name]["all"]["delay"], results[m.name]["all"]["overrun"]
        print(f"{m.name:28s} delay AUROC {d.get('auroc', float('nan')):.3f} Brier {d.get('brier', float('nan')):.3f} | overrun AUROC {o.get('auroc', float('nan')):.3f} Brier {o.get('brier', float('nan')):.3f} | "
              f"COD MAE model {results[m.name]['all'].get('cod_mae_months_model', float('nan')):.1f} vs ISO {results[m.name]['all'].get('cod_mae_months_iso', float('nan')):.1f} months  ({results[m.name]['seconds']}s)", flush=True)
    summary = dict(cutoff=cutoff, n_train=int(len(tr)), n_test=int(len(te)), n_test_new=int(te.new_upgrade.sum()), train_upgrades=int(tr.upgrade_id.nunique()), test_upgrades=int(te.upgrade_id.nunique()),
                   test_obs_dates=sorted(te.obs_date.dt.date.astype(str).unique().tolist()), delay_rate_test=float(te.delay_12m.mean()), overrun_rate_test=float(te.cost_overrun_25.mean()),
                   n_delay_labels_test=int(te.delay_12m.notna().sum()), n_overrun_labels_test=int(te.cost_overrun_25.notna().sum()), results=results,
                   feature_importance=(importance.sort_values("delay_12m", ascending=False).head(25).round(1).to_dict() if importance is not None else None))
    json.dump(summary, open(out / "benchmark.json", "w"), indent=1, default=float)
    # main table
    rows = []
    for name, r in results.items():
        a = r["all"]; nw = r["new_upgrades"]
        rows.append(dict(model=name, delay_auroc=a["delay"].get("auroc"), delay_brier=a["delay"].get("brier"), delay_ece=a["delay"].get("ece"), delay_prauc=a["delay"].get("pr_auc"),
                         over_auroc=a["overrun"].get("auroc"), over_brier=a["overrun"].get("brier"), over_prauc=a["overrun"].get("pr_auc"),
                         cod_mae=a.get("cod_mae_months_model"), p50_cov=a["months_late"].get("cov_p50"), p90_cov=a["months_late"].get("cov_p90"),
                         new_delay_auroc=nw["delay"].get("auroc"), new_over_auroc=nw["overrun"].get("auroc")))
    tab = pd.DataFrame(rows)
    with open(out / "benchmark_main.md", "w") as fh:
        fh.write(f"Chronological holdout: train obs <= {cutoff} ({len(tr)} examples), test obs > {cutoff} ({len(te)} examples, {te.upgrade_id.nunique()} upgrades; {int(te.new_upgrade.sum())} examples of upgrades unseen before the cutoff).\n\n")
        fh.write(tab.round(3).to_markdown(index=False))
    # save test predictions for case studies / UI
    pt = te[["upgrade_id", "obs_date", "to", "voltage_kv", "est_cost_musd", "expected_isd", "delay_12m", "cost_overrun_25", "months_late", "pct_overrun", "new_upgrade"]].copy()
    for name, p in preds.items():
        pt[f"{name}_p_delay"] = p["p_delay"]; pt[f"{name}_p_over"] = p["p_over"]
        pt[f"{name}_late_p50"] = p["q_late"][:, 1]; pt[f"{name}_late_p90"] = p["q_late"][:, 2]
    pt.to_parquet(out / "predictions_test.parquet", index=False)
    print(tab.round(3).to_string(index=False))
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--processed", default=str(PROCESSED))
    ap.add_argument("--out", default=str(TABLES))
    ap.add_argument("--cutoff", default="2017-12-31")
    ap.add_argument("--n-bags", type=int, default=3)
    a = ap.parse_args()
    main(Path(a.processed), Path(a.out), a.cutoff, a.n_bags)
