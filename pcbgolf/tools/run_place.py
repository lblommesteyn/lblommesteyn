import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from place import build_parts, load_nets, Floorplan
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

if __name__ == '__main__':
    iters = int(sys.argv[1]) if len(sys.argv) > 1 else 120000
    seeds = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    parts = build_parts(OPT)
    nets = load_nets(parts)
    ZMAX = 7.0   # mm: barrel-jack-limited envelope, incl. 1.6mm board
    print(f"{len(parts)} parts, {len(nets)} routable nets, Z={ZMAX}mm")
    best = None
    for s in range(seeds):
        t0 = time.time()
        fp = Floorplan(parts, nets, ZMAX, seed=s, lam=0.03)
        c = fp.anneal(iters, report=iters//4 if s == 0 else None)
        _, W, H = fp.cost()
        ov = fp.overlap_area()
        print(f"  seed {s}: cost={c:10.0f}  {W:6.2f} x {H:6.2f} mm  area={W*H:7.0f}  "
              f"overlap={ov:7.2f} mm2  hpwl={fp.hpwl():8.0f}  ({time.time()-t0:.0f}s)")
        if best is None or c < best[0]: best = (c, fp, W, H)
    c, fp, W, H = best
    out = dict(W=W, H=H, Z=ZMAX, area=W*H, vol=W*H*ZMAX, hpwl=fp.hpwl(),
               overlap=fp.overlap_area(),
               parts=[dict(ref=p.ref, fp=p.fp, x=float(fp.x[k]), y=float(fp.y[k]),
                           rot=int(fp.rot[k]), side=int(fp.side[k]), w=p.w, h=p.h, z=p.z)
                      for k, p in enumerate(parts)])
    json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'placement.json'),'w'))
    print(f"\nBEST: {W:.2f} x {H:.2f} mm, area {W*H:.0f} mm2, volume {W*H*ZMAX:.0f} mm3")
