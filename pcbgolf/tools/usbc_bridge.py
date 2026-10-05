"""Lay the D+/D- bridges inside each vertical USB-C receptacle by hand.

A USB-C receptacle brings D+ out twice (A6, B6) and D- twice (A7, B7) so the
plug works either way up, and the board has to join each pair. On the GCT
vertical land pattern the two rows face each other across a 0.78mm channel
with the pairs crossed: A6 sits above B7 and A7 above B6. Joining both needs
one via, and it has to sit in that channel. Freerouting rarely finds it --
these bridges are the connection it leaves open on almost every board -- but
the geometry is fixed, so it is drawn once here, in footprint coordinates:

    D+  A6 -> B6       one diagonal on the top layer through the channel
    D-  A7 -> (0.25, -0.20) -> via (0.75, 0)
        via (0.75, 0) -> via (-0.75, 0)            on the first inner layer
        via (-0.75, 0) -> (-0.25, 0.20) -> B7

The vias sit between A8/B5 and A5/B8 with 0.165mm to those pads; every
other gap is larger. The copper is locked, so pcb2dsn hands it to the router
as protected wiring, and drc.py checks the result like any other copper.

    python3 usbc_bridge.py BOARD.kicad_pcb -o OUT.kicad_pcb
"""
import os, sys, argparse
D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, D)
from sexpr import load, dumps, Q
from collide import rot
import finish_router as F

LIB = 'USB-C-FEMALE-VERT-GCT'
TRACK, VIA, DRILL = 0.10, 0.45, 0.20
# (layer index: 0 top, 1 first inner), polyline in footprint coordinates
DP = [(0, [(-0.25, -0.83), (0.25, 0.83)])]
DN = [(0, [(0.25, -0.83), (0.25, -0.20), (0.75, 0.0)]),
      (1, [(0.75, 0.0), (-0.75, 0.0)]),
      (0, [(-0.75, 0.0), (-0.25, 0.20), (-0.25, 0.83)])]
DN_VIAS = [(0.75, 0.0), (-0.75, 0.0)]


def bridge(path, out, verbose=True):
    pcb = load(path)
    layers = [str(l[1]) for l in pcb.find('layers')[1:] if len(l) > 2 and l[2] == 'signal']
    uid, n = 970000, 0
    for f in pcb.find_all('footprint'):
        if str(f[1]).split(':')[-1] != LIB: continue
        ref = next(str(p[2]) for p in f.find_all('property') if str(p[1]) == 'Reference')
        if f.val('layer') != 'F.Cu':
            raise SystemExit(f'{ref}: vertical USB-C on the back side')
        at = f.find('at'); fx, fy = at[1], at[2]; ang = at[3] if len(at) > 3 else 0
        net = {}
        for p in f.find_all('pad'):
            nn = p.find('net')
            if nn is not None: net[str(p[1])] = int(nn[1])
        if net.get('A6') != net.get('B6') or net.get('A7') != net.get('B7'):
            raise SystemExit(f'{ref}: A6/B6 or A7/B7 not on one net')
        def b(x, y):
            gx, gy = rot(x, y, ang); return round(fx + gx, 4), round(fy + gy, 4)
        for nnum, paths in ((net['A6'], DP), (net['A7'], DN)):
            for li, pts in paths:
                for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
                    pcb.append(F.n('segment', F.n('start', *b(x0, y0)), F.n('end', *b(x1, y1)),
                                   F.n('width', TRACK), F.n('layer', Q(layers[li])),
                                   F.n('locked', 'yes'), F.n('net', nnum),
                                   F.n('uuid', Q(F.uuid_for(uid))))); uid += 1
        for (x, y) in DN_VIAS:
            pcb.append(F.n('via', F.n('at', *b(x, y)), F.n('size', VIA), F.n('drill', DRILL),
                           F.n('layers', Q(layers[0]), Q(layers[-1])),
                           F.n('locked', 'yes'), F.n('net', net['A7']),
                           F.n('uuid', Q(F.uuid_for(uid))))); uid += 1
        n += 1
    open(out, 'w').write(dumps(pcb) + '\n')
    if verbose: print(f"  bridged D+/D- in {n} vertical USB-C receptacle(s), {2*n} vias")
    return n


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('pcb'); ap.add_argument('-o', '--out', required=True)
    a = ap.parse_args()
    bridge(a.pcb, a.out)
