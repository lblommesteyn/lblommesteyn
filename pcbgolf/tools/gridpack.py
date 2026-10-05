"""Grid-occupancy bottom-left packer.

Connectors are placed on the perimeter first and become obstacles; every other
part is then dropped into the lowest-leftmost free cell using an integral-image
free-region test, so the result is always overlap-free on both board sides.
"""
import sys, os, json, math, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from geom2 import EDGE_SPEC

DEBUG = False
GRID = 0.25      # mm per cell
CLR  = 0.18      # mm clearance added to every part

def _thru_rect_cells(gx, gy, w, h, rotdeg, rects):
    """Yield (cx, cy, cw, ch) cell rectangles for a part's through-hole pads."""
    import math
    cx = gx*GRID + w/2; cy = gy*GRID + h/2
    a = math.radians(rotdeg); c, s = math.cos(a), math.sin(a)
    for (dx, dy, pw, ph) in rects:
        # (dx, dy) is a KiCad offset, Y down; this frame is Y up. Flip, then
        # turn CCW by rotdeg. Using KiCad's Y-down rotation here mirrored every
        # hole about the part centre, reserving the far side in the wrong place.
        rx, ry = dx*c + dy*s, dx*s - dy*c
        if rotdeg % 180: pw, ph = ph, pw
        px, py = cx + rx, cy + ry
        yield (int((px - pw/2 - CLR/2)/GRID), int((py - ph/2 - CLR/2)/GRID),
               cells(pw), cells(ph))


def _thru_free(board, side, gx, gy, w, h, rotdeg, rects):
    return not any(board.blocked(side, a, b, c, d)
                   for (a, b, c, d) in _thru_rect_cells(gx, gy, w, h, rotdeg, rects))


def _mark_thru(board, side, gx, gy, w, h, rotdeg, rects):
    """Mark only the through-hole pad rectangles on the far side."""
    for (a, b, c, d) in _thru_rect_cells(gx, gy, w, h, rotdeg, rects):
        board.mark(side, a, b, c, d)


def cells(v):
    return max(1, int(math.ceil((v + CLR) / GRID)))

class Board:
    def __init__(self, W, H):
        self.W, self.H = W, H
        self.nx, self.ny = int(W/GRID), int(H/GRID)
        self.occ = [np.zeros((self.ny, self.nx), dtype=np.int32) for _ in range(2)]

    def blocked(self, side, cx, cy, w, h, both=False):
        if both:
            return (self.blocked(0, cx, cy, w, h) or self.blocked(1, cx, cy, w, h))
        x0 = max(0, cx); y0 = max(0, cy)
        x1 = min(self.nx, cx+w); y1 = min(self.ny, cy+h)
        if x1 <= x0 or y1 <= y0: return True
        return self.occ[side][y0:y1, x0:x1].any()

    def mark(self, side, cx, cy, w, h):
        x0 = max(0, cx); y0 = max(0, cy)
        x1 = min(self.nx, cx+w); y1 = min(self.ny, cy+h)
        self.occ[side][y0:y1, x0:x1] = 1

    def place_near(self, side, w, h, tx, ty, both=False, validate=None, tries=400):
        """Free slot whose centre is closest to (tx, ty) in mm.  Packing toward a
        netlist-derived target keeps connected parts adjacent, which is what makes
        the board routable; bottom-left fill does not."""
        o = (self.occ[0] | self.occ[1]) if both else self.occ[side]
        if w > self.nx or h > self.ny: return None
        S = np.zeros((self.ny+1, self.nx+1), dtype=np.int32)
        S[1:, 1:] = o.cumsum(0).cumsum(1)
        H2, W2 = self.ny-h+1, self.nx-w+1
        if H2 <= 0 or W2 <= 0: return None
        tot = (S[h:h+H2, w:w+W2] - S[0:H2, w:w+W2] - S[h:h+H2, 0:W2] + S[0:H2, 0:W2])
        ys, xs = np.nonzero(tot == 0)
        if len(xs) == 0: return None
        cx = (xs + w/2) * GRID
        cy = (ys + h/2) * GRID
        d2 = (cx - tx)**2 + (cy - ty)**2
        for i in np.argsort(d2)[:tries]:
            gx, gy = int(xs[i]), int(ys[i])
            if validate is None or validate(gx, gy):
                return gx, gy
        return None

    def place_bl(self, side, w, h, both=False, validate=None):
        """Lowest-then-leftmost free slot for a w x h cell block. None if it won't fit.
        both=True requires the slot to be free on BOTH sides (used as a coarse
        pre-filter; exact through-hole masking is applied by the caller)."""
        o = (self.occ[0] | self.occ[1]) if both else self.occ[side]
        if w > self.nx or h > self.ny: return None
        S = np.zeros((self.ny+1, self.nx+1), dtype=np.int32)
        S[1:, 1:] = o.cumsum(0).cumsum(1)
        H2, W2 = self.ny-h+1, self.nx-w+1
        if H2 <= 0 or W2 <= 0: return None
        tot = (S[h:h+H2, w:w+W2] - S[0:H2, w:w+W2] - S[h:h+H2, 0:W2] + S[0:H2, 0:W2])
        free = np.argwhere(tot == 0)
        if len(free) == 0: return None
        order = np.lexsort((free[:, 1], free[:, 0]))      # lowest y, then lowest x
        for i in order:
            gy, gx = int(free[i][0]), int(free[i][1])
            if validate is None or validate(gx, gy):
                return gx, gy
        return None

