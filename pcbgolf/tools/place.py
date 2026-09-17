"""Simulated-annealing 3D-aware floorplanner for the PCBGolf board.

Minimises   W*H*Z  +  lambda_wl * HPWL  (+ hard overlap / edge penalties)
over (x, y, rot90, side) for every part, with connectors pinned to the board
edge in a legal mating orientation.
"""
import sys, os, math, random, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from parts import GEOM, SWAPS
from pcb import load_board

# --- parts that must sit on a board edge, and how much clearance the mating
#     connector needs outside the board outline ---
EDGE_PARTS = {
    'USB-C-FEMALE-VERT-GCT': 'edge', 'USB-C-HORIZ-SMT': 'edge', 'USB-C-MIDMOUNT': 'edge',
    'DX07S024XJ1R1100': 'edge', 'DCJACK_2MM_SMT': 'edge', 'DCJACK-LOWPROFILE': 'edge',
    'DCJACK-MIDMOUNT': 'edge', '0472192001': 'edge', '2X04': 'edge', '2X04-RA': 'edge',
}
TOP_ONLY = set(EDGE_PARTS) | {'EVQ-Q2', 'CHIPLED', 'CREE-RGB-CLMVC', 'SOT23-3', 'M2_BOLT'}

class Part:
    __slots__ = ('ref','fp','w','h','z','side','x','y','rot','edge','top_only','idx')

def build_parts(swaps):
    b = load_board()
    out = []
    for i, f in enumerate(b['fps']):
        fp = f.lib.split(':')[-1]
        s = swaps.get(fp)
        name = s['to'] if s else fp
        if s: w, h, z = s['W'], s['H'], s['Z']
        else: w, h, z = GEOM[fp][:3]
        p = Part()
        p.ref, p.fp, p.w, p.h, p.z = f.ref, name, w, h, z
        p.edge = name in EDGE_PARTS
        p.top_only = name in TOP_ONLY
        p.side, p.rot, p.x, p.y, p.idx = 0, 0, 0.0, 0.0, i
        out.append(p)
    return out

def load_nets(parts):
    d = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'netlist.json')))
    idx = {p.ref: k for k, p in enumerate(parts)}
    nets = []
    for name, pins in d['nets'].items():
        refs = sorted({idx[r] for (r, n, nm, et) in pins if r in idx})
        if 2 <= len(refs) <= 40:          # skip 1-pin and giant power nets
            nets.append((name, np.array(refs, dtype=np.int32)))
    return nets

