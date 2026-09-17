"""Public-topology model: what can be inferred from a HIFLD-like layer alone.

Nodes are (substation, kV) pairs; lines join two substations at a kV; transformers join two
kV levels inside a substation. Reactances are *guessed* from voltage class and straight-line
length (typical ohm/km values) because the public layer has no impedances or ratings.
The resulting DC model yields an *approximate* distribution factor ("apx_dfax") of a POI
injection on every public facility - a physics-informed, purely public feature.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import scipy.sparse as sp
from scipy.sparse.csgraph import connected_components
from ..sim.network import DCNetwork
from ..sim.naming import to_xy_km

X_PER_KM = {765: 0.6e-4, 500: 1.3e-4, 345: 3.1e-4, 230: 8.5e-4, 161: 1.7e-3, 138: 2.5e-3, 115: 3.8e-3, 100: 5.0e-3, 69: 1.2e-2}
X_XFMR = {765: 0.008, 500: 0.012, 345: 0.04, 230: 0.08, 161: 0.12, 138: 0.2, 115: 0.25, 100: 0.3, 69: 0.4}


def _kvc(kv, table):
    return table[min(table, key=lambda k: abs(k - kv))]


class PublicTopology:
    def __init__(self, subs: pd.DataFrame, facilities: pd.DataFrame):
        self.subs = subs.set_index("sub_id")
        fac = facilities.copy()
        self.fac = fac.set_index("fid")
        # nodes
        nodes = set()
        for r in fac.itertuples():
            if r.kind == "L":
                nodes.add((int(r.sub_a), int(r.kv))); nodes.add((int(r.sub_b), int(r.kv)))
            elif r.kind == "X":
                p = r.fid.split(":"); nodes.add((int(p[1]), int(p[2]))); nodes.add((int(p[1]), int(p[3])))
            else:
                nodes.add((int(r.sub_a), int(r.kv)))
        self.nodes = sorted(nodes)
        self.node_idx = {n: i for i, n in enumerate(self.nodes)}
        # implicit transformer ties for substations with several levels but no visible transformer
        by_sub: dict[int, list[int]] = {}
        for s, kv in self.nodes:
            by_sub.setdefault(s, []).append(kv)
        xf_seen = set(fid for fid in fac.fid if fid.startswith("X:"))
        rows = []
        for r in fac.itertuples():
            if r.kind == "L":
                rows.append(dict(fid=r.fid, a=self.node_idx[(int(r.sub_a), int(r.kv))], b=self.node_idx[(int(r.sub_b), int(r.kv))],
                                 x=_kvc(r.kv, X_PER_KM) * max(0.3, float(r.length_km)), kind="L"))
            elif r.kind == "X":
                p = r.fid.split(":")
                rows.append(dict(fid=r.fid, a=self.node_idx[(int(p[1]), int(p[2]))], b=self.node_idx[(int(p[1]), int(p[3]))],
                                 x=_kvc(int(p[2]), X_XFMR), kind="X"))
            else:   # bus tie: same node both ends -> no edge in the DC model (tracked as facility only)
                pass
        for s, kvs in by_sub.items():
            kvs = sorted(kvs)
            for k1, k2 in zip(kvs[:-1], kvs[1:]):
                if f"X:{s}:{k2}:{k1}" not in xf_seen:
                    rows.append(dict(fid=f"IMPLICIT:{s}:{k2}:{k1}", a=self.node_idx[(s, k1)], b=self.node_idx[(s, k2)], x=_kvc(k2, X_XFMR) * 1.5, kind="I"))
        self.edges = pd.DataFrame(rows)
        # largest connected component
        n = len(self.nodes)
        A = sp.csr_matrix((np.ones(len(self.edges)), (self.edges.a.values, self.edges.b.values)), shape=(n, n))
        ncomp, lab = connected_components(A, directed=False)
        main = np.argmax(np.bincount(lab))
        self.in_main = lab == main
        keep_nodes = np.where(self.in_main)[0]
        remap = {int(o): i for i, o in enumerate(keep_nodes)}
        e = self.edges[self.edges.a.map(remap).notna() & self.edges.b.map(remap).notna()].copy()
        e["a2"] = e.a.map(remap).astype(int); e["b2"] = e.b.map(remap).astype(int)
        bus = pd.DataFrame(dict(bus_id=np.arange(len(keep_nodes)), baseKV=[self.nodes[o][1] for o in keep_nodes]))
        br = pd.DataFrame(dict(from_bus_id=e.a2.values, to_bus_id=e.b2.values, x=e.x.values, ratio=0.0, rateA=0.0,
                               branch_device_type=np.where(e.kind.values == "L", "Line", "Transformer")))
        self.net = DCNetwork(bus, br)
        self.edge_fid = e.fid.values
        self.fid_edge = {f: i for i, f in enumerate(self.edge_fid) if not f.startswith("IMPLICIT")}
        self.node_remap = remap
        self.n_main = len(keep_nodes)
        # substation-level graph for hops + geometry
        subs_l = fac[fac.kind == "L"]
        self.sub_ids = np.array(sorted(set(subs_l.sub_a) | set(subs_l.sub_b) | set(self.subs.index)))
        self.sub_pos = {int(s): i for i, s in enumerate(self.sub_ids)}
        a = subs_l.sub_a.map(self.sub_pos).values; b = subs_l.sub_b.map(self.sub_pos).values
        m = len(self.sub_ids)
        G = sp.csr_matrix((np.ones(len(a)), (a, b)), shape=(m, m))
        self.sub_adj = ((G + G.T) > 0).astype(np.int8).tocsr()
        self.sub_xy = to_xy_km(self.subs.reindex(self.sub_ids).lat.values, self.subs.reindex(self.sub_ids).lon.values)
        self.sub_degree = np.asarray(self.sub_adj.sum(axis=1)).ravel()
        fa = fac.sub_a.map(self.sub_pos); fb = fac.sub_b.map(self.sub_pos)
        self.fac_xy_a = self.sub_xy[fa.values.astype(int)]
        self.fac_xy_b = self.sub_xy[fb.fillna(fa).values.astype(int)]
        self.fac_ids = fac.fid.values
        self.fac_pos = {f: i for i, f in enumerate(self.fac_ids)}
        self._hops_cache: dict[int, np.ndarray] = {}
        self._dfax_cache: dict[tuple, np.ndarray] = {}
        self._withdraw = np.ones(self.n_main) / self.n_main

    # ---- geometry / hops -------------------------------------------------------------
    def hops_from_sub(self, sub_id: int, max_hops: int = 8) -> np.ndarray:
        if sub_id not in self._hops_cache:
            src = self.sub_pos[int(sub_id)]
            dist = np.full(len(self.sub_ids), np.inf); dist[src] = 0
            frontier = np.array([src])
            for h in range(1, max_hops + 1):
                nb = self.sub_adj[frontier].nonzero()[1]
                nb = np.unique(nb[np.isinf(dist[nb])])
                if len(nb) == 0:
                    break
                dist[nb] = h; frontier = nb
            self._hops_cache[sub_id] = dist
        return self._hops_cache[sub_id]

    def fac_hops(self, sub_id: int) -> np.ndarray:
        """Hop distance from POI substation to each facility (min over endpoints)."""
        d = self.hops_from_sub(sub_id)
        fa = np.array([self.sub_pos.get(int(s), -1) for s in self.fac.sub_a.values])
        fb = np.array([self.sub_pos.get(int(s), -1) if not np.isnan(s) else -1 for s in self.fac.sub_b.values])
        ha = np.where(fa >= 0, d[np.clip(fa, 0, None)], np.inf); hb = np.where(fb >= 0, d[np.clip(fb, 0, None)], np.inf)
        return np.minimum(ha, hb)

    def fac_dist_km(self, sub_id: int) -> tuple[np.ndarray, np.ndarray]:
        xy = self.sub_xy[self.sub_pos[int(sub_id)]]
        da = np.hypot(*(self.fac_xy_a - xy).T); db = np.hypot(*(self.fac_xy_b - xy).T)
        return np.minimum(da, db), np.maximum(da, db)

    # ---- approximate distribution factors ---------------------------------------------
    def poi_node(self, sub_id: int, kv: float) -> int | None:
        kvs = [k for (s, k) in self.nodes if s == int(sub_id)]
        if not kvs:
            return None
        k = min(kvs, key=lambda x: abs(x - kv))
        o = self.node_idx[(int(sub_id), k)]
        return self.node_remap.get(o)

    def apx_dfax(self, sub_id: int, kv: float) -> np.ndarray | None:
        """Approximate DFAX (flow sensitivity, MW per MW) of +1 MW at the POI, withdrawn
        uniformly across the public network, for every public facility (NaN if unmapped)."""
        key = (int(sub_id), int(kv))
        if key in self._dfax_cache:
            return self._dfax_cache[key]
        node = self.poi_node(sub_id, kv)
        out = np.full(len(self.fac_ids), np.nan)
        if node is None:
            self._dfax_cache[key] = out; return out
        p = self.net.project_ptdf(node, self._withdraw)
        for f, i in self.fid_edge.items():
            out[self.fac_pos[f]] = p[i]
        self._dfax_cache[key] = out
        return out

    def apx_dfax_n1(self, sub_id: int, kv: float, n_cont: int = 30) -> np.ndarray:
        """Max effective DFAX over the n_cont contingencies the project most affects (public-graph LODF)."""
        d0 = self.apx_dfax(sub_id, kv)
        node = self.poi_node(sub_id, kv)
        if node is None:
            return d0
        p = self.net.project_ptdf(node, self._withdraw)
        order = np.argsort(-np.abs(p))[:n_cont]
        best = np.abs(p.copy())
        for k in order:
            L, isl = self.net.lodf_column(int(k))
            if isl:
                continue
            eff = np.abs(p + L * p[k]); eff[k] = 0.0
            best = np.maximum(best, eff)
        out = np.full(len(self.fac_ids), np.nan)
        for f, i in self.fid_edge.items():
            out[self.fac_pos[f]] = best[i]
        return out
