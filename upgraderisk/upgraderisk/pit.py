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
# snapshot families that carry a construction status and a projected in-service date; the cost-allocation view
# lists every baseline upgrade (finished ones included) with a bare not-cancelled flag and is never a reference
STATUS_SOURCES = ("construct_status", "xml_toup_planned", "live_export")
MAX_REF_AGE_DAYS = 45
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
    d["is_status_source"] = d["source"].str.contains("|".join(STATUS_SOURCES))
    d.loc[~d["is_status_source"] & (d["status_n"] != "cancelled"), "status_n"] = "listed"
    return d.sort_values(["upgrade_id", "snapshot_date"]).reset_index(drop=True)


def as_of(long: pd.DataFrame, t, max_age_days: int = MAX_REF_AGE_DAYS) -> pd.DataFrame:
    """Reference row per upgrade at t: the latest status-bearing snapshot with t - max_age_days <= snapshot_date <= t.
    An upgrade that no longer appears in a recent status snapshot has no reference (it left the active list)."""
    t = pd.Timestamp(t)
    v = long[(long["snapshot_date"] <= t) & (long["snapshot_date"] >= t - pd.Timedelta(days=max_age_days)) & long["is_status_source"]]
    return v.groupby("upgrade_id", sort=False).tail(1).reset_index(drop=True)


