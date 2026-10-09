"""Finish a nearly-routed board by negotiated rip-up and reroute in a window.

Freerouting stalls a few connections short, and routing each missing
connection alone around fixed copper (finish_router.py) fails because the
way through is taken. This rips up a window around each gap -- every unlocked
segment and via lying wholly inside it -- and reroutes every net that is now
broken there, together, with negotiated congestion (PathFinder, McMurchie &
Ebeling 1995, the standard FPGA router): nets may overlap at a price that
rises each round (present congestion) and on cells that stay contested
(history), until no two nets claim the same space. The old routing is a
legal solution of everything but the gap, so the window is never harder than
the board was.

Routing is a multi-source Dijkstra (scipy csgraph) per net, grown as a
Steiner tree over its copper clusters, on a grid with 8-way moves per layer
and through-via edges. Obstacles -- all copper left outside the rip-up, pads,
holes, the board edge -- are rasterised with exact clearances; each net may
touch its own copper. A result is kept only if drc.py finds no violation on
the whole board and no connection is lost.

    python3 negotiate.py BOARD.kicad_pcb -o OUT.kicad_pcb
"""
import os, sys, math, argparse, collections, time
D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, D)
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.ndimage import binary_dilation
from sexpr import load, dumps, Q
import drc, collide, ratsnest
import finish_router as F

GRID = 0.05
TRACK = 0.09
CLR = 0.09
VIA = 0.45
DRILL = 0.20
EDGE = 0.30          # copper to board edge
MARGIN = 0.012       # rasterisation safety on top of every clearance
VIA_STEPS = 300      # one via costs as much as 15mm of trace


# ------------------------------------------------------------ geometry
def dist_grid(X, Y, poly, r):
    """distance from each (X, Y) to a capsule/convex polygon, minus r"""
    if len(poly) == 1:
        return np.hypot(X - poly[0][0], Y - poly[0][1]) - r
    def pseg(ax, ay, bx, by):
        dx, dy = bx - ax, by - ay
        L = dx * dx + dy * dy
        if L < 1e-12: return np.hypot(X - ax, Y - ay)
        t = np.clip(((X - ax) * dx + (Y - ay) * dy) / L, 0, 1)
        return np.hypot(X - (ax + t * dx), Y - (ay + t * dy))
    if len(poly) == 2:
        return pseg(*poly[0], *poly[1]) - r
    d = np.full(X.shape, np.inf)
    inside = np.ones(X.shape, bool)
    n = len(poly)
    area = sum(poly[i][0] * poly[(i+1) % n][1] - poly[(i+1) % n][0] * poly[i][1] for i in range(n))
    sgn = 1 if area > 0 else -1
    for i in range(n):
        (ax, ay), (bx, by) = poly[i], poly[(i + 1) % n]
        d = np.minimum(d, pseg(ax, ay, bx, by))
        inside &= sgn * ((bx - ax) * (Y - ay) - (by - ay) * (X - ax)) >= 0
    return np.where(inside, 0.0, d) - r


def gdist(a, b):
    return drc._poly_poly_dist(a['poly'], b['poly']) - a['r'] - b['r']


# ------------------------------------------------------------ window solve
class Window:
    def __init__(self, x0, y0, x1, y1, L):
        self.x0, self.y0 = x0, y0
        self.nx = int((x1 - x0) / GRID) + 1
        self.ny = int((y1 - y0) / GRID) + 1
        self.L = L
        xs = x0 + np.arange(self.nx) * GRID
        ys = y0 + np.arange(self.ny) * GRID
        self.X, self.Y = np.meshgrid(xs, ys)
        self.N = L * self.ny * self.nx

    def idx(self, l, y, x): return (l * self.ny + y) * self.nx + x

    def pos(self, node):
        l, rem = divmod(node, self.ny * self.nx)
        y, x = divmod(rem, self.nx)
        return l, self.x0 + x * GRID, self.y0 + y * GRID


def disc(rad_cells):
    r = int(math.ceil(rad_cells))
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    return (xx * xx + yy * yy) <= rad_cells * rad_cells + 1e-9


