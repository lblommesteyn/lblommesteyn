"""Close the last unrouted connections on a board with an A* maze router.

Freerouting converges with a handful of connections short. Rather than restart
it (which re-spends vias everywhere), this routes only what is missing, on a
grid, with every other net's copper as an obstacle.
"""
import sys, os, math, heapq, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from sexpr import load, dumps, Node, Q
from collide import rot
import ratsnest

GRID = 0.127
TRACK = 0.1          # defaults; the CLI overrides these to match the board
CLEAR = 0.1
VIA_DIA = 0.6

def n(tag, *vals):
    x = Node(); x.append(tag); x.extend(vals); return x

def uuid_for(i):
    h = f"{i:032x}"
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"

class Grid:
    def __init__(self, x0, y0, x1, y1, layers):
        self.x0, self.y0 = x0, y0
        self.nx = int((x1-x0)/GRID)+1
        self.ny = int((y1-y0)/GRID)+1
        self.layers = layers
        self.occ = np.zeros((len(layers), self.ny, self.nx), dtype=bool)
        # A via is several times wider than a trace and spans every layer, so a
        # cell that is free for a trace is often not free for a via. Marking
        # one grid for both is what put 0.6mm vias on top of other nets'
        # copper, overlapping by up to 0.33mm. vocc is layer-independent and
        # carries the via-sized halo.
        self.vocc = np.zeros((self.ny, self.nx), dtype=bool)
    def cell(self, x, y):
        return int(round((x-self.x0)/GRID)), int(round((y-self.y0)/GRID))
    def pos(self, cx, cy):
        return self.x0 + cx*GRID, self.y0 + cy*GRID
    def _span(self, x0, y0, x1, y1):
        """Cell range fully covering a rect.

        cell() rounds, which is right for locating a point but wrong for
        marking an obstacle: rounding can leave the boundary cell unmarked
        although its centre is inside the forbidden region, by up to half a
        cell -- 0.064mm here, more than the clearance budget. Marking has to
        round outwards.
        """
        a = int(math.floor((x0-self.x0)/GRID)); c = int(math.ceil((x1-self.x0)/GRID))
        b = int(math.floor((y0-self.y0)/GRID)); d = int(math.ceil((y1-self.y0)/GRID))
        return (max(a,0), max(b,0), min(c, self.nx-1), min(d, self.ny-1))

    def mark_rect(self, li, x0, y0, x1, y1, pad, via_pad=None):
        a, b, c, d = self._span(x0-pad, y0-pad, x1+pad, y1+pad)
        if c >= a and d >= b:
            idx = range(len(self.layers)) if li is None else [li]
            for i in idx: self.occ[i, b:d+1, a:c+1] = True
        if via_pad is None: return
        a, b, c, d = self._span(x0-via_pad, y0-via_pad, x1+via_pad, y1+via_pad)
        if c >= a and d >= b: self.vocc[b:d+1, a:c+1] = True
    def clear_rect(self, li, x0, y0, x1, y1):
        """Free the cells a rect covers, rounding INWARDS.

        The mirror of _span: freeing a cell that is only partly inside the pad
        would hand the router somewhere it is not actually allowed to be.
        """
        a = int(math.ceil((x0-self.x0)/GRID)); c = int(math.floor((x1-self.x0)/GRID))
        b = int(math.ceil((y0-self.y0)/GRID)); d = int(math.floor((y1-self.y0)/GRID))
        a = max(a,0); b = max(b,0); c = min(c, self.nx-1); d = min(d, self.ny-1)
        if c < a or d < b: return
        idx = range(len(self.layers)) if li is None else [li]
        for i in idx: self.occ[i, b:d+1, a:c+1] = False
    def mark_seg(self, li, p, q, w, pad, via_pad=None):
        steps = max(2, int(math.hypot(q[0]-p[0], q[1]-p[1])/GRID)+1)
        for t in range(steps+1):
            x = p[0] + (q[0]-p[0])*t/steps
            y = p[1] + (q[1]-p[1])*t/steps
            self.mark_rect(li, x-w/2, y-w/2, x+w/2, y+w/2, pad, via_pad)

def build(path, net_filter=None):
    pcb = load(path)
    xs, ys = [], []
    for g in pcb.find_all('gr_line'):
        if g.val('layer') != 'Edge.Cuts': continue
        for k in ('start','end'):
            q = g.find(k); xs.append(q[1]); ys.append(q[2])
    return pcb, (min(xs), min(ys), max(xs), max(ys))

