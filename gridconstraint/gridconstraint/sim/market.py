"""DC-OPF market snapshots on the hidden case -> LMPs, binding constraints, shadow prices.

Soft thermal limits (penalty PENALTY_PRICE $/MWh, like PJM's transmission constraint
penalty factor) and load shedding at VOLL keep the LP feasible under load growth,
retirements and outages. Duals give bus LMPs and constraint shadow prices.
"""
from __future__ import annotations
import numpy as np
import scipy.sparse as sp
from scipy.optimize import linprog
from .. import config as C

VOLL = 5000.0


def solve_opf(net, Pd: np.ndarray, gen_bus: np.ndarray, gen_pmax: np.ndarray, gen_cost: np.ndarray,
              rate: np.ndarray, monitored: np.ndarray, out_mask: np.ndarray | None = None,
              penalty: float = C.PENALTY_PRICE):
    """Returns dict(status, pg, lmp (n,), shadow (m,), flow (m,), shed (n,))."""
    n, m = net.n, net.m
    active = np.ones(m, bool) if out_mask is None else ~out_mask
    b = net.b * active
    A = net.A
    B = (A.T @ sp.diags(b) @ A).tocsr()
    ng = len(gen_bus)
    G = sp.csr_matrix((np.ones(ng), (gen_bus, np.arange(ng))), shape=(n, ng))
    mon = np.where(monitored & (rate > 0) & active)[0]
    Mn = len(mon)
    F = (sp.diags(b[mon]) @ A[mon]).tocsr()             # flow (MW) = F theta
    I_n = sp.identity(n, format="csr")
    # variables: theta(n) | pg(ng) | shed(n) | spill(n) | s(Mn)   [s: slack shared by both directions]
    # balance: B theta - G pg - shed + spill = -Pd    (shed: unserved load; spill: curtailed injection)
    Aeq = sp.hstack([B, -G, -I_n, I_n, sp.csr_matrix((n, Mn))]).tocsr()
    beq = -Pd
    # |F theta| <= rate + s
    Z = sp.csr_matrix((Mn, ng)); Zn = sp.csr_matrix((Mn, n))
    Aub = sp.vstack([sp.hstack([F, Z, Zn, Zn, -sp.identity(Mn, format="csr")]),
                     sp.hstack([-F, Z, Zn, Zn, -sp.identity(Mn, format="csr")])]).tocsr()
    bub = np.r_[rate[mon], rate[mon]]
    c = np.r_[np.zeros(n), gen_cost, np.full(n, VOLL), np.full(n, VOLL), np.full(Mn, penalty)]
    lo = np.r_[np.full(n, -np.inf), np.zeros(ng), np.zeros(n), np.zeros(n), np.zeros(Mn)]
    hi = np.r_[np.full(n, np.inf), gen_pmax, np.maximum(Pd, 0.0), np.maximum(-Pd, 0.0) + 1e-6, np.full(Mn, np.inf)]
    lo[net.ref] = 0.0; hi[net.ref] = 0.0
    res = linprog(c, A_ub=Aub, b_ub=bub, A_eq=Aeq, b_eq=beq, bounds=np.c_[lo, hi], method="highs",
                  options={"presolve": True})
    if res.status != 0:
        return dict(status=res.status, message=res.message)
    x = res.x
    theta = x[:n]; pg = x[n:n + ng]; shed = x[n + ng:2 * n + ng] - x[2 * n + ng:3 * n + ng]
    flow = net.b * active * (theta[net.f] - theta[net.t])
    lmp = -res.eqlin.marginals               # $/MWh: cost of +1 MW load at bus
    mu = res.ineqlin.marginals               # <= 0 for binding
    shadow = np.zeros(m)
    sp_pos = -mu[:Mn]; sp_neg = -mu[Mn:]
    shadow[mon] = np.maximum(sp_pos, sp_neg)
    return dict(status=0, pg=pg, lmp=lmp, shadow=shadow, flow=flow, shed=shed, cost=res.fun)


# ---- multiprocessing helpers (fork start method: globals inherited) ---------------------
_NET = None


def _set_global_net(net):
    global _NET
    _NET = net


def _opf_task(args):
    Pd, gb, pmax, cost, rate, mon, out_mask = args
    return solve_opf(_NET, Pd, gb, pmax, cost, rate, mon, out_mask=out_mask)
