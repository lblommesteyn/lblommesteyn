import sys; sys.path.insert(0,'/home/user/lblommesteyn/pcbgolf/tools')
from pcb import load_board
from collections import defaultdict
b = load_board()
rows = []
for f in b['fps']:
    cw = ch = 0.0
    if f.crtyd: cw, ch = f.crtyd[2]-f.crtyd[0], f.crtyd[3]-f.crtyd[1]
    pw = ph = 0.0
    if f.padbb: pw, ph = f.padbb[2]-f.padbb[0], f.padbb[3]-f.padbb[1]
    rows.append((f.lib.split(':')[-1], f.ref, cw*ch, cw, ch, pw*ph, f.npads))
g = defaultdict(lambda: [0,0.0,0.0,0.0,0.0,0])
for lib, ref, ca, cw, ch, pa, np_ in rows:
    e = g[lib]; e[0]+=1; e[1]+=ca; e[2]=max(e[2],cw); e[3]=max(e[3],ch); e[4]+=pa; e[5]+=np_
tot_c = sum(e[1] for e in g.values()); tot_p = sum(e[4] for e in g.values())
print(f"{'FOOTPRINT':<28}{'QTY':>4}{'W':>7}{'H':>7}{'CRTYD ea':>10}{'CRTYD tot':>11}{'PAD tot':>9}{'pads':>6}")
print('-'*94)
for k,e in sorted(g.items(), key=lambda kv:-kv[1][1]):
    print(f"{k:<28}{e[0]:>4}{e[2]:>7.2f}{e[3]:>7.2f}{e[1]/e[0]:>10.2f}{e[1]:>11.1f}{e[4]:>9.1f}{e[5]:>6}")
print('-'*94)
print(f"{'TOTAL':<28}{len(b['fps']):>4}{'':>14}{'':>10}{tot_c:>11.1f}{tot_p:>9.1f}{sum(f.npads for f in b['fps']):>6}")
print()
print(f"Sum of courtyard areas : {tot_c:8.1f} mm^2   -> square side {tot_c**.5:.1f} mm")
print(f"Sum of pad-bbox areas  : {tot_p:8.1f} mm^2   -> square side {tot_p**.5:.1f} mm")
for pf in (1.0, 1.25, 1.5, 1.8):
    a = tot_c*pf
    print(f"  at {pf:.2f}x packing overhead: {a:7.1f} mm^2  ({a**.5:.1f} mm square)")
