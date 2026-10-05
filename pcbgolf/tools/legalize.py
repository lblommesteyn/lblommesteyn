"""Remove pad-to-pad collisions from a built .kicad_pcb.

Works directly on the board's own geometry - the same pad rectangles collide.py
measures - so placement and validation cannot disagree about what overlaps.
Offending parts are nudged to the nearest position where every one of their pads
clears every other part's pads (and, for through-hole pads, on both sides).
"""
import sys, os, math, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from sexpr import load, dumps, Node
from collide import pads_of, rot

RES = 0.1        # grid mm

def part_rects(pcb):
    """ref -> (own-side rects, through-hole rects, side)."""
    out = {}
    for p in pads_of(pcb):
        e = out.setdefault(p['ref'], dict(own=[], oside=[], thru=[], side=None, net=set()))
        r = (p['x']-p['w']/2, p['y']-p['h']/2, p['x']+p['w']/2, p['y']+p['h']/2)
        if p['side'] == '*': e['thru'].append(r)
        else:
            # each pad keeps its own side: a top connector's bottom shell pads
            # (J3.S2B) were compared as top-side and missed the part under them
            e['own'].append(r); e['oside'].append(p['side']); e['side'] = p['side']
        if p['net']: e['net'].add(p['net'])
    for e in out.values():
        if e['side'] is None: e['side'] = 'F'
    return out

class Occ:
    def __init__(self, x0, y0, x1, y1, clr):
        self.x0, self.y0 = x0 - 2, y0 - 2
        self.nx = int((x1 - x0 + 4)/RES) + 2
        self.ny = int((y1 - y0 + 4)/RES) + 2
        self.g = [np.zeros((self.ny, self.nx), dtype=bool) for _ in range(2)]
        self.clr = clr
    def _idx(self, r, dx=0.0, dy=0.0):
        c = self.clr/2
        a = int((r[0]+dx - c - self.x0)/RES); b = int((r[1]+dy - c - self.y0)/RES)
        d = int(math.ceil((r[2]+dx + c - self.x0)/RES)); e = int(math.ceil((r[3]+dy + c - self.y0)/RES))
        return max(a,0), max(b,0), min(d,self.nx), min(e,self.ny)
    def add(self, rects, sides):
        for r in rects:
            a,b,d,e = self._idx(r)
            for s in sides: self.g[s][b:e, a:d] = True
    def hits(self, rects, sides, dx=0.0, dy=0.0):
        for r in rects:
            a,b,d,e = self._idx(r, dx, dy)
            for s in sides:
                if self.g[s][b:e, a:d].any(): return True
        return False

def legalize(path, out, clearance=0.10, max_shift=6.0, rounds=6, verbose=True):
    pcb = load(path)
    xs, ys = [], []
    for g in pcb.find_all('gr_line'):
        if g.val('layer') != 'Edge.Cuts': continue
        for k in ('start','end'):
            q = g.find(k); xs.append(q[1]); ys.append(q[2])
    bx0, by0, bx1, by1 = min(xs), max(xs), min(ys), max(ys)
    bx1, by0 = max(xs), min(ys)

    fps = {}
    for f in pcb.find_all('footprint'):
        ref = next((str(p[2]) for p in f.find_all('property') if p[1]=='Reference'), None)
        if ref: fps[ref] = f

    moved = 0
    for rnd in range(rounds):
        info = part_rects(pcb)
        # who collides?
        occ_all = Occ(bx0, by0, bx1, by1, clearance)
        bad = set()
        refs = list(info)
        for i, a in enumerate(refs):
            A = info[a]
            for b in refs[i+1:]:
                B = info[b]
                if A['net'] and B['net'] and A['net'] == B['net'] and len(A['net']) == 1:
                    pass
                shared = A['net'] & B['net']
                for ra, sa in list(zip(A['own'], A['oside'])) + [(r, 'x') for r in A['thru']]:
                    for rb, sb in list(zip(B['own'], B['oside'])) + [(r, 'x') for r in B['thru']]:
                        if sa != sb and 'x' not in (sa, sb): continue
                        dx = min(ra[2],rb[2]) - max(ra[0],rb[0])
                        dy = min(ra[3],rb[3]) - max(ra[1],rb[1])
                        # closer than the clearance counts, not just
                        # overlapping: a 0.079mm pad gap passed here and failed
                        # the 0.09mm copper rule after routing
                        if dx > -clearance and dy > -clearance:
                            # same-net touching pads are fine
                            if shared and len(A['net']) == 1 and len(B['net']) == 1: continue
                            bad.add((a, b))
        if not bad:
            if verbose: print(f"  round {rnd}: already legal")
            break
        # move the part with fewer pads in each colliding pair
        todo = []
        for a, b in bad:
            pick = a if len(info[a]['own'])+len(info[a]['thru']) <= len(info[b]['own'])+len(info[b]['thru']) else b
            todo.append(pick)
        todo = list(dict.fromkeys(todo))
        if verbose: print(f"  round {rnd}: {len(bad)} colliding pairs, relocating {len(todo)} part(s)")
        fixed = 0
        for ref in todo:
            me = info[ref]
            occ = Occ(bx0, by0, bx1, by1, clearance)
            for other, o in info.items():
                if other == ref: continue
                for r, sd in zip(o['own'], o['oside']):
                    occ.add([r], [0 if sd == 'F' else 1])
                occ.add(o['thru'], [0, 1])
            mysides = [0 if me['side']=='F' else 1]
            best = None
            steps = int(max_shift/RES)
            for rad in range(1, steps+1):
                for ang in range(0, 360, 10):
                    dx = rad*RES*math.cos(math.radians(ang))
                    dy = rad*RES*math.sin(math.radians(ang))
                    allr = [(r[0]+dx, r[1]+dy, r[2]+dx, r[3]+dy) for r in me['own']+me['thru']]
                    if min(r[0] for r in allr) < bx0 or max(r[2] for r in allr) > bx1: continue
                    if min(r[1] for r in allr) < by0 or max(r[3] for r in allr) > by1: continue
                    if any(occ.hits([r], [0 if sd == 'F' else 1], dx, dy)
                           for r, sd in zip(me['own'], me['oside'])): continue
                    if me['thru'] and occ.hits(me['thru'], [0,1], dx, dy): continue
                    best = (dx, dy); break
                if best: break
            if best:
                at = fps[ref].find('at')
                at[1] = round(at[1] + best[0], 4); at[2] = round(at[2] + best[1], 4)
                fixed += 1; moved += 1
        if verbose: print(f"           relocated {fixed}/{len(todo)}")
        if fixed == 0: break
    open(out, 'w').write(dumps(pcb) + '\n')
    return moved

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('pcb'); ap.add_argument('-o','--out', required=True)
    ap.add_argument('--clearance', type=float, default=0.10)
    a = ap.parse_args()
    n = legalize(a.pcb, a.out, a.clearance)
    print(f"moved {n} part(s) -> {a.out}")