# outward normal of each edge, degrees CCW from +x with Y up: edge 0 is y=0
# (bottom), 1 is x=W, 2 is y=H, 3 is x=0
OUTWARD = {0: 270, 1: 0, 2: 90, 3: 180}

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
        spec = EDGE_SPEC.get(it['fp'], {})
        face = spec.get('face')
        if face is None or 'body' not in spec:
            raise ValueError(f"{it['fp']}: edge connector with no measured opening "
                             f"direction (geom2.EDGE_SPEC 'face')")
        done = False
        for e in [edge_of[k]] + [x for x in range(4) if x != edge_of[k]]:
            # turn the part so its plug opening points out through edge e; the
            # block reserved is its envelope at that rotation
            rot_used = (OUTWARD[e] - face) % 360
            bw, bh = (it['w'], it['h']) if rot_used % 180 == 0 else (it['h'], it['w'])
            span = W if e in (0, 2) else H
            step = bw if e in (0, 2) else bh
            # one cell in from the corner: a connector flush against a SIDE
            # edge too has pads nearer than mkboard's copper-to-edge rule, and
            # the outline grew under the other connectors' openings
            t = GRID
            ux, uy = {0: (0, -1), 1: (1, 0), 2: (0, 1), 3: (-1, 0)}[e]
            # the block is reserved inside the board, but the part itself moves
            # out until its body face (not its envelope) is on the outline
            push = (bw/2 if e in (1, 3) else bh/2) - spec['body']
            while t + step <= span - GRID + 1e-9:
                if e == 0:   cx, cy = t + bw/2, bh/2
                elif e == 2: cx, cy = t + bw/2, H - bh/2
                elif e == 1: cx, cy = W - bw/2, t + bh/2
                else:        cx, cy = bw/2, t + bh/2
                gx = int(round((cx - bw/2)/GRID)); gy = int(round((cy - bh/2)/GRID))
                pcx, pcy = cx + ux*push, cy + uy*push
                # its holes go through at the pushed position, so that is where
                # the far side has to be free
                pgx, pgy = (pcx - bw/2)/GRID, (pcy - bh/2)/GRID
                thru = bool(it.get('thru'))
                tr = it.get('thru_rects') or []
                holes = sum(r[2]*r[3] for r in tr)
                coarse = thru and (not tr or holes > 0.45*bw*bh)
                farok = (coarse or not thru or
                         _thru_free(board, 1, pgx, pgy, bw, bh, rot_used, tr))
                if farok and not board.blocked(0, gx, gy, cells(bw), cells(bh), both=coarse):
                    board.mark(0, gx, gy, cells(bw), cells(bh))
                    if coarse:
                        board.mark(1, gx, gy, cells(bw), cells(bh))
                    elif thru:
                        _mark_thru(board, 1, pgx, pgy, bw, bh, rot_used, tr)
                    out[k] = (pcx, pcy, 0, rot_used)
                    done = True
                    break
                t += GRID
            if done: break
        if not done: return None
    return out