def history_features(long: pd.DataFrame, t) -> pd.DataFrame:
    """Per-upgrade features from all snapshots <= t: age in the table, number of estimate revisions,
    cumulative slip and cost growth since first publication, months to the currently expected ISD."""
    t = pd.Timestamp(t)
    ref = as_of(long, t).set_index("upgrade_id")
    v = long[(long["snapshot_date"] <= t) & long["upgrade_id"].isin(ref.index)]
    g = v.groupby("upgrade_id", sort=False)
    first = g.head(1).set_index("upgrade_id").reindex(ref.index)
    vs = v[v["is_status_source"]].groupby("upgrade_id", sort=False)
    first_status = vs.head(1).set_index("upgrade_id").reindex(ref.index)
    last = ref
    out = pd.DataFrame(index=last.index)
    out["obs_date"] = t
    out["n_snapshots"] = g.size()
    out["age_months"] = [(t - d).days / 30.4375 for d in first["snapshot_date"]]
    out["first_expected_isd"] = first_status["expected_isd"]
    out["expected_isd"] = last["expected_isd"]
    out["slip_so_far_months"] = [(_months(a, b) if pd.notna(a) and pd.notna(b) else np.nan) for a, b in zip(first_status["expected_isd"], last["expected_isd"])]
    out["first_cost_musd"] = first["est_cost_musd"]
    out["est_cost_musd"] = last["est_cost_musd"]
    out["cost_growth_so_far"] = (last["est_cost_musd"] / first["est_cost_musd"] - 1.0).replace([np.inf, -np.inf], np.nan)
    out["months_to_expected_isd"] = [(_months(t, d) if pd.notna(d) else np.nan) for d in last["expected_isd"]]
    vv = v.sort_values(["upgrade_id", "snapshot_date"])
    same = vv["upgrade_id"].eq(vv["upgrade_id"].shift())
    isd = vv["expected_isd"]; prev_isd = vv.groupby("upgrade_id")["expected_isd"].shift()
    chg_isd = same & isd.notna() & prev_isd.notna() & (isd != prev_isd)
    cost = vv["est_cost_musd"]; prev_cost = vv.groupby("upgrade_id")["est_cost_musd"].shift()
    chg_cost = same & cost.notna() & prev_cost.notna() & ((cost - prev_cost).abs() > 1e-9)
    out["n_isd_revisions"] = chg_isd.groupby(vv["upgrade_id"]).sum().reindex(out.index).fillna(0).astype(int)
    out["n_cost_revisions"] = chg_cost.groupby(vv["upgrade_id"]).sum().reindex(out.index).fillna(0).astype(int)
    out["status_n"] = last["status_n"]
    for c in ("to", "facility", "voltage_kv", "upgrade_type", "scope", "source", "status", "pct_complete", "required_date", "task",
              "equipment", "driver", "initial_teac", "last_teac", "state", "region", "last_updated", "study_year", "rating"):
        if c in last:
            out[c] = last[c]
    out["snapshot_date"] = last["snapshot_date"]
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
    later = later[later["status_n"] != "listed"]   # a bare listing carries no status information
    if horizon_end is not None:
        later = later[later["snapshot_date"] <= pd.Timestamp(horizon_end)]
    groups = {k: g for k, g in later.groupby("upgrade_id", sort=False)}
    empty = later.iloc[0:0]
    rows = []
    for r in ref.itertuples(index=False):
        h = groups.get(r.upgrade_id, empty)
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
        actual = None; actual_is_bound = False
        if first_done is not None:
            dated = done[done["actual_isd"].notna()]
            if len(dated):
                actual = dated["actual_isd"].iloc[0]          # the ISO's recorded in-service date (from a later snapshot)
            else:
                actual = first_done["snapshot_date"]; actual_is_bound = True   # only known to be in service by this date
            # the completion is observable from the first snapshot published after the in-service date
            # an energisation is public within about a month of happening (TO/ISO notices), even if our archive
            # sampling did not catch it until later; a status-only sighting is known at that snapshot
            after = h[h["snapshot_date"] >= max(pd.Timestamp(actual), t + pd.Timedelta(days=1))]
            seen = after["snapshot_date"].min() if len(after) else first_done["snapshot_date"]
            done_known = seen if actual_is_bound else min(seen, max(pd.Timestamp(actual) + pd.Timedelta(days=30), t + pd.Timedelta(days=1)))
        else:
            done_known = pd.NaT
        exp_t = r.expected_isd
        cost_t = r.est_cost_musd
        final_cost = (first_done["est_cost_musd"] if first_done is not None else
                      (first_canc["est_cost_musd"] if first_canc is not None else (h["est_cost_musd"].dropna().iloc[-1] if h["est_cost_musd"].notna().any() else np.nan)))
        # delay label (+ the date at which it became knowable)
        delay = np.nan; months_late = np.nan; delay_known = pd.NaT; predetermined = False
        if pd.notna(exp_t):
            deadline = exp_t + pd.Timedelta(days=DELAY_MONTHS * 30.4375)
            if deadline <= t:
                # the 12-month window had already closed when the snapshot was published: the outcome is not a
                # forecast. Keep months_late for reference, no delay label.
                predetermined = True
                if actual is not None:
                    months_late = _months(exp_t, actual)
            elif actual is not None:
                months_late = _months(exp_t, actual); delay = float(months_late > DELAY_MONTHS)
                # decidable once the 12-month window has closed (or the project is seen finished after it)
                delay_known = max(done_known, deadline)
            elif first_canc is not None:
                delay = np.nan  # cancelled: delay undefined (reported separately)
            elif _months(exp_t, last_obs) > DELAY_MONTHS:
                delay = 1.0     # still not built more than DELAY_MONTHS after the promised date
                delay_known = deadline
        # cost label (+ known date)
        over = np.nan; pct = np.nan; over_known = pd.NaT
        if pd.notna(cost_t) and cost_t > 0 and pd.notna(final_cost):
            pct = final_cost / cost_t - 1.0
            exceeded = h[h["est_cost_musd"] > cost_t * (1 + OVERRUN_FRAC)]
            if first_done is not None or first_canc is not None:
                over = float(pct > OVERRUN_FRAC)
                over_known = done_known if first_done is not None else first_canc["snapshot_date"]
                if over == 1.0 and len(exceeded):
                    over_known = min(over_known, exceeded["snapshot_date"].iloc[0])
            elif pct > OVERRUN_FRAC:
                over = 1.0
                over_known = exceeded["snapshot_date"].iloc[0] if len(exceeded) else last_obs
        cancel_known = first_canc["snapshot_date"] if first_canc is not None else pd.NaT
        rows.append(dict(upgrade_id=r.upgrade_id, obs_date=t, expected_isd_t=exp_t, est_cost_t=cost_t,
                         resolved_done=int(first_done is not None), resolved_cancel=int(first_canc is not None),
                         actual_isd=actual, final_cost_musd=final_cost, delay_12m=delay, months_late=months_late,
                         cost_overrun_25=over, pct_overrun=pct if (first_done is not None or first_canc is not None) else np.nan,
                         pct_growth_latest=pct, last_obs=last_obs, delay_known_date=delay_known, overrun_known_date=over_known,
                         cancel_known_date=cancel_known, done_known_date=done_known, actual_isd_is_bound=actual_is_bound, delay_predetermined=predetermined,
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