def pad_key(p):
    return (p['ref'], p['pad'], round(p['x'], 3), round(p['y'], 3))


def net_clusters(pads, segs, vias, n):
    """ratsnest-rule clusters of net n: list of [(type, item)]"""
    nodes = ([('P', p) for p in pads if p['net'] == n] +
             [('S', x) for x in segs if x['net'] == n] +
             [('V', x) for x in vias if x['net'] == n])
    dsu = list(range(len(nodes)))
    def f(a):
        while dsu[a] != a: dsu[a] = dsu[dsu[a]]; a = dsu[a]
        return a
    for a in range(len(nodes)):
        for b in range(a + 1, len(nodes)):
            if ratsnest._touch(nodes[a][0], nodes[a][1], nodes[b][0], nodes[b][1]):
                dsu[f(a)] = f(b)
    groups = collections.defaultdict(list)
    for a in range(len(nodes)): groups[f(a)].append(nodes[a])
    return list(groups.values())


def solve_window(pcb, cu, box, outline, keep_nets, iters=40, verbose=False):
    """Rip up and reroute inside box. Returns (added segs, added vias,
    removed nodes) or None."""
    L = len(cu); li = {l: i for i, l in enumerate(cu)}
    bx0, by0, bx1, by1 = box
    inside = lambda p: bx0 <= p[0] <= bx1 and by0 <= p[1] <= by1
    rip = []
    for s in pcb.find_all('segment'):
        if s.val('locked') == 'yes': continue
        a, b = s.find('start'), s.find('end')
        if inside((a[1], a[2])) and inside((b[1], b[2])): rip.append(s)
    for v in pcb.find_all('via'):
        if v.val('locked') == 'yes': continue
        a = v.find('at')
        if inside((a[1], a[2])): rip.append(v)
    ripset = set(map(id, rip))
    ripped_nets = {int(n.find('net')[1]) for n in rip}
    # the board without the ripped copper
    rest = [c for c in pcb if id(c) not in ripset]
    import copy
    work = copy.copy(pcb); work[:] = rest
    nets, _, items = drc.items(work)
    for it in items:
        it['lays'] = (set(range(L)) if it['layers'] >= set(cu) else {li[x] for x in it['layers'] if x in li})
    # unnetted pads (mechanical tabs) are obstacles too
    for p in collide.pads_of(work):
        if p['net'] is None and not p.get('hole'):
            hw, hh = p['w'] / 2, p['h'] / 2
            items.append(dict(kind='pad', net=('nonet',), layers=set(),
                              lays=set(range(L)) if p['side'] == '*' else {0 if p['side'] == 'F' else L - 1},
                              poly=[(p['x']-hw, p['y']-hh), (p['x']+hw, p['y']-hh),
                                    (p['x']+hw, p['y']+hh), (p['x']-hw, p['y']+hh)], r=0.0))

    # nets to route: broken by the rip-up, or broken already, with copper here
    route_nets = set(ripped_nets) | set(keep_nets)
    W = Window(bx0, by0, bx1, by1, L)
    ox0, oy0, ox1, oy1 = outline
    # static owners: -1 free, net id, -2 blocked for everyone
    tr_own = np.full((L, W.ny, W.nx), -1, np.int64)
    vo_own = np.full((W.ny, W.nx), -1, np.int64)
    def claim(arr, mask, owner):
        if owner is None:
            arr[mask] = -2; return
        free = mask & (arr == -1)
        arr[free] = owner
        arr[mask & (arr != owner) & (arr != -1)] = -2
    reach = max(VIA / 2, TRACK / 2) + 0.25
    own_cells = collections.defaultdict(lambda: np.zeros((L, W.ny, W.nx), bool))
    net_items = collections.defaultdict(list)
    for it in items:
        xs = [p[0] for p in it['poly']]; ys = [p[1] for p in it['poly']]
        if (max(xs) + it['r'] + reach < bx0 or min(xs) - it['r'] - reach > bx1 or
                max(ys) + it['r'] + reach < by0 or min(ys) - it['r'] - reach > by1):
            if isinstance(it['net'], int) and it['net'] in route_nets:
                net_items[it['net']].append(it)
            continue
        d = dist_grid(W.X, W.Y, it['poly'], it['r'])
        need = drc.NPTH_COPPER if it['kind'] == 'hole' else CLR
        owner = it['net'] if isinstance(it['net'], int) else None
        tmask = d < TRACK / 2 + need + MARGIN
        vmask = d < VIA / 2 + need + MARGIN
        for l in it['lays']:
            claim(tr_own[l], tmask, owner)
        claim(vo_own, vmask, owner)
        if owner is not None:
            net_items[owner].append(it)
            if owner in route_nets:
                for l in it['lays']:
                    own_cells[owner][l] |= d <= -1e-6 + 0.0
    # board edge
    de = np.minimum.reduce([W.X - ox0, ox1 - W.X, W.Y - oy0, oy1 - W.Y])
    for l in range(L): tr_own[l][de < TRACK / 2 + EDGE] = -2
    vo_own[de < VIA / 2 + EDGE] = -2

    # copper clusters of each net (whole board), and which cells they own here
    conns = {}
    stubs = {}
    own_ok = {}
    # clusters by ratsnest's own touch rules, so "connected" here means what
    # the completeness check means
    rn, rpads, rsegs, rvias = ratsnest.items_of(work)
    _, ppads, psegs, pvias = ratsnest.items_of(pcb)
    for n in route_nets:
        # which cluster each pad was in before the rip-up: pieces the rip-up
        # made must rejoin their own cluster; only the gap's two clusters are
        # joined to each other
        pre = {}
        for k_, g in enumerate(net_clusters(ppads, psegs, pvias, n)):
            for t, x in g:
                if t == 'P': pre[pad_key(x)] = k_
        if n in keep_nets:
            a_, b_ = keep_nets[n]
            near_ = lambda pt: min((p for p in ppads if p['net'] == n),
                                   key=lambda p: (p['x'] - pt[0]) ** 2 + (p['y'] - pt[1]) ** 2)
            ka, kb = pre[pad_key(near_(a_))], pre[pad_key(near_(b_))]
            pre = {k: (ka if v == kb else v) for k, v in pre.items()}
        units = collections.defaultdict(list)
        for g in net_clusters(rpads, rsegs, rvias, n):
            pk = [pre[pad_key(x)] for t, x in g if t == 'P']
            if not pk: continue                              # dead copper
            its = []
            for t, x in g:
                if t == 'P':
                    its.append(dict(kind='pad', poly=x['poly'], r=0.0,
                                    lays=set(range(L)) if x['layer'] is None else {li[x['layer']]}))
                elif t == 'S':
                    its.append(dict(kind='trace', poly=[x['p'], x['q']], r=x['width'] / 2,
                                    lays={li[x['layer']]}))
                else:
                    its.append(dict(kind='via', poly=[x['p']], r=x['size'] / 2, lays=set(range(L))))
            units[pk[0]].append(its)
        unit_masks = []
        for cl in units.values():
            if len(cl) < 2: continue
            # Where a new path may join each cluster. ratsnest (and our
            # completeness check) joins segments only at coincident endpoints, so
            # an existing trace is a target only at its two ends, and a path that
            # ends there gets a stub to the exact endpoint. Pads and vias count
            # wherever the path lands inside them.
            masks = []
            for g in cl:
                m = np.zeros((L, W.ny, W.nx), bool)
                for it in g:
                    if it['kind'] == 'trace':
                        for E in it['poly']:
                            d = np.hypot(W.X - E[0], W.Y - E[1])
                            hit = d <= it['r']
                            for l in it['lays']:
                                m[l] |= hit
                                for (yy, xx) in zip(*np.nonzero(hit)):
                                    stubs[(n, W.idx(l, yy, xx))] = E
                    else:
                        d = dist_grid(W.X, W.Y, it['poly'], it['r'])
                        hit = d <= -0.02
                        if not hit.any(): hit = d <= 0
                        for l in it['lays']: m[l] |= hit
                masks.append(m)
            if sum(1 for m in masks if m.any()) < len(masks):
                if verbose: print(f"      net {n}: {len(masks)} clusters, {sum(1 for m in masks if m.any())} reach the window")
                return None           # a cluster has no copper in the window
            unit_masks.append(masks)
        if unit_masks:
            conns[n] = unit_masks
            # a net may always stand on its own copper, even where a
            # neighbouring pad's clearance halo covers it (fine-pitch pads)
            own_ok[n] = np.any([m for u in unit_masks for m in u], axis=0)
    if not conns:
        if verbose: print("      nothing to route")
        return None

    # graph template
    L_, ny, nx = L, W.ny, W.nx
    moves = [(0, 1, 1.0), (1, 0, 1.0), (1, 1, math.sqrt(2)), (1, -1, math.sqrt(2))]
    R_tt = (TRACK + CLR + MARGIN) / GRID
    R_vt = (VIA / 2 + TRACK / 2 + CLR + MARGIN) / GRID
    R_vv = (VIA + CLR + MARGIN) / GRID
    D_tt, D_vt, D_vv = disc(R_tt), disc(R_vt), disc(R_vv)

    def edges_for(n):
        ok = (tr_own == -1) | (tr_own == n)
        vok = ((vo_own == -1) | (vo_own == n)) & ok.all(axis=0)
        ok = ok | own_ok[n]
        src, dst, w = [], [], []
        base = np.arange(W.N).reshape(L_, ny, nx)
        for (dy, dx, c) in moves:
            ys0, ys1 = max(0, -dy), ny - max(0, dy)
            xs0, xs1 = max(0, -dx), nx - max(0, dx)
            a = base[:, ys0:ys1, xs0:xs1]; b = base[:, ys0 + dy:ys1 + dy, xs0 + dx:xs1 + dx]
            m = ok[:, ys0:ys1, xs0:xs1] & ok[:, ys0 + dy:ys1 + dy, xs0 + dx:xs1 + dx]
            if c > 1:   # a diagonal must not cut a corner through an obstacle
                m &= ok[:, ys0:ys1, xs0 + dx:xs1 + dx] & ok[:, ys0 + dy:ys1 + dy, xs0:xs1]
            for (p, q) in ((a[m], b[m]), (b[m], a[m])):
                src.append(p); dst.append(q); w.append(np.full(p.size, c))
        for l1 in range(L_):
            for l2 in range(L_):
                if l1 == l2: continue
                p = base[l1][vok]; q = base[l2][vok]
                src.append(p); dst.append(q); w.append(np.full(p.size, -1.0))  # via marker
        return np.concatenate(src), np.concatenate(dst), np.concatenate(w), vok

    EDG = {n: edges_for(n) for n in conns}
    hist = np.zeros((L_, ny, nx))
    vhist = np.zeros((ny, nx))
    pf = 0.5
    result = None
    for it_ in range(iters):
        claims_t = {}; claims_v = {}; paths = {}
        for n in sorted(conns, key=lambda k: -sum(m.sum() for u in conns[k] for m in u)):
            others_t = sum((claims_t[m] for m in claims_t if m != n), np.zeros((L_, ny, nx)))
            others_v = sum((claims_v[m] for m in claims_v if m != n), np.zeros((ny, nx)))
            cost = (1 + hist) * (1 + pf * others_t)
            vcost = (1 + vhist) * (1 + pf * (others_v + others_t.max(axis=0)))
            src, dst, w, vok = EDG[n]
            cflat = cost.reshape(-1); vflat = np.tile(vcost.reshape(-1), L_)
            wt = np.where(w > 0, w * cflat[dst], VIA_STEPS * vflat[dst])
            G = csr_matrix((wt, (src, dst)), shape=(W.N, W.N))
            segs_n = []; vias_n = []
            ok_route = True
            for masks in conns[n]:
                tree = masks[0].copy()
                left = list(range(1, len(masks)))
                while left:
                    srcs = np.flatnonzero(tree.reshape(-1))
                    dist, pred, _ = dijkstra(G, directed=True, indices=srcs, min_only=True,
                                             return_predecessors=True)
                    best = None
                    for k in left:
                        tg = np.flatnonzero(masks[k].reshape(-1))
                        if tg.size == 0: continue
                        j = tg[np.argmin(dist[tg])]
                        if np.isfinite(dist[j]) and (best is None or dist[j] < best[0]):
                            best = (dist[j], k, j)
                    if best is None:
                        if verbose: print(f"      net {n}: no path to its remaining clusters (iter {it_})")
                        ok_route = False; break
                    _, k, j = best
                    node = j; chain = [node]
                    while pred[node] >= 0: node = pred[node]; chain.append(node)
                    chain.reverse()
                    for a, b in zip(chain, chain[1:]):
                        la, xa, ya = W.pos(a); lb, xb, yb = W.pos(b)
                        if la != lb: vias_n.append((xa, ya))
                        else: segs_n.append((la, (xa, ya), (xb, yb)))
                        tree.reshape(-1)[b] = True
                    for end in (chain[0], chain[-1]):
                        Ept = stubs.get((n, end))
                        if Ept is not None:
                            le, xe, ye = W.pos(end)
                            if abs(xe - Ept[0]) > 1e-6 or abs(ye - Ept[1]) > 1e-6:
                                segs_n.append((le, (xe, ye), Ept))
                    tree |= masks[k]
                    left.remove(k)
                if not ok_route: break
            if not ok_route:
                return None
            # claims
            ct = np.zeros((L_, ny, nx), bool)
            for (l, p, q) in segs_n:
                for (x, y) in (p, q):
                    ct[l, int(round((y - W.y0) / GRID)), int(round((x - W.x0) / GRID))] = True
            cv = np.zeros((ny, nx), bool)
            for (x, y) in vias_n:
                cv[int(round((y - W.y0) / GRID)), int(round((x - W.x0) / GRID))] = True
            claims_t[n] = np.stack([binary_dilation(ct[l], D_tt) | binary_dilation(cv, D_vt)
                                    for l in range(L_)]).astype(float)
            claims_v[n] = binary_dilation(cv, D_vv).astype(float)
            paths[n] = (segs_n, vias_n, ct, cv)
        # overuse: a net's centreline inside another net's claim
        over_t = np.zeros((L_, ny, nx), bool); over_v = np.zeros((ny, nx), bool)
        for n, (segs_n, vias_n, ct, cv) in paths.items():
            ot = sum((claims_t[m] for m in claims_t if m != n), np.zeros((L_, ny, nx)))
            ov = sum((claims_v[m] for m in claims_v if m != n), np.zeros((ny, nx)))
            over_t |= ct & (ot > 0)
            over_v |= cv & ((ov > 0) | (ot.max(axis=0) > 0))
        nover = int(over_t.sum() + over_v.sum())
        if verbose: print(f"      iter {it_}: {nover} overused cells")
        if nover == 0:
            result = paths; break
        hist += over_t; vhist += over_v
        pf *= 1.5
    if result is None: return None
    add_s, add_v = [], []
    for n, (segs_n, vias_n, _, _) in result.items():
        for (l, p, q) in segs_n: add_s.append(dict(net=n, layer=cu[l], p=p, q=q))
        for (x, y) in set(vias_n): add_v.append(dict(net=n, p=(x, y)))
    # dead copper of the routed nets (pad-less clusters) inside the window is
    # already gone with the rip-up; outside it stays.
    return add_s, add_v, rip


