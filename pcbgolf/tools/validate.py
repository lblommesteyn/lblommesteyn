"""Structural validation of a generated .kicad_pcb."""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sexpr import load, dumps, Node

def rot(x, y, deg):
    a = math.radians(deg); c, s = math.cos(a), math.sin(a)
    return (x*c + y*s, -x*s + y*c)

def check(path):
    pcb = load(path)
    errs, warns = [], []
    # round-trip
    txt = open(path).read()
    if dumps(pcb) + '\n' != txt:
        from sexpr import _TOKEN
        if _TOKEN.findall(dumps(pcb)+'\n') != _TOKEN.findall(txt):
            errs.append("file does not round-trip through the parser")

    nets = {int(n[1]): str(n[2]) for n in pcb.find_all('net')}
    fps = pcb.find_all('footprint')
    cu = [str(l[1]) for l in pcb.find('layers')[1:] if len(l) > 2 and l[2] == 'signal']

    # outline
    xs, ys = [], []
    for g in pcb.find_all('gr_line'):
        if g.val('layer') != 'Edge.Cuts': continue
        for k in ('start','end'):
            q = g.find(k); xs.append(q[1]); ys.append(q[2])
    if not xs: errs.append("no Edge.Cuts outline")
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)

    front = back = 0
    pad_out = 0
    bad_net = 0
    stray = 0
    pads_total = 0
    for f in fps:
        ref = next((str(p[2]) for p in f.find_all('property') if p[1]=='Reference'), '?')
        lay = f.val('layer')
        isback = (lay == 'B.Cu')
        back += isback; front += not isback
        at = f.find('at'); fx, fy = at[1], at[2]
        ang = at[3] if len(at) > 3 else 0
        # stray layers on the wrong side
        for sub in f.descend('layer'):
            v = str(sub[1]) if len(sub) > 1 else ''
            if isback and v.startswith('F.'): stray += 1
            if not isback and v.startswith('B.'): stray += 1
        for pad in f.find_all('pad'):
            pads_total += 1
            nn = pad.find('net')
            if nn is not None:
                i = int(nn[1])
                if i not in nets or nets[i] != str(nn[2]): bad_net += 1
            pat = pad.find('at'); sz = pad.find('size')
            if not pat or not sz: continue
            gx, gy = rot(pat[1], pat[2], ang)
            gx += fx; gy += fy
            hw, hh = sz[1]/2, sz[2]/2
            r = max(hw, hh)
            if gx - r < x0 - 0.01 or gx + r > x1 + 0.01 or gy - r < y0 - 0.01 or gy + r > y1 + 0.01:
                pad_out += 1
    print(f"  file            : {os.path.basename(path)}")
    print(f"  round-trip      : {'OK' if not errs else 'FAIL'}")
    print(f"  copper layers   : {len(cu)} {cu}")
    print(f"  outline         : {x1-x0:.1f} x {y1-y0:.1f} mm")
    print(f"  footprints      : {len(fps)}  (front {front}, back {back})")
    print(f"  pads            : {pads_total}")
    print(f"  nets declared   : {len(nets)}")
    print(f"  pads outside    : {pad_out}")
    print(f"  bad net refs    : {bad_net}")
    print(f"  wrong-side layer: {stray}")
    for e in errs: print("  ERROR:", e)
    ok = not errs and pad_out == 0 and bad_net == 0 and stray == 0
    print(f"  => {'PASS' if ok else 'PROBLEMS'}")
    return ok

if __name__ == '__main__':
    for p in sys.argv[1:]:
        check(p); print()
