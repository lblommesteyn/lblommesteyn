"""Check that every edge connector's mating opening faces out of the board.

The placer seats an edge connector against the outline, but it only knows the
connector's box, so it can seat it either way round: plug opening against the
edge, or plug opening facing into the board where nothing can be plugged in.
Both look the same to the volume score. This finds each connector's opening
from its own 3D model, by casting a grid of rays inward through each of the
four vertical faces of its placed body and measuring how far they get before
hitting metal or plastic: a ray belongs to the opening when it runs deep
between walls on all four sides. The opening must be on the outline.

    python3 mating.py BOARD.kicad_pcb [...]
"""
import os, sys, math, argparse
D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, D)
import bbox3d
from bbox3d import _models, _shape, _mul, _rx, _ry, _rz, _apply
from sexpr import load
from geom2 import EDGE_SPEC

from OCP.gp import gp_Trsf, gp_Lin, gp_Pnt, gp_Dir
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector

# opening face may sit at most this far inside the outline
FLUSH = 0.10

DIRS = {'+x': (1, 0), '-x': (-1, 0), '+y': (0, 1), '-y': (0, -1)}


def placed(lib, x, y, rho, back, thick):
    """The footprint's model shapes moved into 3D board coords (bbox3d's transform)."""
    out = []
    for path, off, rot in _models(lib):
        sh = _shape(path)
        if sh is None: continue
        Rm = _mul(_rz(-rot[2]), _mul(_ry(-rot[1]), _rx(-rot[0])))
        A = _rz(rho)
        if back:
            M = _mul(A, _mul([[1, 0, 0], [0, -1, 0], [0, 0, -1]], Rm))
            t = _apply(A, [off[0], -off[1], -off[2]]); t = [t[0] + x, t[1] - y, t[2]]
        else:
            M = _mul(A, Rm)
            t = _apply(A, list(off)); t = [t[0] + x, t[1] - y, t[2] + thick]
        tr = gp_Trsf()
        tr.SetValues(M[0][0], M[0][1], M[0][2], t[0], M[1][0], M[1][1], M[1][2], t[1],
                     M[2][0], M[2][1], M[2][2], t[2])
        out.append(BRepBuilderAPI_Transform(sh, tr, True).Shape())
    return out


def openness(shapes, step=0.2, rim=3.0):
    """{dir: (area in mm^2 of the face's enclosed cavity, its max depth)}.

    A ray belongs to a cavity when it runs at least `rim` mm deeper than some
    ray on each of its four sides (left, right, above, below) on the same
    face: a hole in a wall. Counting deep rays alone is fooled by a curved or
    stepped body, whose rays graze past a sloping surface or fly over a short
    back section."""
    bs = []
    for s in shapes:
        b = Bnd_Box(); b.SetGap(0.0); BRepBndLib.Add_s(s, b, True); bs.append(b)
    lo = [min(b.CornerMin().Coord(i) for b in bs) for i in (1, 2, 3)]
    hi = [max(b.CornerMax().Coord(i) for b in bs) for i in (1, 2, 3)]
    ix = []
    for s in shapes:
        it = IntCurvesFace_ShapeIntersector(); it.Load(s, 1e-4); ix.append(it)
    span = [hi[i] - lo[i] for i in range(3)]
    res = {}
    for name, (dx, dy) in DIRS.items():
        ax = 0 if dx else 1                   # axis the rays travel along
        ot = 1 - ax                           # across the face
        # rays enter through the face whose outward normal is (dx, dy)
        start = hi[ax] + 1.0 if (dx + dy) > 0 else lo[ax] - 1.0
        d = gp_Dir(-dx, -dy, 0)
        us = [lo[ot] + step * (i + .5) for i in range(int(span[ot] / step))]
        zs = [lo[2] + step * (j + .5) for j in range(int(span[2] / step))]
        g = []
        for z in zs:
            row = []
            for u in us:
                p = [0, 0, z]; p[ax] = start; p[ot] = u
                first = math.inf
                for it in ix:
                    it.Perform(gp_Lin(gp_Pnt(*p), d), 0.0, span[ax] + 2.0)
                    for k in range(1, it.NbPnt() + 1):
                        first = min(first, it.WParameter(k))
                row.append(first - 1.0)       # inf: the ray missed the body
            g.append(row)
        n = 0; mx = 0.0
        for j in range(len(zs)):
            for i in range(len(us)):
                v = g[j][i]
                if not (rim < v < math.inf): continue
                walls = (any(g[j][k] < v - rim for k in range(i)),
                         any(g[j][k] < v - rim for k in range(i + 1, len(us))),
                         any(g[k][i] < v - rim for k in range(j)),
                         any(g[k][i] < v - rim for k in range(j + 1, len(zs))))
                if all(walls):
                    n += 1; mx = max(mx, v)
        res[name] = (n * step * step, mx)
    return res, (lo, hi)


def check(path, verbose=False):
    pcb = load(path)
    thick = bbox3d.board_thickness(pcb)
    xs, ys = [], []
    for g in pcb.find_all('gr_line'):
        if g.val('layer') != 'Edge.Cuts': continue
        for k in ('start', 'end'):
            q = g.find(k); xs.append(q[1]); ys.append(q[2])
    if not xs:          # no outline drawn (the upstream design): use the parts' extent
        for f in pcb.find_all('footprint'):
            at = f.find('at'); xs.append(at[1]); ys.append(at[2])
    ox = (min(xs), max(xs), -max(ys), -min(ys))     # 3D coords: y negated
    ok = True
    for f in pcb.find_all('footprint'):
        lib = str(f[1]).split(':')[-1]
        spec = EDGE_SPEC.get(lib)
        if not spec or spec['mate'] != 'edge': continue
        ref = next(str(p[2]) for p in f.find_all('property') if str(p[1]) == 'Reference')
        at = f.find('at')
        rho = at[3] if len(at) > 3 else 0.0
        shapes = placed(lib, at[1], at[2], rho, f.val('layer') == 'B.Cu', thick)
        if not shapes:
            print(f"  {ref:<4}{lib:<26} NO MODEL -- cannot check"); ok = False; continue
        op, (lo, hi) = openness(shapes)
        face = max(op, key=lambda k: op[k][0])
        # outline edge each face lies against, and how far the face is from it
        gap = {'+x': ox[1] - hi[0], '-x': lo[0] - ox[0],
               '+y': ox[3] - hi[1], '-y': lo[1] - ox[2]}
        # the opening must be on the outline (or past it): a USB-C plug's
        # overmold reaches below the board's top face, so board in front of
        # the opening stops the plug before it seats
        g = gap[face]
        good = op[face][0] >= 1.0 and g <= FLUSH
        ok &= good
        print(f"  {ref:<4}{lib:<26} opening {face} ({op[face][0]:.1f}mm2 cavity, "
              f"{op[face][1]:.1f}mm deep), {g:+.2f}mm from the outline  "
              f"{'OK' if good else 'FACES INTO THE BOARD' if g > 3 else 'INSET'}")
        if verbose:
            for k, v in op.items():
                print(f"        {k}: cavity {v[0]:5.1f}mm2, {v[1]:.1f}mm deep, edge gap {gap[k]:+.2f}")
    return ok


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('pcb', nargs='+'); ap.add_argument('-v', '--verbose', action='store_true')
    a = ap.parse_args()
    bad = 0
    for p in a.pcb:
        print(os.path.basename(p))
        bad += not check(p, a.verbose)
    sys.exit(1 if bad else 0)
