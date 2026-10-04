"""Clearance check for routed copper: trace, via and pad against each other.

validate.py checks the file and the outline, collide.py checks pad against pad.
Neither looks at routed copper, so a trace laid too close to another net passed
every check here while Freerouting reported it as a clearance violation. This
closes that gap.

Geometry matters here, because getting it wrong invents violations that are not
there. Every piece of copper is either a CAPSULE (a segment swept by a radius)
or a RECT:

  trace            capsule along its path, radius = width/2
  via              capsule of zero length, radius = pad diameter/2 -- round,
                   not square: a 0.45mm square's corners reach 0.093mm further
                   than the circle, which is the same order as the clearance
  circle/oval pad  point or segment, radius = shorter side/2
  rect pad         its four true corners -- the USB-C shield lands sit at 39
                   degrees, and treating them as axis-aligned boxes invented
                   shorts that were not there
  roundrect pad    corners inset by the corner radius, swept by it: exact

Two items on the same layer and different nets must stay `clearance` apart,
edge to edge. Through-hole pads and vias occupy every copper layer.
"""
import sys, os, math, argparse, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sexpr import load, Node
from collide import rot as _rot
import ratsnest


def _seg_seg_dist(p, q, r, s):
    """Distance between two 2D segments."""
    def dot(a, b): return a[0]*b[0] + a[1]*b[1]
    def sub(a, b): return (a[0]-b[0], a[1]-b[1])
    def pt_seg(a, b, c):
        d = sub(c, b); L = dot(d, d)
        if L < 1e-12: return math.hypot(a[0]-b[0], a[1]-b[1])
        t = max(0.0, min(1.0, dot(sub(a, b), d) / L))
        px, py = b[0] + d[0]*t, b[1] + d[1]*t
        return math.hypot(a[0]-px, a[1]-py)
    d1, d2 = sub(q, p), sub(s, r)
    den = d1[0]*d2[1] - d1[1]*d2[0]
    if abs(den) > 1e-12:
        t = ((r[0]-p[0])*d2[1] - (r[1]-p[1])*d2[0]) / den
        u = ((r[0]-p[0])*d1[1] - (r[1]-p[1])*d1[0]) / den
        if 0 <= t <= 1 and 0 <= u <= 1: return 0.0
    return min(pt_seg(p, r, s), pt_seg(q, r, s), pt_seg(r, p, q), pt_seg(s, p, q))


def _poly_poly_dist(A, B):
    """Distance between two convex point sets (1, 2 or more points each)."""
    if len(A) == 1 and len(B) == 1:
        return math.hypot(A[0][0]-B[0][0], A[0][1]-B[0][1])
    ea = [(A[i], A[(i+1) % len(A)]) for i in range(len(A))] if len(A) > 2 \
         else [(A[0], A[-1])]
    eb = [(B[i], B[(i+1) % len(B)]) for i in range(len(B))] if len(B) > 2 \
         else [(B[0], B[-1])]
    if len(A) > 2 and any(_point_in_poly(q, A) for q in B): return 0.0
    if len(B) > 2 and any(_point_in_poly(q, B) for q in A): return 0.0
    return min(_seg_seg_dist(p, q, r, t) for (p, q) in ea for (r, t) in eb)


def _point_in_poly(pt, poly):
    sign = None
    for i in range(len(poly)):
        a, b = poly[i], poly[(i+1) % len(poly)]
        cr = (b[0]-a[0])*(pt[1]-a[1]) - (b[1]-a[1])*(pt[0]-a[0])
        if abs(cr) < 1e-12: continue
        s = cr > 0
        if sign is None: sign = s
        elif s != sign: return False
    return True


def _inset_rect(cx, cy, w, h, ang, r):
    """A rotated rect shrunk by r on every side, as a point set.

    A rect offset inward by r has half-extents (w/2-r, h/2-r), clamped at
    zero -- it is NOT the corners pulled toward the centroid, which is what an
    earlier version did: for a 1.1x1.9 pad with rratio 0.5 (a stadium, fully
    rounded ends) that gave a 0.948x0.549 rect swept by 0.55 instead of a
    0x0.8 segment swept by 0.55, inflating the pad by 0.47mm a side and
    inventing clearance violations.

    Collapses to a segment or a point when r reaches half a side, which is
    exactly right: those are the oval and circular cases.
    """
    a = max(0.0, w/2.0 - r); b = max(0.0, h/2.0 - r)
    if a < 1e-9 and b < 1e-9:
        return [(cx, cy)]
    if a < 1e-9:
        p = _rot(0.0, b, ang); return [(cx-p[0], cy-p[1]), (cx+p[0], cy+p[1])]
    if b < 1e-9:
        p = _rot(a, 0.0, ang); return [(cx-p[0], cy-p[1]), (cx+p[0], cy+p[1])]
    return [(cx+dx, cy+dy) for dx, dy in
            (_rot(-a, -b, ang), _rot(a, -b, ang), _rot(a, b, ang), _rot(-a, b, ang))]


