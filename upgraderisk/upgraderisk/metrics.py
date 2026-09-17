from __future__ import annotations
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss, log_loss


def classification(y, p):
    y = np.asarray(y, float); p = np.asarray(p, float); m = ~np.isnan(y)
    y, p = y[m], np.clip(p[m], 1e-6, 1 - 1e-6)
    if len(y) < 10 or len(np.unique(y)) < 2:
        return dict(n=int(len(y)), rate=float(y.mean()) if len(y) else None)
    bins = np.clip((p * 10).astype(int), 0, 9)
    ece = sum(abs(y[bins == b].mean() - p[bins == b].mean()) * (bins == b).mean() for b in range(10) if (bins == b).any())
    return dict(n=int(len(y)), rate=float(y.mean()), brier=float(brier_score_loss(y, p)), logloss=float(log_loss(y, p)),
                auroc=float(roc_auc_score(y, p)), pr_auc=float(average_precision_score(y, p)), ece=float(ece),
                brier_skill=float(1 - brier_score_loss(y, p) / brier_score_loss(y, np.full_like(y, y.mean()))))


def reliability(y, p, nbins=10):
    y = np.asarray(y, float); p = np.asarray(p, float); m = ~np.isnan(y); y, p = y[m], p[m]
    bins = np.clip((p * nbins).astype(int), 0, nbins - 1)
    return pd.DataFrame([dict(bin=b, n=int((bins == b).sum()), pred=float(p[bins == b].mean()), obs=float(y[bins == b].mean())) for b in range(nbins) if (bins == b).any()])


def quantiles(y, q):
    """q: (n,3) columns P10/P50/P90. Returns MAE of P50, coverage of P50 (target .5) and P90 (target .9), interval width."""
    y = np.asarray(y, float); m = ~np.isnan(y); y, q = y[m], np.asarray(q)[m]
    if len(y) < 5:
        return dict(n=int(len(y)))
    return dict(n=int(len(y)), mae_p50=float(np.mean(np.abs(y - q[:, 1]))), cov_p50=float(np.mean(y <= q[:, 1])), cov_p90=float(np.mean(y <= q[:, 2])),
                cov_p10=float(np.mean(y <= q[:, 0])), width_p10_p90=float(np.mean(q[:, 2] - q[:, 0])),
                pinball_p90=float(np.mean(np.maximum(0.9 * (y - q[:, 2]), 0.1 * (q[:, 2] - y)))))
