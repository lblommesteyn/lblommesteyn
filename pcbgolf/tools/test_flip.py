"""Check orient_footprint() against ground truth captured from pcbnew itself.

The expected values below were produced by KiCad 7's own FOOTPRINT::Flip() and
SetOrientationDegrees() on a deliberately asymmetric test footprint
(pad "1" at (-3,-1) angle 0; pad "3" at (3,2) angle 90).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sexpr import parse, dumps, Node, Q
from mkboard import orient_footprint

SRC = '''(footprint "t:A"
  (layer "F.Cu")
  (at 100 100)
  (fp_line (start -3 -2) (end 3 -2) (layer "F.SilkS"))
  (pad "1" smd rect (at -3 -1) (size 1 0.6) (layers "F.Cu" "F.Paste" "F.Mask"))
  (pad "3" smd rect (at 3 2 90) (size 1 0.6) (layers "F.Cu" "F.Paste" "F.Mask"))
)'''

# (rho, back) -> {pad: (x, y, angle_or_None)}   as pcbnew wrote them
EXPECT = {
    (0,   False): {'1': (-3, -1, None), '3': (3,  2, 90)},
    (90,  False): {'1': (-3, -1, 90),   '3': (3,  2, 180)},
    (270, False): {'1': (-3, -1, 270),  '3': (3,  2, None)},
    (0,   True):  {'1': (-3,  1, None), '3': (3, -2, 270)},
    (90,  True):  {'1': (-3,  1, 90),   '3': (3, -2, None)},
    (180, True):  {'1': (-3,  1, 180),  '3': (3, -2, 90)},
    (270, True):  {'1': (-3,  1, 270),  '3': (3, -2, 180)},
}

def run():
    fails = 0
    for (rho, back), exp in sorted(EXPECT.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        fp = parse(SRC)
        orient_footprint(fp, rho, back)
        got = {}
        for pad in fp.find_all('pad'):
            at = pad.find('at')
            got[str(pad[1])] = (at[1], at[2], at[3] if len(at) > 3 else None)
        side = 'back ' if back else 'front'
        ok = all(abs(got[k][0]-v[0]) < 1e-6 and abs(got[k][1]-v[1]) < 1e-6
                 and ((got[k][2] is None and v[2] is None) or
                      (got[k][2] is not None and v[2] is not None and abs(got[k][2]-v[2]) < 1e-6))
                 for k, v in exp.items())
        # layers must follow the side
        lay = [str(l[1]) for l in fp.descend('layer')]
        layok = all((l.startswith('B.') if back else l.startswith('F.'))
                    for l in lay if l[:2] in ('F.', 'B.'))
        print(f"  {side} rot {rho:>3}: {'ok  ' if ok and layok else 'FAIL'}  "
              + '  '.join(f"{k}={got[k]}" for k in sorted(got)))
        if not (ok and layok):
            fails += 1
            print(f"        expected {exp}")

    # orient_footprint places a part on a given side; it does not toggle.  The
    # meaningful invariants are that the Y mirror is self-inverse, and that a
    # front placement at rotation 0 leaves the source untouched.
    def pads(node):
        return {str(p[1]): (p.find('at')[1], p.find('at')[2]) for p in node.find_all('pad')}
    a = parse(SRC); orient_footprint(a, 0, True); orient_footprint(a, 0, True)
    mirror_ok = pads(a) == pads(parse(SRC))
    print(f"  Y mirror is self-inverse: {'ok' if mirror_ok else 'FAIL'}")
    if not mirror_ok: fails += 1

    c = parse(SRC); orient_footprint(c, 0, False)
    noop_ok = dumps(c) == dumps(parse(SRC))
    print(f"  front @ rot 0 is a no-op: {'ok' if noop_ok else 'FAIL'}")
    if not noop_ok: fails += 1
    return fails

if __name__ == '__main__':
    print("orient_footprint() vs pcbnew ground truth:")
    f = run()
    print("ALL PASS" if f == 0 else f"{f} FAILURES")
    sys.exit(1 if f else 0)
