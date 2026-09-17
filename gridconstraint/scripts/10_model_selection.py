"""Model selection on the VALIDATION split only (test reported for completeness, never used to
choose): current bagged binary GBM vs a strongly regularised GBM vs LambdaRank per project."""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np, pandas as pd, lightgbm as lgb
from gridconstraint import config as C
from gridconstraint.eval.metrics import rank_metrics
from gridconstraint.eval.benchmark import load_dataset
from gridconstraint.models.latent import add_latent_feature
from gridconstraint.models.tabular import MainRanker, feature_columns

CONFIGS = {
    "binary_current": dict(n_estimators=900, learning_rate=0.05, num_leaves=63, min_child_samples=40, subsample=0.8, subsample_freq=1, colsample_bytree=0.7, reg_lambda=2.0, verbose=-1, n_jobs=4),
    "binary_regularised": dict(n_estimators=600, learning_rate=0.03, num_leaves=15, min_child_samples=300, subsample=0.7, subsample_freq=1, colsample_bytree=0.5, reg_lambda=10.0, min_split_gain=0.01, verbose=-1, n_jobs=4),
}

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "queue"
    pub, X = load_dataset(mode)
    X = add_latent_feature(X, pub)
    cols = feature_columns(X, exclude={"publication_date", "queue_date", "project_type", "poi_sub_id"})
    tr, va, te = (X[X.split == s].sort_values("project_id") for s in ("train", "valid", "test"))
    rows = []
    def ev(name, sva, ste):
        for split, d, sc in (("valid", va, sva), ("test", te, ste)):
            rm = rank_metrics(d.assign(score=sc), "score"); na = rank_metrics(d.assign(score=sc)[d.touches_poi == 0], "score")
            rows.append(dict(config=name, split=split, hit5=rm["hit@5"], hit10=rm["hit@10"], recall10=rm["recall@10"], mrr=rm["mrr"], na_hit5=na["hit@5"], na_recall10=na["recall@10"]))
    for name, params in CONFIGS.items():
        m = MainRanker(cols, n_bags=1, params=params).fit(tr, va)
        ev(name, m.predict(va)[1], m.predict(te)[1])
    # LambdaRank (query = project)
    def groups(d):
        return d.groupby("project_id", sort=False).size().values
    rk = lgb.LGBMRanker(n_estimators=600, learning_rate=0.05, num_leaves=31, min_child_samples=100, subsample=0.8, subsample_freq=1, colsample_bytree=0.7,
                        reg_lambda=5.0, verbose=-1, n_jobs=4, label_gain=[0, 1])
    rk.fit(tr[cols].fillna(0), tr.y.astype(int), group=groups(tr), eval_set=[(va[cols].fillna(0), va.y.astype(int))], eval_group=[groups(va)],
           eval_at=[5, 10], callbacks=[lgb.early_stopping(80, verbose=False)])
    ev("lambdarank", rk.predict(va[cols].fillna(0)), rk.predict(te[cols].fillna(0)))
    df = pd.DataFrame(rows); df.to_csv(C.TABLES / f"model_selection_{mode}.csv", index=False)
    print(df.round(3).to_string())
    best = df[df.split == "valid"].sort_values("recall10", ascending=False).iloc[0].config
    print("best on validation (recall@10):", best)
