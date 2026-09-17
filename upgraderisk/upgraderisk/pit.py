"""Point-in-time views over the longitudinal table upgrade x snapshot_date.

The long table has one row per (upgrade_id, snapshot_date). A snapshot is what the ISO published on
snapshot_date: current estimate, expected in-service date, status. Features at observation date t may
only use rows with snapshot_date <= t; labels use rows with snapshot_date > t.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from .config import DELAY_MONTHS, OVERRUN_FRAC

TERMINAL_DONE = {"in service", "in-service", "complete", "completed", "energized"}
TERMINAL_CANCEL = {"cancelled", "canceled", "withdrawn", "removed", "terminated", "retired"}


def _months(a, b) -> float:
    """Whole-and-fractional months from a to b (positive when b is later)."""
    a, b = pd.Timestamp(a), pd.Timestamp(b)
    return (b - a).days / 30.4375


def norm_status(s) -> str:
    s = str(s or "").strip().lower()
    if any(k in s for k in TERMINAL_CANCEL):
        return "cancelled"
    if any(k in s for k in TERMINAL_DONE):
        return "in_service"
    return "active" if s else "unknown"


def prepare(long: pd.DataFrame) -> pd.DataFrame:
    d = long.copy()
    d["snapshot_date"] = pd.to_datetime(d["snapshot_date"])
    d["expected_isd"] = pd.to_datetime(d["expected_isd"], errors="coerce")
    d["actual_isd"] = pd.to_datetime(d.get("actual_isd"), errors="coerce")
    d["est_cost_musd"] = pd.to_numeric(d["est_cost_musd"], errors="coerce")
    d["status_n"] = d["status"].map(norm_status)
    if "cancelled" in d:
        d.loc[d["cancelled"].fillna(False).astype(bool), "status_n"] = "cancelled"
    return d.sort_values(["upgrade_id", "snapshot_date"]).reset_index(drop=True)


def as_of(long: pd.DataFrame, t) -> pd.DataFrame:
    """Latest snapshot per upgrade with snapshot_date <= t (strict point-in-time)."""
    t = pd.Timestamp(t)
    v = long[long["snapshot_date"] <= t]
    return v.groupby("upgrade_id", sort=False).tail(1).reset_index(drop=True)


def history_features(long: pd.DataFrame, t) -> pd.DataFrame:
    """Per-upgrade features from all snapshots <= t: age in the table, number of estimate revisions,
    cumulative slip and cost growth since first publication, months to the currently expected ISD."""
    t = pd.Timestamp(t)
    v = long[long["snapshot_date"] <= t]
    g = v.groupby("upgrade_id", sort=False)
    first = g.head(1).set_index("upgrade_id")
    last = g.tail(1).set_index("upgrade_id")
    out = pd.DataFrame(index=last.index)
    out["obs_date"] = t
    out["n_snapshots"] = g.size()
    out["age_months"] = [(t - d).days / 30.4375 for d in first["snapshot_date"]]
    out["first_expected_isd"] = first["expected_isd"]
    out["expected_isd"] = last["expected_isd"]
    out["slip_so_far_months"] = [(_months(a, b) if pd.notna(a) and pd.notna(b) else np.nan) for a, b in zip(first["expected_isd"], last["expected_isd"])]
    out["first_cost_musd"] = first["est_cost_musd"]
    out["est_cost_musd"] = last["est_cost_musd"]
    out["cost_growth_so_far"] = (last["est_cost_musd"] / first["est_cost_musd"] - 1.0).replace([np.inf, -np.inf], np.nan)
    out["months_to_expected_isd"] = [(_months(t, d) if pd.notna(d) else np.nan) for d in last["expected_isd"]]
    n_isd_changes = g["expected_isd"].apply(lambda s: int((s.dropna().diff().dropna() != pd.Timedelta(0)).sum()))
    n_cost_changes = g["est_cost_musd"].apply(lambda s: int((s.dropna().diff().dropna().abs() > 1e-9).sum()))
    out["n_isd_revisions"] = n_isd_changes
    out["n_cost_revisions"] = n_cost_changes
    out["status_n"] = last["status_n"]
    for c in ("to", "facility", "voltage_kv", "upgrade_type", "scope", "source"):
        if c in last:
            out[c] = last[c]
    return out.reset_index()


def outcomes(long: pd.DataFrame, t, horizon_end=None) -> pd.DataFrame:
    """Labels for each upgrade active at t, using only snapshots AFTER t (plus the reference values at t).

    resolved_done   : later snapshot shows in service (actual_isd known or status in service)
    resolved_cancel : later snapshot shows cancelled/withdrawn
    delay_12m       : 1 if in-service date (actual, or the fact of still being unbuilt) is > DELAY_MONTHS after
                      the expected ISD published at t; 0 if completed within that window; NaN when censored
                      (last observation before expected_isd_t + DELAY_MONTHS and not yet done)
    cost_overrun_25 : 1 if the final (or latest) cost exceeds est_cost_t by > OVERRUN_FRAC; 0 if resolved
                      without exceeding; NaN when unresolved and not (yet) exceeded
    months_late     : actual_isd - expected_isd_t in months (completed only)
    pct_overrun     : final_cost / est_cost_t - 1 (resolved only)
    time_to_done_m  : months from t to actual in-service (completed) / to last observation (censored)
    event_done      : 1 if completed (for survival models), 0 if censored
    """
    t = pd.Timestamp(t)
    ref = as_of(long, t)
    ref = ref[ref["status_n"] == "active"]
    later = long[long["snapshot_date"] > t]
    if horizon_end is not None:
        later = later[later["snapshot_date"] <= pd.Timestamp(horizon_end)]
    rows = []
    for r in ref.itertuples(index=False):
        h = later[later["upgrade_id"] == r.upgrade_id]
        last_obs = h["snapshot_date"].max() if len(h) else t
        done = h[h["status_n"] == "in_service"]
        canc = h[h["status_n"] == "cancelled"]
        first_done = done.iloc[0] if len(done) else None
        first_canc = canc.iloc[0] if len(canc) else None
        # a cancellation seen before completion wins
        if first_canc is not None and (first_done is None or first_canc["snapshot_date"] < first_done["snapshot_date"]):
            first_done = None
        else:
            first_canc = None
        actual = None
        if first_done is not None:
            actual = first_done["actual_isd"] if pd.notna(first_done["actual_isd"]) else first_done["snapshot_date"]
        exp_t = r.expected_isd
        cost_t = r.est_cost_musd
        final_cost = (first_done["est_cost_musd"] if first_done is not None else
                      (first_canc["est_cost_musd"] if first_canc is not None else (h["est_cost_musd"].dropna().iloc[-1] if h["est_cost_musd"].notna().any() else np.nan)))
        # delay label
        delay = np.nan; months_late = np.nan
        if pd.notna(exp_t):
            if actual is not None:
                months_late = _months(exp_t, actual); delay = float(months_late > DELAY_MONTHS)
            elif first_canc is not None:
                delay = np.nan  # cancelled: delay undefined (reported separately)
            elif _months(exp_t, last_obs) > DELAY_MONTHS:
                delay = 1.0     # still not built more than DELAY_MONTHS after the promised date
        # cost label
        over = np.nan; pct = np.nan
        if pd.notna(cost_t) and cost_t > 0 and pd.notna(final_cost):
            pct = final_cost / cost_t - 1.0
            if first_done is not None or first_canc is not None:
                over = float(pct > OVERRUN_FRAC)
            elif pct > OVERRUN_FRAC:
                over = 1.0
        rows.append(dict(upgrade_id=r.upgrade_id, obs_date=t, expected_isd_t=exp_t, est_cost_t=cost_t,
                         resolved_done=int(first_done is not None), resolved_cancel=int(first_canc is not None),
                         actual_isd=actual, final_cost_musd=final_cost, delay_12m=delay, months_late=months_late,
                         cost_overrun_25=over, pct_overrun=pct if (first_done is not None or first_canc is not None) else np.nan,
                         pct_growth_latest=pct, last_obs=last_obs,
                         time_to_done_m=_months(t, actual) if actual is not None else _months(t, last_obs),
                         event_done=int(first_done is not None)))
    return pd.DataFrame(rows)


def build_examples(long: pd.DataFrame, obs_dates) -> pd.DataFrame:
    """Stack (features at t, labels after t) for every observation date."""
    parts = []
    for t in obs_dates:
        f = history_features(long, t)
        f = f[f["status_n"] == "active"]
        y = outcomes(long, t)
        parts.append(f.merge(y, on=["upgrade_id", "obs_date"], how="inner"))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def vintage_check(long: pd.DataFrame, t) -> bool:
    """Features at t must be identical whether or not the future rows are present in the table."""
    full = history_features(long, t).set_index("upgrade_id").sort_index()
    trunc = history_features(long[long["snapshot_date"] <= pd.Timestamp(t)], t).set_index("upgrade_id").sort_index()
    pd.testing.assert_frame_equal(full, trunc, check_like=True)
    return True
