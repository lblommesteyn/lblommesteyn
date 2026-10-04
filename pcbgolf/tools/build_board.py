"""End-to-end: pack -> write .kicad_pcb -> legalise -> validate.

Legalisation runs on the built board using the same pad geometry the collision
checker uses, so the placement is guaranteed physically legal regardless of any
subtlety in the packer's envelope model.
"""
import sys, os, json, io, contextlib, argparse
D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, D)
import gridpack as G
import aplace
from fdplace import make_items, net_index
from parts import SWAPS
import mkboard, collide, validate, legalize
from sexpr import dumps

def pick(m):
    s = {}
    for fp, to in m.items():
        for c in SWAPS.get(fp, []):
            if c['to'] == to: s[fp] = c
    return s

OPT = pick({'LQFP-144_20x20mm_P0.5mm':'LQFP-100_14x14','SOIC-8_3.9x4.9mm_P1.27mm':'SC70-5',
            '0402-R':'0201-R','0402-C':'0201-C','0805-C':'0603-C',
            'USB-C-FEMALE-VERT-GCT':'USB-C-MIDMOUNT','2X04':'2X04-RA',
            'DCJACK_2MM_SMT':'DCJACK-MIDMOUNT'})

def quiet(fn, *a, **k):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf): r = fn(*a, **k)
    return r, buf.getvalue()

def build(swaps, z, cands, layers, out_pcb, out_place, iters=200, seed=7, clearance=0.10, tall=2.5, analytical=True):
    items, areas = make_items(swaps, tall=tall)
    nets = net_index(items)
    print(f"parts {len(items)}, nets {len(nets)}, Z={z}, layers={layers}")
    results = []
    for (W, H) in cands:
        pos = None
        if analytical:
            b = aplace.place(items, nets, os.path.join(D,'netlist.json'), W, H,
                             rounds=5, verbose=False, anchor_w0=1.0)
            if b: pos = b[1]
        if pos is None:
            c, pos, st = G.solve(items, nets, W, H, z, iters=iters, seed=seed)
        if pos is None:
            print(f"  slot {W}x{H}: pack infeasible"); continue
        parts = [dict(ref=items[k]['ref'], fp=items[k]['fp'], src=items[k]['src'],
                      x=pos[k][0], y=pos[k][1], side=pos[k][2], rot=pos[k][3],
                      w=items[k]['w'], h=items[k]['h'], z=items[k]['z'],
                      ox=items[k]['ox'], oy=items[k]['oy'], edge=items[k]['edge'],
                      thru=items[k]['thru']) for k in sorted(pos)]
        tmp_p = out_place + '.tmp'
        json.dump(dict(W=W, H=H, Z=z, area=W*H, vol=W*H*z, parts=parts), open(tmp_p,'w'))
        pcb, info = mkboard.build(tmp_p, os.path.join(D,'netlist.json'), layers)
        raw = out_pcb + '.raw'
        open(raw,'w').write(dumps(pcb)+'\n')
        (moved, _) = quiet(legalize.legalize, raw, out_pcb, clearance)
        (res, _) = quiet(collide.check, out_pcb, clearance, 0)
        nov, ntight = res
        # the outline may need to grow after legalisation
        pcb2, info2 = mkboard.build(tmp_p, os.path.join(D,'netlist.json'), layers)
        print(f"  slot {W}x{H} -> {info['W']}x{info['H']} mm, area {info['area']:7.1f}, "
              f"moved {moved:>2}, overlaps {nov}, tight {ntight}")
        results.append((nov, info['area'], W, H, parts, info, out_pcb))
        os.remove(tmp_p); os.remove(raw)
        if nov == 0:
            json.dump(dict(W=W, H=H, Z=z, area=W*H, vol=W*H*z, parts=parts), open(out_place,'w'))
            return info, out_pcb
    clean = [r for r in results if r[0] == 0]
    if clean:
        clean.sort(key=lambda r: r[1])
        nov, area, W, H, parts, info, p = clean[0]
        json.dump(dict(W=W,H=H,Z=z,area=W*H,vol=W*H*z,parts=parts), open(out_place,'w'))
        return info, p
    return None, None

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--bom', choices=['stock','opt'], default='stock')
    ap.add_argument('--layers', type=int, default=2)
    ap.add_argument('-o','--out', required=True)
    a = ap.parse_args()
    if a.bom == 'stock':
        info, p = build({}, 10.6, [(42,46),(44,46),(44,48),(46,48),(48,50)],
                        a.layers, a.out, os.path.join(D,'place_stock.json'))
    else:
        info, p = build(OPT, 7.0, [(38,40),(40,42),(42,44),(44,46)],
                        a.layers, a.out, os.path.join(D,'place_opt.json'))
    if info:
        print(f"\nBOARD: {info['W']} x {info['H']} mm, area {info['area']} mm2 -> {p}")
        validate.check(p)
        collide.check(p, 0.10, 0)
    else:
        print("no legal board produced")
