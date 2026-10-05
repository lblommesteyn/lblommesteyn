"""Clear a corridor around every unrouted connection, for the router to retry.

Freerouting converges with a handful of connections it cannot fit: the space
they need is taken by nets routed earlier.  Resuming does not help, because the
blockers are still there.  This removes OTHER nets' traces and vias inside a
corridor around each gap -- the straight line between the two closest pads of
the islands that need joining -- and leaves everything else in place.  On the
next resumed run the stranded connections are routed into cleared space and the
displaced nets re-route around them.

    python3 ripup.py BOARD -o OUT [--radius 1.5]

Pads are never touched; only routing.  Prints how many connections each
corridor serves and how much copper was removed.
"""
import os, sys, math, argparse
D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, D)
from sexpr import load, dumps, Node
import ratsnest
from drc import _seg_seg_dist


def gaps(pcb):
    """[(net, p, q)]: one segment per missing connection, between the closest
    pads of two disjoint islands of that net."""
    nets, pads, segs, vias = ratsnest.items_of(pcb)
    cl = ratsnest.clusters(nets=nets, pads=pads, segs=segs, vias=vias)
    out = []
    for net, groups in cl.items():
        if len(groups) < 2: continue
        # join islands greedily, nearest first, like a spanning tree
        joined = [groups[0]]
        rest = list(groups[1:])
        while rest:
            best = None
            for gi, g in enumerate(rest):
                for a in (p for j in joined for p in j):
                    for b in g:
                        d = math.hypot(a['x']-b['x'], a['y']-b['y'])
                        if best is None or d < best[0]:
                            best = (d, gi, (a['x'], a['y']), (b['x'], b['y']))
            _, gi, p, q = best
            out.append((nets.get(net, str(net)), net, p, q))
            joined.append(rest.pop(gi))
    return out


def ripup(path, out, radius=1.5, verbose=True, mode='ends'):
    """mode='ends' clears a disc around each END of every gap; 'line' clears a
    corridor along the whole straight line between them.

    'line' was the first version and is far too destructive: several gaps are
    20-34mm long, so a corridor slices the board in half and rips hundreds of
    segments the router cannot put back -- 29 open connections became ~120.
    What actually blocks a stranded connection is congestion where it has to
    escape its pads, so clearing around the ends frees the bottleneck while
    leaving the rest of the board's routing alone.
    """
    pcb = load(path)
    G = gaps(pcb)
    if mode == 'line':
        corridors = [(num, p, q) for _, num, p, q in G]
    else:
        corridors = [(num, e, e) for _, num, p, q in G for e in (p, q)]

    def hit(net, p, q):
        for gnet, a, b in corridors:
            if net == gnet: continue
            if _seg_seg_dist(p, q, a, b) < radius:
                return True
        return False

    keep, nseg, nvia = [], 0, 0
    for c in pcb:
        if isinstance(c, Node) and c.tag in ('segment', 'via'):
            nn = c.find('net')
            net = int(nn[1]) if nn is not None else -1
            if c.tag == 'segment':
                a, b = c.find('start'), c.find('end')
                if hit(net, (a[1], a[2]), (b[1], b[2])):
                    nseg += 1; continue
            else:
                at = c.find('at')
                if hit(net, (at[1], at[2]), (at[1], at[2])):
                    nvia += 1; continue
        keep.append(c)
    del pcb[:]
    pcb.extend(keep)
    open(out, 'w').write(dumps(pcb) + '\n')
    if verbose:
        print(f"  {len(G)} unrouted connection(s); corridor radius {radius} mm")
        for name, _, p, q in G:
            print(f"     {name:<16} {math.hypot(p[0]-q[0], p[1]-q[1]):5.1f} mm gap")
        print(f"  removed {nseg} segments and {nvia} vias of other nets")
    return len(G), nseg, nvia


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('pcb'); ap.add_argument('-o', '--out', required=True)
    ap.add_argument('--radius', type=float, default=1.5)
    ap.add_argument('--mode', choices=('ends', 'line'), default='ends')
    a = ap.parse_args()
    ripup(a.pcb, a.out, a.radius, mode=a.mode)
