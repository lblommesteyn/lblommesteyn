"""True PCBA bounding box from the 3D assembly.

The challenge scores "PCBA bounding box volume", and asks for a STEP file of
the assembly -- so the box must contain every component body, not just the
board outline extruded by the tallest part.  A component body can overhang
the copper outline (the DC jack's shell is 12.6 mm wide against a 9.4 mm pad
span), and such overhang counts.

Component bodies come from each footprint's own 3D model, placed with KiCad's
transform convention, which was derived empirically from `kicad-cli pcb
export step` over seven placement cases (front/back x rotated/not x offset)
and reproduces them to within the exporter's own mesh tolerance:

    R_model = Rz(-rz) . Ry(-ry) . Rx(-rx)                    # (rotate xyz)
    front:  p = Rz(rho) . (R_model.p_local + off) + (x, -y, T)
    back:   p = Rz(rho) . (diag(1,-1,-1).R_model.p_local
                           + (ox, -oy, -oz))                 + (x, -y, 0)

with T the board thickness, (x, y, rho) the footprint placement, and the PCB
Y axis negated because KiCad's 3D space is right-handed.

Footprints with no resolvable model fall back to a box from parts.GEOM.
"""
import os, sys, math, argparse

D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, D)
from sexpr import load, parse
from parts import GEOM, LEAD_TAIL

PRETTY = ['/home/user/commaai/pcbgolf/pcbgolf.pretty',
          os.path.join(os.path.dirname(D), 'pcbgolf-gen.pretty')]
PRJ = '/home/user/commaai/pcbgolf'

_OCC = True
try:
    from OCP.STEPControl import STEPControl_Reader
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.gp import gp_Trsf
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
except ImportError:                                    # pragma: no cover
    _OCC = False


# ---------------------------------------------------------------- matrices
def _mul(A, B):
    return [[sum(A[i][k] * B[k][j] for k in range(3)) for j in range(3)]
            for i in range(3)]

def _rx(d):
    a = math.radians(d)
    return [[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]]

def _ry(d):
    a = math.radians(d)
    return [[math.cos(a), 0, math.sin(a)], [0, 1, 0], [-math.sin(a), 0, math.cos(a)]]

def _rz(d):
    a = math.radians(d)
    return [[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]]

def _apply(M, v):
    return [sum(M[i][k] * v[k] for k in range(3)) for i in range(3)]


# ---------------------------------------------------------------- models
_shape_cache = {}
_fp_cache = {}

def _find_fp(lib):
    if lib in _fp_cache: return _fp_cache[lib]
    for d in PRETTY:
        p = os.path.join(d, lib + '.kicad_mod')
        if os.path.exists(p):
            _fp_cache[lib] = p; return p
    _fp_cache[lib] = None
    return None

def _models(lib):
    """[(step_path, offset, rotate)] declared by this footprint"""
    p = _find_fp(lib)
    if not p: return []
    out = []
    def walk(n):
        if not isinstance(n, list): return
        if n and n[0] == 'model':
            off = rot = (0., 0., 0.)
            for sub in n[2:]:
                if isinstance(sub, list) and sub and sub[0] in ('offset', 'rotate'):
                    for s2 in sub[1:]:
                        if isinstance(s2, list) and s2 and s2[0] == 'xyz':
                            v = tuple(float(t) for t in s2[1:4])
                            if sub[0] == 'offset': off = v
                            else: rot = v
            out.append((str(n[1]).replace('${KIPRJMOD}', PRJ), off, rot))
        for s in n: walk(s)
    walk(parse(open(p).read()))
    return out

def _shape(path):
    if path in _shape_cache: return _shape_cache[path]
    sh = None
    if _OCC and os.path.exists(path):
        r = STEPControl_Reader()
        if r.ReadFile(path) == IFSelect_RetDone:
            r.TransferRoots()
            sh = r.OneShape()
            BRepMesh_IncrementalMesh(sh, 0.01, False, 0.1, True)
    _shape_cache[path] = sh
    return sh


