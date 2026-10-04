"""Find what is still unconnected on a routed .kicad_pcb.

Clusters each net's pads, tracks and vias by geometric touching; a net needing
N clusters joined still needs N-1 connections.
"""
import sys, os, math, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sexpr import load, Node
from collide import rot

TOL = 0.02

class DSU:
    def __init__(self): self.p = {}
    def find(self, a):
        self.p.setdefault(a, a)
        while self.p[a] != a: self.p[a] = self.p[self.p[a]]; a = self.p[a]
        return a
    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb: self.p[ra] = rb

def seg_rect_hit(p, q, r):
    """Does segment p-q touch axis-aligned rect r=(x0,y0,x1,y1)?"""
    x0, y0, x1, y1 = r
    for (x, y) in (p, q):
        if x0-TOL <= x <= x1+TOL and y0-TOL <= y <= y1+TOL: return True
    return False

def items_of(pcb):
    """Per net: pads (rects), track segments, vias."""
    nets = {int(n[1]): str(n[2]) for n in pcb.find_all('net')}
    pads, segs, vias = [], [], []
    for f in pcb.find_all('footprint'):
        ref = next((str(p[2]) for p in f.find_all('property') if p[1]=='Reference'), '?')
        at = f.find('at'); fx, fy = at[1], at[2]
        ang = at[3] if len(at) > 3 else 0
        for pad in f.find_all('pad'):
            nn = pad.find('net')
            if nn is None: continue
            pat = pad.find('at'); sz = pad.find('size')
            if not pat or not sz: continue
            gx, gy = rot(pat[1], pat[2], ang); gx += fx; gy += fy
            pang = pat[3] if len(pat) > 3 else 0
            if not isinstance(pang, (int,float)): pang = 0
            w, h = sz[1], sz[2]
            lays = [str(v) for v in (pad.find('layers') or Node())[1:]]
            thru = (len(pad)>2 and str(pad[2])=='thru_hole') or any(l=='*.Cu' for l in lays)
            side = None if thru else ('B.Cu' if any(l.startswith('B.') for l in lays) else 'F.Cu')
            shape = str(pad[3]) if len(pad) > 3 else 'rect'
            # Pads are not all axis-aligned: the USB-C shield lands sit at 39
            # degrees.  Keep the true corners, and derive the bounding box from
            # them rather than swapping w/h for the 90-degree case only.
            poly = [(gx + _rx, gy + _ry)
                    for _rx, _ry in (rot(-w/2, -h/2, pang), rot(w/2, -h/2, pang),
                                     rot(w/2, h/2, pang), rot(-w/2, h/2, pang))]
            xs_ = [q_[0] for q_ in poly]; ys_ = [q_[1] for q_ in poly]
            rr = pad.find('roundrect_rratio')
            pads.append(dict(net=int(nn[1]), ref=ref, pad=str(pad[1]), layer=side,
                             rect=(min(xs_), min(ys_), max(xs_), max(ys_)),
                             x=gx, y=gy, shape=shape, w=w, h=h, rot=pang,
                             poly=poly, rratio=(rr[1] if rr else 0.0)))
    for s in pcb.find_all('segment'):
        nn = s.find('net')
        if nn is None: continue
        a, b = s.find('start'), s.find('end')
        w = s.find('width')
        segs.append(dict(net=int(nn[1]), layer=s.val('layer'),
                         p=(a[1], a[2]), q=(b[1], b[2]),
                         width=(w[1] if w else 0.1)))
    for v in pcb.find_all('via'):
        nn = v.find('net')
        if nn is None: continue
        at = v.find('at')
        vias.append(dict(net=int(nn[1]), p=(at[1], at[2]),
                         size=(v.find('size') or [None,0.6])[1]))
    return nets, pads, segs, vias

def clusters(pcb=None, nets=None, pads=None, segs=None, vias=None):
    """net number -> list of clusters, each a list of that net's pads that are
    already joined by copper."""
    from collections import defaultdict
    bynet = defaultdict(lambda: dict(pads=[], segs=[], vias=[]))
    for p in pads: bynet[p['net']]['pads'].append(p)
    for s in segs: bynet[s['net']]['segs'].append(s)
    for v in vias: bynet[v['net']]['vias'].append(v)
    out = {}
    for net, g in bynet.items():
        if len(g['pads']) < 2: continue
        d = DSU()
        nodes = ([('P', i, p) for i, p in enumerate(g['pads'])] +
                 [('S', i, s) for i, s in enumerate(g['segs'])] +
                 [('V', i, v) for i, v in enumerate(g['vias'])])
        for a in range(len(nodes)):
            ta, ia, oa = nodes[a]
            for b in range(a+1, len(nodes)):
                tb, ib, ob = nodes[b]
                if _touch(ta, oa, tb, ob): d.union((ta, ia), (tb, ib))
        grp = defaultdict(list)
        for i, p in enumerate(g['pads']): grp[d.find(('P', i))].append(p)
        if len(grp) > 1: out[net] = list(grp.values())
    return out