def pack(items, W, H, order, rot, side, slot, edge_of=None, targets=None):
    b = Board(W, H)
    econ = [k for k, it in enumerate(items) if it['edge']]
    res = perimeter_place(b, econ, items, slot, rot, edge_of)
    if res is None: return None
    # Everything else stays one cell off the outline. A part packed flush
    # against it has pads closer than mkboard's 0.3mm copper-to-edge rule, so
    # mkboard grew the outline -- which also left the edge connectors' openings
    # set back from the new edge.
    for s_ in (0, 1):
        b.occ[s_][0, :] = 1; b.occ[s_][-1, :] = 1
        b.occ[s_][:, 0] = 1; b.occ[s_][:, -1] = 1
    for k in order:
        it = items[k]
        w, h = it['w'], it['h']
        if rot.get(k, 0) % 2: w, h = h, w
        rdeg = 90*(rot.get(k, 0) % 2)       # rot holds quarter turns; holes want degrees
        thru = bool(it.get('thru'))
        tr = it.get('thru_rects') or []
        # a part whose through-holes span most of its body is simplest to treat as
        # fully double-sided; otherwise only its holes block the far side
        span = sum(r[2]*r[3] for r in tr)
        coarse = thru and (not tr or span > 0.45*it['w']*it['h'])
        # its assigned side first; a part not pinned to the top may take the
        # other side when its own is full (through-hole parts reserve room on
        # the far side that the side split did not budget for)
        p = None
        for s in [side[k]] + ([] if it.get('top') else [1 - side[k]]):
            far = None
            if thru and not coarse:
                # its holes pierce the board, so they must also be clear on the far side
                def far(gx, gy, _b=b, _w=w, _h=h, _r=rdeg, _tr=tr, _s=s):
                    return _thru_free(_b, 1-_s, gx, gy, _w, _h, _r, _tr)
            t = targets.get(k) if targets else None
            if t is not None:
                p = b.place_near(s, cells(w), cells(h), t[0], t[1], both=coarse,
                                 validate=far, tries=4000)
            if p is None:                      # always fall back to a legal slot
                p = b.place_bl(s, cells(w), cells(h), both=coarse, validate=far)
            if p is not None: break
        if p is None:
            if DEBUG: print(f"      FAIL on {it['ref']} ({it['fp']}) {w:.2f}x{h:.2f} side {side[k]}")
            return None
        gx, gy = p
        b.mark(s, gx, gy, cells(w), cells(h))
        if coarse:
            b.mark(1-s, gx, gy, cells(w), cells(h))
        elif thru:
            _mark_thru(b, 1-s, gx, gy, w, h, rdeg, tr)
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

def board_z(items, side, thickness=1.6):
    """Assembly height implied by a side assignment."""
    top = bot = 0.0
    for k, it in enumerate(items):
        if side.get(k, 0): bot = max(bot, it['z'])
        else:              top = max(top, it['z'])
    return top + thickness + bot


def solve(items, nets, W, H, z, iters=1200, seed=0, lam=1.2, verbose=False,
          dynamic_z=True, thickness=1.6, targets=None):
    rng = random.Random(seed)
    core = [k for k, it in enumerate(items) if not it['edge']]
    econ = [k for k, it in enumerate(items) if it['edge']]
    order = sorted(core, key=lambda k: -max(items[k]['w'], items[k]['h']))
    rot = {k: 0 for k in range(len(items))}
    side = {k: items[k]['side'] for k in range(len(items))}
    slot = {k: i for i, k in enumerate(econ)}
    edge_of = {k: i % 4 for i, k in enumerate(econ)}
    def cost():
        p = pack(items, W, H, order, rot, side, slot, edge_of, targets)
        if p is None: return 1e9, None
        zz = board_z(items, side, thickness) if dynamic_z else z
        return W*H*zz + lam*hpwl(p, nets), p
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
