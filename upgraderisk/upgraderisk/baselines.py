"""Non-learned and simple baselines. Each returns P(delay>12m), P(overrun>25%), and P50/P90 months-late / pct-overrun."""
from __future__ import annotations
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression, LinearRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer


def _clip(p):
    return np.clip(np.asarray(p, dtype=float), 1e-4, 1 - 1e-4)


class AlwaysOnTime:
    """The ISO's own expectation: no delay, no overrun, COD = current expected ISD, cost = current estimate."""
    name = "always_on_time"

    def fit(self, tr):
        return self

    def predict(self, te):
        n = len(te)
        return dict(p_delay=np.full(n, 0.02), p_over=np.full(n, 0.02), q_late=np.zeros((n, 3)), q_over=np.zeros((n, 3)))


class BaseRate:
    """Training-window base rates and empirical quantiles (constant prediction)."""
    name = "base_rate"

    def fit(self, tr):
        self.pd_ = tr["delay_12m"].mean(); self.po_ = tr["cost_overrun_25"].mean()
        self.ql_ = tr["months_late"].dropna().quantile([.1, .5, .9]).values
        self.qo_ = tr["pct_overrun"].dropna().quantile([.1, .5, .9]).values
        return self

    def predict(self, te):
        n = len(te)
        return dict(p_delay=np.full(n, self.pd_), p_over=np.full(n, self.po_), q_late=np.tile(self.ql_, (n, 1)), q_over=np.tile(self.qo_, (n, 1)))


class ProjectAgeHeuristic:
    """Delay risk from how long the project has been listed and how much it has already slipped (binned rates)."""
    name = "project_age"

    def _bins(self, d):
        age = pd.cut(d["age_months"].fillna(0), [-1, 6, 18, 36, 1e9], labels=False)
        slip = pd.cut(d["slip_so_far_months"].fillna(0), [-1e9, 0.5, 6, 12, 1e9], labels=False)
        return age.astype(int) * 10 + slip.astype(int)

    def fit(self, tr):
        b = self._bins(tr)
        self.pd_ = tr.groupby(b)["delay_12m"].mean(); self.po_ = tr.groupby(b)["cost_overrun_25"].mean()
        self.ql_ = tr.groupby(b)["months_late"].quantile([.1, .5, .9]).unstack(); self.qo_ = tr.groupby(b)["pct_overrun"].quantile([.1, .5, .9]).unstack()
        self.gd_, self.go_ = tr["delay_12m"].mean(), tr["cost_overrun_25"].mean()
        self.gl_ = tr["months_late"].dropna().quantile([.1, .5, .9]).values; self.go2_ = tr["pct_overrun"].dropna().quantile([.1, .5, .9]).values
        return self

    def predict(self, te):
        b = self._bins(te)
        pdl = b.map(self.pd_).fillna(self.gd_).values; po = b.map(self.po_).fillna(self.go_).values
        ql = np.vstack([self.ql_.loc[x].values if x in self.ql_.index and self.ql_.loc[x].notna().all() else self.gl_ for x in b])
        qo = np.vstack([self.qo_.loc[x].values if x in self.qo_.index and self.qo_.loc[x].notna().all() else self.go2_ for x in b])
        return dict(p_delay=pdl, p_over=po, q_late=ql, q_over=qo)


class GroupRate:
    """Point-in-time historical rate of the group (TO, voltage class, equipment type), already computed as a feature."""

    def __init__(self, key):
        self.key = key; self.name = f"rate_{key}"

    def fit(self, tr):
        self.fill_d, self.fill_o = tr["delay_12m"].mean(), tr["cost_overrun_25"].mean()
        g = tr.groupby(self.key)
        self.ql_ = g["months_late"].quantile([.1, .5, .9]).unstack(); self.qo_ = g["pct_overrun"].quantile([.1, .5, .9]).unstack()
        self.gl_ = tr["months_late"].dropna().quantile([.1, .5, .9]).values; self.go_ = tr["pct_overrun"].dropna().quantile([.1, .5, .9]).values
        return self

    def predict(self, te):
        pdl = te[f"rate_{self.key}_delay_12m"].fillna(self.fill_d).values; po = te[f"rate_{self.key}_cost_overrun_25"].fillna(self.fill_o).values
        ql = np.vstack([self.ql_.loc[x].values if x in self.ql_.index and self.ql_.loc[x].notna().all() else self.gl_ for x in te[self.key]])
        qo = np.vstack([self.qo_.loc[x].values if x in self.qo_.index and self.qo_.loc[x].notna().all() else self.go_ for x in te[self.key]])
        return dict(p_delay=pdl, p_over=po, q_late=ql, q_over=qo)


class SmallLogistic:
    """Logistic / linear models on a handful of interpretable features (voltage, cost, duration) or on all numeric features."""

    def __init__(self, cols, name):
        self.cols = cols; self.name = name

    def _pipe(self, clf):
        return make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), clf)

    def fit(self, tr):
        X = tr[self.cols]
        md = tr["delay_12m"].notna(); mo = tr["cost_overrun_25"].notna()
        self.cd_ = self._pipe(LogisticRegression(max_iter=2000, C=0.5)).fit(X[md], tr.loc[md, "delay_12m"])
        self.co_ = self._pipe(LogisticRegression(max_iter=2000, C=0.5)).fit(X[mo], tr.loc[mo, "cost_overrun_25"])
        ml = tr["months_late"].notna(); mp = tr["pct_overrun"].notna()
        self.rl_ = self._pipe(LinearRegression()).fit(X[ml], tr.loc[ml, "months_late"])
        self.rp_ = self._pipe(LinearRegression()).fit(X[mp], tr.loc[mp, "pct_overrun"].clip(-1, 5))
        resid_l = tr.loc[ml, "months_late"] - self.rl_.predict(X[ml]); resid_p = tr.loc[mp, "pct_overrun"].clip(-1, 5) - self.rp_.predict(X[mp])
        self.ql_ = resid_l.quantile([.1, .5, .9]).values; self.qp_ = resid_p.quantile([.1, .5, .9]).values
        return self

    def predict(self, te):
        X = te[self.cols]
        return dict(p_delay=_clip(self.cd_.predict_proba(X)[:, 1]), p_over=_clip(self.co_.predict_proba(X)[:, 1]),
                    q_late=self.rl_.predict(X)[:, None] + self.ql_[None, :], q_over=self.rp_.predict(X)[:, None] + self.qp_[None, :])
