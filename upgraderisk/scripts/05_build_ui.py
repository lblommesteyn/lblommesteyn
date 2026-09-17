"""Build the static prototype page: every holdout example (real upgrade x real historical date) scored by the
final bundle, with drivers, analogs and the eventual outcome, embedded as JSON in upgraderisk/app_template.html.
Output: outputs/ui/index.html"""
from __future__ import annotations
import argparse, json, pickle, sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from upgraderisk import features
from upgraderisk.config import PROCESSED, TABLES, OUTPUTS


def jd(x):
    if x is None or (isinstance(x, float) and np.isnan(x)) or (hasattr(x, "__class__") and x.__class__.__name__ == "NaTType"):
        return None
    if isinstance(x, (pd.Timestamp,)):
        return str(x.date())
    if isinstance(x, (np.floating,)):
        return None if np.isnan(x) else round(float(x), 4)
    if isinstance(x, (np.integer,)):
        return int(x)
    return x


def main(cutoff: str, max_rows: int, out: Path):
    with open(PROCESSED / "model_bundle.pkl", "rb") as fh:
        b = pickle.load(fh)
    ex = pd.read_parquet(PROCESSED / "examples.parquet")
    f, num, cat = features.design(ex)
    te = f[f["obs_date"] > cutoff].copy().sort_values(["obs_date", "upgrade_id"])
    seen = set(f.loc[f["obs_date"] <= cutoff, "upgrade_id"])
    if max_rows and len(te) > max_rows:
        te = te.sample(max_rows, random_state=0).sort_values(["obs_date", "upgrade_id"])
    ps = [m.predict(te) for m in b["members"]]
    p = {k: np.nanmean([x[k] for x in ps], axis=0) for k in ps[0]}
    s = b["survival"].predict(te)
    cols = b["num"] + b["cat"]
    contrib = np.mean([m.clf_["delay_12m"].predict(m._X(te), pred_contrib=True)[:, :-1] for m in b["members"]], axis=0)
    an = b["analogs"]; an = an[((an["resolved_done"] == 1) | (an["resolved_cancel"] == 1))]
    an_lc = np.log1p(an["est_cost_musd"].fillna(0).clip(lower=0)).values
    rows = []
    for i, (_, r) in enumerate(te.iterrows()):
        exp = r["expected_isd"]; cost = r["est_cost_musd"]
        def add_m(m):
            return None if pd.isna(exp) else str((exp + pd.Timedelta(days=float(m) * 30.4375)).date())
        order = np.argsort(-np.abs(contrib[i]))[:5]
        drivers = [dict(f=cols[j], v=(jd(r[cols[j]]) if cols[j] in b["num"] else str(r[cols[j]])[:24]), c=round(float(contrib[i][j]), 2)) for j in order]
        fam = str(r["upgrade_id"]).split(".")[0]
        d = (1.0 * (an["to"].astype(str) != str(r["to"])).values + 0.7 * (an["voltage_class"].astype(str) != str(r["voltage_class"])).values
             + 0.7 * (an["equipment"].astype(str) != str(r["equipment"])).values + 0.5 * (an["status"].astype(str) != str(r["status"])).values
             + 0.4 * np.abs(an_lc - np.log1p(max(float(cost) if pd.notna(cost) else 0, 0)))
             + 0.02 * np.abs(an["months_to_expected_isd"].fillna(0).values - (float(r["months_to_expected_isd"]) if pd.notna(r["months_to_expected_isd"]) else 0)))
        d = d + 99 * ((an["upgrade_id"].astype(str).str.split(".").str[0] == fam) | (an["obs_date"] >= r["obs_date"])).values
        idx = np.argsort(d)[:12]
        ana, seen_ids = [], set()
        for j in idx:
            a = an.iloc[j]
            if a["upgrade_id"] in seen_ids or d[j] >= 99:
                continue
            seen_ids.add(a["upgrade_id"])
            ana.append(dict(id=a["upgrade_id"], to=a["to"], kv=jd(a["voltage_kv"]), eq=str(a["equipment"])[:20], exp=jd(a["expected_isd"]), act=jd(a["actual_isd"]),
                            late=jd(a["months_late"]), over=jd(a["pct_overrun"]), canc=int(a["resolved_cancel"])))
            if len(ana) >= 4:
                break
        rows.append(dict(id=r["upgrade_id"], obs=str(r["obs_date"].date()), new=bool(r["upgrade_id"] not in seen), to=str(r["to"]), kv=jd(r["voltage_kv"]), vc=str(r["voltage_class"]),
                         eq=str(r["equipment"]), task=str(r["task"]), st=str(r["status"]), scope=str(r["scope"])[:160], cost=jd(cost), exp=jd(exp), req=jd(r["required_date"]),
                         age=jd(r["age_months"]), slip=jd(r["slip_so_far_months"]), nrev=int(r["n_isd_revisions"]), cg=jd(r["cost_growth_so_far"]), pc=jd(r["pct_complete"]),
                         h=jd(r["months_to_expected_isd"]),
                         pd_=round(float(p["p_delay"][i]), 3), po=round(float(p["p_over"][i]), 3), pc_=(None if np.isnan(p["p_cancel"][i]) else round(float(p["p_cancel"][i]), 3)),
                         ps=round(float(s["p_delay"][i]), 3), late=[round(float(x), 1) for x in p["q_late"][i]], over=[round(float(x), 3) for x in p["q_over"][i]],
                         cod=[add_m(x) for x in p["q_late"][i]], drv=drivers, ana=ana,
                         out=dict(done=int(r["resolved_done"]), canc=int(r["resolved_cancel"]), act=jd(r["actual_isd"]), ml=jd(r["months_late"]), dl=jd(r["delay_12m"]),
                                  ov=jd(r["cost_overrun_25"]), po=jd(r["pct_overrun"]), fc=jd(r["final_cost_musd"]), last=jd(r["last_obs"]))))
    bench = json.load(open(TABLES / "benchmark.json"))
    g = bench["results"]["gbm"]["all"]; base = bench["results"]["base_rate"]["all"]; best_base = max((k for k in bench["results"] if k not in ("gbm", "dt_survival")), key=lambda k: bench["results"][k]["all"]["delay"].get("auroc", 0))
    rel = {lab: pd.read_csv(TABLES / f"reliability_gbm_{lab}.csv").to_dict(orient="records") for lab in ("delay_12m", "cost_overrun_25")}
    summary = json.load(open(PROCESSED / "dataset_summary.json"))
    meta = dict(cutoff=cutoff, n_rows=len(rows), n_upgrades=int(te["upgrade_id"].nunique()), test_dates=sorted(te["obs_date"].dt.date.astype(str).unique().tolist()),
                delay_rate=round(float(te["delay_12m"].mean()), 3), over_rate=round(float(te["cost_overrun_25"].mean()), 3),
                gbm=dict(auroc=g["delay"].get("auroc"), brier=g["delay"].get("brier"), ece=g["delay"].get("ece"), over_auroc=g["overrun"].get("auroc"), over_brier=g["overrun"].get("brier"),
                         cod_mae=g.get("cod_mae_months_model"), iso_mae=g.get("cod_mae_months_iso"), p90=g["months_late"].get("cov_p90"), p50=g["months_late"].get("cov_p50")),
                base=dict(brier=base["delay"].get("brier"), over_brier=base["overrun"].get("brier")),
                best_baseline=dict(name=best_base, auroc=bench["results"][best_base]["all"]["delay"].get("auroc"), over_auroc=bench["results"][best_base]["all"]["overrun"].get("auroc")),
                new=dict(auroc=bench["results"]["gbm"]["new_upgrades"]["delay"].get("auroc"), over_auroc=bench["results"]["gbm"]["new_upgrades"]["overrun"].get("auroc"), n=bench["n_test_new"]),
                n_train=bench["n_train"], train_upgrades=bench["train_upgrades"], reliability=rel, snapshots=len(summary["snapshot_dates"]["legacy_construct_status"]),
                first_snapshot=summary["snapshot_dates"]["legacy_construct_status"][0], last_snapshot=summary["snapshot_dates"]["legacy_construct_status"][-1],
                resolved=summary["unique_upgrades_resolved"], upgrades_total=summary["n_upgrades"])
    tpl = (Path(__file__).resolve().parents[1] / "upgraderisk" / "app_template.html").read_text()
    html = tpl.replace("/*__META__*/null", json.dumps(meta)).replace("/*__ROWS__*/[]", json.dumps(rows, separators=(",", ":")))
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(html)
    print(f"rows {len(rows)}  upgrades {meta['n_upgrades']}  bytes {len(html.encode()):,}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--cutoff", default="2017-12-31"); ap.add_argument("--max-rows", type=int, default=0); ap.add_argument("--out", default=str(OUTPUTS / "ui"))
    a = ap.parse_args(); main(a.cutoff, a.max_rows, Path(a.out))
