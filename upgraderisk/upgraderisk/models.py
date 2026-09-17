"""Gradient-boosted classifiers with isotonic calibration, quantile regressors, and a Cox survival model."""
from __future__ import annotations
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.isotonic import IsotonicRegression

QS = [0.1, 0.5, 0.9]


def _prep(X: pd.DataFrame, cats):
    X = X.copy()
    for c in cats:
        X[c] = X[c].astype("category")
    return X


class GBMRisk:
    """LightGBM: two calibrated classifiers (delay, overrun) + quantile regressors for months late and % overrun.
    Calibration is fitted on the chronologically later part of the training window (never on test)."""
    name = "gbm"

    def __init__(self, num_cols, cat_cols, seed=0, n_estimators=400, calib_frac=0.25):
        self.num, self.cat, self.seed, self.n_est, self.calib_frac = list(num_cols), list(cat_cols), seed, n_estimators, calib_frac

    def _X(self, d):
        X = d[self.num + self.cat].copy()
        for c in self.cat:
            X[c] = pd.Categorical(X[c].astype(str), categories=self.cat_levels_[c])
        return X

    def _params(self, objective, alpha=None):
        p = dict(objective=objective, n_estimators=self.n_est, learning_rate=0.03, num_leaves=15, min_child_samples=25, subsample=0.8, subsample_freq=1,
                 colsample_bytree=0.8, reg_lambda=5.0, random_state=self.seed, verbose=-1, max_cat_to_onehot=8, cat_smooth=20)
        if alpha is not None:
            p["alpha"] = alpha
        return p

    def fit(self, tr):
        tr = tr.sort_values("obs_date")
        self.cat_levels_ = {c: sorted(set(tr[c].astype(str).unique().tolist()) | {"unknown"}) for c in self.cat}
        cut = int(len(tr) * (1 - self.calib_frac))
        fit_part, cal_part = tr.iloc[:cut], tr.iloc[cut:]
        self.clf_, self.iso_ = {}, {}
        for lab in ("delay_12m", "cost_overrun_25"):
            m = fit_part[lab].notna(); mc = cal_part[lab].notna()
            clf = lgb.LGBMClassifier(**self._params("binary")).fit(self._X(fit_part[m]), fit_part.loc[m, lab].astype(int))
            self.clf_[lab] = clf
            if mc.sum() >= 50 and cal_part.loc[mc, lab].nunique() == 2:
                raw = clf.predict_proba(self._X(cal_part[mc]))[:, 1]
                self.iso_[lab] = IsotonicRegression(out_of_bounds="clip", y_min=0.001, y_max=0.999).fit(raw, cal_part.loc[mc, lab].astype(int))
            # refit on the full window for the final probabilities (calibration map kept)
            mm = tr[lab].notna()
            self.clf_[lab] = lgb.LGBMClassifier(**self._params("binary")).fit(self._X(tr[mm]), tr.loc[mm, lab].astype(int))
        self.q_ = {}
        for lab, tgt in (("months_late", "months_late"), ("pct_overrun", "pct_overrun")):
            m = tr[tgt].notna()
            y = tr.loc[m, tgt].clip(-24, 120) if tgt == "months_late" else tr.loc[m, tgt].clip(-1, 5)
            self.q_[lab] = [lgb.LGBMRegressor(**self._params("quantile", alpha=q)).fit(self._X(tr[m]), y) for q in QS]
        return self

    def predict(self, te):
        X = self._X(te)
        out = {}
        for lab, key in (("delay_12m", "p_delay"), ("cost_overrun_25", "p_over")):
            raw = self.clf_[lab].predict_proba(X)[:, 1]
            out[key] = np.clip(self.iso_[lab].predict(raw) if lab in self.iso_ else raw, 1e-4, 1 - 1e-4)
            out[key + "_raw"] = raw
        ql = np.column_stack([m.predict(X) for m in self.q_["months_late"]]); ql.sort(axis=1)
        qo = np.column_stack([m.predict(X) for m in self.q_["pct_overrun"]]); qo.sort(axis=1)
        out["q_late"], out["q_over"] = ql, qo
        return out

    def importance(self):
        cols = self.num + self.cat
        return pd.DataFrame({lab: pd.Series(c.booster_.feature_importance("gain"), index=cols) for lab, c in self.clf_.items()})


class CoxSurvival:
    """Cox proportional hazards on time from observation to in-service (cancellation and unresolved = censored).
    Reports P(not in service by expected ISD + 12 months) as a delay probability and the median time-to-done."""
    name = "cox"

    def __init__(self, num_cols):
        self.num = [c for c in num_cols if not c.startswith("n_")]

    def fit(self, tr):
        from lifelines import CoxPHFitter
        d = tr[self.num + ["time_to_done_m", "event_done"]].copy()
        d["time_to_done_m"] = d["time_to_done_m"].clip(lower=0.1)
        self.med_ = d[self.num].median(); d[self.num] = d[self.num].fillna(self.med_)
        self.sd_ = d[self.num].std().replace(0, 1); d[self.num] = (d[self.num] - self.med_) / self.sd_
        keep = [c for c in self.num if d[c].std() > 0]
        self.keep_ = keep
        self.cph_ = CoxPHFitter(penalizer=0.05).fit(d[keep + ["time_to_done_m", "event_done"]], "time_to_done_m", "event_done")
        self.over_ = BaseRateHolder(tr)
        return self

    def predict(self, te):
        d = te[self.num].copy().fillna(self.med_); d = (d - self.med_) / self.sd_
        sf = self.cph_.predict_survival_function(d[self.keep_])
        horizon = (te["months_to_expected_isd"].fillna(0).clip(lower=0) + 12).values
        times = sf.index.values
        p_delay = np.array([np.interp(h, times, sf.iloc[:, i].values) for i, h in enumerate(horizon)])
        med = self.cph_.predict_median(d[self.keep_]).values.astype(float)
        med = np.where(np.isinf(med), times.max(), med)
        q_late = np.column_stack([np.array([np.interp(1 - q, sf.iloc[:, i].values[::-1], times[::-1]) for i in range(sf.shape[1])]) for q in (0.1, 0.5, 0.9)])
        q_late = q_late - te["months_to_expected_isd"].fillna(0).values[:, None]
        q_late.sort(axis=1)
        return dict(p_delay=np.clip(p_delay, 1e-4, 1 - 1e-4), p_over=self.over_.p_over(len(te)), q_late=q_late, q_over=self.over_.q_over(len(te)), median_ttd=med)


class BaseRateHolder:
    def __init__(self, tr):
        self.po = tr["cost_overrun_25"].mean(); self.qo = tr["pct_overrun"].dropna().quantile([.1, .5, .9]).values

    def p_over(self, n):
        return np.full(n, self.po)

    def q_over(self, n):
        return np.tile(self.qo, (n, 1))
