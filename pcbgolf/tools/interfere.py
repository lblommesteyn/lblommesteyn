"""3D interference between component bodies, from their own STEP models.

collide.py checks pads, and the placer reserves each part's footprint
envelope, but neither sees the bodies themselves: a barrel jack's shell that
overhangs its pads, or a through-hole pin tail that comes out of the far side
of a thin board into a part mounted there. This places every model exactly as
bbox3d does and reports every pair of parts whose solids touch or come
closer than `gap`.

    python3 interfere.py BOARD.kicad_pcb [--gap 0.0]
"""
import os, sys, argparse
D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, D)
import bbox3d
from sexpr import load
from mating import placed

from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.gp import gp_Pnt


def bodies(path):
    pcb = load(path)
    thick = bbox3d.board_thickness(pcb)
    out = []
    for f in pcb.find_all('footprint'):
        lib = str(f[1]).split(':')[-1]
        ref = next((str(p[2]) for p in f.find_all('property') if str(p[1]) == 'Reference'), '?')
        at = f.find('at')
        rho = at[3] if len(at) > 3 else 0.0
        back = f.val('layer') == 'B.Cu'
        sh = placed(lib, at[1], at[2], rho, back, thick)
        if not sh:
            # no model: the same box bbox3d scores the part with
            b = bbox3d._fallback(lib, at[1], at[2], rho, back, thick)
            if min(b[1] - b[0], b[3] - b[2], b[5] - b[4]) <= 1e-6:
                continue                     # nothing physical (a net tie)
            sh = [BRepPrimAPI_MakeBox(gp_Pnt(b[0], b[2], b[4]), gp_Pnt(b[1], b[3], b[5])).Shape()]
        bs = []
        for s in sh:
            b = Bnd_Box(); b.SetGap(0.0); BRepBndLib.Add_s(s, b, True); bs.append(b)
        lo = [min(b.CornerMin().Coord(i) for b in bs) for i in (1, 2, 3)]
        hi = [max(b.CornerMax().Coord(i) for b in bs) for i in (1, 2, 3)]
        out.append((ref, lib, sh, lo, hi))
    return out, thick


def check(path, gap=0.0, verbose=True):
    parts, thick = bodies(path)
    bad = []
    for i in range(len(parts)):
        ra, la, sa, loa, hia = parts[i]
        for j in range(i + 1, len(parts)):
            rb, lb, sb, lob, hib = parts[j]
            if any(loa[k] > hib[k] + gap or lob[k] > hia[k] + gap for k in range(3)):
                continue
            d = None
            for x in sa:
                for y in sb:
                    m = BRepExtrema_DistShapeShape(x, y)
                    if m.IsDone():
                        d = m.Value() if d is None else min(d, m.Value())
            if d is not None and d <= gap + 1e-6:
                bad.append((ra, la, rb, lb, d))
    if verbose:
        print(f"  {os.path.basename(path)}: {len(parts)} bodies, board {thick}mm, "
              f"{len(bad)} touching pair(s)")
        for ra, la, rb, lb, d in bad:
            print(f"    {ra:<5}{la:<26} x {rb:<5}{lb:<26} {d:.3f}mm")
    return bad


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('pcb', nargs='+'); ap.add_argument('--gap', type=float, default=0.0)
    a = ap.parse_args()
    n = 0
    for p in a.pcb:
        n += len(check(p, a.gap))
    sys.exit(1 if n else 0)
