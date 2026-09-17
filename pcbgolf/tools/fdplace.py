"""Force-directed, connectivity-aware placement with shrink-to-fit legalisation.

Springs pull net members together; a separation force resolves courtyard
overlaps; connectors are pinned to the nearest board edge.  The board box is
shrunk until overlaps can no longer be legalised, which gives the tightest
routable-ish outline for a given BOM.
"""
import sys, os, json, math, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from parts import GEOM, SWAPS
from pcb import load_board
from place import EDGE_PARTS
# Only connectors, the push button and the through-hole mounting bolts are
# genuinely side-constrained.  Status LEDs read fine from either face.
TOP_ONLY = set(EDGE_PARTS) | {'EVQ-Q2', 'M2_BOLT'}

class FD:
    def __init__(self, items, nets, W, H, seed=0, clr=0.15):
        self.n = len(items); self.items = items
        rng = np.random.default_rng(seed)
        self.w = np.array([it['w'] for it in items]) + clr
        self.h = np.array([it['h'] for it in items]) + clr
        self.edge = np.array([it['edge'] for it in items])
        self.side = np.array([it['side'] for it in items], dtype=np.int8)
        self.rot = np.zeros(self.n, dtype=np.int8)
        self.W, self.H = W, H
        self.x = rng.uniform(0, W, self.n); self.y = rng.uniform(0, H, self.n)
        self.nets = nets

    def dims(self):
        even = (self.rot % 2 == 0)
        return np.where(even, self.w, self.h), np.where(even, self.h, self.w)

    def overlap(self, pw=None, ph=None):
        if pw is None: pw, ph = self.dims()
        tot = 0.0; worst = 0.0
        for s in (0, 1):
            m = np.where(self.side == s)[0]
            if len(m) < 2: continue
            x, y, w, h = self.x[m], self.y[m], pw[m], ph[m]
            dx = (w[:,None]+w[None,:])/2 - np.abs(x[:,None]-x[None,:])
            dy = (h[:,None]+h[None,:])/2 - np.abs(y[:,None]-y[None,:])
            ov = np.clip(dx,0,None)*np.clip(dy,0,None)
            np.fill_diagonal(ov, 0.0)
            tot += ov.sum()/2; worst = max(worst, ov.max())
        return tot, worst

    def step(self, k_spring=0.12, k_sep=0.55, k_edge=0.5):
        pw, ph = self.dims()
        fx = np.zeros(self.n); fy = np.zeros(self.n)
        # springs: pull every net's members toward its centroid
        for refs in self.nets:
            if len(refs) < 2: continue
            cx = self.x[refs].mean(); cy = self.y[refs].mean()
            wgt = k_spring / math.sqrt(len(refs))
            fx[refs] += wgt*(cx - self.x[refs]); fy[refs] += wgt*(cy - self.y[refs])
        # separation per side
        for s in (0, 1):
            m = np.where(self.side == s)[0]
            if len(m) < 2: continue
            x, y, w, h = self.x[m], self.y[m], pw[m], ph[m]
            ddx = x[:,None]-x[None,:]; ddy = y[:,None]-y[None,:]
            ox = (w[:,None]+w[None,:])/2 - np.abs(ddx)
            oy = (h[:,None]+h[None,:])/2 - np.abs(ddy)
            hit = (ox > 0) & (oy > 0)
            np.fill_diagonal(hit, False)
            # push along the axis of least penetration
            px = np.where(ox <= oy, np.sign(ddx + 1e-12)*ox, 0.0) * hit
            py = np.where(oy <  ox, np.sign(ddy + 1e-12)*oy, 0.0) * hit
            fx[m] += k_sep*px.sum(axis=1); fy[m] += k_sep*py.sum(axis=1)
        # edge parts snap to nearest border
        e = np.where(self.edge)[0]
        if len(e):
            d = np.stack([self.x[e]-pw[e]/2, self.W-self.x[e]-pw[e]/2,
                          self.y[e]-ph[e]/2, self.H-self.y[e]-ph[e]/2])
            which = np.argmin(d, axis=0)
            for i, k in enumerate(e):
                if which[i] == 0: fx[k] += k_edge*(pw[k]/2 - self.x[k])
                elif which[i] == 1: fx[k] += k_edge*(self.W-pw[k]/2 - self.x[k])
                elif which[i] == 2: fy[k] += k_edge*(ph[k]/2 - self.y[k])
                else: fy[k] += k_edge*(self.H-ph[k]/2 - self.y[k])
        self.x += np.clip(fx, -1.5, 1.5); self.y += np.clip(fy, -1.5, 1.5)
        self.x = np.clip(self.x, pw/2, self.W-pw/2)
        self.y = np.clip(self.y, ph/2, self.H-ph/2)

    def run(self, iters=600):
        for i in range(iters):
            self.step(k_spring=0.12*(1-0.7*i/iters), k_sep=0.35+0.45*i/iters)
        return self.overlap()

    def hpwl(self):
        t = 0.0
        for refs in self.nets:
            if len(refs) < 2: continue
            t += np.ptp(self.x[refs]) + np.ptp(self.y[refs])
        return t

