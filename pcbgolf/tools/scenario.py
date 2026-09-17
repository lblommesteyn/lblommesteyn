"""Score model: evaluate BOM/architecture scenarios analytically."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pcb import load_board
from parts import GEOM, SWAPS
from collections import Counter

def inventory():
    b = load_board()
    c = Counter(f.lib.split(':')[-1] for f in b['fps'])
    return c

def area_of(counts, subs):
    """subs: fp -> swap dict (or None to keep). Returns (area, maxZ, extra_vias, rows)."""
    tot = 0.0; zmax = 0.0; dv = 0; rows = []
    for fp, n in counts.items():
        g = GEOM[fp]
        s = subs.get(fp)
        if s: W,H,Z = s['W'], s['H'], s['Z']
        else: W,H,Z = g[0], g[1], g[2]
        a = W*H*n
        tot += a; zmax = max(zmax, Z); dv += s['d_vias'] if s else 0
        rows.append((fp, n, W, H, Z, a, s['to'] if s else '-'))
    return tot, zmax, dv, rows

def score(area_parts, zmax, vias, layers, pack=1.35, board_thick=1.6,
          bottom_z=0.0, dual_side=False, min_area=0.0):
    """pack: area overhead for routing channels/keepouts. Returns dict."""
    usable = area_parts / (2.0 if dual_side else 1.0)
    board_area = max(usable * pack, min_area)
    Z = zmax + board_thick + bottom_z
    vol = board_area * Z
    return dict(board_area=board_area, side=board_area**0.5, Z=Z, vol=vol,
                vias=vias, layers=layers,
                score=vol + 50*vias + 5000*layers)

def show(name, r, extra=''):
    print(f"{name:<44} {r['side']:>6.1f}mm sq {r['board_area']:>7.0f}mm2 "
          f"Z={r['Z']:>5.2f}  vol={r['vol']:>8.0f}  via={r['vias']:>4}x50={50*r['vias']:>6} "
          f"L={r['layers']}={5000*r['layers']:>6}  SCORE={r['score']:>8.0f}  {extra}")

if __name__ == '__main__':
    counts = inventory()
    print("=== Scenario sweep (pack=1.35 routing overhead) ===\n")
    base_area, base_z, _, rows = area_of(counts, {})
    print(f"Stock BOM: parts area {base_area:.0f} mm2, tallest part {base_z:.2f} mm\n")
    print("Top area consumers (stock):")
    for fp,n,W,H,Z,a,_ in sorted(rows, key=lambda r:-r[5])[:10]:
        print(f"   {fp:<28} n={n:<4} {W:5.2f}x{H:<5.2f} z={Z:<5.2f} area={a:7.1f}")
    print()

    def pick(mapping):
        subs = {}
        for fp, to in mapping.items():
            for s in SWAPS.get(fp, []):
                if s['to'] == to: subs[fp] = s
        return subs

    scenarios = [
        ("A. stock BOM, 1-sided, 4 layer, 500 vias", {}, False, 4, 500),
        ("B. stock BOM, 1-sided, 2 layer, 700 vias", {}, False, 2, 700),
        ("C. +LQFP100 +SOT23 opamp", dict({'LQFP-144_20x20mm_P0.5mm':'LQFP-100_14x14',
             'SOIC-8_3.9x4.9mm_P1.27mm':'SOT23-5'}), False, 4, 450),
        ("D. C +0201 passives", dict({'LQFP-144_20x20mm_P0.5mm':'LQFP-100_14x14',
             'SOIC-8_3.9x4.9mm_P1.27mm':'SOT23-5','0402-R':'0201-R','0402-C':'0201-C',
             '0805-C':'0603-C'}), False, 4, 450),
        ("E. D + horiz USB-C + RA header + LP jack", dict({'LQFP-144_20x20mm_P0.5mm':'LQFP-100_14x14',
             'SOIC-8_3.9x4.9mm_P1.27mm':'SOT23-5','0402-R':'0201-R','0402-C':'0201-C','0805-C':'0603-C',
             'USB-C-FEMALE-VERT-GCT':'USB-C-HORIZ-SMT','2X04':'2X04-RA',
             'DCJACK_2MM_SMT':'DCJACK-LOWPROFILE'}), False, 4, 450),
        ("F. E + double-sided assembly", dict({'LQFP-144_20x20mm_P0.5mm':'LQFP-100_14x14',
             'SOIC-8_3.9x4.9mm_P1.27mm':'SOT23-5','0402-R':'0201-R','0402-C':'0201-C','0805-C':'0603-C',
             'USB-C-FEMALE-VERT-GCT':'USB-C-HORIZ-SMT','2X04':'2X04-RA',
             'DCJACK_2MM_SMT':'DCJACK-LOWPROFILE'}), True, 4, 500),
        ("G. F + midmount jack/USB-C (Z floor)", dict({'LQFP-144_20x20mm_P0.5mm':'LQFP-100_14x14',
             'SOIC-8_3.9x4.9mm_P1.27mm':'SOT23-5','0402-R':'0201-R','0402-C':'0201-C','0805-C':'0603-C',
             'USB-C-FEMALE-VERT-GCT':'USB-C-MIDMOUNT','2X04':'2X04-RA',
             'DCJACK_2MM_SMT':'DCJACK-MIDMOUNT'}), True, 4, 500),
        ("H. G but VFQFN68 MCU", dict({'LQFP-144_20x20mm_P0.5mm':'VFQFN-68_8x8',
             'SOIC-8_3.9x4.9mm_P1.27mm':'SOT23-5','0402-R':'0201-R','0402-C':'0201-C','0805-C':'0603-C',
             'USB-C-FEMALE-VERT-GCT':'USB-C-MIDMOUNT','2X04':'2X04-RA',
             'DCJACK_2MM_SMT':'DCJACK-MIDMOUNT'}), True, 4, 500),
        ("I. G but UFBGA169 MCU (+110 vias)", dict({'LQFP-144_20x20mm_P0.5mm':'UFBGA-169_7x7',
             'SOIC-8_3.9x4.9mm_P1.27mm':'SOT23-5','0402-R':'0201-R','0402-C':'0201-C','0805-C':'0603-C',
             'USB-C-FEMALE-VERT-GCT':'USB-C-MIDMOUNT','2X04':'2X04-RA',
             'DCJACK_2MM_SMT':'DCJACK-MIDMOUNT'}), True, 4, 500),
        ("J. H on 2 layers, 750 vias", dict({'LQFP-144_20x20mm_P0.5mm':'VFQFN-68_8x8',
             'SOIC-8_3.9x4.9mm_P1.27mm':'SOT23-5','0402-R':'0201-R','0402-C':'0201-C','0805-C':'0603-C',
             'USB-C-FEMALE-VERT-GCT':'USB-C-MIDMOUNT','2X04':'2X04-RA',
             'DCJACK_2MM_SMT':'DCJACK-MIDMOUNT'}), True, 2, 750),
        ("K. H on 6 layers, 350 vias", dict({'LQFP-144_20x20mm_P0.5mm':'VFQFN-68_8x8',
             'SOIC-8_3.9x4.9mm_P1.27mm':'SOT23-5','0402-R':'0201-R','0402-C':'0201-C','0805-C':'0603-C',
             'USB-C-FEMALE-VERT-GCT':'USB-C-MIDMOUNT','2X04':'2X04-RA',
             'DCJACK_2MM_SMT':'DCJACK-MIDMOUNT'}), True, 6, 350),
    ]
    print(f"{'SCENARIO':<44} {'side':>8} {'area':>10} {'Z':>8}  {'volume':>12} {'vias':>12} {'layers':>10}   {'SCORE':>8}")
    print('-'*130)
    for name, mapping, dual, L, vias in scenarios:
        subs = pick(mapping)
        a, z, dv, _ = area_of(counts, subs)
        bottom = 1.4 if 'midmount' in name.lower() or 'MIDMOUNT' in str(mapping.values()) else 0.0
        r = score(a, z, vias + dv, L, dual_side=dual, bottom_z=bottom)
        show(name, r)
