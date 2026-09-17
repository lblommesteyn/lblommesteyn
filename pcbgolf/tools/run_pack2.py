import sys, os, json, math, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pack2 import Packer, CLR
from fdplace import make_items, net_index
from parts import SWAPS

def pick(mapping):
    subs = {}
    for fp, to in mapping.items():
        for s in SWAPS.get(fp, []):
            if s['to'] == to: subs[fp] = s
    return subs

OPT = pick({'LQFP-144_20x20mm_P0.5mm':'LQFP-100_14x14',
            'SOIC-8_3.9x4.9mm_P1.27mm':'SOT23-5',
            '0402-R':'0201-R','0402-C':'0201-C','0805-C':'0603-C',
            'USB-C-FEMALE-VERT-GCT':'USB-C-MIDMOUNT','2X04':'2X04-RA',
            'DCJACK_2MM_SMT':'DCJACK-MIDMOUNT'})

def run(label, swaps, z, widths, iters, lam, out=None):
    items, areas = make_items(swaps)
    nets = net_index(items)
    print(f"\n=== {label} ===  top {areas[0]:.0f} mm2 / bottom {areas[1]:.0f} mm2, "
          f"{len(items)} parts, {len(nets)} nets, Z={z}mm")
    best = None
    for W in widths:
        p = Packer(items, nets, W, z, seed=1, lam=lam)
        c = p.anneal(iters)
        _, Wb, Hb = p.cost()
        vol = Wb*Hb*z
        print(f"  strip {W:>5.1f} -> {Wb:6.2f} x {Hb:6.2f} mm  area {Wb*Hb:7.0f} mm2  "
              f"vol {vol:8.0f}  hpwl {p.hpwl():7.0f}  cost {c:9.0f}")
        if best is None or c < best[0]: best = (c, p, Wb, Hb, items, nets)
    c, p, W, H, items, nets = best
    print(f"  BEST {W:.2f} x {H:.2f} mm, area {W*H:.0f} mm2, volume {W*H*z:.0f} mm3")
    if out:
        json.dump(dict(W=W, H=H, Z=z, area=W*H, vol=W*H*z, hpwl=p.hpwl(),
                       parts=[dict(ref=items[k]['ref'], fp=items[k]['fp'], src=items[k]['src'],
                                   x=p.pos[k][0], y=p.pos[k][1], side=p.pos[k][2],
                                   rot=90*(p.rot[k]%2), w=items[k]['w'], h=items[k]['h'],
                                   z=items[k]['z'], edge=items[k]['edge'])
                              for k in range(len(items)) if k in p.pos]),
                  open(out, 'w'))
        print(f"  -> {out}")
    return best

if __name__ == '__main__':
    D = os.path.dirname(os.path.abspath(__file__))
    run('STOCK BOM (Z=10.6mm, vertical USB-C + std jack)', {}, 10.6,
        [30, 34, 38, 42], 2500, 1.2, os.path.join(D, 'place_stock.json'))
    run('OPTIMISED BOM (Z=7.0mm, midmount jack)', OPT, 7.0,
        [26, 30, 34, 38], 2500, 1.2, os.path.join(D, 'place_opt.json'))
