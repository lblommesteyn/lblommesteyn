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
        p = dict(objective=objective, n_estimators=self.n_est, learning_rate=0.03, num_leaves=15, min_child_samples=40, subsample=0.8, subsample_freq=1,
                 colsample_bytree=0.8, reg_lambda=10.0, random_state=self.seed, verbose=-1, max_cat_to_onehot=8, cat_smooth=30, min_data_per_group=50)
        if alpha is not None:
            p["alpha"] = alpha
        return p

    def fit(self, tr):
        from sklearn.linear_model import LogisticRegression
        from sklearn.model_selection import GroupKFold
        tr = tr.sort_values("obs_date")
        self.cat_levels_ = {c: sorted(set(tr[c].astype(str).unique().tolist()) | {"unknown"}) for c in self.cat}
        self.clf_, self.cal_ = {}, {}
        for lab in ("delay_12m", "cost_overrun_25", "cancelled"):
            if lab not in tr or tr[lab].notna().sum() < 100 or tr[lab].dropna().nunique() < 2:
                continue
            mm = tr[lab].notna(); X = self._X(tr[mm]); y = tr.loc[mm, lab].astype(int).values; groups = tr.loc[mm, "upgrade_id"].values
            # out-of-fold raw scores (folds grouped by upgrade) -> Platt map; robust with few positives
            if y.sum() >= 30 and (1 - y).sum() >= 30 and len(np.unique(groups)) >= 10:
                oof = np.zeros(len(y))
                for tr_i, te_i in GroupKFold(n_splits=5).split(X, y, groups):
                    c = lgb.LGBMClassifier(**self._params("binary")).fit(X.iloc[tr_i], y[tr_i])
                    oof[te_i] = c.predict_proba(X.iloc[te_i])[:, 1]
                z = np.log(np.clip(oof, 1e-5, 1 - 1e-5) / (1 - np.clip(oof, 1e-5, 1 - 1e-5)))[:, None]
                self.cal_[lab] = LogisticRegression(C=1.0).fit(z, y)
            self.clf_[lab] = lgb.LGBMClassifier(**self._params("binary")).fit(X, y)
        self.q_ = {}
        for lab, tgt in (("months_late", "months_late"), ("pct_overrun", "pct_overrun")):
            mq = tr[tgt].notna()
            if mq.sum() < 50:
                self.q_[lab] = None; continue
            yq = tr.loc[mq, tgt].clip(-24, 120) if tgt == "months_late" else tr.loc[mq, tgt].clip(-1, 5)
            self.q_[lab] = [lgb.LGBMRegressor(**self._params("quantile", alpha=q)).fit(self._X(tr[mq]), yq) for q in QS]
        return self

    def predict(self, te):
        X = self._X(te)
        out = {}
        for lab, key in (("delay_12m", "p_delay"), ("cost_overrun_25", "p_over"), ("cancelled", "p_cancel")):
            if lab not in self.clf_:
                out[key] = np.full(len(te), np.nan); continue
            raw = self.clf_[lab].predict_proba(X)[:, 1]
            if lab in self.cal_:
                z = np.log(np.clip(raw, 1e-5, 1 - 1e-5) / (1 - np.clip(raw, 1e-5, 1 - 1e-5)))[:, None]
                cal = self.cal_[lab].predict_proba(z)[:, 1]
            else:
                cal = raw
            out[key] = np.clip(cal, 1e-4, 1 - 1e-4)
            out[key + "_raw"] = raw
        n = len(te)
        ql = np.column_stack([m.predict(X) for m in self.q_["months_late"]]) if self.q_.get("months_late") else np.zeros((n, 3)); ql.sort(axis=1)
        qo = np.column_stack([m.predict(X) for m in self.q_["pct_overrun"]]) if self.q_.get("pct_overrun") else np.zeros((n, 3)); qo.sort(axis=1)
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


class DiscreteTimeSurvival:
    """Discrete-time (monthly) hazard model with LightGBM, no external survival dependency.
    Each example is expanded into person-months from the observation date until in-service (event) or the last
    observation (censored, cancellations included); the classifier learns h(k | x). Survival S(k) = prod(1-h).
    Reports P(not in service by the ISO's expected date + 12 months) and the P10/P50/P90 months-late implied by S."""
    name = "dt_survival"

    def __init__(self, num_cols, cat_cols, seed=0, max_months=84, step=1):
        self.num, self.cat, self.seed, self.K, self.step = list(num_cols), list(cat_cols), seed, max_months, step

    def _X(self, d, k):
        X = d[self.num + self.cat].copy()
        for c in self.cat:
            X[c] = pd.Categorical(X[c].astype(str), categories=self.cat_levels_[c])
        X["k_month"] = np.asarray(k, dtype=float)
        return X

    def fit(self, tr):
        self.cat_levels_ = {c: sorted(set(tr[c].astype(str).unique().tolist()) | {"unknown"}) for c in self.cat}
        t = tr["time_to_done_m"].clip(lower=0.5, upper=self.K).values; e = tr["event_done"].values.astype(int)
        rows, ks, ys = [], [], []
        rng = np.random.default_rng(self.seed)
        for i in range(len(tr)):
            n = int(np.ceil(t[i] / self.step))
            kk = np.arange(1, n + 1) * self.step
            # subsample long censored histories to keep the expansion tractable
            if n > 24:
                keep = np.concatenate([np.arange(24), rng.choice(np.arange(24, n), size=min(n - 24, 12), replace=False)])
                keep.sort(); kk = kk[keep]
            y = np.zeros(len(kk), dtype=int)
            if e[i] == 1:
                y[-1] = 1 if kk[-1] >= t[i] else 0
            rows.append(np.full(len(kk), i)); ks.append(kk); ys.append(y)
        idx = np.concatenate(rows); k = np.concatenate(ks); y = np.concatenate(ys)
        X = self._X(tr.iloc[idx], k)
        self.clf_ = lgb.LGBMClassifier(objective="binary", n_estimators=300, learning_rate=0.05, num_leaves=15, min_child_samples=50, subsample=0.8, subsample_freq=1,
                                       colsample_bytree=0.8, reg_lambda=5.0, random_state=self.seed, verbose=-1).fit(X, y)
        self.over_ = BaseRateHolder(tr)
        return self

    def survival(self, te):
        n = len(te); ks = np.arange(1, self.K + 1, self.step)
        H = np.zeros((n, len(ks)))
        for j, k in enumerate(ks):
            H[:, j] = self.clf_.predict_proba(self._X(te, np.full(n, k)))[:, 1]
        S = np.cumprod(1 - H, axis=1)
        return ks, S

    def predict(self, te):
        ks, S = self.survival(te)
        horizon = (te["months_to_expected_isd"].fillna(0).clip(lower=0) + 12).values
        p_delay = np.array([np.interp(h, ks, S[i]) for i, h in enumerate(horizon)])
        def q_time(i, q):  # time by which P(done) >= q
            done = 1 - S[i]
            return float(np.interp(q, done, ks)) if done[-1] >= q else float(ks[-1])
        q = np.array([[q_time(i, 0.1), q_time(i, 0.5), q_time(i, 0.9)] for i in range(len(te))])
        q_late = q - te["months_to_expected_isd"].fillna(0).values[:, None]
        return dict(p_delay=np.clip(p_delay, 1e-4, 1 - 1e-4), p_over=self.over_.p_over(len(te)), q_late=q_late, q_over=self.over_.q_over(len(te)),
                    median_ttd=q[:, 1])
