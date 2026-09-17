"""Main learned model: gradient-boosted ranker over (project, candidate facility) rows with
isotonic calibration on the validation split and a bagged ensemble for uncertainty."""
from __future__ import annotations
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.isotonic import IsotonicRegression

ID_COLS = {"project_id", "fid", "y", "y_loading", "as_of", "split"}


def feature_columns(df: pd.DataFrame, exclude: set | None = None) -> list[str]:
    ex = ID_COLS | (exclude or set())
    return [c for c in df.columns if c not in ex and pd.api.types.is_numeric_dtype(df[c])]


class MainRanker:
    def __init__(self, cols: list[str], n_bags: int = 5, params: dict | None = None):
        self.cols = cols
        self.n_bags = n_bags
        self.params = params or dict(n_estimators=900, learning_rate=0.05, num_leaves=63, min_child_samples=40, subsample=0.8,
                                     subsample_freq=1, colsample_bytree=0.7, reg_lambda=2.0, verbose=-1, n_jobs=4)
        self.models = []
        self.iso = None

    def fit(self, tr: pd.DataFrame, va: pd.DataFrame):
        Xtr, ytr = tr[self.cols].fillna(0), tr.y.values
        Xva, yva = va[self.cols].fillna(0), va.y.values
        self.models = []
        for b in range(self.n_bags):
            m = lgb.LGBMClassifier(random_state=b, **self.params)
            m.fit(Xtr, ytr, eval_set=[(Xva, yva)], eval_metric="average_precision",
                  callbacks=[lgb.early_stopping(100, verbose=False)])
            self.models.append(m)
        raw = self._raw(va)
        self.iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(raw.mean(axis=1), yva)
        return self

    def _raw(self, df):
        X = df[self.cols].fillna(0)
        return np.column_stack([m.predict_proba(X)[:, 1] for m in self.models])

    def predict(self, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """returns (calibrated prob, raw mean, bag std)"""
        raw = self._raw(df)
        mean = raw.mean(axis=1)
        return self.iso.predict(mean), mean, raw.std(axis=1)

    def importance(self) -> pd.Series:
        imp = np.mean([m.booster_.feature_importance(importance_type="gain") for m in self.models], axis=0)
        return pd.Series(imp, index=self.cols).sort_values(ascending=False)
