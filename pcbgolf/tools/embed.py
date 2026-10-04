"""Spectral layout of the netlist: a 2D target position for every part.

Parts that share nets are pulled together, which is what makes a board
routable.  Packing by descending size (bottom-left fill) produces a dense but
essentially random placement; packing each part near its spectral target keeps
connected parts adjacent.
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np

def net_graph(items, netlist_path, max_pins=8):
    """Weighted adjacency over parts. Big nets (power/ground) carry no locality
    information and are skipped."""
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
                A[refs[i], refs[j]] += w
                A[refs[j], refs[i]] += w
    return A

def spectral(items, netlist_path, W, H, max_pins=8):
    """Returns an (n,2) array of target positions inside a W x H board."""
    A = net_graph(items, netlist_path, max_pins)
    n = A.shape[0]
    deg = A.sum(1)
    L = np.diag(deg) - A
    # normalised Laplacian keeps high-degree parts from dominating
    dm = np.where(deg > 0, 1/np.sqrt(np.maximum(deg, 1e-9)), 0.0)
    Ln = (L * dm).T * dm
    vals, vecs = np.linalg.eigh(Ln)
    order = np.argsort(vals)
    picks = [i for i in order if vals[i] > 1e-8][:2]
    while len(picks) < 2: picks.append(order[len(picks)])
    xy = vecs[:, picks] * dm[:, None]
    # isolated parts (no small-net connections) get placed centrally
    for k in range(n):
        if deg[k] <= 0: xy[k] = 0.0
    # The raw eigenvectors bunch most parts into a small region, which starves
    # the nearest-free search.  Rank-transform each axis so the targets spread
    # over the whole board while keeping their relative order (and so locality).
    for c in range(2):
        v = xy[:, c]
        r = np.argsort(np.argsort(v)).astype(float)
        xy[:, c] = r / max(n - 1, 1)
    xy[:, 0] *= W; xy[:, 1] *= H
    return xy

if __name__ == '__main__':
    from fdplace import make_items, net_index
    items, _ = make_items({}, tall=1.8)
    xy = spectral(items, os.path.join(os.path.dirname(os.path.abspath(__file__)),'netlist.json'), 48, 50)
    # report cluster quality: mean net span under the target layout
    nets = net_index(items)
    tot = 0.0
    for refs in nets:
        tot += np.ptp(xy[refs,0]) + np.ptp(xy[refs,1])
    print(f"target-layout HPWL: {tot:.0f} mm over {len(nets)} nets "
          f"(mean span {tot/len(nets):.1f} mm)")
    for ref in ('U3','U4','J5','J6','J7','J8','U13','U5'):
        k = next((i for i,it in enumerate(items) if it['ref']==ref), None)
        if k is not None: print(f"   {ref:<5} target ({xy[k,0]:5.1f}, {xy[k,1]:5.1f})")


def refine(items, nets, pos, netlist_path, W, H, max_pins=8):
    """New targets = centroid of each part's neighbours' actual positions.
    Iterating place->refine is a cheap analytical placer and cuts wirelength
    well below what a single spectral pass gives."""
    import json
    idx = {it['ref']: k for k, it in enumerate(items)}
    n = len(items)
    acc = np.zeros((n, 2)); wt = np.zeros(n)
    d = json.load(open(netlist_path))
    for name, pins in d['nets'].items():
        refs = sorted({idx[r] for (r, p, nm, et) in pins if r in idx})
        if not (2 <= len(refs) <= max_pins): continue
        pts = np.array([[pos[k][0], pos[k][1]] for k in refs if k in pos])
        if len(pts) < 2: continue
        c = pts.mean(0); w = 1.0/(len(refs)-1)
        for k in refs:
            if k in pos: acc[k] += c*w; wt[k] += w
    out = {}
    for k in range(n):
        if wt[k] > 0: out[k] = (float(np.clip(acc[k,0]/wt[k],0,W)),
                                float(np.clip(acc[k,1]/wt[k],0,H)))
        elif k in pos: out[k] = (pos[k][0], pos[k][1])
    return out
