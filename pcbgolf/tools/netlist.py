"""Build a full netlist from the flat multi-sheet PCBGolf schematics."""
import sys, glob, math, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sexpr import load, Node
from collections import defaultdict

SCHDIR = '/home/user/commaai/pcbgolf'
Q = 4  # quantise to 1/4 of 0.01mm grid

_SHEET = ['']
def key(x, y):
    return (_SHEET[0], round(x*100), round(y*100))

class DSU:
    def __init__(self): self.p = {}
    def find(self, a):
        self.p.setdefault(a, a)
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]; a = self.p[a]
        return a
    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb: self.p[ra] = rb

def xform(px, py, sx, sy, ang, mirror, variant=0):
    x, y = px, -py
    if mirror == 'x': y = -y
    elif mirror == 'y': x = -x
    a = math.radians(ang)
    c, s = math.cos(a), math.sin(a)
    if variant == 0:
        xr, yr = x*c + y*s, -x*s + y*c
    else:
        xr, yr = x*c - y*s, x*s + y*c
    return sx + xr, sy + yr

def on_segment(p, a, b, tol=1e-6):
    (px,py),(ax,ay),(bx,by) = p,a,b
    cross = (bx-ax)*(py-ay) - (by-ay)*(px-ax)
    if abs(cross) > 1e-4: return False
    dot = (px-ax)*(bx-ax) + (py-ay)*(by-ay)
    L2 = (bx-ax)**2 + (by-ay)**2
    return -1e-6 <= dot <= L2 + 1e-6

def build(variant=0, verbose=False):
    dsu = DSU()
    pin_at = defaultdict(list)     # point -> [(ref, pinnum, pinname, etype)]
    label_at = defaultdict(list)   # point -> [name]
    power_pins = []                # (point, netname)
    comps = {}                     # ref -> dict
    nc_points = set()
    hits = miss = 0

    for path in sorted(glob.glob(os.path.join(SCHDIR, 'pcbgolf*.kicad_sch'))):
        sch = load(path)
        _SHEET[0] = os.path.basename(path)
        libs = {}
        ls = sch.find('lib_symbols')
        if ls:
            for s in ls.find_all('symbol'):
                name = s[1]
                pins = []
                ispower = s.find('power') is not None
                for sub in s.find_all('symbol'):
                    for p in sub.find_all('pin'):
                        at = p.find('at')
                        nm = p.find('name'); nu = p.find('number')
                        pins.append(dict(x=at[1], y=at[2],
                                         etype=str(p[1]),
                                         name=str(nm[1]) if nm else '',
                                         num=str(nu[1]) if nu else '',
                                         unit=_unit_of(sub[1])))
                for p in s.find_all('pin'):
                    at = p.find('at'); nm = p.find('name'); nu = p.find('number')
                    pins.append(dict(x=at[1], y=at[2], etype=str(p[1]),
                                     name=str(nm[1]) if nm else '',
                                     num=str(nu[1]) if nu else '', unit=1))
                libs[name] = dict(pins=pins, power=ispower)

        wire_segs = []
        for w in sch.find_all('wire'):
            pts = w.find('pts')
            if not pts: continue
            xy = pts.find_all('xy')
            if len(xy) < 2: continue
            a = (xy[0][1], xy[0][2]); b = (xy[1][1], xy[1][2])
            wire_segs.append((a,b))
            dsu.union(key(*a), key(*b))

        for j in sch.find_all('junction'):
            at = j.find('at'); jp = (at[1], at[2])
            for (a,b) in wire_segs:
                if on_segment(jp, a, b):
                    dsu.union(key(*jp), key(*a)); dsu.union(key(*jp), key(*b))

        for tag in ('label','global_label','hierarchical_label'):
            for l in sch.find_all(tag):
                at = l.find('at')
                label_at[key(at[1], at[2])].append(str(l[1]))

        for nc in sch.find_all('no_connect'):
            at = nc.find('at'); nc_points.add(key(at[1], at[2]))

        for sym in sch.find_all('symbol'):
            lib_id = sym.val('lib_id')
            at = sym.find('at')
            sx, sy = at[1], at[2]
            ang = at[3] if len(at) > 3 else 0
            mir = sym.val('mirror')
            unit = sym.val('unit', 1, 1)
            ref = val = fp = mpn = ''
            for p in sym.find_all('property'):
                if p[1]=='Reference': ref = str(p[2])
                elif p[1]=='Value': val = str(p[2])
                elif p[1]=='Footprint': fp = str(p[2])
                elif p[1]=='MPN': mpn = str(p[2])
            L = libs.get(lib_id)
            if L is None: continue
            if L['power'] or ref.startswith('#PWR') or ref.startswith('#FLG'):
                for pin in L['pins']:
                    px, py = xform(pin['x'], pin['y'], sx, sy, ang, mir, variant)
                    power_pins.append((key(px,py), val))
                continue
            comps.setdefault(ref, dict(ref=ref, value=val, fp=fp, mpn=mpn, lib=lib_id, pins={}))
            for pin in L['pins']:
                if pin['unit'] not in (0, unit) and len(set(p['unit'] for p in L['pins'])) > 1:
                    continue
                px, py = xform(pin['x'], pin['y'], sx, sy, ang, mir, variant)
                k = key(px, py)
                pin_at[k].append((ref, pin['num'], pin['name'], pin['etype']))
                comps[ref]['pins'][pin['num']] = dict(name=pin['name'], etype=pin['etype'], pt=k)
                touching = any(on_segment((px,py), a, b) for (a,b) in wire_segs)
                if touching or k in label_at or k in nc_points: hits += 1
                else: miss += 1
                for (a,b) in wire_segs:
                    if on_segment((px,py), a, b):
                        dsu.union(k, key(*a)); dsu.union(k, key(*b))

    return dsu, pin_at, label_at, power_pins, comps, nc_points, hits, miss

