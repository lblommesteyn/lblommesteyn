"""Load real pad geometry for every footprint in pcbgolf.pretty."""
import os, sys, math, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sexpr import load

PRETTY = '/home/user/commaai/pcbgolf/pcbgolf.pretty'

def load_footprints():
    out = {}
    for f in glob.glob(os.path.join(PRETTY, '*.kicad_mod')):
        fp = load(f)
        name = os.path.basename(f)[:-10]
        pads = []
        for p in fp.find_all('pad'):
            at = p.find('at'); sz = p.find('size')
            if not at or not sz: continue
            ptype = str(p[2]) if len(p) > 2 else 'smd'
            shape = str(p[3]) if len(p) > 3 else 'rect'
            rot = at[3] if len(at) > 3 else 0.0
            if not isinstance(rot, (int, float)): rot = 0.0
            layers = [str(x) for x in (p.find('layers') or [])[1:]]
            pads.append(dict(name=str(p[1]), x=at[1], y=at[2], rot=rot,
                             w=sz[1], h=sz[2], type=ptype, shape=shape, layers=layers))
        lo = [1e9,1e9]; hi=[-1e9,-1e9]
        for pd in pads:
            lo[0]=min(lo[0],pd['x']-pd['w']/2); lo[1]=min(lo[1],pd['y']-pd['h']/2)
            hi[0]=max(hi[0],pd['x']+pd['w']/2); hi[1]=max(hi[1],pd['y']+pd['h']/2)
        out[name] = dict(pads=pads, bbox=lo+hi,
                         w=hi[0]-lo[0] if pads else 1.0, h=hi[1]-lo[1] if pads else 1.0)
    return out

if __name__ == '__main__':
    fps = load_footprints()
    print(f"{len(fps)} footprints")
    for k in sorted(fps):
        v = fps[k]
        print(f"  {k:<30} {len(v['pads']):>3} pads  {v['w']:6.2f} x {v['h']:6.2f}")
