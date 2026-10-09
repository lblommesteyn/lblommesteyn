"""Constrained via minimisation: same copper, fewer vias.

Freerouting decides each wire's layer while it routes and never revisits it.
With the geometry held fixed, choosing layers afresh is the classic
constrained via minimisation problem (CVM; Hsu 1983, Pinter 1983, Chang & Du
1987), reported to remove up to ~40% of vias on hard multilayer examples. It
is graph colouring with an objective:

  chains     union-find over same-net segments that touch on a layer, except
             at a via or through-hole pad: a chain must stay on one layer
  domains    a chain may not take a layer where it would come too close to
             another net's pad, any via, or a mechanical hole; a chain that
             lands on an SMD pad is fixed to that pad's layer; locked copper
             (hand-drawn bridges) keeps its layer
  conflicts  two chains of different nets that come within the clearance of
             each other in plan cannot share a layer
  objective  a via site can be deleted when every chain (and pad) meeting
             there ends up on one layer; maximise the deleted sites

solved exactly as an integer programme (HiGHS through scipy). Nothing moves
in the plane and vias are only ever removed, so connectivity and clearance
are preserved by construction; drc.py, ratsnest.py and lvs.py re-check the
result anyway.

    python3 cvm.py BOARD.kicad_pcb -o OUT.kicad_pcb [--time 600]
"""
import os, sys, math, argparse, collections, time
D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, D)
import numpy as np
from sexpr import load, dumps, Q
import drc, collide

CLEAR = 0.09
EPS = 1e-3


def seg_dist(p, q, r, s):
    return drc._seg_seg_dist(p, q, r, s)


def pt_seg(a, b, c):
    return drc._seg_seg_dist(a, a, b, c)


class DSU:
    def __init__(self, n): self.p = list(range(n))
    def find(self, a):
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]; a = self.p[a]
        return a
    def union(self, a, b): self.p[self.find(a)] = self.find(b)


def build(path, clearance=CLEAR):
    pcb = load(path)
    cu = [str(l[1]) for l in pcb.find('layers')[1:] if len(l) > 2 and l[2] == 'signal']
    L = len(cu); li = {l: i for i, l in enumerate(cu)}
    segnodes = [s for s in pcb.find_all('segment')]
    vianodes = [v for v in pcb.find_all('via')]
    S = []
    for s in segnodes:
        a, b = s.find('start'), s.find('end')
        S.append(dict(p=(a[1], a[2]), q=(b[1], b[2]), r=s.find('width')[1] / 2,
                      l=li[s.val('layer')], net=int(s.find('net')[1]),
                      locked=s.val('locked') == 'yes'))
    V = []
    for v in vianodes:
        a = v.find('at')
        V.append(dict(p=(a[1], a[2]), r=v.find('size')[1] / 2, net=int(v.find('net')[1]),
                      locked=v.val('locked') == 'yes'))
    # pads and holes: exact geometry from drc.items, plus unnetted pads
    nets, _, items = drc.items(pcb)
    obst = []                         # (kind, net, layers set or None=all, poly, r)
    for o in items:
        if o['kind'] == 'pad':
            lays = {li[x] for x in o['layers'] if x in li}
            obst.append(('pad', o['net'], lays, o['poly'], o['r'], o['label']))
        elif o['kind'] == 'hole':
            obst.append(('hole', None, set(range(L)), o['poly'], o['r'], o['label']))
    for p in collide.pads_of(pcb):
        if p['net'] is None and not p.get('hole'):
            hw, hh = p['w'] / 2, p['h'] / 2
            poly = [(p['x']-hw, p['y']-hh), (p['x']+hw, p['y']-hh),
                    (p['x']+hw, p['y']+hh), (p['x']-hw, p['y']+hh)]
            lays = set(range(L)) if p['side'] == '*' else {0 if p['side'] == 'F' else L-1}
            obst.append(('pad', -1, lays, poly, 0.0, f"{p['ref']}.{p['pad']}"))
    return pcb, cu, segnodes, vianodes, S, V, obst