def route_board(path, out, max_conn=200, verbose=True, via_cost=1200,
                track=TRACK, clear=CLEAR, via_dia=VIA_DIA):
    pcb, (bx0, by0, bx1, by1) = build(path)
    layers = [str(l[1]) for l in pcb.find('layers')[1:] if len(l)>2 and l[2]=='signal']
    nets, pads, segs, vias = ratsnest.items_of(pcb)
    total, missing = ratsnest.analyse(path, verbose=0)
    if total == 0:
        print("  already fully connected"); return 0
    name2num = {v: k for k, v in nets.items()}
    li = {l: i for i, l in enumerate(layers)}
    pad_clear = clear + track/2
    via_clear = clear + via_dia/2

    added_segs, added_vias = [], []
    uid = 900000
    fixed = 0
    for netname, need, _ in missing:
        nnum = name2num.get(netname)
        if nnum is None: continue
        for _ in range(need):
            g = Grid(bx0, by0, bx1, by1, layers)
            # obstacles: every other net's copper
            for p in pads:
                if p['net'] == nnum: continue
                l = None if p['layer'] is None else li.get(p['layer'])
                g.mark_rect(l, *p['rect'], pad_clear, via_clear)
            for s in segs:
                if s['net'] == nnum: continue
                g.mark_seg(li.get(s['layer']), s['p'], s['q'], s['width'],
                           pad_clear, via_clear)
            for v in vias:
                if v['net'] == nnum: continue
                r = v['size']/2
                g.mark_rect(None, v['p'][0]-r, v['p'][1]-r,
                            v['p'][0]+r, v['p'][1]+r, pad_clear, via_clear)
            for s in added_segs:
                if s['net'] == nnum: continue
                g.mark_seg(li.get(s['layer']), s['p'], s['q'], track,
                           pad_clear, via_clear)
            for v in added_vias:
                if v['net'] == nnum: continue
                r = v['size']/2
                g.mark_rect(None, v['p'][0]-r, v['p'][1]-r,
                            v['p'][0]+r, v['p'][1]+r, pad_clear, via_clear)
            # A neighbouring net's clearance halo can cover this net's own pad
            # -- on a 0.25mm-pitch USB-C land pattern it always does -- and a
            # maze router that treats its own destination as an obstacle can
            # never reach it.  Standing on your own pad is legal, so free those
            # cells back up in the TRACE grid.  vocc is deliberately left
            # alone: being allowed to stand somewhere does not make it a legal
            # place to drop a via.
            for p in pads:
                if p['net'] != nnum: continue
                l = None if p['layer'] is None else li.get(p['layer'])
                g.clear_rect(l, *p['rect'])
            cl = ratsnest.clusters(nets=nets, pads=pads,
                                   segs=segs + added_segs, vias=vias + added_vias)
            before = (len(added_segs), len(added_vias))
            ok = connect_one(g, li, layers, nnum, netname, pads, segs, vias,
                             added_segs, added_vias, uid, cl, via_cost,
                             via_dia)
            # A degenerate one-cell path emits nothing while still returning
            # True, which used to be reported as a closed connection against a
            # byte-identical file.  No copper, no claim.
            if ok and (len(added_segs), len(added_vias)) == before:
                ok = False
            if not ok: break
            uid += 1000
            fixed += 1
            if verbose: print(f"    routed {netname}")

    # write
    for s in added_segs:
        pcb.append(n('segment', n('start', round(s['p'][0],4), round(s['p'][1],4)),
                     n('end', round(s['q'][0],4), round(s['q'][1],4)),
                     n('width', track), n('layer', Q(s['layer'])), n('net', s['net']),
                     n('uuid', Q(uuid_for(uid))))); uid += 1
    for v in added_vias:
        pcb.append(n('via', n('at', round(v['p'][0],4), round(v['p'][1],4)),
                     n('size', via_dia), n('drill', round(via_dia/2.25, 3)),
                     n('layers', Q(layers[0]), Q(layers[-1])), n('net', v['net']),
                     n('uuid', Q(uuid_for(uid))))); uid += 1
    open(out,'w').write(dumps(pcb)+'\n')
    return fixed

