"""Post-hoc analyses on the saved test predictions: (a) ranking restricted to facilities NOT
directly connected to the POI (the non-trivial part of the problem), (b) per-year drift,
(c) probabilistic skill summary. Trained baselines are refit deterministically."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np, pandas as pd
from gridconstraint import config as C
from gridconstraint.eval.metrics import rank_metrics
from gridconstraint.eval.benchmark import load_dataset
from gridconstraint.models import baselines as B
from gridconstraint.models.latent import add_latent_feature

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "queue"
    pub, X = load_dataset(mode)
    X = add_latent_feature(X, pub)
    tr, va, te = (X[X.split == s] for s in ("train", "valid", "test"))
    pred = pd.read_parquet(C.PROCESSED / f"test_predictions_{mode}.parquet")[["project_id", "fid", "p_main_raw", "p_main"]]
    te = te.merge(pred, on=["project_id", "fid"], how="left")
    gs = B.GeoSizeModel().fit(tr); st = B.SimpleTabular().fit(tr)
    scores = {"B1_nearest_projects": B.score_nearest_projects(te), "B2_queue_density": B.score_queue_density(te),
              "B3_historical_congestion": B.score_historical_congestion(te), "B4_geo_size_logit": gs.predict(te),
              "B5_simple_tabular_gbm": st.predict(te), "P0_public_topology_dfax": B.score_apx_dfax(te),
              "L0_latent_only": te.latent_score.values, "MAIN_all_features": te.p_main_raw.values}
    rows = []
    for name, sc in scores.items():
        d = te.assign(score=sc)
        full = rank_metrics(d, "score")
        na = rank_metrics(d[d.touches_poi == 0], "score")
        rows.append(dict(model=name, subset="all facilities", **{k: full[k] for k in ("hit@1", "hit@5", "hit@10", "recall@5", "recall@10", "precision@5", "mrr", "n_projects")}))
        rows.append(dict(model=name, subset="non-adjacent facilities only", **{k: na[k] for k in ("hit@1", "hit@5", "hit@10", "recall@5", "recall@10", "precision@5", "mrr", "n_projects")}))
    pd.DataFrame(rows).to_csv(C.TABLES / f"nonadjacent_{mode}.csv", index=False)
    te["year"] = pd.to_datetime(te.queue_date).dt.year
    yr = []
    for y, g in te.groupby("year"):
        for name in ("MAIN_all_features", "B4_geo_size_logit", "P0_public_topology_dfax"):
            sc = pd.Series(scores[name], index=te.index).loc[g.index].values
            rm = rank_metrics(g.assign(score=sc), "score")
            yr.append(dict(year=int(y), model=name, n_projects=rm["n_projects"], **{k: rm[k] for k in ("hit@5", "hit@10", "recall@10", "mrr")}))
    pd.DataFrame(yr).to_csv(C.TABLES / f"per_year_{mode}.csv", index=False)
    print(pd.DataFrame(rows).round(3).to_string()); print(pd.DataFrame(yr).round(3).to_string())