def make_items(swaps, seed=0):
    import geom2
    b = load_board()
    rng = random.Random(seed)
    items = []
    for f in b['fps']:
        fp = f.lib.split(':')[-1]
        s = swaps.get(fp)
        name = s['to'] if s else fp
        z = s['Z'] if s else GEOM[fp][2]
        w, h, ox, oy = geom2.box(name, None)
        needs_edge, ew, dp = geom2.edge_orientation(name, w, h)
        items.append(dict(ref=f.ref, fp=name, src=fp, w=w, h=h, z=z,
                          ox=ox, oy=oy, edge_w=ew, depth=dp,
                          edge=needs_edge,
                          top=needs_edge or name in ('EVQ-Q2','M2_BOLT'), side=0))
    # balance the two sides by area, connectors/LEDs/button stay on top
    free = [it for it in items if not it['top']]
    free.sort(key=lambda it: -it['w']*it['h'])
    a = [sum(it['w']*it['h'] for it in items if it['top']), 0.0]
    for it in free:
        s = 0 if a[0] <= a[1] else 1
        it['side'] = s; a[s] += it['w']*it['h']
    return items, a

def net_index(items):
    d = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'netlist.json')))
    idx = {it['ref']: k for k, it in enumerate(items)}
    out = []
    for name, pins in d['nets'].items():
        refs = sorted({idx[r] for (r, n, nm, et) in pins if r in idx})
        if 2 <= len(refs) <= 30: out.append(np.array(refs))
    return out

if __name__ == '__main__':
    def pick(mapping):
        subs = {}
        for fp, to in mapping.items():
            for s in SWAPS.get(fp, []):
                if s['to'] == to: subs[fp] = s
        return subs
    OPT = pick({'LQFP-144_20x20mm_P0.5mm':'LQFP-100_14x14',
                'SOIC-8_3.9x4.9mm_P1.27mm':'SOT23-5',
                '0402-R':'0201-R','0402-C':'0201-C','0805-C':'0603-C',
                'USB-C-FEMALE-VERT-GCT':'USB-C-MIDMOUNT','2X04':'2X04-RA',
                'DCJACK_2MM_SMT':'DCJACK-MIDMOUNT'})
    for label, swaps in (('STOCK BOM', {}), ('OPTIMISED BOM', OPT)):
        items, areas = make_items(swaps)
        nets = net_index(items)
        print(f"\n=== {label} === top-side area {areas[0]:.0f} mm2, bottom {areas[1]:.0f} mm2, "
              f"{len(nets)} nets")
        print(f"{'board':>14} {'overlap mm2':>12} {'worst':>8} {'hpwl':>9}  verdict")
        for scale in (1.55, 1.40, 1.30, 1.22, 1.16, 1.10):
            A = max(areas)*scale
            W = math.sqrt(A*1.1); H = A/W
            best = None
            for sd in range(3):
                fd = FD(items, nets, W, H, seed=sd)
                tot, worst = fd.run(700)
                if best is None or tot < best[0]: best = (tot, worst, fd)
            tot, worst, fd = best
            ok = 'LEGAL' if worst < 0.05 else ('tight' if worst < 0.5 else 'OVERLAP')
            print(f"{W:6.1f}x{H:<7.1f} {tot:>12.2f} {worst:>8.3f} {fd.hpwl():>9.0f}  {ok} (density {max(areas)/A:.0%})")