def connect_one(g, li, layers, nnum, netname, pads, segs, vias,
                added_segs, added_vias, uid, cl=None, via_cost=1200,
                via_dia=VIA_DIA):
    """A* between the two CLOSEST disjoint clusters of this net.

    Routing pad 0 to any other pad re-routes connections that already exist,
    which burns vias without closing anything - the clusters have to come from
    the connectivity analysis.
    """
    groups = (cl or {}).get(nnum)
    if not groups or len(groups) < 2: return False
    best = None
    for i in range(len(groups)):
        for j in range(i+1, len(groups)):
            for a in groups[i]:
                for b in groups[j]:
                    d = abs(a['x']-b['x']) + abs(a['y']-b['y'])
                    if best is None or d < best[0]: best = (d, i, j, a, b)
    _, gi, gj, src, _b = best
    tgt = groups[gj]
    starts = []
    for lname in layers:
        if src['layer'] in (None, lname):
            cx, cy = g.cell(src['x'], src['y']); starts.append((li[lname], cy, cx))
    # a through-hole pad already spans every layer, so starting on any of them
    # is free - no via needed at the pad itself
    goals = set()
    for p in tgt:
        for lname in layers:
            if p['layer'] in (None, lname):
                cx, cy = g.cell(p['x'], p['y']); goals.add((li[lname], cy, cx))
    if not starts or not goals: return False
    res = astar(g, starts, goals, via_cost)
    if res is None: return False
    path, nvia = res
    # Emit. A* steps one layer at a time, so a 0->3 hop is three moves at the
    # same (x,y) and must become ONE via, not three.
    prev = None
    via_at = set()
    for (l, cy, cx) in path:
        if prev is not None:
            if prev[0] != l:
                x, y = g.pos(cx, cy)
                key = (round(x, 3), round(y, 3))
                if key not in via_at:
                    via_at.add(key)
                    added_vias.append(dict(net=nnum, p=(x, y), size=via_dia))
            else:
                x0, y0 = g.pos(prev[2], prev[1]); x1, y1 = g.pos(cx, cy)
                added_segs.append(dict(net=nnum, layer=layers[l],
                                       p=(x0, y0), q=(x1, y1)))
        prev = (l, cy, cx)
    return True

def astar(g, starts, goals, via_cost=1200, max_nodes=1500000):
    """Trace length is free in the PCBGolf score and a via costs 50 points, so
    the router should take almost any detour rather than change layer.
    via_cost is in grid steps: 1200 steps at 0.127mm is ~150mm of trace."""
    nl, ny, nx = g.occ.shape
    goalset = set(goals)
    gy = np.array([q[1] for q in goals]); gx = np.array([q[2] for q in goals])
    def h(s):
        return (abs(gx - s[2]).min() + abs(gy - s[1]).min())
    openq = []
    best = {}
    for s in starts:
        if g.occ[s]: continue
        best[s] = 0
        heapq.heappush(openq, (h(s), 0, s, None))
    came = {}
    seen = 0
    while openq:
        f, cost, cur, par = heapq.heappop(openq)
        if cur in came: continue
        came[cur] = par
        seen += 1
        if seen > max_nodes: return None
        if cur in goalset:
            path = []
            c = cur
            while c is not None: path.append(c); c = came[c]
            return list(reversed(path)), 0
        l, y, x = cur
        for dl, dy, dx, w in ((0,1,0,1),(0,-1,0,1),(0,0,1,1),(0,0,-1,1),
                              (1,0,0,via_cost),(-1,0,0,via_cost)):
            nl2, ny2, nx2 = l+dl, y+dy, x+dx
            if not (0 <= nl2 < nl and 0 <= ny2 < ny and 0 <= nx2 < nx): continue
            nxt = (nl2, ny2, nx2)
            if nxt in came: continue
            if g.occ[nxt]: continue
            # Changing layer plants a via here, and a via needs far more room
            # than the trace that is allowed through this cell.
            if dl and g.vocc[y, x]: continue
            nc = cost + w
            if best.get(nxt, 1<<30) <= nc: continue
            best[nxt] = nc
            heapq.heappush(openq, (nc + h(nxt), nc, nxt, cur))
    return None

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('pcb'); ap.add_argument('-o','--out', required=True)
    ap.add_argument('--via-cost', type=int, default=1200)
    ap.add_argument('--track', type=float, default=TRACK,
                    help='trace width to add, matching the board')
    ap.add_argument('--clearance', type=float, default=CLEAR)
    ap.add_argument('--via-dia', type=float, default=VIA_DIA)
    a = ap.parse_args()
    fixed = route_board(a.pcb, a.out, via_cost=a.via_cost, track=a.track,
                        clear=a.clearance, via_dia=a.via_dia)
    print(f"  closed {fixed} connection(s) -> {a.out}")
