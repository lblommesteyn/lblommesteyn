"""Build the longitudinal table (upgrade x snapshot_date) from the fetched PJM snapshots, then the
point-in-time example table (features at each observation date, labels strictly from later snapshots).

Outputs (data/processed): snapshots_long.parquet, examples.parquet, dataset_summary.json
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from upgraderisk import pit
from upgraderisk.config import PROCESSED, MIN_RESOLVED_FOR_MODELING, DELAY_MONTHS, OVERRUN_FRAC
from upgraderisk.pjm_snapshots import build_long, SNAP_DIR


def main(snap_dir: Path, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    long = build_long(snap_dir)
    long.to_parquet(out / "snapshots_long.parquet", index=False)
    prep = pit.prepare(long)
    # observation dates = the legacy construction-status snapshot dates (the only dates with projected ISDs + status)
    obs = sorted(prep.loc[prep["source"].str.contains("construct_status"), "snapshot_date"].unique())
    ex = pit.build_examples(prep, obs)
    ex.to_parquet(out / "examples.parquet", index=False)
    for t in obs[:: max(1, len(obs) // 8)]:
        pit.vintage_check(prep, t)
    resolved = ex[(ex.resolved_done == 1) | (ex.resolved_cancel == 1)]
    uniq_resolved = resolved["upgrade_id"].nunique()
    summ = dict(
        n_snapshot_rows=int(len(long)), n_upgrades=int(long["upgrade_id"].nunique()),
        sources={k: int(v) for k, v in long["src_family"].value_counts().items()},
        snapshot_dates=dict(legacy_construct_status=[str(pd.Timestamp(t).date()) for t in obs],
                            cost_allocation=[str(pd.Timestamp(t).date()) for t in sorted(prep.loc[prep["source"].str.contains("cost_allocation"), "snapshot_date"].unique())],
                            live=[str(pd.Timestamp(t).date()) for t in sorted(prep.loc[prep["source"].str.startswith("live"), "snapshot_date"].unique())]),
        n_examples=int(len(ex)), n_example_upgrades=int(ex["upgrade_id"].nunique()),
        examples_resolved_done=int((ex.resolved_done == 1).sum()), examples_resolved_cancel=int((ex.resolved_cancel == 1).sum()),
        unique_upgrades_resolved=int(uniq_resolved),
        delay_label_available=int(ex["delay_12m"].notna().sum()), delay_rate=float(ex["delay_12m"].mean()) if ex["delay_12m"].notna().any() else None,
        overrun_label_available=int(ex["cost_overrun_25"].notna().sum()), overrun_rate=float(ex["cost_overrun_25"].mean()) if ex["cost_overrun_25"].notna().any() else None,
        censored_examples=int(((ex.resolved_done == 0) & (ex.resolved_cancel == 0)).sum()),
        months_late_quantiles={str(q): float(v) for q, v in ex["months_late"].dropna().quantile([.1, .25, .5, .75, .9]).items()} if ex["months_late"].notna().any() else None,
        pct_overrun_quantiles={str(q): float(v) for q, v in ex["pct_overrun"].dropna().quantile([.1, .25, .5, .75, .9]).items()} if ex["pct_overrun"].notna().any() else None,
        definitions=dict(delay_months=DELAY_MONTHS, overrun_frac=OVERRUN_FRAC),
        go_no_go=dict(threshold=MIN_RESOLVED_FOR_MODELING, unique_resolved=int(uniq_resolved), proceed=bool(uniq_resolved >= MIN_RESOLVED_FOR_MODELING)),
    )
    json.dump(summ, open(out / "dataset_summary.json", "w"), indent=1)
    print(json.dumps(summ, indent=1))
    return summ


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--snap-dir", default=str(SNAP_DIR))
    ap.add_argument("--out", default=str(PROCESSED))
    a = ap.parse_args()
    main(Path(a.snap_dir), Path(a.out))
