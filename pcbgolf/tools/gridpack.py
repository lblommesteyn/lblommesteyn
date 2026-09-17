"""Grid-occupancy bottom-left packer.

Connectors are placed on the perimeter first and become obstacles; every other
part is then dropped into the lowest-leftmost free cell using an integral-image
free-region test, so the result is always overlap-free on both board sides.
"""
import sys, os, json, math, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np

DEBUG = False
GRID = 0.25      # mm per cell
CLR  = 0.18      # mm clearance added to every part

def cells(v):
    return max(1, int(math.ceil((v + CLR) / GRID)))

class Board:
    def __init__(self, W, H):
        self.W, self.H = W, H
        self.nx, self.ny = int(W/GRID), int(H/GRID)
        self.occ = [np.zeros((self.ny, self.nx), dtype=np.int32) for _ in range(2)]

    def blocked(self, side, cx, cy, w, h):
        x0 = max(0, cx); y0 = max(0, cy)
        x1 = min(self.nx, cx+w); y1 = min(self.ny, cy+h)
        if x1 <= x0 or y1 <= y0: return True
        return self.occ[side][y0:y1, x0:x1].any()

    def mark(self, side, cx, cy, w, h):
        x0 = max(0, cx); y0 = max(0, cy)
        x1 = min(self.nx, cx+w); y1 = min(self.ny, cy+h)
        self.occ[side][y0:y1, x0:x1] = 1

    def place_bl(self, side, w, h):
        """Lowest-then-leftmost free slot for a w x h cell block. None if it won't fit."""
        o = self.occ[side]
        if w > self.nx or h > self.ny: return None
        S = np.zeros((self.ny+1, self.nx+1), dtype=np.int32)
        S[1:, 1:] = o.cumsum(0).cumsum(1)
        H2, W2 = self.ny-h+1, self.nx-w+1
        if H2 <= 0 or W2 <= 0: return None
        tot = (S[h:h+H2, w:w+W2] - S[0:H2, w:w+W2] - S[h:h+H2, 0:W2] + S[0:H2, 0:W2])
        free = np.argwhere(tot == 0)
        if len(free) == 0: return None
        # lowest y, then lowest x
        idx = np.lexsort((free[:, 1], free[:, 0]))[0]
        return int(free[idx][1]), int(free[idx][0])

def perimeter_place(board, econ, items, slot, rot, edge_of=None):
    """Seat each connector with its mating face on a board edge.  Scans its
    assigned edge from the corner for the first free slot, then falls back to
    the other three edges, so corners never deadlock the placement."""
    W, H = board.W, board.H
    out = {}
    if edge_of is None:
        edge_of = {k: i % 4 for i, k in enumerate(econ)}
    for k in sorted(econ, key=lambda k: -max(items[k]['w'], items[k]['h'])):
        it = items[k]
        short, long_ = min(it['w'], it['h']), max(it['w'], it['h'])
        done = False
        for e in [edge_of[k]] + [x for x in range(4) if x != edge_of[k]]:
            if e in (0, 2): bw, bh = short, long_
            else:           bw, bh = long_, short
            span = W if e in (0, 2) else H
            step = bw if e in (0, 2) else bh
            t = 0.0
            while t + step <= span + 1e-9:
                if e == 0:   cx, cy = t + bw/2, bh/2
                elif e == 2: cx, cy = t + bw/2, H - bh/2
                elif e == 1: cx, cy = W - bw/2, t + bh/2
                else:        cx, cy = bw/2, t + bh/2
                gx = int(round((cx - bw/2)/GRID)); gy = int(round((cy - bh/2)/GRID))
                if not board.blocked(0, gx, gy, cells(bw), cells(bh)):
                    board.mark(0, gx, gy, cells(bw), cells(bh))
                    out[k] = (cx, cy, 0, 0 if e in (0, 2) else 90)
                    done = True
                    break
                t += GRID
            if done: break
        if not done: return None
    return out

