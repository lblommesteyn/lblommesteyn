"""Export a STEP file of the real PCBA assembly.

The challenge asks for "a STEP file of the final assembly", and scores the
PCBA bounding box -- so the file has to carry the actual component bodies, not
stand-in boxes.  This builds the board slab from the Edge.Cuts outline and
adds every footprint's own 3D model, placed with the KiCad transform
convention derived in bbox3d.py.  Footprints whose model is missing (the
generated 0201/SC70/LQFP-100 land patterns) fall back to a box from
parts.GEOM so they still occupy their real volume.

Writing the STEP and measuring the bounding box therefore use one code path,
so the submitted file and the reported score cannot disagree.
"""
import os, sys, math, argparse

D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, D)
from sexpr import load
from parts import GEOM, LEAD_TAIL
import bbox3d

from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakePrism
from OCP.BRepBuilderAPI import (BRepBuilderAPI_Transform, BRepBuilderAPI_MakeWire,
                                BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace)
from OCP.gp import gp_Trsf, gp_Pnt, gp_Vec
from OCP.TopoDS import TopoDS_Compound
from OCP.BRep import BRep_Builder
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.STEPControl import STEPControl_Writer, STEPControl_StepModelType
from OCP.Interface import Interface_Static
from OCP.IFSelect import IFSelect_RetDone


def _outline_slab(pcb, thick):
    """Board solid: the Edge.Cuts polygon extruded through the stackup."""
    pts = []
    for g in pcb.find_all('gr_line'):
        if g.val('layer') != 'Edge.Cuts': continue
        a, b = g.find('start'), g.find('end')
        pts.append(((a[1], a[2]), (b[1], b[2])))
    if not pts:
        raise SystemExit('no Edge.Cuts outline')
    # chain the segments into a loop; fall back to the bounding rectangle
    try:
        loop = [pts[0][0], pts[0][1]]
        rest = pts[1:]
        while rest:
            for i, (a, b) in enumerate(rest):
                if abs(a[0]-loop[-1][0]) < 1e-6 and abs(a[1]-loop[-1][1]) < 1e-6:
                    loop.append(b); rest.pop(i); break
                if abs(b[0]-loop[-1][0]) < 1e-6 and abs(b[1]-loop[-1][1]) < 1e-6:
                    loop.append(a); rest.pop(i); break
            else:
                raise ValueError('outline not a single loop')
        if abs(loop[0][0]-loop[-1][0]) < 1e-6 and abs(loop[0][1]-loop[-1][1]) < 1e-6:
            loop.pop()
        w = BRepBuilderAPI_MakeWire()
        for i in range(len(loop)):
            x0, y0 = loop[i]; x1, y1 = loop[(i+1) % len(loop)]
            w.Add(BRepBuilderAPI_MakeEdge(gp_Pnt(x0, -y0, 0.0), gp_Pnt(x1, -y1, 0.0)).Edge())
        face = BRepBuilderAPI_MakeFace(w.Wire()).Face()
        return BRepPrimAPI_MakePrism(face, gp_Vec(0, 0, thick)).Shape()
    except Exception:
        xs = [c[0] for s in pts for c in s]; ys = [c[1] for s in pts for c in s]
        return BRepPrimAPI_MakeBox(gp_Pnt(min(xs), -max(ys), 0.0),
                                   max(xs)-min(xs), max(ys)-min(ys), thick).Shape()


def _placed_models(lib, x, y, rho, back, thick):
    """Transformed OCC shapes for this footprint's 3D models."""
    out = []
    for path, off, rot in bbox3d._models(lib):
        sh = bbox3d._shape(path)
        if sh is None: continue
        Rm = bbox3d._mul(bbox3d._rz(-rot[2]),
                         bbox3d._mul(bbox3d._ry(-rot[1]), bbox3d._rx(-rot[0])))
        A = bbox3d._rz(rho)
        if back:
            M = bbox3d._mul(A, bbox3d._mul([[1, 0, 0], [0, -1, 0], [0, 0, -1]], Rm))
            t = bbox3d._apply(A, [off[0], -off[1], -off[2]])
            t = [t[0] + x, t[1] - y, t[2]]
        else:
            M = bbox3d._mul(A, Rm)
            t = bbox3d._apply(A, list(off))
            t = [t[0] + x, t[1] - y, t[2] + thick]
        tr = gp_Trsf()
        tr.SetValues(M[0][0], M[0][1], M[0][2], t[0],
                     M[1][0], M[1][1], M[1][2], t[1],
                     M[2][0], M[2][1], M[2][2], t[2])
        out.append(BRepBuilderAPI_Transform(sh, tr, True).Shape())
    return out


def _fallback_box(lib, x, y, rho, back, thick):
    g = GEOM.get(lib)
    w, h, z = (g[0], g[1], g[2]) if g else (2.0, 2.0, 1.0)
    if z <= 0: return None
    c, s = abs(math.cos(math.radians(rho))), abs(math.sin(math.radians(rho)))
    ew, eh = w*c + h*s, w*s + h*c
    if min(ew, eh, z) < 1e-4: return None
    z0, dz = (-z, z) if back else (thick, z)
    out = max(0.0, LEAD_TAIL.get(lib, 0.0) - thick)   # lead tails exit the far side
    if out:
        if back: dz = z + out
        else:    z0, dz = -out, z + out
    return BRepPrimAPI_MakeBox(gp_Pnt(x - ew/2, -y - eh/2, z0), ew, eh, dz).Shape()


def export(pcb_path, out, thick=None):
    pcb = load(pcb_path)
    if thick is None: thick = bbox3d.board_thickness(pcb)
    builder = BRep_Builder()
    comp = TopoDS_Compound()
    builder.MakeCompound(comp)
    builder.Add(comp, _outline_slab(pcb, thick))

    n_model = n_box = 0
    for f in pcb.find_all('footprint'):
        lib = str(f[1]).split(':')[-1]
        at = f.find('at')
        x, y = at[1], at[2]
        rho = at[3] if len(at) > 3 else 0.0
        back = f.val('layer') == 'B.Cu'
        shapes = _placed_models(lib, x, y, rho, back, thick)
        if shapes:
            n_model += len(shapes)
            for s in shapes: builder.Add(comp, s)
        else:
            b = _fallback_box(lib, x, y, rho, back, thick)
            if b is not None:
                n_box += 1; builder.Add(comp, b)

    Interface_Static.SetCVal_s('write.step.schema', 'AP214')
    w = STEPControl_Writer()
    w.Transfer(comp, STEPControl_StepModelType.STEPControl_AsIs)
    if w.Write(out) != IFSelect_RetDone:
        raise SystemExit('STEP write failed')

    box = Bnd_Box(); box.SetGap(0.0); BRepBndLib.Add_s(comp, box, True)
    lo, hi = box.CornerMin(), box.CornerMax()
    W, H, Z = hi.X()-lo.X(), hi.Y()-lo.Y(), hi.Z()-lo.Z()
    return dict(out=out, models=n_model, boxes=n_box,
                W=round(W, 3), H=round(H, 3), Z=round(Z, 3),
                volume=round(W*H*Z, 1),
                bytes=os.path.getsize(out))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('pcb')
    ap.add_argument('-o', '--out', required=True)
    ap.add_argument('--thickness', type=float, default=None)
    a = ap.parse_args()
    for k, v in export(a.pcb, a.out, a.thickness).items():
        print(f"    {k:<10} {v}")