def _unit_of(subname):
    try: return int(subname.rsplit('_',2)[-2])
    except Exception: return 1

def netlist(variant=0):
    dsu, pin_at, label_at, power_pins, comps, nc_points, hits, miss = build(variant)
    for pt, name in power_pins:
        dsu.union(pt, ('NET', name))
    for pt, names in label_at.items():
        for nm in names:
            dsu.union(pt, ('NET', nm))
    nets = defaultdict(set)
    names = defaultdict(set)
    for pt, plist in pin_at.items():
        r = dsu.find(pt)
        for (ref, num, pname, etype) in plist:
            nets[r].add((ref, num, pname, etype))
    for pt, nlist in label_at.items():
        r = dsu.find(pt)
        for nm in nlist: names[r].add(nm)
    for pt, nm in power_pins:
        names[dsu.find(pt)].add(nm)
    out = {}
    for i, (r, pins) in enumerate(nets.items()):
        nm = sorted(names.get(r, []))
        out[nm[0] if nm else f'N${i}'] = sorted(pins)
    return out, comps, hits, miss

if __name__ == '__main__':
    best = None
    for v in (0,1):
        r = build(v); h, m = r[6], r[7]
        print(f"variant {v}: pin-on-wire hits {h}  misses {m}  ({100*h/(h+m):.1f}%)")
        if best is None or h > best[1]: best = (v,h)
    v = best[0]
    nets, comps, h, m = netlist(v)
    print(f"\nUsing variant {v}: {len(nets)} nets, {len(comps)} components")
    json.dump({'nets': {k: [list(p) for p in v_] for k,v_ in nets.items()},
               'comps': comps}, open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'netlist.json'),'w'), indent=1)
    from collections import Counter
    c = Counter({k: len(v_) for k,v_ in nets.items()})
    print("\nTop 20 nets by pin count:")
    for k,n in c.most_common(20): print(f"  {n:>4}  {k}")
    print(f"\ntotal connected pins: {sum(c.values())}")
