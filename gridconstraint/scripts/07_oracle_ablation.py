"""Which *private* planning data would close the gap? Oracle ablation: give the main model the
hidden case's true N-0 distribution factor (i.e. exact impedances and topology) as one extra
feature and re-run the chronological benchmark. The remaining gap after that is attributable
to ratings / dispatch / contingency definitions (headroom), which are also private."""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np, pandas as pd
from gridconstraint import config as C
from gridconstraint.data import loaders as L
from gridconstraint.sim.network import DCNetwork
from gridconstraint.eval.benchmark import load_dataset
from gridconstraint.models.latent import add_latent_feature
from gridconstraint.models.tabular import MainRanker, feature_columns
from gridconstraint.eval.metrics import rank_metrics, calibration


def true_dfax_table(X, pub):
    bus, br, pl = L.load_bus(), L.load_branch(), L.load_plant()
    net = DCNetwork(bus, br)
    w = np.zeros(net.n); np.add.at(w, pl[pl.status == 1].bus_id.map(net.bus_idx).values, pl[pl.status == 1].Pg.values); w = np.clip(w, 0, None); w /= w.sum()
    fac = pd.read_csv(C.WORLD / "branches.csv")
    fid_branches = fac.groupby("fid").branch.apply(np.array).to_dict()
    out = {}
    q = pub.queue.set_index("project_id")
    for pid in X.project_id.unique():
        r = q.loc[pid]
        sb = bus[(bus.sub_id == r.poi_sub_id) & (bus.baseKV == r.poi_kv)]
        if len(sb) == 0:
            sb = bus[bus.sub_id == r.poi_sub_id]
        bi = net.bus_idx[int(sb.bus_id.iloc[0])]
        p = np.abs(net.project_ptdf(bi, w))
        fids = X.fid.values[X.project_id.values == pid]
        out[pid] = {f: float(p[fid_branches[f]].max()) if f in fid_branches else 0.0 for f in set(fids)}
    return out


if __name__ == "__main__":
    pub, X = load_dataset("queue")
    X = add_latent_feature(X, pub)
    td = true_dfax_table(X, pub)
    X["ORACLE_true_dfax"] = [td[p].get(f, 0.0) for p, f in zip(X.project_id, X.fid)]
    X["ORACLE_true_contrib_mw"] = X.ORACLE_true_dfax * X.mw
    tr, va, te = (X[X.split == s] for s in ("train", "valid", "test"))
    base_cols = feature_columns(X, exclude={"publication_date", "queue_date", "project_type", "poi_sub_id", "ORACLE_true_dfax", "ORACLE_true_contrib_mw"})
    rows = []
    for name, cols in (("MAIN_public_only", base_cols), ("MAIN_plus_true_impedances(oracle)", base_cols + ["ORACLE_true_dfax", "ORACLE_true_contrib_mw"]),
                       ("true_impedances_only(oracle DFAX rank)", None)):
        if cols is None:
            d = te.assign(score=te.ORACLE_true_dfax.values); rm = rank_metrics(d, "score"); rows.append(dict(model=name, **rm)); continue
        m = MainRanker(cols, n_bags=2).fit(tr, va)
        p, raw, sd = m.predict(te)
        d = te.assign(score=raw, prob=p); rm = rank_metrics(d, "score"); cal = calibration(d, "prob")
        rows.append(dict(model=name, **rm, ece=cal["ece"], brier=cal["brier"]))
    res = pd.DataFrame(rows).set_index("model")
    res.to_csv(C.TABLES / "oracle_ablation_queue.csv")
    print(res[["hit@1", "hit@5", "hit@10", "recall@10", "mrr"]].round(3).to_string())
