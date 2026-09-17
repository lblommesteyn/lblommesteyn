"""Required baselines. Each `score_*` adds a score column to the candidate table; the trained
ones (`geo_size`, `simple_tabular`) fit on the train split only."""
from __future__ import annotations
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
import lightgbm as lgb

GEO_COLS = ["dist_km", "dist_far_km", "hops", "fac_kv", "kv_ratio", "same_kv", "fac_len_km", "kind_L", "kind_X", "kind_B",
            "touches_poi", "end_degree_max", "log_mw", "poi_kv", "type_gen", "type_battery", "type_load"]
SIMPLE_COLS = GEO_COLS + ["fac_n_named", "fac_years_since_named", "cong_hours_all", "fac_queue_mw_active_25km", "queue_mw_active_50km",
                          "apx_dfax", "analog_frac"]


def score_nearest_projects(df: pd.DataFrame) -> np.ndarray:
    """Nearest historical projects: similarity-weighted fraction of the 10 most similar prior
    studied projects (<= 80 km) that named the facility; ties broken by distance."""
    return df.analog_wfrac.values * 1000 + df.analog_frac.values * 10 - df.dist_km.values / 1000.0


def score_queue_density(df: pd.DataFrame) -> np.ndarray:
    """Queue-density heuristic: prior active queue MW near the facility, discounted by distance to the POI."""
    return np.log1p(df.fac_queue_mw_active_25km.values) / (1.0 + df.dist_km.values / 20.0) + 1e-6 * df.touches_poi.values


def score_historical_congestion(df: pd.DataFrame) -> np.ndarray:
    """Historical-congestion heuristic: hours binding (all history) x mean shadow price, discounted by distance."""
    return np.log1p(df.cong_hours_all.values) * np.log1p(df.cong_mean_sp_24m.values + df.cong_max_sp_24m.values * 0.1 + 1) / (1.0 + df.dist_km.values / 20.0)


def score_apx_dfax(df: pd.DataFrame) -> np.ndarray:
    """Public-topology physics only: approximate N-1 distribution factor from guessed impedances."""
    return df.apx_dfax_n1.values


class GeoSizeModel:
    def __init__(self):
        self.m = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, C=1.0))

    def fit(self, tr):
        self.m.fit(tr[GEO_COLS].fillna(0), tr.y)
        return self

    def predict(self, df):
        return self.m.predict_proba(df[GEO_COLS].fillna(0))[:, 1]


class SimpleTabular:
    def __init__(self, seed=0):
        self.m = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=31, min_child_samples=50, subsample=0.8,
                                    subsample_freq=1, colsample_bytree=0.8, random_state=seed, verbose=-1)

    def fit(self, tr):
        self.m.fit(tr[SIMPLE_COLS].fillna(0), tr.y)
        return self

    def predict(self, df):
        return self.m.predict_proba(df[SIMPLE_COLS].fillna(0))[:, 1]