def items(pcb):
    """Flatten copper into {kind, net, layers, geometry, half-width, label}."""
    nets, pads, segs, vias = ratsnest.items_of(pcb)
    cu = [str(l[1]) for l in pcb.find('layers')[1:] if len(l) > 2 and l[2] == 'signal']
    out = []
    for p in pads:
        lay = set(cu) if p['layer'] is None else {p['layer']}
        base = dict(kind='pad', net=p['net'], layers=lay,
                    label=f"{p['ref']}.{p['pad']}")
        w, h, sh = p['w'], p['h'], p['shape']
        if sh == 'circle':
            base.update(poly=[(p['x'], p['y'])], r=max(w, h)/2.0)
        elif sh == 'oval':
            r = min(w, h)/2.0
            ax, ay = ((w-h)/2.0, 0.0) if w >= h else (0.0, (h-w)/2.0)
            rx, ry = _rot(ax, ay, p['rot'])
            base.update(poly=[(p['x']-rx, p['y']-ry), (p['x']+rx, p['y']+ry)], r=r)
        elif sh == 'roundrect' and p.get('rratio'):
            r = p['rratio'] * min(w, h)
            base.update(poly=_inset_rect(p['x'], p['y'], w, h, p['rot'], r), r=r)
        else:
            base.update(poly=p['poly'], r=0.0)
        out.append(base)
    for s_ in segs:
        out.append(dict(kind='trace', net=s_['net'], layers={s_['layer']},
                        poly=[s_['p'], s_['q']], r=s_['width']/2.0,
                        label='trace'))
    for v in vias:
        out.append(dict(kind='via', net=v['net'], layers=set(cu),
                        poly=[v['p']], r=v['size']/2.0, label='via'))
    return nets, cu, out


def gap(a, b):
    """Edge-to-edge distance between two copper items, ignoring layers."""
    return _poly_poly_dist(a['poly'], b['poly']) - a['r'] - b['r']


def check(path, clearance=0.09, verbose=12, ignore_intra_footprint=True):
    pcb = load(path)
    nets, cu, it = items(pcb)
    CELL = 2.0
    grid = collections.defaultdict(list)
    for i, o in enumerate(it):
        xs = [q_[0] for q_ in o['poly']]; ys = [q_[1] for q_ in o['poly']]
        x0, x1 = min(xs) - o['r'], max(xs) + o['r']
        y0, y1 = min(ys) - o['r'], max(ys) + o['r']
        for gx in range(int((x0-clearance)//CELL), int((x1+clearance)//CELL)+1):
            for gy in range(int((y0-clearance)//CELL), int((y1+clearance)//CELL)+1):
                grid[(gx, gy)].append(i)

    seen = set(); bad = []
    for ids in grid.values():
        for ai in range(len(ids)):
            for bi in range(ai+1, len(ids)):
                i, j = ids[ai], ids[bi]
                if i == j: continue
                key = (i, j) if i < j else (j, i)
                if key in seen: continue
                seen.add(key)
                a, b = it[i], it[j]
                if a['net'] == b['net']: continue
                if not (a['layers'] & b['layers']): continue
                if ignore_intra_footprint and a['kind'] == 'pad' and b['kind'] == 'pad':
                    if a['label'].split('.')[0] == b['label'].split('.')[0]: continue
                g = gap(a, b)
                if g < clearance - 1e-6:
                    bad.append((g, a['kind'], a['label'], nets.get(a['net'], '?'),
                                b['kind'], b['label'], nets.get(b['net'], '?')))
    bad.sort()
    kinds = collections.Counter(tuple(sorted((x[1], x[4]))) for x in bad)
    print(f"  {os.path.basename(path)}")
    print(f"  copper items        : {len(it)}")
    print(f"  clearance rule      : {clearance} mm")
    print(f"  violations          : {len(bad)}")
    print(f"  actually touching   : {sum(1 for x in bad if x[0] < 0)}")
    for k, c in kinds.most_common():
        print(f"     {k[0]:<6} vs {k[1]:<6} {c}")
    for g, ka, la, na, kb, lb, nb in bad[:verbose]:
        tag = 'SHORT  ' if g < 0 else 'tight  '
        print(f"    {tag} {g:+.4f}mm  {ka} {la}[{na}]  vs  {kb} {lb}[{nb}]")
    return len(bad), bad


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('pcb', nargs='+')
    ap.add_argument('--clearance', type=float, default=0.09)
    ap.add_argument('-v', '--verbose', type=int, default=12)
    a = ap.parse_args()
    rc = 0
    for p in a.pcb:
        n, _ = check(p, a.clearance, a.verbose)
        print()
        rc = max(rc, 1 if n else 0)
    sys.exit(rc)
