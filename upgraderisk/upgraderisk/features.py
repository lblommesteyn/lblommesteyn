"""Feature matrix for the example table, computed strictly point-in-time."""
from __future__ import annotations
import numpy as np
import pandas as pd

NUMERIC = ["age_months", "n_snapshots", "slip_so_far_months", "cost_growth_so_far", "months_to_expected_isd", "n_isd_revisions", "n_cost_revisions",
           "log_cost", "pct_complete", "voltage_kv", "months_required_minus_expected", "months_since_initial_teac", "months_since_last_teac",
           "months_since_last_update", "obs_year"]
CATEG = ["status", "to", "equipment", "task", "driver_short", "voltage_class", "state", "region"]
RATE_KEYS = ["to", "voltage_class", "equipment", "status"]


def _months(a, b):
    return (pd.to_datetime(b) - pd.to_datetime(a)).dt.days / 30.4375


def voltage_class(kv):
    kv = pd.to_numeric(kv, errors="coerce")
    return pd.cut(kv, [-1, 100, 200, 400, 10000], labels=["<100", "100-199", "200-399", "400+"]).astype(str).replace("nan", "unknown")


def base_features(ex: pd.DataFrame) -> pd.DataFrame:
    f = ex.copy()
    f["log_cost"] = np.log1p(pd.to_numeric(f["est_cost_musd"], errors="coerce").clip(lower=0))
    f["voltage_class"] = voltage_class(f["voltage_kv"])
    f["months_required_minus_expected"] = _months(f["expected_isd"], f["required_date"]) if "required_date" in f else np.nan
    f["months_since_initial_teac"] = _months(f["initial_teac"], f["obs_date"]) if "initial_teac" in f else np.nan
    f["months_since_last_teac"] = _months(f["last_teac"], f["obs_date"]) if "last_teac" in f else np.nan
    f["months_since_last_update"] = _months(f["last_updated"], f["obs_date"]) if "last_updated" in f else np.nan
    f["obs_year"] = pd.to_datetime(f["obs_date"]).dt.year
    f["driver_short"] = f["driver"].fillna("").astype(str).str.split("(").str[0].str.strip().str[:40] if "driver" in f else ""
    for c in CATEG:
        if c not in f:
            f[c] = "unknown"
        f[c] = f[c].fillna("unknown").astype(str).replace("", "unknown")
    for c in NUMERIC:
        if c not in f:
            f[c] = np.nan
        f[c] = pd.to_numeric(f[c], errors="coerce")
    return f


def pit_group_rates(ex: pd.DataFrame, label: str, known_col: str, keys=RATE_KEYS, prior_n: float = 5.0) -> pd.DataFrame:
    """For every example (row i at obs_date t), the historical rate of `label` among earlier examples of the same
    group whose label was already KNOWN at t (known date <= t), shrunk toward the global known rate at t.
    Strictly point-in-time: uses obs_date < t and known_col <= t only."""
    out = pd.DataFrame(index=ex.index)
    lab = ex[label]
    known = pd.to_datetime(ex[known_col])
    valid = lab.notna() & known.notna()
    base = ex[valid][["obs_date", label]].copy(); base["known"] = known[valid]
    dates = np.sort(ex["obs_date"].unique())
    # global rate per obs date
    glob = {}
    for t in dates:
        m = base[(base["obs_date"] < t) & (base["known"] <= t)]
        glob[t] = (m[label].mean() if len(m) else np.nan, len(m))
    out[f"global_rate_{label}"] = [glob[t][0] for t in ex["obs_date"]]
    out[f"global_n_{label}"] = [glob[t][1] for t in ex["obs_date"]]
    for k in keys:
        col = ex[k].fillna("unknown").astype(str)
        rates = np.full(len(ex), np.nan); ns = np.zeros(len(ex))
        bk = base.assign(key=col[valid].values)
        for t in dates:
            idx = np.where(ex["obs_date"].values == t)[0]
            m = bk[(bk["obs_date"] < t) & (bk["known"] <= t)]
            g = m.groupby("key")[label].agg(["sum", "count"])
            gl = glob[t][0] if pd.notna(glob[t][0]) else 0.5
            for i in idx:
                kk = col.iat[i]
                if kk in g.index:
                    s, n = g.loc[kk, "sum"], g.loc[kk, "count"]
                    rates[i] = (s + prior_n * gl) / (n + prior_n); ns[i] = n
                else:
                    rates[i] = gl
        out[f"rate_{k}_{label}"] = rates; out[f"n_{k}_{label}"] = ns
    return out


def design(ex: pd.DataFrame):
    """Return (features DataFrame with numeric + categorical + PIT rate columns, list of numeric cols, list of categorical cols)."""
    f = base_features(ex)
    r1 = pit_group_rates(f, "delay_12m", "delay_known_date")
    r2 = pit_group_rates(f, "cost_overrun_25", "overrun_known_date")
    f = pd.concat([f, r1, r2], axis=1)
    rate_cols = list(r1.columns) + list(r2.columns)
    return f, NUMERIC + rate_cols, CATEG