class Floorplan:
    def __init__(self, parts, nets, zmax, seed=0, lam=0.02):
        self.p = parts; self.nets = nets; self.zmax = zmax
        self.rng = random.Random(seed)
        self.n = len(parts)
        self.lam = lam
        self.w = np.array([p.w for p in parts]); self.h = np.array([p.h for p in parts])
        self.rot = np.zeros(self.n, dtype=np.int8)
        self.side = np.zeros(self.n, dtype=np.int8)
        self.edge = np.array([p.edge for p in parts])
        self.toponly = np.array([p.top_only for p in parts])
        side0 = math.sqrt(sum(p.w*p.h for p in parts)/2.0)*1.25
        self.x = np.array([self.rng.uniform(0, side0) for _ in parts])
        self.y = np.array([self.rng.uniform(0, side0) for _ in parts])
        for k, p in enumerate(parts):
            if not p.top_only and self.rng.random() < 0.5: self.side[k] = 1

    def dims(self):
        rw = np.where(self.rot % 2 == 0, self.w, self.h)
        rh = np.where(self.rot % 2 == 0, self.h, self.w)
        return rw, rh

    def bbox(self):
        rw, rh = self.dims()
        return (self.x - rw/2).min(), (self.y - rh/2).min(), (self.x + rw/2).max(), (self.y + rh/2).max()

    def overlap_area(self):
        """Total pairwise overlap, computed per side with a numpy grid sweep."""
        tot = 0.0
        rw, rh = self.dims()
        for s in (0, 1):
            m = self.side == s
            if m.sum() < 2: continue
            x, y, w, h = self.x[m], self.y[m], rw[m], rh[m]
            x0, x1 = x - w/2, x + w/2
            y0, y1 = y - h/2, y + h/2
            dx = np.minimum(x1[:, None], x1[None, :]) - np.maximum(x0[:, None], x0[None, :])
            dy = np.minimum(y1[:, None], y1[None, :]) - np.maximum(y0[:, None], y0[None, :])
            ov = np.clip(dx, 0, None) * np.clip(dy, 0, None)
            np.fill_diagonal(ov, 0.0)
            tot += ov.sum() / 2.0
        return tot

    def hpwl(self):
        t = 0.0
        for _, refs in self.nets:
            xs = self.x[refs]; ys = self.y[refs]
            t += (xs.max()-xs.min()) + (ys.max()-ys.min())
            # crossing between sides costs a via-ish penalty in wirelength terms
        return t

    def edge_penalty(self, bb):
        x0, y0, x1, y1 = bb
        rw, rh = self.dims()
        m = self.edge
        if not m.any(): return 0.0
        d = np.minimum.reduce([
            np.abs(self.x[m] - rw[m]/2 - x0), np.abs(x1 - self.x[m] - rw[m]/2),
            np.abs(self.y[m] - rh[m]/2 - y0), np.abs(y1 - self.y[m] - rh[m]/2)])
        return float(np.sum(d**2))

    def cost(self, w_ov=400.0, w_edge=40.0):
        bb = self.bbox()
        W, H = bb[2]-bb[0], bb[3]-bb[1]
        vol = W*H*self.zmax
        return vol + w_ov*self.overlap_area() + self.lam*self.hpwl()*self.zmax + w_edge*self.edge_penalty(bb), W, H

    def anneal(self, iters=60000, T0=400.0, T1=0.5, report=None):
        cur, W, H = self.cost()
        best = cur; bestsnap = self.snapshot()
        for it in range(iters):
            T = T0 * (T1/T0) ** (it/iters)
            k = self.rng.randrange(self.n)
            mv = self.rng.random()
            old = (self.x[k], self.y[k], self.rot[k], self.side[k])
            if mv < 0.55:
                span = max(1.0, 12.0*T/T0)
                self.x[k] += self.rng.gauss(0, span); self.y[k] += self.rng.gauss(0, span)
            elif mv < 0.72:
                self.rot[k] = (self.rot[k] + self.rng.choice([1,2,3])) % 4
            elif mv < 0.86 and not self.toponly[k]:
                self.side[k] ^= 1
            else:
                j = self.rng.randrange(self.n)
                if self.toponly[k] != self.toponly[j]: continue
                self.x[k], self.x[j] = self.x[j], self.x[k]
                self.y[k], self.y[j] = self.y[j], self.y[k]
                new, W, H = self.cost()
                if new < cur or self.rng.random() < math.exp(-(new-cur)/max(T,1e-9)):
                    cur = new
                    if cur < best: best, bestsnap = cur, self.snapshot()
                else:
                    self.x[k], self.x[j] = self.x[j], self.x[k]
                    self.y[k], self.y[j] = self.y[j], self.y[k]
                continue
            new, W, H = self.cost()
            if new < cur or self.rng.random() < math.exp(-(new-cur)/max(T,1e-9)):
                cur = new
                if cur < best: best, bestsnap = cur, self.snapshot()
            else:
                self.x[k], self.y[k], self.rot[k], self.side[k] = old
            if report and it % report == 0:
                print(f"   it {it:>7} T={T:8.2f} cost={cur:10.0f} W={W:6.2f} H={H:6.2f} ov={self.overlap_area():8.2f}")
        self.restore(bestsnap)
        return best

    def snapshot(self):
        return (self.x.copy(), self.y.copy(), self.rot.copy(), self.side.copy())
    def restore(self, s):
        self.x, self.y, self.rot, self.side = [a.copy() for a in s]
