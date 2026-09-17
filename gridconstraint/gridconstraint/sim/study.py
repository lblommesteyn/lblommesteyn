"""PJM-style interconnection study procedure on the hidden planning case.

For a project injecting P MW at a POI (or withdrawing P MW for a large load) we emulate
the two thermal tests that generate most PJM network upgrades:

* Generator deliverability / N-0: project injection offset by a system-wide generation
  re-dispatch (`withdraw` vector), all monitored facilities checked against rating.
* Single-contingency (N-1) analysis over a contingency set (non-radial >=100 kV branches
  that the project materially affects or that are electrically local to the POI).

A facility is *attributed* to the project when (PJM Manual 14B logic, simplified):
  post-contingency loading > 100 % of rating, AND
  the project's distribution factor on the facility (under that contingency) >= 5 %, AND
  the project's contribution aggravates the overload (same sign as the flow).
The output is per *branch*; aggregation to public facility ids happens in world.py.
"""
from __future__ import annotations
import numpy as np
from .. import config as C


class LODFCache:
    """LODF columns restricted to the monitored rows (memory-bounded LRU)."""

    def __init__(self, net, monitored_idx: np.ndarray, max_entries: int = 8000):
        self.net = net
        self.M = monitored_idx
        self.pos = {int(b): i for i, b in enumerate(monitored_idx)}
        self.cols: dict[int, np.ndarray] = {}
        self.islanding: dict[int, bool] = {}
        self.max_entries = max_entries

    def get(self, k: int, cache: bool = True):
        if k in self.cols:
            col = self.cols.pop(k); self.cols[k] = col   # LRU touch
            return col, self.islanding[k]
        col, isl = self.net.lodf_column(k)
        colm = col[self.M].astype(np.float32)
        if cache:
            if len(self.cols) >= self.max_entries:
                self.cols.pop(next(iter(self.cols)))
            self.cols[k] = colm
        self.islanding[k] = isl
        return colm, isl

    def stack(self, ks: np.ndarray, cache: bool = True):
        cols = []; keep = []
        for k in ks:
            col, isl = self.get(int(k), cache=cache)
            if isl:
                continue
            cols.append(col); keep.append(int(k))
        if not cols:
            return np.zeros((len(self.M), 0), np.float32), np.array([], int)
        return np.stack(cols, axis=1), np.array(keep)


def select_contingencies(net, ptdf: np.ndarray, poi_bus: int, eligible: np.ndarray, hops_cache: dict,
                         min_dfax: float = 0.02, local_hops: int = 3, cap: int = 500) -> np.ndarray:
    """Contingency set = eligible branches with |ptdf| >= min_dfax, plus electrically-local ones."""
    if poi_bus not in hops_cache:
        hops_cache[poi_bus] = net.hops_from(poi_bus, local_hops)
    h = hops_cache[poi_bus]
    local = np.isfinite(h[net.f]) & np.isfinite(h[net.t])
    sel = eligible & ((np.abs(ptdf) >= min_dfax) | local)
    idx = np.where(sel)[0]
    if len(idx) > cap:
        idx = idx[np.argsort(-np.abs(ptdf[idx]))[:cap]]
    return idx


def run_study(net, rate: np.ndarray, base_flow: np.ndarray, ptdf: np.ndarray, P: float,
              monitored: np.ndarray, cont_idx: np.ndarray, lodf: LODFCache,
              dfax_thr: float = C.DFAX_THRESHOLD, load_thr: float = C.LOADING_THRESHOLD,
              max_facilities: int = 25) -> list[dict]:
    """Return attributed overloads for a project with signed injection P (MW) and PTDF (m,).
    base_flow excludes the project. Each dict is one monitored branch with its worst case."""
    Mi = lodf.M                      # monitored rows (rate > 0 guaranteed by construction)
    f0 = base_flow[Mi]; d0 = ptdf[Mi]; r = rate[Mi]
    contrib0 = P * d0
    f1 = f0 + contrib0
    results = {}
    # ---- N-0 ----
    loading = np.abs(f1) / r
    flag = (loading > load_thr) & (np.abs(d0) >= dfax_thr) & (np.sign(contrib0) == np.sign(f1))
    for j in np.where(flag)[0]:
        results[int(Mi[j])] = dict(branch=int(Mi[j]), cont=-1, loading_post=float(loading[j]),
                                   loading_pre=float(abs(f0[j]) / r[j]), dfax=float(abs(d0[j])),
                                   contrib_mw=float(abs(contrib0[j])), flow_post=float(abs(f1[j])), rating=float(r[j]))
    # ---- N-1 ----
    if len(cont_idx):
        L, ks = lodf.stack(cont_idx)
        if len(ks):
            Lm = L                                        # (M, Cn) already monitored rows
            fk = base_flow[ks] + P * ptdf[ks]             # flow on contingency branches incl. project
            Fpost = f1[:, None] + Lm * fk[None, :]        # post-contingency flows incl. project
            Dpost = d0[:, None] + Lm * ptdf[ks][None, :]  # effective project DFAX
            Cpost = P * Dpost
            Lpost = np.abs(Fpost) / r[:, None]
            flag = (Lpost > load_thr) & (np.abs(Dpost) >= dfax_thr) & (np.sign(Cpost) == np.sign(Fpost))
            # exclude the contingency branch itself (flow is zero after outage)
            for j, k in enumerate(ks):
                if int(k) in lodf.pos:
                    flag[lodf.pos[int(k)], j] = False
            rows, cols = np.where(flag)
            if len(rows):
                # keep worst contingency per branch
                order = np.lexsort((-Lpost[rows, cols], rows))
                rows, cols = rows[order], cols[order]
                seen = set()
                for rr, cc in zip(rows, cols):
                    if rr in seen:
                        continue
                    seen.add(rr)
                    b = int(Mi[rr])
                    cand = dict(branch=b, cont=int(ks[cc]), loading_post=float(Lpost[rr, cc]),
                                loading_pre=float(abs(Fpost[rr, cc] - Cpost[rr, cc]) / r[rr]),
                                dfax=float(abs(Dpost[rr, cc])), contrib_mw=float(abs(Cpost[rr, cc])),
                                flow_post=float(abs(Fpost[rr, cc])), rating=float(r[rr]))
                    if b not in results or cand["loading_post"] > results[b]["loading_post"]:
                        results[b] = cand
    out = sorted(results.values(), key=lambda d: -d["loading_post"])
    return out[:max_facilities]


def effective_dfax(ptdf_j: np.ndarray, branch: int, cont: int, lodf: LODFCache) -> float:
    """Effective DFAX of another project on `branch` under contingency `cont`."""
    if cont < 0:
        return float(ptdf_j[branch])
    col, isl = lodf.get(cont)
    return float(ptdf_j[branch] + col[lodf.pos[branch]] * ptdf_j[cont])
