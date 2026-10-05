"""Analytical placement: quadratic wirelength minimisation with iterative
spreading (SimPL/RePlAce style).

The greedy packer sorts by size and fills bottom-left, which is dense but
random for routing (measured HPWL 6940mm against a 977mm spectral target).
This solves for the true minimum-squared-wirelength positions, legalises them
onto the grid, then re-solves with each part anchored to where it legalised -
anchor weight rising each round - so the result is both spread and short.
"""
import sys, os, json, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import gridpack as G

def clique_laplacian(items, netlist_path, max_pins=8):
    idx = {it['ref']: k for k, it in enumerate(items)}
    n = len(items)
    A = np.zeros((n, n))
    d = json.load(open(netlist_path))
    for name, pins in d['nets'].items():
        refs = sorted({idx[r] for (r, p, nm, et) in pins if r in idx})
        if not (2 <= len(refs) <= max_pins): continue
        w = 1.0 / (len(refs) - 1)
        for i in range(len(refs)):
            for j in range(i+1, len(refs)):
                A[refs[i], refs[j]] += w; A[refs[j], refs[i]] += w
    return np.diag(A.sum(1)) - A, A

def solve_positions(L, anchor_xy, anchor_w, W, H):
    """(L + diag(w)) p = w * anchor, solved per axis."""
    n = L.shape[0]
    M = L + np.diag(anchor_w)
    out = np.zeros((n, 2))
    for c, lim in ((0, W), (1, H)):
        b = anchor_w * anchor_xy[:, c]
        try:
            out[:, c] = np.linalg.solve(M, b)
        except np.linalg.LinAlgError:
            out[:, c] = np.linalg.lstsq(M, b, rcond=None)[0]
        out[:, c] = np.clip(out[:, c], 0, lim)
    return out

def place(items, nets, netlist_path, W, H, rounds=8, seed=7, verbose=True,
          anchor_w0=0.5, edges=None):
    n = len(items)
    L, A = clique_laplacian(items, netlist_path)
    econ = [k for k, it in enumerate(items) if it['edge']]
    core = [k for k, it in enumerate(items) if not it['edge']]
    order = sorted(core, key=lambda k: -max(items[k]['w'], items[k]['h']))
    rot = {k: 0 for k in range(n)}
    side = {k: items[k]['side'] for k in range(n)}
    slot = {k: i for i, k in enumerate(econ)}
    eo = {k: i % 4 for i, k in enumerate(econ)} if edges is None else dict(edges)

    # Seeding from the centre collapses the solve (the only anchor is the same
    # point for every part) and legalisation then fails, because placing large
    # parts in the middle fragments the board.  Seed from the spectral layout,
    # which is already spread, and let the quadratic solve shorten it.
    from embed import spectral
    anchor = spectral(items, netlist_path, W, H).astype(float)
    aw = np.full(n, float(anchor_w0))
    best = None
    for r in range(rounds):
        cont = solve_positions(L, anchor, aw, W, H)
        targets = {k: (float(cont[k, 0]), float(cont[k, 1])) for k in range(n)}
        pos = G.pack(items, W, H, order, rot, side, slot, eo, targets)
        if pos is None:
            if verbose: print(f"    round {r}: legalisation failed")
            break
        hp = G.hpwl(pos, nets)
        if verbose: print(f"    round {r}: HPWL {hp:7.0f} mm   (anchor w {aw[0]:.3f})")
        if best is None or hp < best[0]:
            best = (hp, dict(pos), dict(targets))
        for k in range(n):
            if k in pos: anchor[k] = (pos[k][0], pos[k][1])
        aw = aw * 1.6 + 0.05          # tighten the pull to the legal positions
    return best

def place_any_edges(items, nets, netlist_path, W, H, verbose=False, **kw):
    """place() over every assignment of edge connectors to board edges; the
    best HPWL wins. Which edge each connector seats on decides whether the rest
    packs at all: with one fixed assignment, legalisation failed at every
    outline and the build fell back to the bottom-left packer."""
    import itertools
    econ = [k for k, it in enumerate(items) if it['edge']]
    best = None
    for combo in itertools.product(range(4), repeat=len(econ)):
        b = place(items, nets, netlist_path, W, H, verbose=False,
                  edges=dict(zip(econ, combo)), **kw)
        if verbose:
            print(f"    edges {combo}: {'failed' if b is None else f'HPWL {b[0]:.0f}'}")
        if b and (best is None or b[0] < best[0]):
            best = b
    return best


if __name__ == '__main__':
    from fdplace import make_items, net_index
    from embed import spectral
    D = os.path.dirname(os.path.abspath(__file__))
    NL = os.path.join(D, 'netlist.json')
    items, _ = make_items({}, tall=1.8)
    nets = net_index(items)
    W, H = 48, 50
    print("baseline (size-descending bottom-left):")
    econ = [k for k, it in enumerate(items) if it['edge']]
    core = [k for k, it in enumerate(items) if not it['edge']]
    pos0 = G.pack(items, W, H,
                  sorted(core, key=lambda k: -max(items[k]['w'], items[k]['h'])),
                  {k: 0 for k in range(len(items))},
                  {k: items[k]['side'] for k in range(len(items))},
                  {k: i for i, k in enumerate(econ)},
                  {k: i % 4 for i, k in enumerate(econ)})
    print(f"    HPWL {G.hpwl(pos0, nets):7.0f} mm")
    xy = spectral(items, NL, W, H)
    pos1 = G.pack(items, W, H,
                  sorted(core, key=lambda k: -max(items[k]['w'], items[k]['h'])),
                  {k: 0 for k in range(len(items))},
                  {k: items[k]['side'] for k in range(len(items))},
                  {k: i for i, k in enumerate(econ)},
                  {k: i % 4 for i, k in enumerate(econ)},
                  {k: (xy[k,0], xy[k,1]) for k in range(len(items))})
    print(f"spectral target:\n    HPWL {G.hpwl(pos1, nets):7.0f} mm")
    print("analytical:")
    best = None
    for w0 in (0.2, 0.5, 1.5):
        print(f'  anchor_w0={w0}')
        b = place(items, nets, NL, W, H, rounds=6, anchor_w0=w0)
        if b and (best is None or b[0] < best[0]): best = b
    
    if best: print(f"BEST analytical HPWL {best[0]:.0f} mm")
    else: print('analytical placement failed')