def _touch(ta, oa, tb, ob):
    if ta == 'P' and tb == 'P':
        # Two same-net pads whose copper overlaps are one region, so they are
        # connected without any track between them.  The USB-C shield lugs are
        # exactly this: S2T on the front, S2B on the back and S2TH, a plated
        # through-hole, all at one point.  Without this they read as three
        # separate islands and the net reports connections that are not
        # actually missing.
        if not (oa['layer'] is None or ob['layer'] is None
                or oa['layer'] == ob['layer']):
            return False
        ra, rb = oa['rect'], ob['rect']
        return (ra[0] - TOL <= rb[2] and rb[0] - TOL <= ra[2] and
                ra[1] - TOL <= rb[3] and rb[1] - TOL <= ra[3])
    if ta == 'S' and tb == 'S':
        if oa['layer'] != ob['layer']: return False
        return any(abs(x1-x2) < TOL and abs(y1-y2) < TOL
                   for (x1, y1) in (oa['p'], oa['q'])
                   for (x2, y2) in (ob['p'], ob['q']))
    if ta == 'S' and tb == 'P':
        return (ob['layer'] is None or ob['layer'] == oa['layer']) and \
               seg_rect_hit(oa['p'], oa['q'], ob['rect'])
    if ta == 'P' and tb == 'S':
        return (oa['layer'] is None or oa['layer'] == ob['layer']) and \
               seg_rect_hit(ob['p'], ob['q'], oa['rect'])
    if ta == 'S' and tb == 'V':
        return any(abs(x1-ob['p'][0]) < ob['size']/2+TOL and
                   abs(y1-ob['p'][1]) < ob['size']/2+TOL
                   for (x1, y1) in (oa['p'], oa['q']))
    if ta == 'V' and tb == 'S':
        return any(abs(x1-oa['p'][0]) < oa['size']/2+TOL and
                   abs(y1-oa['p'][1]) < oa['size']/2+TOL
                   for (x1, y1) in (ob['p'], ob['q']))
    if ta == 'P' and tb == 'V':
        r = oa['rect']
        return r[0]-TOL <= ob['p'][0] <= r[2]+TOL and r[1]-TOL <= ob['p'][1] <= r[3]+TOL
    if ta == 'V' and tb == 'P':
        r = ob['rect']
        return r[0]-TOL <= oa['p'][0] <= r[2]+TOL and r[1]-TOL <= oa['p'][1] <= r[3]+TOL
    return False


def analyse(path, verbose=10):
    pcb = load(path)
    nets, pads, segs, vias = items_of(pcb)
    from collections import defaultdict
    bynet = defaultdict(lambda: dict(pads=[], segs=[], vias=[]))
    for p in pads: bynet[p['net']]['pads'].append(p)
    for s in segs: bynet[s['net']]['segs'].append(s)
    for v in vias: bynet[v['net']]['vias'].append(v)

    missing = []
    for net, g in bynet.items():
        if len(g['pads']) < 2: continue
        d = DSU()
        nodes = []
        for i, p in enumerate(g['pads']): nodes.append(('P', i, p))
        for i, s in enumerate(g['segs']): nodes.append(('S', i, s))
        for i, v in enumerate(g['vias']): nodes.append(('V', i, v))
        # One definition of what touches what, in _touch: this used to be a
        # second inline copy, and they drifted -- a fix to _touch silently did
        # nothing here.
        for a in range(len(nodes)):
            ta, ia, oa = nodes[a]
            for b in range(a+1, len(nodes)):
                tb, ib, ob = nodes[b]
                if _touch(ta, oa, tb, ob):
                    d.union((ta, ia), (tb, ib))
        roots = {d.find(('P', i)) for i in range(len(g['pads']))}
        if len(roots) > 1:
            missing.append((nets.get(net, f'net{net}'), len(roots)-1, len(g['pads'])))
    missing.sort(key=lambda m: -m[1])
    total = sum(m[1] for m in missing)
    print(f"  {os.path.basename(path)}")
    print(f"    nets with pads      : {sum(1 for g in bynet.values() if len(g['pads'])>=2)}")
    print(f"    nets not fully joined: {len(missing)}")
    print(f"    connections missing : {total}")
    for nm, k, np_ in missing[:verbose]:
        print(f"       {nm:<18} {k} connection(s) short ({np_} pads)")
    return total, missing

if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('pcb', nargs='+')
    a = ap.parse_args()
    for p in a.pcb: analyse(p); print()
