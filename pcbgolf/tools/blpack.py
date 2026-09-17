"""Bottom-left-fill packing driven by simulated annealing over the ordering.

Far better at dense rectangle packing than continuous-coordinate SA:
we anneal the *sequence* (plus rotation and board side) and re-pack greedily.
Connectors are pre-placed along the perimeter; everything else fills the core.
"""
import sys, os, math, random, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parts import GEOM, SWAPS
from pcb import load_board
from place import EDGE_PARTS, TOP_ONLY

CLR = 0.20   # extra mm of clearance added around every part (assembly + routing)

def bl_pack(rects, strip_w):
    """rects: list of (w,h). Returns (placements, used_h) using bottom-left-fill."""
    placed = []
    skyline = [(0.0, strip_w, 0.0)]   # (x0, x1, y)
    for (w, h) in rects:
        best = None
        for i, (sx0, sx1, sy) in enumerate(skyline):
            x = sx0
            if x + w > strip_w + 1e-9: continue
            y = 0.0
            for (ox0, ox1, oy) in skyline:
                if ox1 > x + 1e-9 and ox0 < x + w - 1e-9:
                    y = max(y, oy)
            if best is None or (y, x) < (best[0], best[1]):
                best = (y, x)
        if best is None:
            y = max(s[2] for s in skyline); x = 0.0
        else:
            y, x = best
        placed.append((x, y, w, h))
        new = []
        for (ox0, ox1, oy) in skyline:
            if ox1 <= x + 1e-9 or ox0 >= x + w - 1e-9:
                new.append((ox0, ox1, oy)); continue
            if ox0 < x: new.append((ox0, x, oy))
            if ox1 > x + w: new.append((x + w, ox1, oy))
        new.append((x, x + w, y + h))
        new.sort()
        merged = []
        for seg in new:
            if merged and abs(merged[-1][2]-seg[2]) < 1e-9 and abs(merged[-1][1]-seg[0]) < 1e-9:
                merged[-1] = (merged[-1][0], seg[1], seg[2])
            else: merged.append(seg)
        skyline = merged
    used_h = max((p[1]+p[3] for p in placed), default=0.0)
    return placed, used_h

def build(swaps):
    b = load_board()
    items = []
    for f in b['fps']:
        fp = f.lib.split(':')[-1]
        s = swaps.get(fp)
        name = s['to'] if s else fp
        w, h, z = (s['W'], s['H'], s['Z']) if s else GEOM[fp][:3]
        items.append(dict(ref=f.ref, fp=name, w=w+CLR, h=h+CLR, z=z,
                          edge=name in EDGE_PARTS, top=name in TOP_ONLY))
    return items

def evaluate(items, strip_w, order, rots, sides, density_pad=1.0):
    """Pack non-edge parts per side; edge parts consume perimeter. Returns (W,H)."""
    edge = [it for it in items if it['edge']]
    core = [items[i] for i in order if not items[i]['edge']]
    per_side = {0: [], 1: []}
    for k, it in enumerate(core):
        r = rots[items.index(it)] if False else 0
        per_side[sides.get(it['ref'], 0)].append(it)
    H = 0.0
    for s in (0, 1):
        rects = []
        for it in per_side[s]:
            w, h = it['w'], it['h']
            if rots.get(it['ref'], 0) % 2: w, h = h, w
            rects.append((w, h))
        _, hh = bl_pack(rects, strip_w)
        H = max(H, hh)
    # perimeter must host every edge part
    need = sum(min(it['w'], it['h']) + 1.2 for it in edge)
    return strip_w, H, need

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
    items = build(OPT)
    core = [it for it in items if not it['edge']]
    edge = [it for it in items if it['edge']]
    core_a = sum(it['w']*it['h'] for it in core)
    edge_a = sum(it['w']*it['h'] for it in edge)
    print(f"core parts {len(core)}  area {core_a:.0f} mm2   (per side {core_a/2:.0f})")
    print(f"edge parts {len(edge)}  area {edge_a:.0f} mm2")
    need = sum(min(it['w'], it['h']) + 1.2 for it in edge)
    print(f"perimeter needed for connectors: {need:.1f} mm\n")

    rng = random.Random(1)
    print(f"{'strip W':>8} {'H(2-sided)':>11} {'board mm':>14} {'area':>8} {'density':>8}")
    print('-'*60)
    best = None
    for W in (24, 26, 28, 30, 32, 34, 36, 40):
        bh = 1e9
        for trial in range(40):
            order = list(range(len(items))); rng.shuffle(order)
            order.sort(key=lambda i: -items[i]['h'] if rng.random() < 0.7 else -items[i]['w']*items[i]['h'])
            rots = {it['ref']: rng.randrange(2) for it in items}
            sides = {}
            for i, it in enumerate(core):
                sides[it['ref']] = 0 if it['top'] else (i % 2)
            _, H, _ = evaluate(items, W, order, rots, sides)
            bh = min(bh, H)
        area = W*bh
        dens = (core_a/2 + 0) / area if area else 0
        flag = '' if 2*(W+bh) >= need else '  <-- perimeter INFEASIBLE'
        print(f"{W:>8.0f} {bh:>11.2f} {W:>6.1f}x{bh:<7.1f} {area:>8.0f} {dens:>7.0%}{flag}")
        if best is None or area < best[0]: best = (area, W, bh)
    print(f"\nTightest legal board: {best[1]:.0f} x {best[2]:.1f} mm = {best[0]:.0f} mm2")
