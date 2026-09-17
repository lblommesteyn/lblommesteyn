import sys, os, json, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gridpack as G
from fdplace import make_items, net_index
from parts import SWAPS

def pick(m):
    s = {}
    for fp, to in m.items():
        for c in SWAPS.get(fp, []):
            if c['to'] == to: s[fp] = c
    return s

OPT = pick({'LQFP-144_20x20mm_P0.5mm':'LQFP-100_14x14','SOIC-8_3.9x4.9mm_P1.27mm':'SOT23-5',
            '0402-R':'0201-R','0402-C':'0201-C','0805-C':'0603-C',
            'USB-C-FEMALE-VERT-GCT':'USB-C-MIDMOUNT','2X04':'2X04-RA',
            'DCJACK_2MM_SMT':'DCJACK-MIDMOUNT'})

def sweep(label, swaps, z, cand, out, iters=700):
    items, areas = make_items(swaps)
    nets = net_index(items)
    print(f"\n=== {label} === parts {len(items)}, nets {len(nets)}, "
          f"area top {areas[0]:.0f} / bottom {areas[1]:.0f} mm2, Z={z}")
    best = None
    for (W, H) in cand:
        c, pos, st = G.solve(items, nets, W, H, z, iters=iters, seed=1)
        if pos is None:
            print(f"  {W:5.1f} x {H:5.1f}  -> INFEASIBLE (won't fit)")
            continue
        used = max(max(p[1] for p in pos.values()), 0)
        print(f"  {W:5.1f} x {H:5.1f}  area {W*H:7.0f}  vol {W*H*z:8.0f}  "
              f"hpwl {G.hpwl(pos, nets):7.0f}  cost {c:9.0f}")
        if best is None or c < best[0]: best = (c, W, H, pos, items)
    if best:
        c, W, H, pos, items = best
        print(f"  BEST {W:.1f} x {H:.1f} = {W*H:.0f} mm2, volume {W*H*z:.0f} mm3")
        json.dump(dict(W=W, H=H, Z=z, area=W*H, vol=W*H*z,
                       parts=[dict(ref=items[k]['ref'], fp=items[k]['fp'], src=items[k]['src'],
                                   x=pos[k][0], y=pos[k][1], side=pos[k][2], rot=pos[k][3],
                                   w=items[k]['w'], h=items[k]['h'], z=items[k]['z'],
                                   edge=items[k]['edge'])
                              for k in sorted(pos)]), open(out, 'w'))
        print(f"  -> {out}")
    return best

if __name__ == '__main__':
    D = os.path.dirname(os.path.abspath(__file__))
    sweep('STOCK BOM', {}, 10.6,
          [(30,32),(32,32),(32,36),(34,34),(36,34),(38,32),(40,30)], os.path.join(D,'place_stock.json'))
    sweep('OPTIMISED BOM', OPT, 7.0,
          [(32,30),(34,30),(34,32),(34,34),(36,32),(38,30),(40,28)], os.path.join(D,'place_opt.json'))