def apply(pcb, cu, add_s, add_v, rip):
    import copy
    out = copy.deepcopy(pcb)
    ripkeys = set()
    for c in rip:
        if c[0] == 'segment':
            a, b = c.find('start'), c.find('end')
            ripkeys.add(('s', a[1], a[2], b[1], b[2], c.val('layer')))
        else:
            a = c.find('at'); ripkeys.add(('v', a[1], a[2]))
    keep = []
    for c in out:
        if isinstance(c, list) and c and c[0] == 'segment':
            a, b = c.find('start'), c.find('end')
            if ('s', a[1], a[2], b[1], b[2], c.val('layer')) in ripkeys: continue
        if isinstance(c, list) and c and c[0] == 'via':
            a = c.find('at')
            if ('v', a[1], a[2]) in ripkeys: continue
        keep.append(c)
    out[:] = keep
    # not merged into straight runs: another path may join any vertex, and a
    # join is only recognised at a shared endpoint
    segs = add_s
    uid = 880000
    for s in segs:
        out.append(F.n('segment', F.n('start', round(s['p'][0], 4), round(s['p'][1], 4)),
                       F.n('end', round(s['q'][0], 4), round(s['q'][1], 4)),
                       F.n('width', TRACK), F.n('layer', Q(s['layer'])),
                       F.n('net', s['net']), F.n('uuid', Q(F.uuid_for(uid))))); uid += 1
    for v in add_v:
        out.append(F.n('via', F.n('at', round(v['p'][0], 4), round(v['p'][1], 4)),
                       F.n('size', VIA), F.n('drill', DRILL),
                       F.n('layers', Q(cu[0]), Q(cu[-1])),
                       F.n('net', v['net']), F.n('uuid', Q(F.uuid_for(uid))))); uid += 1
    return out


