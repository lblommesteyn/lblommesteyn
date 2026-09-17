"""Vintage / leakage tests. On the synthetic toy table always; on the real long table when it exists."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from upgraderisk import pit
from upgraderisk.config import PROCESSED
from tests.test_pit import toy


def _check_examples_pit(prep, ex):
    # every label field is either NaN or derived from rows strictly after obs_date
    for r in ex.sample(min(len(ex), 200), random_state=0).itertuples():
        later = prep[(prep.upgrade_id == r.upgrade_id) & (prep.snapshot_date > r.obs_date)]
        earlier = prep[(prep.upgrade_id == r.upgrade_id) & (prep.snapshot_date <= r.obs_date)]
        assert r.n_snapshots == len(earlier)
        assert r.snapshot_date >= r.obs_date - pd.Timedelta(days=pit.MAX_REF_AGE_DAYS)
        if r.resolved_done == 1:
            assert (later.status_n == "in_service").any()
        if r.resolved_done == 0 and r.resolved_cancel == 0:
            assert not (later.status_n == "in_service").any()
        # feature values equal the latest snapshot at or before obs_date
        last = earlier[earlier.is_status_source].sort_values("snapshot_date").iloc[-1]
        if pd.notna(last.est_cost_musd):
            assert abs(r.est_cost_musd - last.est_cost_musd) < 1e-9


def test_toy_vintage():
    d = toy()
    ex = pit.build_examples(d, ["2020-02-01", "2020-08-01", "2021-08-01"])
    _check_examples_pit(d, ex)
    for t in ["2020-02-01", "2021-08-01"]:
        assert pit.vintage_check(d, t)


@pytest.mark.skipif(not (PROCESSED / "snapshots_long.parquet").exists(), reason="real long table not built yet")
def test_real_vintage():
    long = pd.read_parquet(PROCESSED / "snapshots_long.parquet")
    prep = pit.prepare(long)
    obs = sorted(prep.loc[prep["source"].str.contains("construct_status"), "snapshot_date"].unique())
    for t in obs[:: max(1, len(obs) // 5)]:
        assert pit.vintage_check(prep, t)
    ex = pd.read_parquet(PROCESSED / "examples.parquet")
    _check_examples_pit(prep, ex)
    # no label can be resolved by a snapshot at or before its own observation date
    assert (ex["last_obs"] >= ex["obs_date"]).all()
    done = ex[ex.resolved_done == 1]
    assert (pd.to_datetime(done["done_known_date"]) > done["obs_date"]).all()      # completion never knowable at observation
    assert (pd.to_datetime(done["actual_isd"]) > done["obs_date"]).mean() > 0.75   # recorded in-service dates mostly after observation
