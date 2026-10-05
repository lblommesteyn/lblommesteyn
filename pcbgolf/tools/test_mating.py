"""Each edge connector's recorded opening direction agrees with its 3D model.

geom2.EDGE_SPEC 'face' tells the placer which way the plug opening points;
a wrong value seats the connector facing into the board. This measures the
opening from the model itself (mating.openness) and compares.

    python3 test_mating.py
"""
import os, sys, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from geom2 import EDGE_SPEC
from mating import placed, openness

ANGLE = {'+x': 0, '+y': 90, '-x': 180, '-y': 270}

def test_faces():
    checked = 0
    for lib, spec in sorted(EDGE_SPEC.items()):
        if spec['mate'] != 'edge' or 'face' not in spec: continue
        sh = placed(lib, 0.0, 0.0, 0.0, False, 1.6)
        assert sh, f"{lib}: no 3D model to check the opening against"
        op, (lo, hi) = openness(sh)
        face = max(op, key=lambda k: op[k][0])
        others = sorted(v[0] for k, v in op.items() if k != face)
        assert op[face][0] >= 1.0 and others[-1] < 0.2 * op[face][0], \
            f"{lib}: opening not unambiguous: {op}"
        assert ANGLE[face] == spec['face'], \
            f"{lib}: model opens {face} ({ANGLE[face]} deg), EDGE_SPEC says {spec['face']}"
        # and the body face sits where EDGE_SPEC 'body' says
        from geom2 import measured
        _, _, ox, oy = measured(lib)
        d = {0: hi[0] - ox, 180: ox - lo[0], 270: -lo[1] - oy, 90: oy + hi[1]}[spec['face']]
        assert abs(d - spec['body']) < 0.01, f"{lib}: body face {d:.3f} from centre, EDGE_SPEC says {spec['body']}"
        print(f"  {lib:<26} opens {face}  ({op[face][0]:.1f} mm2), face {d:.3f} from centre  ok")
        checked += 1
    assert checked >= 4

if __name__ == '__main__':
    test_faces(); print('ok')
