"""DC network engine: PTDF / LODF / N-1 screening on a sparse B matrix.

Everything is in MW if injections are given in MW (angles are then in "MW-scaled"
radians; we never need physical angles). Susceptance b = 1/(x*tap) in per unit on the
case base; flow_MW = b * (theta_f - theta_t) when theta solves B theta = P_MW.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import scipy.sparse as sp
from scipy.sparse.linalg import splu


class DCNetwork:
    def __init__(self, bus: pd.DataFrame, branch: pd.DataFrame, ref_bus_id: int | None = None):
        self.bus = bus.reset_index(drop=True)
        self.branch = branch.reset_index(drop=True)
        self.n = len(self.bus)
        self.m = len(self.branch)
        self.bus_idx = {int(b): i for i, b in enumerate(self.bus.bus_id.values)}
        self.f = self.branch.from_bus_id.map(self.bus_idx).values.astype(np.int64)
        self.t = self.branch.to_bus_id.map(self.bus_idx).values.astype(np.int64)
        x = self.branch.x.values.astype(float).copy()
        tap = self.branch.ratio.values.astype(float).copy()
        tap[tap == 0] = 1.0
        self.b = 1.0 / (x * tap)
        self.rate = self.branch.rateA.values.astype(float).copy()
        kv = self.bus.set_index("bus_id").baseKV
        self.kv_from = self.branch.from_bus_id.map(kv).values
        self.kv_to = self.branch.to_bus_id.map(kv).values
        self.kvmax = np.maximum(self.kv_from, self.kv_to)
        self.is_xfmr = (self.branch.branch_device_type != "Line").values
        self.A = sp.csr_matrix(
            (np.r_[np.ones(self.m), -np.ones(self.m)],
             (np.r_[np.arange(self.m), np.arange(self.m)], np.r_[self.f, self.t])),
            shape=(self.m, self.n))
        self.B = (self.A.T @ sp.diags(self.b) @ self.A).tocsc()
        if ref_bus_id is None:
            # ref = highest-degree internal bus (stable choice)
            deg = np.bincount(np.r_[self.f, self.t], minlength=self.n)
            ref_bus_id = int(self.bus.bus_id.values[np.argmax(deg)])
        self.ref = self.bus_idx[int(ref_bus_id)]
        self.keep = np.ones(self.n, bool)
        self.keep[self.ref] = False
        self.lu = splu(self.B[self.keep][:, self.keep])
        self._ptdf_cache: dict[int, np.ndarray] = {}

    # ---- basic solves -----------------------------------------------------------
    def solve_theta(self, P: np.ndarray) -> np.ndarray:
        theta = np.zeros(self.n)
        theta[self.keep] = self.lu.solve(P[self.keep])
        return theta

    def flows(self, P: np.ndarray) -> np.ndarray:
        th = self.solve_theta(P)
        return self.b * (th[self.f] - th[self.t])

    def ptdf_vector(self, inj: np.ndarray) -> np.ndarray:
        """Flow sensitivities (m,) to an injection vector (n,), assumed balanced (sum 0)."""
        return self.flows(inj)

    def ptdf_bus(self, i: int) -> np.ndarray:
        """PTDF column for +1 at bus i, -1 at the reference bus (cached)."""
        if i not in self._ptdf_cache:
            e = np.zeros(self.n); e[i] = 1.0; e[self.ref] -= 1.0
            self._ptdf_cache[i] = self.flows(e).astype(np.float32)
        return self._ptdf_cache[i]

    def ptdf_pair(self, i: int, j: int) -> np.ndarray:
        """PTDF for +1 at i, -1 at j."""
        return self.ptdf_bus(i).astype(float) - self.ptdf_bus(j).astype(float)

    def project_ptdf(self, poi_idx: int, withdraw: np.ndarray) -> np.ndarray:
        """Sensitivity of flows to +1 MW at the POI withdrawn according to `withdraw`
        (n,), which sums to 1 (e.g. load-proportional). Emulates a system-wide
        re-dispatch offset as in a generator deliverability test."""
        inj = -withdraw.copy(); inj[poi_idx] += 1.0
        return self.flows(inj)

    # ---- LODF -------------------------------------------------------------------
    def lodf_column(self, k: int) -> tuple[np.ndarray, bool]:
        """LODF for outage of branch k: post-outage flow_l = flow_l + L[l]*flow_k.
        Returns (L (m,), islanding_flag)."""
        p = self.ptdf_pair(self.f[k], self.t[k])
        denom = 1.0 - p[k]
        if abs(denom) < 1e-6:  # radial / islanding outage
            L = np.zeros(self.m); L[k] = -1.0
            return L, True
        L = p / denom
        L[k] = -1.0
        return L, False

    def lodf_matrix(self, cont: np.ndarray, rows: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
        """LODF matrix restricted to monitored `rows` (M,) x contingencies `cont` (Cn,).
        Returns (L float32 (M,Cn), islanding (Cn,) bool)."""
        rows = np.arange(self.m) if rows is None else rows
        L = np.zeros((len(rows), len(cont)), dtype=np.float32)
        isl = np.zeros(len(cont), bool)
        for j, k in enumerate(cont):
            col, flag = self.lodf_column(int(k))
            L[:, j] = col[rows]
            isl[j] = flag
        return L, isl

    # ---- topology helpers --------------------------------------------------------
    def adjacency(self, mask: np.ndarray | None = None) -> sp.csr_matrix:
        mask = np.ones(self.m, bool) if mask is None else mask
        f, t = self.f[mask], self.t[mask]
        M = sp.csr_matrix((np.ones(len(f)), (f, t)), shape=(self.n, self.n))
        return ((M + M.T) > 0).astype(np.int8).tocsr()

    def hops_from(self, src: int, max_hops: int, mask: np.ndarray | None = None) -> np.ndarray:
        """BFS hop distance from bus index src (inf beyond max_hops)."""
        adj = self.adjacency(mask)
        dist = np.full(self.n, np.inf); dist[src] = 0
        frontier = np.array([src])
        for h in range(1, max_hops + 1):
            nb = adj[frontier].nonzero()[1]
            nb = np.unique(nb[np.isinf(dist[nb])])
            if len(nb) == 0:
                break
            dist[nb] = h
            frontier = nb
        return dist
