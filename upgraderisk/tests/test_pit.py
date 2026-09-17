"""Unit tests on a tiny hand-made long table (the only synthetic data in upgraderisk)."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from upgraderisk import pit


def toy():
    rows = [
        # b1: promised 2021-06 at $10M, slips to 2022-12 and $14M, in service 2023-01  -> late 19 months, +40 %
        ("b1", "2020-01-15", 10.0, "2021-06-01", "Engineering", None),
        ("b1", "2020-07-15", 11.0, "2021-12-01", "Engineering", None),
        ("b1", "2021-07-15", 14.0, "2022-12-01", "Under Construction", None),
        ("b1", "2023-02-15", 14.0, "2022-12-01", "In Service", "2023-01-20"),
        # b2: on time, cost flat
        ("b2", "2020-01-15", 5.0, "2020-12-01", "Under Construction", None),
        ("b2", "2020-07-15", 5.0, "2020-12-01", "Under Construction", None),
        ("b2", "2021-01-15", 5.2, "2020-12-01", "In Service", "2020-11-30"),
        # b3: cancelled
        ("b3", "2020-01-15", 50.0, "2024-06-01", "Conceptual", None),
        ("b3", "2021-07-15", 50.0, "2024-06-01", "Cancelled", None),
        # b4: censored (never resolves in table); by 2023-02 it is >12 months past the 2021-06 promise
        ("b4", "2020-01-15", 20.0, "2021-06-01", "Engineering", None),
        ("b4", "2023-02-15", 30.0, "2024-06-01", "Engineering", None),
    ]
    d = pd.DataFrame(rows, columns=["upgrade_id", "snapshot_date", "est_cost_musd", "expected_isd", "status", "actual_isd"])
    d["source"] = "toy_construct_status"; d["to"] = "TO1"; d["facility"] = "F"; d["voltage_kv"] = 230; d["upgrade_type"] = "baseline"; d["scope"] = ""
    return pit.prepare(d)


def test_as_of_is_point_in_time():
    d = toy()
    v = pit.as_of(d, "2020-08-01").set_index("upgrade_id")
    assert v.loc["b1", "est_cost_musd"] == 11.0 and v.loc["b1", "snapshot_date"] == pd.Timestamp("2020-07-15")
    assert "b4" not in v.index                      # last seen 2020-01-15: no recent status snapshot -> not active at t
    v2 = pit.as_of(d, "2020-08-01", max_age_days=10000).set_index("upgrade_id")
    assert "b4" in v2.index and v2.loc["b4", "est_cost_musd"] == 20.0


def test_outcomes():
    d = toy()
    y = pit.outcomes(d, "2020-02-01").set_index("upgrade_id")
    assert y.loc["b1", "delay_12m"] == 1 and abs(y.loc["b1", "months_late"] - 19.7) < 0.5
    assert y.loc["b1", "cost_overrun_25"] == 1 and abs(y.loc["b1", "pct_overrun"] - 0.4) < 1e-9
    assert y.loc["b2", "delay_12m"] == 0 and y.loc["b2", "cost_overrun_25"] == 0 and y.loc["b2", "event_done"] == 1
    assert y.loc["b3", "resolved_cancel"] == 1 and np.isnan(y.loc["b3", "delay_12m"])
    assert y.loc["b4", "delay_12m"] == 1 and y.loc["b4", "event_done"] == 0          # known late, still censored for completion
    assert y.loc["b4", "cost_overrun_25"] == 1 and np.isnan(y.loc["b4", "pct_overrun"])  # already exceeded, not final


def test_outcomes_censored_when_too_early():
    d = toy()
    y = pit.outcomes(d[d.snapshot_date <= "2021-01-31"], "2020-02-01").set_index("upgrade_id")
    assert np.isnan(y.loc["b1", "delay_12m"])  # last obs 2021-01 < 2021-06 + 12 months, not done
    assert np.isnan(y.loc["b4", "cost_overrun_25"])


def test_history_features_and_vintage():
    d = toy()
    f = pit.history_features(d, "2021-08-01").set_index("upgrade_id")
    assert f.loc["b1", "n_snapshots"] == 3 and f.loc["b1", "n_isd_revisions"] == 2 and abs(f.loc["b1", "cost_growth_so_far"] - 0.4) < 1e-9
    assert pit.vintage_check(d, "2021-08-01")
    ex = pit.build_examples(d, ["2020-02-01", "2021-08-01"])
    assert set(ex.columns) >= {"delay_12m", "cost_overrun_25", "age_months", "slip_so_far_months"}
    assert (ex["obs_date"] < ex["last_obs"]).all() or ex.empty
