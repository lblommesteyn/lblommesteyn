"""Legal-by-construction placer.

Connectors are assigned to perimeter slots; every other part is packed with
bottom-left-fill inside the core.  Simulated annealing over (order, rotation,
side, connector slot) minimises  W*H*Z + lambda*HPWL.  Output is always
overlap-free, so it can be handed straight to a router.
"""
import sys, os, json, math, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parts import GEOM, SWAPS
from pcb import load_board
from place import EDGE_PARTS, TOP_ONLY

CLR = 0.18

def bl_pack(rects, strip_w):
    """rects: [(w,h)] -> [(x,y,w,h)], used height. Bottom-left-fill on a skyline."""
    placed = []
    sky = [(0.0, strip_w, 0.0)]
    for (w, h) in rects:
        best = None
        cands = sorted({s[0] for s in sky} | {s[1]-w for s in sky if s[1]-w >= 0})
        for x in cands:
            if x < -1e-9 or x + w > strip_w + 1e-9: continue
            y = 0.0
            for (ox0, ox1, oy) in sky:
                if ox1 > x + 1e-9 and ox0 < x + w - 1e-9: y = max(y, oy)
            if best is None or (y, x) < best: best = (y, x)
        if best is None:
            y, x = max(s[2] for s in sky), 0.0
        else: y, x = best
        placed.append((x, y, w, h))
        new = []
        for (ox0, ox1, oy) in sky:
            if ox1 <= x + 1e-9 or ox0 >= x + w - 1e-9: new.append((ox0, ox1, oy)); continue
            if ox0 < x: new.append((ox0, x, oy))
            if ox1 > x + w: new.append((x + w, ox1, oy))
        new.append((x, x + w, y + h)); new.sort()
        merged = []
        for seg in new:
            if merged and abs(merged[-1][2]-seg[2]) < 1e-9 and abs(merged[-1][1]-seg[0]) < 1e-9:
                merged[-1] = (merged[-1][0], seg[1], seg[2])
            else: merged.append(seg)
        sky = merged
    return placed, max((p[1]+p[3] for p in placed), default=0.0)

class Packer:
    def __init__(self, items, nets, strip_w, z, seed=0, lam=1.2):
        self.items = items; self.nets = nets; self.W = strip_w; self.z = z
        self.rng = random.Random(seed); self.lam = lam
        self.core = [k for k, it in enumerate(items) if not it['edge']]
        self.econ = [k for k, it in enumerate(items) if it['edge']]
        self.order = self.core[:]; self.rng.shuffle(self.order)
        self.order.sort(key=lambda k: -max(items[k]['w'], items[k]['h']))
        self.rot = {k: 0 for k in range(len(items))}
        self.side = {k: items[k]['side'] for k in range(len(items))}
        self.slot = {k: i for i, k in enumerate(self.econ)}
        self.pos = {}

    def layout(self):
        """Pack both sides; connectors ring the perimeter clockwise from (0,0)."""
        H = 0.0; res = {}
        for s in (0, 1):
            rects, keys = [], []
            for k in self.order:
                if self.side[k] != s: continue
                it = self.items[k]; w, h = it['w']+CLR, it['h']+CLR
                if self.rot[k] % 2: w, h = h, w
                rects.append((w, h)); keys.append(k)
            pl, hh = bl_pack(rects, self.W)
            H = max(H, hh)
            for k, (x, y, w, h) in zip(keys, pl): res[k] = (x+w/2, y+h/2, s)
        # connectors: walk the perimeter, ordered by slot
        per = 2*(self.W + H)
        econ = sorted(self.econ, key=lambda k: self.slot[k])
        need = sum(min(self.items[k]['w'], self.items[k]['h'])+1.2 for k in econ)
        t = 0.0
        for k in econ:
            it = self.items[k]
            L = min(it['w'], it['h'])+1.2
            c = (t + L/2) % max(per, 1e-9)
            if c < self.W: p = (c, 0.0)
            elif c < self.W+H: p = (self.W, c-self.W)
            elif c < 2*self.W+H: p = (2*self.W+H-c, H)
            else: p = (0.0, per-c)
            res[k] = (p[0], p[1], 0)
            t += L
        self.pos = res
        return self.W, H, need <= per

    def hpwl(self):
        t = 0.0
        for refs in self.nets:
            xs = [self.pos[k][0] for k in refs if k in self.pos]
            ys = [self.pos[k][1] for k in refs if k in self.pos]
            if len(xs) < 2: continue
            t += (max(xs)-min(xs)) + (max(ys)-min(ys))
        return t

    def cost(self):
        W, H, ok = self.layout()
        c = W*H*self.z + self.lam*self.hpwl()
        if not ok: c += 50000
        return c, W, H

    def anneal(self, iters=4000, T0=2500.0, T1=5.0, report=None):
        cur, W, H = self.cost(); best = cur; snap = self.snap()
        for i in range(iters):
            T = T0*(T1/T0)**(i/iters)
            m = self.rng.random()
            if m < 0.45 and len(self.order) > 2:
                a, b = self.rng.randrange(len(self.order)), self.rng.randrange(len(self.order))
                self.order[a], self.order[b] = self.order[b], self.order[a]
                undo = ('ord', a, b)
            elif m < 0.65:
                k = self.rng.choice(self.order); self.rot[k] ^= 1; undo = ('rot', k, 0)
            elif m < 0.85:
                cands = [k for k in self.order if not self.items[k]['top']]
                if not cands: continue
                k = self.rng.choice(cands); self.side[k] ^= 1; undo = ('side', k, 0)
            else:
                if len(self.econ) < 2: continue
                a, b = self.rng.choice(self.econ), self.rng.choice(self.econ)
                self.slot[a], self.slot[b] = self.slot[b], self.slot[a]
                undo = ('slot', a, b)
            new, W, H = self.cost()
            if new < cur or self.rng.random() < math.exp(-(new-cur)/max(T, 1e-9)):
                cur = new
                if cur < best: best, snap = cur, self.snap()
            else:
                t, a, b = undo
                if t == 'ord': self.order[a], self.order[b] = self.order[b], self.order[a]
                elif t == 'rot': self.rot[a] ^= 1
                elif t == 'side': self.side[a] ^= 1
                else: self.slot[a], self.slot[b] = self.slot[b], self.slot[a]
            if report and i % report == 0:
                print(f"   it {i:>6} T={T:8.1f} cost={cur:10.0f} {W:6.2f}x{H:6.2f} hpwl={self.hpwl():7.0f}")
        self.restore(snap); self.cost()
        return best

    def snap(self):
        return (list(self.order), dict(self.rot), dict(self.side), dict(self.slot))
    def restore(self, s):
        self.order, self.rot, self.side, self.slot = list(s[0]), dict(s[1]), dict(s[2]), dict(s[3])
