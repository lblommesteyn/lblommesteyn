"""Regenerate the deliverables in submission/ and build the distributable zip.

Everything under submission/ is generated from the placement + netlist, so it is
reproducible and diffable; the .zip itself is a build artifact and is gitignored.

    python3 tools/make_package.py [--zip OUT.zip]
"""
import json, csv, os, sys, argparse, zipfile
D = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(D)
sys.path.insert(0, D)
from parts import SWAPS
from collections import defaultdict

SUB = os.path.join(ROOT, 'submission')

# the swaps that define the recommended design
CHOSEN = {'LQFP-144_20x20mm_P0.5mm': 'LQFP-100_14x14',
          'SOIC-8_3.9x4.9mm_P1.27mm': 'SC70-5',
          '0402-R': '0201-R', '0402-C': '0201-C', '0805-C': '0603-C',
          'USB-C-FEMALE-VERT-GCT': 'USB-C-MIDMOUNT', '2X04': '2X04-RA',
          'DCJACK_2MM_SMT': 'DCJACK-MIDMOUNT'}

VARIANTS = [
    ('RECOMMENDED 2L double-sided, 300 vias', 1680, 7.0, 300, 2, 0),
    ('2L double-sided, 400 vias',             1680, 7.0, 400, 2, 0),
    ('2L double-sided, 500 vias',             1680, 7.0, 500, 2, 0),
    ('4L double-sided, 300 vias',             1680, 7.0, 300, 4, 0),
    ('fallback 2L single-sided solid GND',    3132, 7.0,  90, 2, 300),
]
JUMPER_AREA = 1.15 * 0.65
LEADER = 84578

def swapinfo():
    out = {}
    for fp, to in CHOSEN.items():
        for c in SWAPS.get(fp, []):
            if c['to'] == to: out[fp] = c
    return out

def build():
    os.makedirs(SUB, exist_ok=True)
    P = json.load(open(os.path.join(D, 'place_opt.json')))
    NL = json.load(open(os.path.join(D, 'netlist.json')))
    comps, si = NL['comps'], swapinfo()

    rows = defaultdict(list)
    for p in P['parts']:
        c = comps.get(p['ref'], {})
        s = si.get(p['src'])
        rows[(p['src'], c.get('value', ''), c.get('mpn', ''),
              s['to'] if s else p['src'], s['part'] if s else '(unchanged)',
              s['risk'] if s else '-', s['note'] if s else '')].append(p['ref'])
    with open(f'{SUB}/BOM.csv', 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['qty','refs','value','orig_footprint','orig_mpn',
                    'new_footprint','new_part','risk','rationale'])
        for k, refs in sorted(rows.items(), key=lambda kv: (-len(kv[1]), kv[0][0])):
            src, val, mpn, tofp, topart, risk, note = k
            w.writerow([len(refs), ' '.join(sorted(refs)), val, src, mpn,
                        tofp, topart, risk, note])

    with open(f'{SUB}/placement.csv', 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['ref','footprint','x_mm','y_mm','rotation_deg','side','height_mm'])
        for p in sorted(P['parts'], key=lambda p: p['ref']):
            w.writerow([p['ref'], p['fp'], f"{p['x']:.3f}", f"{p['y']:.3f}",
                        p['rot'], 'bottom' if p['side'] else 'top', f"{p['z']:.2f}"])

    with open(f'{SUB}/netlist.csv', 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['net','pin_count','pins'])
        for n, pins in sorted(NL['nets'].items(), key=lambda kv: -len(kv[1])):
            if len(pins) < 2: continue
            w.writerow([n, len(pins), ' '.join(f"{r}.{p}" for r, p, _, _ in pins)])

    with open(f'{SUB}/SCORE.csv', 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['variant','board_mm','area_mm2','Z_mm','volume_mm3','vias',
                    'via_pts','layers','layer_pts','SCORE','vs_84578'])
        for name, a, z, v, l, j in VARIANTS:
            area = a + j*JUMPER_AREA
            s = area*z + 50*v + 5000*l
            w.writerow([name, '40 x 42' if a == 1680 else '58 x 54', f"{area:.0f}", z,
                        f"{area*z:.0f}", v, 50*v, l, 5000*l, f"{s:.0f}", f"{s-LEADER:.0f}"])
    return P

TOOLS = ['sexpr.py','pcb.py','fplib.py','netlist.py','geom2.py','parts.py','gridpack.py',
         'fdplace.py','scorecard.py','render.py','step_bbox.py','dsn.py','ses.py',
         'run_grid.py','make_package.py','place_opt.json']

def make_zip(out):
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for f in ('README.md','BOM.csv','placement.csv','netlist.csv','SCORE.csv'):
            p = os.path.join(SUB, f)
            if os.path.exists(p): z.write(p, f)
        z.write(os.path.join(ROOT, 'FINDINGS.md'), 'FINDINGS.md')
        z.write(os.path.join(ROOT, 'placement_opt.svg'), 'placement.svg')
        for t in TOOLS:
            p = os.path.join(D, t)
            if os.path.exists(p): z.write(p, f'tools/{t}')
    return out

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--zip', default=os.path.join(ROOT, 'pcbgolf-best-design.zip'))
    a = ap.parse_args()
    P = build()
    print(f"submission/ regenerated from {P['W']}x{P['H']}mm placement ({len(P['parts'])} parts)")
    if os.path.exists(os.path.join(SUB, 'README.md')):
        print("packaged ->", make_zip(a.zip))
    else:
        print(f"note: write {SUB}/README.md first, then re-run to build the zip")
