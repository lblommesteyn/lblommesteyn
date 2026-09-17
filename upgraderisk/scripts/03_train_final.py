"""Train the final model bundle on all examples observed up to the cutoff (same cutoff as the benchmark, so the
bundle's quality is exactly what the benchmark measured) and save it for the CLI / UI / case studies."""
from __future__ import annotations
import argparse, json, pickle, sys, time
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from upgraderisk import features, models, pit
from upgraderisk.config import PROCESSED, SEED


def main(processed: Path, cutoff: str, n_bags: int):
    ex = pd.read_parquet(processed / "examples.parquet")
    f, num, cat = features.design(ex)
    if cutoff == "last":
        cutoff = str(f["obs_date"].max().date())
    tr = pit.known_by(f[f["obs_date"] <= cutoff], cutoff)   # only outcomes knowable at the cutoff
    t0 = time.time()
    members = [models.GBMRisk(num, cat, seed=SEED + i).fit(tr) for i in range(n_bags)]
    surv = models.DiscreteTimeSurvival(num, cat, seed=SEED).fit(tr)
    # analog index: resolved training examples with their outcomes (for "similar past upgrades")
    keep = ["upgrade_id", "obs_date", "to", "voltage_kv", "voltage_class", "equipment", "task", "status", "est_cost_musd", "expected_isd", "months_to_expected_isd",
            "age_months", "slip_so_far_months", "scope", "facility", "upgrade_type", "delay_12m", "months_late", "cost_overrun_25", "pct_overrun", "resolved_done",
            "resolved_cancel", "actual_isd", "final_cost_musd", "cancelled", "delay_known_date", "overrun_known_date", "done_known_date", "cancel_label_known_date"]
    analogs = f.loc[f["obs_date"] <= cutoff, keep].copy()   # full outcomes; the predictor filters by what was known at the as-of date
    bundle = dict(cutoff=cutoff, trained_at=time.strftime("%Y-%m-%d"), n_train=int(len(tr)), num=num, cat=cat, members=members, survival=surv, analogs=analogs,
                  train_examples=tr[["upgrade_id", "obs_date", "to", "voltage_class", "equipment", "status", "delay_12m", "cost_overrun_25", "delay_known_date", "overrun_known_date"]].copy(),
                  analog_outcomes_note="analog outcomes are shown as known today (they may not have been known at the as-of date)",
                  seconds=round(time.time() - t0, 1))
    with open(processed / "model_bundle.pkl", "wb") as fh:
        pickle.dump(bundle, fh)
    print(json.dumps(dict(cutoff=cutoff, n_train=len(tr), n_bags=n_bags, seconds=bundle["seconds"])))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--processed", default=str(PROCESSED))
    ap.add_argument("--cutoff", default="last", help="'last' = labels knowable at the last observation date")
    ap.add_argument("--n-bags", type=int, default=3)
    a = ap.parse_args()
    main(Path(a.processed), a.cutoff, a.n_bags)