def solve(path, out, clearance=CLEAR, time_limit=600, verbose=True):
    from scipy.optimize import milp, LinearConstraint, Bounds
    from scipy.sparse import coo_matrix
    t0 = time.time()
    pcb, cu, segnodes, vianodes, S, V, obst = build(path, clearance)
    L = len(cu); n = len(S)

    # spatial grid over segments
    CELL = 1.0
    grid = collections.defaultdict(list)
    def cells_of(p, q, r):
        x0, x1 = min(p[0], q[0]) - r - clearance, max(p[0], q[0]) + r + clearance
        y0, y1 = min(p[1], q[1]) - r - clearance, max(p[1], q[1]) + r + clearance
        for gx in range(int(x0 // CELL), int(x1 // CELL) + 1):
            for gy in range(int(y0 // CELL), int(y1 // CELL) + 1):
                yield (gx, gy)
    for i, s in enumerate(S):
        for c in cells_of(s['p'], s['q'], s['r']): grid[c].append(i)

    # site points: vias and through-hole pads of each net
    def near(a, b, tol=EPS): return abs(a[0]-b[0]) < tol and abs(a[1]-b[1]) < tol
    def touches_point(s, pt, rad):
        return pt_seg(pt, s['p'], s['q']) <= rad + 1e-6

    # 1. chains: same net, same layer, touching, not at a via
    dsu = DSU(n)
    via_pts = collections.defaultdict(list)
    for k, v in enumerate(V): via_pts[v['net']].append(k)
    for i, s in enumerate(S):
        cand = set()
        for c in cells_of(s['p'], s['q'], s['r']): cand.update(grid[c])
        for j in cand:
            if j <= i: continue
            t = S[j]
            if t['net'] != s['net'] or t['l'] != s['l']: continue
            if seg_dist(s['p'], s['q'], t['p'], t['q']) > s['r'] + t['r'] + 1e-6: continue
            # where do they meet? if it is at a via of this net, keep them apart
            meet = [pt for pt in (s['p'], s['q'], t['p'], t['q'])
                    if touches_point(s, pt, s['r']) and touches_point(t, pt, t['r'])]
            at_via = any(any(math.hypot(pt[0]-V[k]['p'][0], pt[1]-V[k]['p'][1]) < V[k]['r']
                             for k in via_pts[s['net']]) for pt in meet) if meet else False
            if not at_via:
                dsu.union(i, j)
    roots = sorted({dsu.find(i) for i in range(n)})
    cid = {r: k for k, r in enumerate(roots)}
    chain = [cid[dsu.find(i)] for i in range(n)]
    C = len(roots)
    members = collections.defaultdict(list)
    for i, c in enumerate(chain): members[c].append(i)
    cur = [S[members[c][0]]['l'] for c in range(C)]
    cnet = [S[members[c][0]]['net'] for c in range(C)]
    for c in range(C):
        assert all(S[i]['l'] == cur[c] for i in members[c])
    locked = [any(S[i]['locked'] for i in members[c]) for c in range(C)]

    # 2. domains
    allowed = [set(range(L)) for _ in range(C)]
    for c in range(C):
        if locked[c]: allowed[c] = {cur[c]}
    for c in range(C):
        for i in members[c]:
            s = S[i]
            cap = [s['p'], s['q']]
            for (kind, onet, lays, poly, r, lab) in obst:
                # quick bbox reject
                xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
                m = r + s['r'] + 0.25
                if (max(s['p'][0], s['q'][0]) < min(xs) - m or min(s['p'][0], s['q'][0]) > max(xs) + m or
                        max(s['p'][1], s['q'][1]) < min(ys) - m or min(s['p'][1], s['q'][1]) > max(ys) + m):
                    continue
                g = drc._poly_poly_dist(cap, poly) - r - s['r']
                if kind == 'pad' and onet == cnet[c]:
                    # its own net's pad: if the chain lands on an SMD pad it is
                    # pinned to that pad's layer (only counts if it touches it now)
                    if g <= 1e-6 and len(lays) == 1 and cur[c] in lays:
                        allowed[c] &= lays
                    continue
                need = drc.NPTH_COPPER if kind == 'hole' else clearance
                if g < need - 1e-6:
                    allowed[c] -= lays
            # vias of other nets block every layer
            for k, v in enumerate(V):
                if v['net'] == cnet[c]: continue
                if abs(v['p'][0] - s['p'][0]) > 3 and abs(v['p'][0] - s['q'][0]) > 3: continue
                if pt_seg(v['p'], s['p'], s['q']) - v['r'] - s['r'] < clearance - 1e-6:
                    allowed[c] = set()
    bad = [c for c in range(C) if cur[c] not in allowed[c]]
    if bad:
        # the board already violates something here; leave those chains alone
        for c in bad: allowed[c] = {cur[c]}

    # 3. conflicts between chains of different nets
    conf = set()
    for i, s in enumerate(S):
        cand = set()
        for cc in cells_of(s['p'], s['q'], s['r']): cand.update(grid[cc])
        for j in cand:
            if j <= i: continue
            t = S[j]
            if t['net'] == s['net']: continue
            a, b = chain[i], chain[j]
            if a == b or (min(a, b), max(a, b)) in conf: continue
            if seg_dist(s['p'], s['q'], t['p'], t['q']) - s['r'] - t['r'] < clearance - 1e-6:
                conf.add((min(a, b), max(a, b)))

    # 4. via sites: members are chains with a segment at the via, plus pads
    sites = []
    for k, v in enumerate(V):
        mem = set(); pinned = set(); att = []
        for c_ in {chain[i] for c2 in cells_of(v['p'], v['p'], v['r']) for i in grid[c2]
                   if S[i]['net'] == v['net']}:
            for i in members[c_]:
                s = S[i]
                if touches_point(s, v['p'], v['r'] + s['r']):
                    mem.add(c_); att.append(i)
        # removing the via is only safe if, all on one layer, the copper that
        # met at it still touches without it: the attached segments must form
        # one connected group by segment-to-segment contact
        dd = DSU(len(att))
        for a_ in range(len(att)):
            for b_ in range(a_ + 1, len(att)):
                sa, sb = S[att[a_]], S[att[b_]]
                if seg_dist(sa['p'], sa['q'], sb['p'], sb['q']) <= sa['r'] + sb['r'] - 1e-4:
                    dd.union(a_, b_)
        exact = len({dd.find(a_) for a_ in range(len(att))}) <= 1
        for (kind, onet, lays, poly, r, lab) in obst:
            if kind != 'pad' or onet != v['net']: continue
            xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
            if not (min(xs) - r - v['r'] <= v['p'][0] <= max(xs) + r + v['r'] and
                    min(ys) - r - v['r'] <= v['p'][1] <= max(ys) + r + v['r']): continue
            if drc._poly_poly_dist([v['p']], poly) - r - v['r'] <= 1e-6:
                pinned |= {frozenset(lays)}
        removable = exact and not v['locked'] and all(len(p) == 1 for p in pinned)
        players = set().union(*pinned) if pinned else set()
        if removable and len(players) > 1: removable = False
        sites.append(dict(k=k, mem=sorted(mem), pin=players, removable=removable))

    # 5. integer programme
    xi = {}
    for c in range(C):
        for l in sorted(allowed[c]): xi[(c, l)] = len(xi)
    si = {}
    for st in sites:
        if not st['removable'] or not st['mem']: continue
        for l in range(L):
            if st['pin'] and l not in st['pin']: continue
            if all((c, l) in xi for c in st['mem']):
                si[(st['k'], l)] = len(xi) + len(si)
    nv = len(xi) + len(si)
    rows, cols, vals, lo, hi = [], [], [], [], []
    r = 0
    def add(coefs, a, b):
        nonlocal r
        for j, v_ in coefs: rows.append(r); cols.append(j); vals.append(v_)
        lo.append(a); hi.append(b); r += 1
    for c in range(C):
        add([(xi[(c, l)], 1) for l in allowed[c]], 1, 1)
    for (a, b) in conf:
        for l in allowed[a] & allowed[b]:
            add([(xi[(a, l)], 1), (xi[(b, l)], 1)], -np.inf, 1)
    for (k, l), j in si.items():
        st = sites[k]
        for c in st['mem']:
            add([(j, 1), (xi[(c, l)], -1)], -np.inf, 0)
    by_site = collections.defaultdict(list)
    for (k, l), j in si.items(): by_site[k].append(j)
    for k, js in by_site.items():
        add([(j, 1) for j in js], -np.inf, 1)
    A = coo_matrix((vals, (rows, cols)), shape=(r, nv)).tocsr()
    obj = np.zeros(nv)
    for j in si.values(): obj[j] = -1.0          # maximise removed sites
    # a tiny preference for the current layer keeps the answer close to the original
    for (c, l), j in xi.items():
        if l == cur[c]: obj[j] = -1e-4
    if verbose:
        print(f"  {len(S)} segments in {C} chains, {len(V)} vias "
              f"({sum(1 for s in sites if s['removable'])} removable sites), "
              f"{len(conf)} conflicting chain pairs, {nv} variables, {r} constraints "
              f"({time.time()-t0:.0f}s to build)")
    res = milp(obj, constraints=LinearConstraint(A, lo, hi), integrality=np.ones(nv),
               bounds=Bounds(0, 1), options=dict(time_limit=time_limit, disp=False))
    if res.x is None:
        print("  no solution:", res.message); return None
    x = res.x
    newl = [cur[c] for c in range(C)]
    for (c, l), j in xi.items():
        if x[j] > 0.5: newl[c] = l
    removed = {k for (k, l), j in si.items() if x[j] > 0.5}
    # sanity: a removed site really has all members on one layer
    for k in removed:
        st = sites[k]
        assert len({newl[c] for c in st['mem']}) <= 1
    moved = sum(1 for c in range(C) if newl[c] != cur[c])
    for i, sn in enumerate(segnodes):
        sn.find('layer')[1] = Q(cu[newl[chain[i]]])
    keep = [c for c in pcb if not (isinstance(c, list) and c and c[0] == 'via'
                                   and any(c is vianodes[k] for k in removed))]
    pcb[:] = keep
    open(out, 'w').write(dumps(pcb) + '\n')
    if verbose:
        print(f"  {res.message.strip()}  -- moved {moved} chains, removed {len(removed)} of "
              f"{len(V)} vias -> {len(V) - len(removed)}  ({time.time()-t0:.0f}s)")
    return len(V) - len(removed)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('pcb'); ap.add_argument('-o', '--out', required=True)
    ap.add_argument('--time', type=float, default=600)
    ap.add_argument('--clearance', type=float, default=CLEAR)
    a = ap.parse_args()
    solve(a.pcb, a.out, a.clearance, a.time)
