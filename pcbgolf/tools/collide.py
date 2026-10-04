"""Check a .kicad_pcb for pad-to-pad collisions between different nets.

validate.py checks outline containment and net consistency; this checks that the
placement is physically legal, which is a different failure mode.
"""
import sys, os, math, itertools, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sexpr import load, Node

def rot(x, y, d):
    a = math.radians(d); c, s = math.cos(a), math.sin(a)
    return (x*c + y*s, -x*s + y*c)

def pads_of(pcb):
    out = []
    for f in pcb.find_all('footprint'):
        ref = next((str(p[2]) for p in f.find_all('property') if p[1]=='Reference'), '?')
        at = f.find('at'); fx, fy = at[1], at[2]
        fang = at[3] if len(at) > 3 else 0
        for p in f.find_all('pad'):
            if len(p) > 2 and str(p[2]) == 'np_thru_hole': continue
            pat = p.find('at'); sz = p.find('size')
            if not pat or not sz: continue
            gx, gy = rot(pat[1], pat[2], fang); gx += fx; gy += fy
            pang = pat[3] if len(pat) > 3 else 0
            if not isinstance(pang, (int, float)): pang = 0
            w, h = sz[1], sz[2]
            # the pad's own angle is absolute in the file
            if abs((pang % 180) - 90) < 1: w, h = h, w
            elif pang % 180 > 1:            # non-orthogonal: use the circumscribed box
                a = math.radians(pang)
                w2 = abs(w*math.cos(a)) + abs(h*math.sin(a))
                h2 = abs(w*math.sin(a)) + abs(h*math.cos(a))
                w, h = w2, h2
            lays = [str(v) for v in (p.find('layers') or Node())[1:]]
            thru = (len(p) > 2 and str(p[2]) == 'thru_hole') or any(l == '*.Cu' for l in lays)
            side = 'B' if any(l.startswith('B.') for l in lays) and not thru else 'F'
            if thru: side = '*'
            nn = p.find('net')
            net = str(nn[2]) if nn is not None and len(nn) > 2 else None
            out.append(dict(ref=ref, pad=str(p[1]), x=gx, y=gy, w=w, h=h,
                            side=side, net=net))
    return out

def check(path, clearance=0.10, verbose=12):
    pcb = load(path)
    pads = pads_of(path if isinstance(path, Node) else pcb)
    intra = []
    grid = collections.defaultdict(list)
    CELL = 2.0
    for p in pads:
        grid[(int(p['x']//CELL), int(p['y']//CELL))].append(p)
    hits = []
    seen = set()
    for (i, j), grp in grid.items():
        near = []
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                near += grid.get((i+di, j+dj), [])
        for a, b in itertools.combinations(near, 2):
            if a is b: continue
            if a['side'] != b['side'] and '*' not in (a['side'], b['side']): continue
            if a['net'] and b['net'] and a['net'] == b['net']: continue
            key = tuple(sorted((f"{a['ref']}.{a['pad']}", f"{b['ref']}.{b['pad']}")))
            if key in seen: continue
            seen.add(key)
            if a['ref'] == b['ref']:
                # Inside one footprint the spacing is the vendor's land pattern,
                # not a placement decision -- but the autorouter counts it as a
                # pre-existing clearance violation, so report it rather than
                # hide it.  The 0.25mm-pitch USB-C (J3) is the only source here,
                # and the upstream board has the same pairs plus 24 that
                # actually overlap.
                dx = abs(a['x']-b['x']) - (a['w']+b['w'])/2
                dy = abs(a['y']-b['y']) - (a['h']+b['h'])/2
                if max(dx, dy) < clearance:
                    intra.append((max(dx, dy), a['ref']))
                continue
            dx = abs(a['x']-b['x']) - (a['w']+b['w'])/2
            dy = abs(a['y']-b['y']) - (a['h']+b['h'])/2
            g = max(dx, dy)
            if g < clearance:
                hits.append((g, key[0], key[1], a['net'], b['net']))
    hits.sort()
    overlap = [h for h in hits if h[0] < 0]
    print(f"  pads                 : {len(pads)}")
    print(f"  inter-part pairs < {clearance}mm : {len(hits)}")
    print(f"  actually OVERLAPPING : {len(overlap)}")
    if intra:
        by = collections.Counter(r for _, r in intra)
        worst = min(g for g, _ in intra)
        print(f"  intra-footprint < {clearance}mm : {len(intra)} "
              f"({', '.join('%s x%d' % (r, c) for r, c in by.most_common())}; "
              f"tightest {worst:+.3f}mm) - vendor land pattern")
    for g, x, y, n1, n2 in hits[:verbose]:
        tag = 'OVERLAP' if g < 0 else 'tight  '
        print(f"    {tag} {g:+.3f}mm  {x:<14}[{str(n1)[:12]:<12}] {y:<14}[{str(n2)[:12]}]")
    return len(overlap), len(hits)

if __name__ == '__main__':
    for p in sys.argv[1:]:
        print(os.path.basename(p)); check(p); print()
