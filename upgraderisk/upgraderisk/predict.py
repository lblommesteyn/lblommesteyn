"""Score one upgrade at an as-of date using only information published at or before that date.

    from upgraderisk.predict import Predictor
    p = Predictor.load()
    p.explain("b2752", "2018-01-25")      # real upgrade at a historical date
    p.explain_custom(dict(to="AEP", voltage_kv=138, est_cost_musd=12, expected_isd="2029-06-01", equipment="Transmission Line", ...), "2019-12-15")
"""
from __future__ import annotations
import pickle
from pathlib import Path
import numpy as np
import pandas as pd
from . import pit, features
from .config import PROCESSED


class Predictor:
    def __init__(self, bundle, long: pd.DataFrame):
        self.b = bundle
        self.long = pit.prepare(long)

    @classmethod
    def load(cls, processed: Path = PROCESSED):
        with open(processed / "model_bundle.pkl", "rb") as fh:
            b = pickle.load(fh)
        return cls(b, pd.read_parquet(processed / "snapshots_long.parquet"))

    # ------------------------------------------------------------------ feature assembly (point-in-time)
    def _rates_at(self, f: pd.DataFrame) -> pd.DataFrame:
        """Group rates from the bundle's training examples whose labels were known by the as-of date."""
        t = pd.Timestamp(f["obs_date"].iloc[0])
        hist = self.b["train_examples"]
        out = {}
        for lab, known in (("delay_12m", "delay_known_date"), ("cost_overrun_25", "overrun_known_date")):
            m = hist[(hist["obs_date"] < t) & (pd.to_datetime(hist[known]) <= t) & hist[lab].notna()]
            g = m[lab].mean() if len(m) else 0.5
            out[f"global_rate_{lab}"] = g; out[f"global_n_{lab}"] = len(m)
            for k in features.RATE_KEYS:
                key = str(f[k].iloc[0])
                mk = m[m[k].astype(str) == key]
                out[f"rate_{k}_{lab}"] = (mk[lab].sum() + 5 * g) / (len(mk) + 5) if len(mk) else g
                out[f"n_{k}_{lab}"] = len(mk)
        for k, v in out.items():
            f[k] = v
        return f

    def _row_for(self, upgrade_id: str, as_of: str) -> pd.DataFrame:
        t = pd.Timestamp(as_of)
        hist = self.long[self.long["upgrade_id"] == upgrade_id]
        if hist.empty:
            raise KeyError(f"{upgrade_id}: not in the snapshot table")
        f = pit.history_features(hist, t)
        if f.empty:
            last = hist[hist["snapshot_date"] <= t]
            raise ValueError(f"{upgrade_id}: no status snapshot within {pit.MAX_REF_AGE_DAYS} days before {t.date()} "
                             f"(last seen {last['snapshot_date'].max().date() if len(last) else 'never'}; available dates: {sorted(hist['snapshot_date'].dt.date.unique())[:12]})")
        return f

    def _design(self, row: pd.DataFrame) -> pd.DataFrame:
        f = features.base_features(row)
        return self._rates_at(f)

    # ------------------------------------------------------------------ scoring
    def score(self, f: pd.DataFrame) -> dict:
        ps = [m.predict(f) for m in self.b["members"]]
        p = {k: np.mean([x[k] for x in ps], axis=0) for k in ps[0]}
        s = self.b["survival"].predict(f)
        exp = pd.Timestamp(f["expected_isd"].iloc[0]) if pd.notna(f["expected_isd"].iloc[0]) else None
        cost = float(f["est_cost_musd"].iloc[0]) if pd.notna(f["est_cost_musd"].iloc[0]) else None
        def add_months(d, m):
            return (d + pd.Timedelta(days=float(m) * 30.4375)).date().isoformat() if d is not None else None
        out = dict(p_delay_12m=float(p["p_delay"][0]), p_cost_overrun_25=float(p["p_over"][0]),
                   months_late_p10_p50_p90=[float(x) for x in p["q_late"][0]], pct_overrun_p10_p50_p90=[float(x) for x in p["q_over"][0]],
                   survival_p_delay=float(s["p_delay"][0]), survival_median_months_to_done=float(s["median_ttd"][0]),
                   iso_expected_isd=exp.date().isoformat() if exp is not None else None, iso_cost_musd=cost,
                   model_cod_p10=add_months(exp, p["q_late"][0][0]), model_cod_p50=add_months(exp, p["q_late"][0][1]), model_cod_p90=add_months(exp, p["q_late"][0][2]),
                   model_cost_p10=cost * (1 + p["q_over"][0][0]) if cost is not None else None, model_cost_p50=cost * (1 + p["q_over"][0][1]) if cost is not None else None,
                   model_cost_p90=cost * (1 + p["q_over"][0][2]) if cost is not None else None)
        return out

    def drivers(self, f: pd.DataFrame, top: int = 8) -> dict:
        """Per-feature contributions (LightGBM pred_contrib, log-odds) averaged over the bag."""
        res = {}
        for lab in ("delay_12m", "cost_overrun_25"):
            contribs = []
            for m in self.b["members"]:
                X = m._X(f)
                c = m.clf_[lab].predict(X, pred_contrib=True)[0][:-1]
                contribs.append(c)
            c = np.mean(contribs, axis=0)
            cols = self.b["num"] + self.b["cat"]
            order = np.argsort(-np.abs(c))[:top]
            res[lab] = [dict(feature=cols[i], value=(None if pd.isna(f[cols[i]].iloc[0]) else (float(f[cols[i]].iloc[0]) if cols[i] in self.b["num"] else str(f[cols[i]].iloc[0]))),
                             contribution_logodds=float(c[i])) for i in order]
        return res

    def analogs(self, f: pd.DataFrame, k: int = 8) -> pd.DataFrame:
        a = self.b["analogs"]
        a = a[(a["resolved_done"] == 1) | (a["resolved_cancel"] == 1)]
        t = pd.Timestamp(f["obs_date"].iloc[0])
        a = a[a["obs_date"] < t]
        if a.empty:
            return a
        row = f.iloc[0]
        d = np.zeros(len(a))
        d += 1.0 * (a["to"].astype(str) != str(row["to"])).values
        d += 0.7 * (a["voltage_class"].astype(str) != str(row["voltage_class"])).values
        d += 0.7 * (a["equipment"].astype(str) != str(row["equipment"])).values
        d += 0.5 * (a["status"].astype(str) != str(row["status"])).values
        lc = np.log1p(a["est_cost_musd"].fillna(0).clip(lower=0)); d += 0.4 * np.abs(lc - np.log1p(max(float(row["est_cost_musd"] or 0), 0))).values
        d += 0.02 * np.abs(a["months_to_expected_isd"].fillna(0) - float(row["months_to_expected_isd"] if pd.notna(row["months_to_expected_isd"]) else 0)).values
        a = a.assign(distance=d).sort_values("distance")
        a = a.drop_duplicates("upgrade_id").head(k)
        return a[["upgrade_id", "obs_date", "to", "voltage_kv", "equipment", "status", "est_cost_musd", "expected_isd", "actual_isd", "months_late", "pct_overrun", "resolved_cancel", "scope", "distance"]]

    def explain(self, upgrade_id: str, as_of: str, k_analogs: int = 8) -> dict:
        f = self._design(self._row_for(upgrade_id, as_of))
        return self._package(f, k_analogs, upgrade_id)

    def explain_custom(self, characteristics: dict, as_of: str, k_analogs: int = 8) -> dict:
        """Score a hypothetical upgrade from user-supplied characteristics (no history: age 0, one snapshot)."""
        t = pd.Timestamp(as_of)
        row = dict(upgrade_id="custom", obs_date=t, n_snapshots=1, age_months=0.0, first_expected_isd=pd.to_datetime(characteristics.get("expected_isd")),
                   expected_isd=pd.to_datetime(characteristics.get("expected_isd")), slip_so_far_months=0.0, first_cost_musd=characteristics.get("est_cost_musd"),
                   est_cost_musd=characteristics.get("est_cost_musd"), cost_growth_so_far=0.0,
                   months_to_expected_isd=(pd.to_datetime(characteristics.get("expected_isd")) - t).days / 30.4375 if characteristics.get("expected_isd") else np.nan,
                   n_isd_revisions=0, n_cost_revisions=0, status_n="active", snapshot_date=t)
        for kk in ("to", "facility", "voltage_kv", "upgrade_type", "scope", "source", "status", "pct_complete", "required_date", "task", "equipment", "driver",
                   "initial_teac", "last_teac", "state", "region", "last_updated", "study_year", "rating"):
            row[kk] = characteristics.get(kk, np.nan if kk in ("voltage_kv", "pct_complete") else ("unknown" if kk not in ("required_date", "initial_teac", "last_teac", "last_updated") else pd.NaT))
        row.update({k: v for k, v in characteristics.items() if k in row})
        f = self._design(pd.DataFrame([row]))
        return self._package(f, k_analogs, "custom")

    def _package(self, f, k_analogs, upgrade_id):
        out = dict(upgrade_id=upgrade_id, as_of=str(pd.Timestamp(f["obs_date"].iloc[0]).date()), snapshot_used=str(pd.Timestamp(f["snapshot_date"].iloc[0]).date()) if "snapshot_date" in f and pd.notna(f["snapshot_date"].iloc[0]) else None,
                   inputs=dict(to=str(f["to"].iloc[0]), voltage_kv=(None if pd.isna(f["voltage_kv"].iloc[0]) else float(f["voltage_kv"].iloc[0])), status=str(f["status"].iloc[0]), equipment=str(f["equipment"].iloc[0]),
                               est_cost_musd=(None if pd.isna(f["est_cost_musd"].iloc[0]) else float(f["est_cost_musd"].iloc[0])), expected_isd=(None if pd.isna(f["expected_isd"].iloc[0]) else str(pd.Timestamp(f["expected_isd"].iloc[0]).date())),
                               age_months=float(f["age_months"].iloc[0]), slip_so_far_months=(None if pd.isna(f["slip_so_far_months"].iloc[0]) else float(f["slip_so_far_months"].iloc[0])),
                               n_isd_revisions=int(f["n_isd_revisions"].iloc[0]), cost_growth_so_far=(None if pd.isna(f["cost_growth_so_far"].iloc[0]) else float(f["cost_growth_so_far"].iloc[0])),
                               scope=str(f["scope"].iloc[0])[:200]),
                   prediction=self.score(f), drivers=self.drivers(f), analogs=self.analogs(f, k_analogs).to_dict(orient="records"),
                   caveat="Statistical estimate from public snapshots of the ISO's own tables; not an engineering or schedule assessment.")
        for a in out["analogs"]:
            for kk in ("obs_date", "expected_isd", "actual_isd"):
                a[kk] = None if pd.isna(a[kk]) else str(pd.Timestamp(a[kk]).date())
        return out
