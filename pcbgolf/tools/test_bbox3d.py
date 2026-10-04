"""Pin the 3D placement convention used by bbox3d / step_assembly.

The seven cases below were produced by `kicad-cli pcb export step` (KiCad
7.0.11) on single-footprint boards -- front and back, rotated and not, with a
rotated model and with a plain XYZ offset -- and the component solid's
bounding box was read back with OpenCascade.  The exporter inflates each box
by its mesh tolerance, so the tolerance here is 0.08 mm rather than exact.

If this fails, bbox3d is placing bodies differently from KiCad and every
reported volume is wrong.
"""
import os, sys
D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, D)
import bbox3d

MODEL = ('/home/user/commaai/pcbgolf/pcbgolf.3dshapes/'
         'Connector_BarrelJack.3dshapes/PJ-002AH-SMT-TR.step')

# (x, y, rho, back, offset, rotate) -> kicad-cli measured (x0,x1,y0,y1,z0,z1)
CASES = [
    ((0,  0,  0,  False, (-5, 0, 6.5), (-90, 0, 90)),
     (-5.017,  9.917,  -6.167,  6.467,   0.833, 12.667)),
    ((10, 7,  0,  False, (-5, 0, 6.5), (-90, 0, 90)),
     ( 4.983, 19.917, -13.167, -0.533,   0.833, 12.667)),
    ((0,  0,  30, False, (-5, 0, 6.5), (-90, 0, 90)),
     (-6.506, 10.841,  -6.323,  8.905,   0.833, 12.667)),
    ((0,  0,  0,  True,  (-5, 0, 6.5), (-90, 0, 90)),
     (-5.017,  9.917,  -6.467,  6.167, -11.067,  0.767)),
    ((0,  0,  0,  False, (1, 2, 3),    (0, 0, 0)),
     (-5.467,  7.167,  -5.317,  6.517, -10.267,  4.667)),
    ((0,  0,  0,  True,  (1, 2, 3),    (0, 0, 0)),
     (-5.467,  7.167,  -6.517,  5.317,  -3.067, 11.867)),
    ((0,  0,  30, True,  (1, 2, 3),    (0, 0, 0)),
     (-6.987,  7.939,  -7.305,  7.489,  -3.067, 11.867)),
]

TOL = 0.08


def _place(x, y, rho, back, off, rot, thick=1.6):
    """bbox3d._place for one explicit model, bypassing footprint lookup."""
    sh = bbox3d._shape(MODEL)
    assert sh is not None, 'cannot load ' + MODEL
    from OCP.gp import gp_Trsf
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
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
    moved = BRepBuilderAPI_Transform(sh, tr, True).Shape()
    b = Bnd_Box(); b.SetGap(0.0); BRepBndLib.Add_s(moved, b, True)
    lo, hi = b.CornerMin(), b.CornerMax()
    return (lo.X(), hi.X(), lo.Y(), hi.Y(), lo.Z(), hi.Z())


def main():
    bad = 0
    for args, want in CASES:
        got = _place(*args)
        err = max(abs(a - b) for a, b in zip(got, want))
        tag = 'ok  ' if err <= TOL else 'FAIL'
        if err > TOL: bad += 1
        print('  at=(%g,%g) rot=%g %s off=%s rot3d=%s: %s max err %.3f'
              % (args[0], args[1], args[2], 'back' if args[3] else 'front',
                 args[4], args[5], tag, err))
    # the part that sets this design's height, stated outright
    jack = _place(0, 0, 0, False, (-5, 0, 6.5), (-90, 0, 90))
    h = jack[5] - 1.6
    print('  DC jack height above board: %.2f mm' % h)
    if not (10.9 < h < 11.2):
        print('  FAIL expected ~11.0'); bad += 1
    print('ALL PASS' if not bad else '%d FAILURES' % bad)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