def missing(pcb):
    nets, pads, segs, vias = ratsnest.items_of(pcb)
    cl = ratsnest.clusters(nets=nets, pads=pads, segs=segs, vias=vias)
    return sum(len(g) - 1 for g in cl.values())


def run(path, outp, margins=(1.5, 2.5, 3.5, 5.0), verbose=True):
    import io, contextlib, ripup
    pcb = load(path)
    cu = [str(l[1]) for l in pcb.find('layers')[1:] if len(l) > 2 and l[2] == 'signal']
    xs, ys = [], []
    for g in pcb.find_all('gr_line'):
        if g.val('layer') != 'Edge.Cuts': continue
        for k in ('start', 'end'): q = g.find(k); xs.append(q[1]); ys.append(q[2])
    outline = (min(xs), min(ys), max(xs), max(ys))
    m0 = missing(pcb)
    if verbose: print(f"  {os.path.basename(path)}: {m0} connection(s) missing")
    tried = set()
    while True:
        gaps = ripup.gaps(pcb)
        progress = False
        for (net, _, a, b) in gaps:
            key = (net, round(a[0], 2), round(a[1], 2), round(b[0], 2), round(b[1], 2))
            if key in tried: continue
            tried.add(key)
            nnum = next(int(x[1]) for x in pcb.find_all('net') if str(x[2]) == net)
            for m in margins:
                box = (max(outline[0], min(a[0], b[0]) - m), max(outline[1], min(a[1], b[1]) - m),
                       min(outline[2], max(a[0], b[0]) + m), min(outline[3], max(a[1], b[1]) + m))
                t0 = time.time()
                res = solve_window(pcb, cu, box, outline, {nnum: (a, b)})
                if res is None:
                    if verbose: print(f"    {net}: window +{m}mm: no legal routing ({time.time()-t0:.0f}s)")
                    continue
                cand = apply(pcb, cu, *res)
                tmp = outp + '.tmp'
                open(tmp, 'w').write(dumps(cand) + '\n')
                with contextlib.redirect_stdout(io.StringIO()):
                    nv, _ = drc.check(tmp, CLR, 0)
                m1 = missing(cand)
                nvia0 = len(pcb.find_all('via')); nvia1 = len(cand.find_all('via'))
                if verbose:
                    print(f"    {net}: window +{m}mm: missing {m0} -> {m1}, DRC {nv}, "
                          f"vias {nvia0} -> {nvia1} ({time.time()-t0:.0f}s)")
                if nv == 0 and m1 < m0:
                    pcb, m0 = cand, m1
                    open(outp, 'w').write(dumps(pcb) + '\n')
                    progress = True
                    break
            if progress: break
        if not progress or m0 == 0: break
    open(outp, 'w').write(dumps(pcb) + '\n')
    if os.path.exists(outp + '.tmp'): os.remove(outp + '.tmp')
    if verbose: print(f"  -> {m0} missing, {len(pcb.find_all('via'))} vias: {outp}")
    return m0


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('pcb'); ap.add_argument('-o', '--out', required=True)
    a = ap.parse_args()
    run(a.pcb, a.out)
