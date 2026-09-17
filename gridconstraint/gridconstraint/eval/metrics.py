"""Ranking, calibration and classification metrics for the facility-risk task."""
from __future__ import annotations
import numpy as np
import pandas as pd


def rank_metrics(df: pd.DataFrame, score: str, ks=(1, 3, 5, 10, 20), y: str = "y") -> dict:
    """Per-project ranking metrics averaged over projects with >= 1 positive.
    hit@k  : any true facility in top-k (the headline "appeared in top-K" metric)
    recall@k, precision@k, MRR, plus all@k (every true facility in top-k)."""
    out = {f"hit@{k}": [] for k in ks}
    out.update({f"recall@{k}": [] for k in ks}); out.update({f"precision@{k}": [] for k in ks}); out.update({f"all@{k}": [] for k in ks})
    out["mrr"] = []; n_proj = 0
    for pid, g in df.groupby("project_id", sort=False):
        pos = g[y].values > 0.5
        if pos.sum() == 0:
            continue
        n_proj += 1
        order = np.argsort(-g[score].values, kind="stable")
        ranked = pos[order]
        first = np.argmax(ranked) + 1 if ranked.any() else np.inf
        out["mrr"].append(1.0 / first)
        for k in ks:
            top = ranked[:k]
            out[f"hit@{k}"].append(float(top.any()))
            out[f"recall@{k}"].append(top.sum() / pos.sum())
            out[f"precision@{k}"].append(top.sum() / k)
            out[f"all@{k}"].append(float(top.sum() == pos.sum()))
    res = {k: float(np.mean(v)) if v else np.nan for k, v in out.items()}
    res["n_projects"] = n_proj
    return res


def calibration(df: pd.DataFrame, prob: str, y: str = "y", n_bins: int = 10) -> dict:
    p = np.clip(df[prob].values, 0, 1); t = df[y].values
    bins = np.linspace(0, 1, n_bins + 1)
    idx = np.clip(np.digitize(p, bins) - 1, 0, n_bins - 1)
    ece = 0.0; table = []
    for b in range(n_bins):
        m = idx == b
        if m.sum() == 0:
            continue
        conf, acc = p[m].mean(), t[m].mean()
        ece += m.mean() * abs(conf - acc)
        table.append(dict(bin=b, n=int(m.sum()), mean_pred=float(conf), frac_pos=float(acc)))
    brier = float(np.mean((p - t) ** 2))
    base = t.mean()
    brier_skill = 1 - brier / float(np.mean((base - t) ** 2)) if base > 0 else np.nan
    return dict(ece=float(ece), brier=brier, brier_skill=float(brier_skill), table=table)


def project_level_expected_count(df: pd.DataFrame, prob: str, y: str = "y") -> dict:
    """Does sum of probabilities track the number of constrained facilities per project?"""
    g = df.groupby("project_id").agg(expected=(prob, "sum"), actual=(y, "sum"))
    return dict(mae=float((g.expected - g.actual).abs().mean()), corr=float(np.corrcoef(g.expected, g.actual)[0, 1]) if len(g) > 2 else np.nan,
                mean_expected=float(g.expected.mean()), mean_actual=float(g.actual.mean()))
