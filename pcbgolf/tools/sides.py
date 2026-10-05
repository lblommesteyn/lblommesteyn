"""Assign parts to the front or back by connectivity, not just by area.

make_items sorts the free parts by area and drops each onto whichever side is
lighter. That balances the sides and ignores the netlist completely, so on the
44x46 board 117 nets span both sides -- and every one of them needs at least
one via just to change side. The router then used 414 vias against that floor
of ~109, most of them crossings that a tidier split would also avoid.

This is Fiduccia-Mattheyses: start from the area-balanced split, repeatedly move
the free part whose move cuts the most two-sided nets, lock it, and keep the
best prefix of moves, all under an area-balance limit so both sides still fit.

Power and ground nets are given no weight. They reach every corner of the board
and span both sides whatever happens, so counting them only adds noise.
"""
import os, sys, json
D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, D)

BIG = 12          # nets with more pins than this carry no weight


def nets_of(items, netlist=os.path.join(D, 'netlist.json')):
    idx = {it['ref']: k for k, it in enumerate(items)}
    out = []
    for nm, pins in json.load(open(netlist))['nets'].items():
        ks = sorted({idx[p[0]] for p in pins if p[0] in idx})
        if 2 <= len(ks) and len(pins) <= BIG:
            out.append(ks)
    return out


def cut(side, nets):
    return sum(1 for ks in nets if len({side[k] for k in ks}) > 1)


def bipartition(items, tol=0.06, passes=12, verbose=True):
    """Set items[k]['side'] in place. Returns (cut_before, cut_after)."""
    n = len(items)
    area = [it['w'] * it['h'] for it in items]
    fixed = [bool(it.get('top')) for it in items]
    side = [0 if fixed[k] else int(it.get('side', 0)) for k, it in enumerate(items)]
    nets = nets_of(items)
    on = [[] for _ in range(n)]
    for j, ks in enumerate(nets):
        for k in ks: on[k].append(j)
    total = sum(area)
    lim = tol * total

    def counts(j):
        c = [0, 0]
        for k in nets[j]: c[side[k]] += 1
        return c
    cnt = [counts(j) for j in range(len(nets))]
    sa = [sum(a for a, s in zip(area, side) if s == 0),
          sum(a for a, s in zip(area, side) if s == 1)]

    def gain(k):
        s, g = side[k], 0
        for j in on[k]:
            c = cnt[j]
            if c[s] == 1: g += 1          # k was alone on its side: net becomes one-sided
            if c[1 - s] == 0: g -= 1      # net was one-sided: moving k splits it
        return g

    before = cut(side, nets)
    best_cut = before
    for p in range(passes):
        locked = [fixed[k] for k in range(n)]
        moves, cur, best_i, best_c = [], best_cut, -1, best_cut
        while True:
            cand = None
            for k in range(n):
                if locked[k]: continue
                s = side[k]
                na = [sa[0], sa[1]]; na[s] -= area[k]; na[1 - s] += area[k]
                if abs(na[0] - na[1]) > lim and abs(na[0] - na[1]) >= abs(sa[0] - sa[1]):
                    continue
                g = gain(k)
                if cand is None or g > cand[0]: cand = (g, k)
            if cand is None: break
            g, k = cand
            s = side[k]
            for j in on[k]:
                cnt[j][s] -= 1; cnt[j][1 - s] += 1
            sa[s] -= area[k]; sa[1 - s] += area[k]
            side[k] = 1 - s; locked[k] = True
            cur -= g; moves.append(k)
            if cur < best_c and abs(sa[0] - sa[1]) <= lim:
                best_c, best_i = cur, len(moves) - 1
        # roll back everything after the best prefix
        for k in reversed(moves[best_i + 1:]):
            s = side[k]
            for j in on[k]:
                cnt[j][s] -= 1; cnt[j][1 - s] += 1
            sa[s] -= area[k]; sa[1 - s] += area[k]
            side[k] = 1 - s
        if verbose:
            print(f"  pass {p+1}: two-sided nets {best_cut} -> {best_c}  "
                  f"(front {sa[0]:.0f} / back {sa[1]:.0f} mm^2)")
        if best_c >= best_cut: break
        best_cut = best_c
    for k, it in enumerate(items):
        it['side'] = side[k]
    return before, best_cut


if __name__ == '__main__':
    from fdplace import make_items
    import build_board as B
    acc = B.pick({'LQFP-144_20x20mm_P0.5mm': 'LQFP-100_14x14',
                  'SOIC-8_3.9x4.9mm_P1.27mm': 'SOT23-5',
                  '0402-R': '0201-R', '0402-C': '0201-C', '0805-C': '0603-C'})
    items, _ = make_items(acc, tall=1.60)
    b, a = bipartition(items)
    print(f"two-sided signal nets: {b} -> {a}")