# ---------------------------------------------------------------- placement
def _place(lib, x, y, rho, back, thick):
    """Return (xmin,xmax,ymin,ymax,zmin,zmax) in 3D board coords, or None."""
    boxes = []
    for path, off, rot in _models(lib):
        sh = _shape(path)
        if sh is None: continue
        Rm = _mul(_rz(-rot[2]), _mul(_ry(-rot[1]), _rx(-rot[0])))
        A = _rz(rho)
        if back:
            M = _mul(A, _mul([[1, 0, 0], [0, -1, 0], [0, 0, -1]], Rm))
            t = _apply(A, [off[0], -off[1], -off[2]])
            t = [t[0] + x, t[1] - y, t[2]]
        else:
            M = _mul(A, Rm)
            t = _apply(A, list(off))
            t = [t[0] + x, t[1] - y, t[2] + thick]
        tr = gp_Trsf()
        tr.SetValues(M[0][0], M[0][1], M[0][2], t[0],
                     M[1][0], M[1][1], M[1][2], t[1],
                     M[2][0], M[2][1], M[2][2], t[2])
        moved = BRepBuilderAPI_Transform(sh, tr, True).Shape()
        b = Bnd_Box(); b.SetGap(0.0); BRepBndLib.Add_s(moved, b, True)
        lo, hi = b.CornerMin(), b.CornerMax()
        boxes.append((lo.X(), hi.X(), lo.Y(), hi.Y(), lo.Z(), hi.Z()))
    if not boxes: return None
    return (min(b[0] for b in boxes), max(b[1] for b in boxes),
            min(b[2] for b in boxes), max(b[3] for b in boxes),
            min(b[4] for b in boxes), max(b[5] for b in boxes))

def _fallback(lib, x, y, rho, back, thick):
    """Box from parts.GEOM for footprints with no 3D model."""
    g = GEOM.get(lib)
    w, h, z = (g[0], g[1], g[2]) if g else (2.0, 2.0, 1.0)
    c, s = abs(math.cos(math.radians(rho))), abs(math.sin(math.radians(rho)))
    ew, eh = w * c + h * s, w * s + h * c
    zlo, zhi = (-z, 0.0) if back else (thick, thick + z)
    # a lead tail longer than the board exits the far side
    out = max(0.0, LEAD_TAIL.get(lib, 0.0) - thick)
    if out:
        if back: zhi = thick + out
        else:    zlo = -out
    return (x - ew / 2, x + ew / 2, -y - eh / 2, -y + eh / 2, zlo, zhi)


# ---------------------------------------------------------------- board
def bbox(path, thick=1.6, verbose=False):
    pcb = load(path)
    xs, ys = [], []
    for g in pcb.find_all('gr_line'):
        if g.val('layer') != 'Edge.Cuts': continue
        for k in ('start', 'end'):
            q = g.find(k); xs.append(q[1]); ys.append(q[2])
    bx = (min(xs), max(xs), -max(ys), -min(ys), 0.0, thick)
    lim = list(bx)
    worst = []
    nofp = []
    for f in pcb.find_all('footprint'):
        lib = str(f[1]).split(':')[-1]
        at = f.find('at')
        x, y = at[1], at[2]
        rho = at[3] if len(at) > 3 else 0.0
        back = f.val('layer') == 'B.Cu'
        b = _place(lib, x, y, rho, back, thick)
        if b is None:
            b = _fallback(lib, x, y, rho, back, thick)
            nofp.append(lib)
        ref = ''
        for p in f.find_all('property'):
            if str(p[1]) == 'Reference': ref = str(p[2])
        over = max(bx[0] - b[0], b[1] - bx[1], bx[2] - b[2], b[3] - bx[3])
        if over > 0.01:
            worst.append((round(over, 2), ref, lib))
        lim = [min(lim[0], b[0]), max(lim[1], b[1]),
               min(lim[2], b[2]), max(lim[3], b[3]),
               min(lim[4], b[4]), max(lim[5], b[5])]
    W, H, Z = lim[1] - lim[0], lim[3] - lim[2], lim[5] - lim[4]
    res = dict(W=round(W, 3), H=round(H, 3), Z=round(Z, 3),
               volume=round(W * H * Z, 1),
               outline_W=round(bx[1] - bx[0], 3), outline_H=round(bx[3] - bx[2], 3),
               overhang_x=round(max(bx[0] - lim[0], lim[1] - bx[1]), 3),
               overhang_y=round(max(bx[2] - lim[2], lim[3] - bx[3]), 3),
               z_top=round(lim[5] - thick, 3), z_bot=round(-lim[4], 3),
               no_model=sorted(set(nofp)))
    if verbose:
        res['overhanging'] = sorted(worst, reverse=True)[:12]
    return res


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('pcb', nargs='+')
    ap.add_argument('--thickness', type=float, default=1.6)
    ap.add_argument('-v', '--verbose', action='store_true')
    a = ap.parse_args()
    if not _OCC:
        sys.exit('OpenCascade (cadquery-ocp) is required: pip install cadquery-ocp')
    for p in a.pcb:
        print(os.path.basename(p))
        for k, v in bbox(p, a.thickness, a.verbose).items():
            print(f"    {k:<12} {v}")
        print()
