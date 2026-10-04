"""Score a routed .kicad_pcb with the official PCBGolf formula.

    score = bounding-box volume (mm^3) + 50 x vias + 5000 x copper layers

Height is taken from the tallest placed part plus board thickness plus the
tallest back-side part, using the measured heights in parts.py.
"""
import sys, os, argparse
D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, D)
from sexpr import load, Node
from parts import GEOM
import geom2

LEADER = 84578

def height(pcb, thickness=1.6):
    top = bot = 0.0
    for f in pcb.find_all('footprint'):
        lib = str(f[1]).split(':')[-1]
        g = GEOM.get(lib)
        z = g[2] if g else 1.0
        if f.val('layer') == 'B.Cu': bot = max(bot, z)
        else: top = max(top, z)
    return top + thickness + bot, top, bot

def score(path, thickness=1.6, exact=True):
    pcb = load(path)
    xs, ys = [], []
    for g in pcb.find_all('gr_line'):
        if g.val('layer') != 'Edge.Cuts': continue
        for k in ('start','end'):
            q = g.find(k); xs.append(q[1]); ys.append(q[2])
    W, H = max(xs)-min(xs), max(ys)-min(ys)
    cu = [l for l in pcb.find('layers')[1:] if len(l) > 2 and l[2] == 'signal']
    vias = len(pcb.find_all('via'))
    segs = pcb.find_all('segment')
    Z, top, bot = height(pcb, thickness)
    vol = W*H*Z
    # The score is the PCBA bounding box, so a component body that overhangs
    # the copper outline counts.  bbox3d measures the real assembly from the
    # footprints' 3D models; fall back to outline x height if it is unusable.
    if exact:
        try:
            import bbox3d
            b = bbox3d.bbox(path, thickness)
            W, H, Z, vol = b['W'], b['H'], b['Z'], b['volume']
            top, bot = b['z_top'], b['z_bot'] - thickness
        except Exception as e:
            print('    (bbox3d unavailable: %s; using outline x height)' % e)
    s = vol + 50*vias + 5000*len(cu)
    tracklen = 0.0
    for sg in segs:
        a, b = sg.find('start'), sg.find('end')
        tracklen += ((a[1]-b[1])**2 + (a[2]-b[2])**2) ** 0.5
    return dict(W=round(W,3), H=round(H,3), area=round(W*H,1), Z=round(Z,2),
                top=round(top,2), bottom=round(bot,2), volume=round(vol,1),
                vias=vias, via_pts=50*vias, layers=len(cu), layer_pts=5000*len(cu),
                segments=len(segs), track_mm=round(tracklen,1), score=round(s,1),
                vs_leader=round(s-LEADER,1), margin=f"{1-s/LEADER:.0%}")

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('pcb', nargs='+')
    ap.add_argument('--thickness', type=float, default=1.6)
    ap.add_argument('--no-exact', action='store_true',
                    help='outline x height instead of the measured 3D assembly box')
    a = ap.parse_args()
    for p in a.pcb:
        print(os.path.basename(p))
        for k, v in score(p, a.thickness, not a.no_exact).items():
            print(f"    {k:<12} {v}")
        print()