def pack(items, W, H, order, rot, side, slot, edge_of=None):
    b = Board(W, H)
    econ = [k for k, it in enumerate(items) if it['edge']]
    res = perimeter_place(b, econ, items, slot, rot, edge_of)
    if res is None: return None
    for k in order:
        it = items[k]
        w, h = it['w'], it['h']
        if rot.get(k, 0) % 2: w, h = h, w
        s = side[k]
        p = b.place_bl(s, cells(w), cells(h))
        if p is None:
            if DEBUG: print(f"      FAIL on {it['ref']} ({it['fp']}) {w:.2f}x{h:.2f} side {s}")
            return None
        gx, gy = p
        b.mark(s, gx, gy, cells(w), cells(h))
        if it['fp'] == 'M2_BOLT':
            b.mark(1-s, gx, gy, cells(w), cells(h))
        res[k] = (gx*GRID + w/2, gy*GRID + h/2, s, 90*(rot.get(k, 0) % 2))
    return res

def hpwl(pos, nets):
    t = 0.0
    for refs in nets:
        xs = [pos[k][0] for k in refs if k in pos]
        ys = [pos[k][1] for k in refs if k in pos]
        if len(xs) < 2: continue
        t += (max(xs)-min(xs)) + (max(ys)-min(ys))
    return t

def solve(items, nets, W, H, z, iters=1200, seed=0, lam=1.2, verbose=False):
    rng = random.Random(seed)
    core = [k for k, it in enumerate(items) if not it['edge']]
    econ = [k for k, it in enumerate(items) if it['edge']]
    order = sorted(core, key=lambda k: -max(items[k]['w'], items[k]['h']))
    rot = {k: 0 for k in range(len(items))}
    side = {k: items[k]['side'] for k in range(len(items))}
    slot = {k: i for i, k in enumerate(econ)}
    edge_of = {k: i % 4 for i, k in enumerate(econ)}
    def cost():
        p = pack(items, W, H, order, rot, side, slot, edge_of)
        if p is None: return 1e9, None
        return W*H*z + lam*hpwl(p, nets), p
    cur, pos = cost(); best = cur; bp = pos
    bstate = (list(order), dict(rot), dict(side), dict(slot), dict(edge_of))
    for i in range(iters):
        T = 900*(4.0/900)**(i/iters)
        m = rng.random()
        if m < 0.45 and len(order) > 2:
            a, b = rng.randrange(len(order)), rng.randrange(len(order))
            order[a], order[b] = order[b], order[a]; undo = ('o', a, b)
        elif m < 0.68:
            k = rng.choice(order); rot[k] ^= 1; undo = ('r', k, 0)
        elif m < 0.88:
            c = [k for k in order if not items[k]['top']]
            if not c: continue
            k = rng.choice(c); side[k] ^= 1; undo = ('s', k, 0)
        elif m < 0.94:
            if len(econ) < 2: continue
            a, b = rng.choice(econ), rng.choice(econ)
            slot[a], slot[b] = slot[b], slot[a]; undo = ('l', a, b)
        else:
            k = rng.choice(econ); old = edge_of[k]
            edge_of[k] = rng.randrange(4); undo = ('e', k, old)
        new, p = cost()
        if new < cur or rng.random() < math.exp(-(new-cur)/max(T, 1e-9)):
            cur, pos = new, p
            if cur < best:
                best, bp = cur, p
                bstate = (list(order), dict(rot), dict(side), dict(slot), dict(edge_of))
        else:
            t, a, b = undo
            if t == 'o': order[a], order[b] = order[b], order[a]
            elif t == 'r': rot[a] ^= 1
            elif t == 's': side[a] ^= 1
            elif t == 'l': slot[a], slot[b] = slot[b], slot[a]
            else: edge_of[a] = b
        if verbose and i % max(1, iters//6) == 0:
            print(f"    it {i:>5} T={T:7.1f} cost={cur:10.0f}")
    return best, bp, bstate
