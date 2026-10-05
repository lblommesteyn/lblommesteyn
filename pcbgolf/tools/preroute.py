"""Route the hard local connections first, on the empty board, and lock them.

Across four independent routes the connections the autorouter strands are
mostly bridges WITHIN one connector: a USB-C receptacle carries D+ on A6 and
B6, D- on A7 and B7, VBUS on four pins, for reversibility, and the board must
tie each set together across the connector between fine-pitch pads. The
autorouter gets to them when the area is already full and cannot fit them.

Done first, on a board with only pads on it, they are short and easy. This
routes every same-net pad group on the chosen connectors with finish_router's
A* (DRC-safe trace and via grids), then marks the copper locked so pcb2dsn
hands it to Freerouting as protected wiring that it routes around rather than
rips up.

    python3 preroute.py BOARD -o OUT [--refs J3,J5,J6,J7,J8]
"""
import os, sys, argparse
D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, D)
from sexpr import load, dumps, Node, Q
import ratsnest
import finish_router as F

SKIP_NETS = {'GND'}     # ground is a plane-scale net; its connector pins are
                        # tied by the shield pads and everything nearby


def merge_collinear(segs, eps=1e-6):
    """Join A*'s one-grid-step segments into straight runs.

    The maze router emits one segment per 0.127mm cell, so 16 bridges came out
    as 845 segments, which the autorouter then has to carry as 845 protected
    obstacles. Consecutive same-net, same-layer steps in the same direction are
    one segment."""
    out = []
    for s in segs:
        if out:
            t = out[-1]
            if (t['net'] == s['net'] and t['layer'] == s['layer']
                    and abs(t['q'][0]-s['p'][0]) < eps and abs(t['q'][1]-s['p'][1]) < eps):
                d1 = (t['q'][0]-t['p'][0], t['q'][1]-t['p'][1])
                d2 = (s['q'][0]-s['p'][0], s['q'][1]-s['p'][1])
                if abs(d1[0]*d2[1] - d1[1]*d2[0]) < eps and d1[0]*d2[0] + d1[1]*d2[1] > 0:
                    out[-1] = dict(t, q=s['q']); continue
        out.append(dict(s))
    return out


def preroute(path, out, refs, track=0.09, clear=0.09, via_dia=0.45,
             via_cost=10000, verbose=True):
    pcb, (bx0, by0, bx1, by1) = F.build(path)
    layers = [str(l[1]) for l in pcb.find('layers')[1:] if len(l) > 2 and l[2] == 'signal']
    nets, pads, segs, vias = ratsnest.items_of(pcb)
    li = {l: i for i, l in enumerate(layers)}
    pad_clear = clear + track / 2
    via_clear = clear + via_dia / 2

    # connector-local groups: same net, same ref, more than one pad
    groups = {}
    for p in pads:
        if p['ref'] in refs and nets.get(p['net']) not in SKIP_NETS:
            groups.setdefault((p['ref'], p['net']), []).append(p)
    jobs = [(k, v) for k, v in sorted(groups.items()) if len(v) >= 2]

    added_segs, added_vias = [], []
    uid, done, failed = 700000, 0, []
    for (ref, nnum), gp in jobs:
        name = nets.get(nnum, str(nnum))
        # pads that already share copper (stacked top/bottom lands) are one cluster
        cl = ratsnest.clusters(nets=nets, pads=gp,
                               segs=[s for s in added_segs if s['net'] == nnum],
                               vias=[v for v in added_vias if v['net'] == nnum])
        clusters = cl.get(nnum, [])
        while len(clusters) >= 2:
            g = F.Grid(bx0, by0, bx1, by1, layers)
            for p in pads:
                if p['net'] == nnum: continue
                l = None if p['layer'] is None else li.get(p['layer'])
                g.mark_rect(l, *p['rect'], pad_clear, via_clear)
            for s in added_segs:
                if s['net'] == nnum: continue
                g.mark_seg(li.get(s['layer']), s['p'], s['q'], track, pad_clear, via_clear)
            for v in added_vias:
                if v['net'] == nnum: continue
                r = v['size'] / 2
                g.mark_rect(None, v['p'][0]-r, v['p'][1]-r, v['p'][0]+r, v['p'][1]+r,
                            pad_clear, via_clear)
            for p in gp:
                l = None if p['layer'] is None else li.get(p['layer'])
                g.clear_rect(l, *p['rect'])
            before = (len(added_segs), len(added_vias))
            ok = F.connect_one(g, li, layers, nnum, name, pads, segs, vias,
                               added_segs, added_vias, uid, {nnum: clusters},
                               via_cost, via_dia)
            if not ok or (len(added_segs), len(added_vias)) == before:
                failed.append(f'{ref}:{name}'); break
            done += 1; uid += 1000
            cl = ratsnest.clusters(nets=nets, pads=gp,
                                   segs=[s for s in added_segs if s['net'] == nnum],
                                   vias=[v for v in added_vias if v['net'] == nnum])
            clusters = cl.get(nnum, [])

    added_segs = merge_collinear(added_segs)
    for s in added_segs:
        pcb.append(F.n('segment', F.n('start', round(s['p'][0], 4), round(s['p'][1], 4)),
                       F.n('end', round(s['q'][0], 4), round(s['q'][1], 4)),
                       F.n('width', track), F.n('layer', Q(s['layer'])),
                       F.n('locked', 'yes'), F.n('net', s['net']),
                       F.n('uuid', Q(F.uuid_for(uid))))); uid += 1
    for v in added_vias:
        pcb.append(F.n('via', F.n('at', round(v['p'][0], 4), round(v['p'][1], 4)),
                       F.n('size', via_dia), F.n('drill', round(via_dia / 2.25, 3)),
                       F.n('layers', Q(layers[0]), Q(layers[-1])),
                       F.n('locked', 'yes'), F.n('net', v['net']),
                       F.n('uuid', Q(F.uuid_for(uid))))); uid += 1
    open(out, 'w').write(dumps(pcb) + '\n')
    if verbose:
        print(f"  {len(jobs)} connector groups; {done} connections pre-routed, "
              f"{len(added_vias)} vias")
        if failed: print(f"  could not pre-route: {', '.join(failed)}")
    return done, len(added_vias), failed


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('pcb'); ap.add_argument('-o', '--out', required=True)
    ap.add_argument('--refs', default='J3,J5,J6,J7,J8')
    a = ap.parse_args()
    preroute(a.pcb, a.out, set(a.refs.split(',')))
