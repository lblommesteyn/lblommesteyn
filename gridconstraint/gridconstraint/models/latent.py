"""Latent-factor model: learn facility and POI embeddings from repeated project->constraint
outcomes *and* market co-binding, without any planning-case access.

Interaction matrix rows = "contexts" (a POI substation for a studied project, or a market hour),
columns = facilities. A truncated SVD gives facility vectors v_f; a POI vector u_s is the
(recency-weighted) average of the rows of studies at s. New / unseen POIs are cold-started
from studied POIs within 40 km (public geometry), weighted by exp(-d/15). The score
u_s . v_f is used both as a standalone model and as a feature for the main ranker.
Fits are done per year on studies published before that year, so a row never sees its own
study (leakage-safe stacking)."""
from __future__ import annotations
import numpy as np
import pandas as pd
import scipy.sparse as sp
from scipy.sparse.linalg import svds


class LatentModel:
    def __init__(self, pub, dim: int = 24, market_weight: float = 0.3):
        self.pub = pub
        self.dim = dim
        self.market_weight = market_weight
        self.fac_ids = pub.fac.fid.values
        self.fpos = {f: i for i, f in enumerate(self.fac_ids)}
        self.sub_xy = pub.sub_xy

    def fit(self, cutoff: pd.Timestamp):
        F = self.pub.findings[self.pub.findings.publication_date < cutoff]
        Cm = self.pub.constraints[(self.pub.constraints.datetime < cutoff) & self.pub.constraints.fid.notna()]
        rows, cols, vals = [], [], []
        ctx = {}   # context key -> row index
        self.poi_rows: dict[int, list[int]] = {}
        for r in F.itertuples():
            if r.fid not in self.fpos:
                continue
            key = ("p", r.project_id)
            if key not in ctx:
                ctx[key] = len(ctx); self.poi_rows.setdefault(int(r.poi_sub_id), []).append(ctx[key])
            rows.append(ctx[key]); cols.append(self.fpos[r.fid]); vals.append(1.0)
        for r in Cm.itertuples():
            if r.fid not in self.fpos:
                continue
            key = ("h", r.datetime)
            if key not in ctx:
                ctx[key] = len(ctx)
            rows.append(ctx[key]); cols.append(self.fpos[r.fid]); vals.append(self.market_weight * min(1.0, np.log1p(r.shadow_price) / 5))
        n_ctx = len(ctx)
        if n_ctx < self.dim + 2 or len(rows) == 0:
            self.V = None; return self
        M = sp.csr_matrix((vals, (rows, cols)), shape=(n_ctx, len(self.fac_ids)))
        # tf-idf style column scaling to avoid ubiquitous facilities dominating
        df_ = np.asarray((M > 0).sum(axis=0)).ravel()
        idf = np.log((1 + n_ctx) / (1 + df_)) + 0.5
        M = M @ sp.diags(idf)
        k = min(self.dim, min(M.shape) - 1)
        U, S, Vt = svds(M.astype(float), k=k)
        self.U = U * S; self.V = Vt.T                       # contexts x k, facilities x k
        self.poi_vec = {s: self.U[ix].mean(axis=0) for s, ix in self.poi_rows.items()}
        self.poi_ids = np.array(list(self.poi_vec)); self.poi_mat = np.vstack([self.poi_vec[s] for s in self.poi_ids]) if len(self.poi_ids) else None
        self.poi_xy = np.vstack([self.sub_xy[s] for s in self.poi_ids]) if len(self.poi_ids) else None
        return self

    def poi_embedding(self, sub_id: int):
        if self.V is None or self.poi_mat is None:
            return None
        if int(sub_id) in self.poi_vec:
            return self.poi_vec[int(sub_id)], True
        d = np.hypot(*(self.poi_xy - self.sub_xy[int(sub_id)]).T)
        w = np.exp(-d / 15.0) * (d <= 40)
        if w.sum() < 1e-6:
            return None
        return (w[:, None] * self.poi_mat).sum(axis=0) / w.sum(), False

    def score(self, sub_id: int, fids: np.ndarray) -> np.ndarray:
        e = self.poi_embedding(sub_id)
        if e is None:
            return np.zeros(len(fids))
        u, _ = e
        idx = np.array([self.fpos.get(f, -1) for f in fids])
        s = np.zeros(len(fids))
        ok = idx >= 0
        s[ok] = self.V[idx[ok]] @ u
        return s


def add_latent_feature(X: pd.DataFrame, pub, dim=24) -> pd.DataFrame:
    """Yearly expanding-window fits: rows with as_of in year Y get scores from a model fit on
    studies published before Jan 1 of Y (never their own study)."""
    X = X.copy(); X["latent_score"] = 0.0; X["latent_seen_poi"] = 0.0
    years = sorted(pd.to_datetime(X.as_of).dt.year.unique())
    for y in years:
        m = LatentModel(pub, dim=dim).fit(pd.Timestamp(year=y, month=1, day=1))
        sel = pd.to_datetime(X.as_of).dt.year == y
        if m.V is None:
            continue
        for pid, g in X[sel].groupby("project_id"):
            sub = int(pub.q_by_pid.loc[pid].poi_sub_id)
            sc = m.score(sub, g.fid.values)
            X.loc[g.index, "latent_score"] = sc
            e = m.poi_embedding(sub)
            X.loc[g.index, "latent_seen_poi"] = float(e is not None and e[1])
    return X
