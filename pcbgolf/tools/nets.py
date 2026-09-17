import sys; sys.path.insert(0,'/home/user/lblommesteyn/pcbgolf/tools')
from sexpr import load
from collections import defaultdict, Counter

pcb = load('/home/user/commaai/pcbgolf/pcbgolf.kicad_pcb')
net_pads = defaultdict(list)     # net -> [(ref, padname)]
comp_used = {}                   # ref -> (used_pads, total_pads)
for f in pcb.find_all('footprint'):
    ref = ''
    for p in f.find_all('property'):
        if p[1] == 'Reference': ref = str(p[2])
    used = 0; tot = 0
    for pad in f.find_all('pad'):
        ptype = pad[2] if len(pad) > 2 else ''
        if ptype == 'np_thru_hole':      # pure mechanical hole
            continue
        tot += 1
        n = pad.find('net')
        if n and len(n) > 2 and str(n[2]) not in ('', 'unconnected'):
            used += 1
            net_pads[str(n[2])].append((ref, str(pad[1])))
    comp_used[ref] = (used, tot)

print("=== MCU / big parts: used vs total pins ===")
for ref in ('U3','U4','J3','J2','J5','J6','J7','J8','J4','J1'):
    if ref in comp_used:
        u,t = comp_used[ref]
        print(f"  {ref:<5} {u:>4} used / {t:>4} pads   ({100*u/max(t,1):.0f}%)")

sizes = Counter({n: len(v) for n,v in net_pads.items()})
print(f"\n=== nets: {len(net_pads)} total, {sum(sizes.values())} connected pads ===")
print("Top 15 nets by pad count:")
for n,c in sizes.most_common(15):
    print(f"  {c:>4}  {n}")
two = sum(1 for c in sizes.values() if c==2)
print(f"\n2-pad nets: {two}   3+ pad nets: {sum(1 for c in sizes.values() if c>2)}")
gndish = [n for n in net_pads if n.upper() in ('GND','AGND','DGND','PGND') or n.upper().startswith('GND')]
pwr = [n for n in net_pads if any(k in n.upper() for k in ('VCC','VDD','3V3','5V','12V','+3','+5','VBUS','VIN'))]
gp = sum(len(net_pads[n]) for n in gndish)
pp = sum(len(net_pads[n]) for n in pwr)
print(f"GND-ish nets {len(gndish)} -> {gp} pads")
print(f"Power nets  {len(pwr)} -> {pp} pads")
print(f"Signal pads (non gnd/pwr): {sum(sizes.values()) - gp - pp}")
