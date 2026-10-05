"""Corrected component geometry: measured pad bboxes, origin offsets, and
explicit per-connector edge requirements.

Replaces the hand-entered boxes in parts.py, which the autorouter showed were
wrong for the DC jack (axes swapped) and ignored large footprint-origin offsets
(microSD is 6.9mm off its origin), putting parts off-board.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fplib import load_footprints
from parts import GEOM

# Clearance added around every placement box: 0.15mm design clearance each side
# plus room for one 0.15mm track to pass = 0.5mm total.
CLR = 0.50

# How a connector meets the board edge.
#   mate = 'edge'     mating face must sit on the outline (cable enters sideways)
#   mate = 'vertical' mates from above: needs clear airspace, not board edge
#   edge_w           dimension that runs ALONG the edge (the mating face width)
#   face             for 'edge' parts: the direction the plug opening faces at
#                    rotation 0, in degrees CCW from +x with Y up (the placement
#                    and 3D frame). Measured from each part's own 3D model by
#                    mating.py, which also checks every built board; the placer
#                    rotates the part so this points out of its edge.
#   body             distance (mm) from the footprint envelope's centre to the
#                    model's face on that side. The envelope (courtyard, pads)
#                    reaches past the body, so seating the envelope on the edge
#                    left the opening up to 1.5mm inside the board, where a
#                    USB-C plug's overmold, which reaches below the board's top
#                    face, hits the board edge before the plug seats. The placer
#                    pushes the part out until this face is on the outline.
EDGE_SPEC = {
    'USB-C-FEMALE-VERT-GCT': dict(mate='vertical', edge_w=8.53),
    '2X04':                  dict(mate='vertical', edge_w=9.50),
    'DX07S024XJ1R1100':      dict(mate='edge',     edge_w=10.30, face=270, body=4.980),
    'DCJACK_2MM_SMT':        dict(mate='edge',     edge_w=8.60,  face=180, body=7.627),
    '0472192001':            dict(mate='edge',     edge_w=15.20, face=270, body=5.991),
    'EVQ-Q2':                dict(mate='vertical', edge_w=10.00),
    # swapped variants
    'USB-C-HORIZ-SMT':       dict(mate='edge',     edge_w=8.94),
    'USB-C-MIDMOUNT':        dict(mate='edge',     edge_w=8.94),
    'DCJACK-LOWPROFILE':     dict(mate='edge',     edge_w=9.00),
    'DCJACK-MIDMOUNT':       dict(mate='edge',     edge_w=9.00),
    '2X04-RA':               dict(mate='edge',     edge_w=10.20),
    '2X04-SMD':              dict(mate='vertical', edge_w=9.50),
    'DCJACK_PJ063AH':        dict(mate='edge',     edge_w=11.00, face=270, body=6.500),
}

# placement boxes for parts that have no footprint in pcbgolf.pretty yet
SWAP_DIMS = {
    'USB-C-HORIZ-SMT':   (9.20, 7.60),
    'USB-C-MIDMOUNT':    (9.20, 7.60),
    'DCJACK-LOWPROFILE': (9.00, 14.00),
    'DCJACK-MIDMOUNT':   (9.00, 14.00),
    '2X04-RA':           (10.20, 8.90),
    'LQFP-100_14x14':    (16.20, 16.20),
    'SC70-5':            (2.60, 2.90),
    'SOT23-5':           (2.85, 4.20),
    '0201-R':            (1.15, 0.65),
    '0201-C':            (1.15, 0.65),
    '0603-C':            (2.20, 1.30),
}

_FPS = None
def _fps():
    global _FPS
    if _FPS is None: _FPS = load_footprints()
    return _FPS

def measured(fp_name):
    """(w, h, ox, oy) - full envelope (pads union body outline) and its centre
    relative to the footprint origin, in the footprint's native orientation."""
    f = _fps().get(fp_name)
    if f is None or not f['pads']:
        g = GEOM.get(fp_name)
        return (g[0], g[1], 0.0, 0.0) if g else (1.0, 1.0, 0.0, 0.0)
    e = f.get('env') or f['bbox']
    return (e[2]-e[0], e[3]-e[1], (e[0]+e[2])/2, (e[1]+e[3])/2)

def has_thru(fp_name):
    """True if the footprint has plated or non-plated through holes, which
    occupy BOTH board sides."""
    f = _fps().get(fp_name)
    if f is None: return False
    return any(p['type'] in ('thru_hole', 'np_thru_hole') for p in f['pads'])


# Vias a footprint always gets, as (x, y, size) in footprint coordinates: they
# go through the board like a through-hole pad, so the far side under them must
# stay clear. usbc_bridge.py puts two in every vertical USB-C's pad channel.
FIXED_VIAS = {
    'USB-C-FEMALE-VERT-GCT': [(0.75, 0.0, 0.45), (-0.75, 0.0, 0.45)],
}


def thru_rects(fp_name):
    """Through-hole pad rectangles as (dx, dy, w, h) offsets from the envelope
    centre.  Only these pierce the board, so only these block the far side."""
    f = _fps().get(fp_name)
    if f is None: return []
    w, h, cx, cy = measured(fp_name)
    out = []
    for p in f['pads']:
        if p['type'] not in ('thru_hole', 'np_thru_hole'): continue
        out.append((p['x'] - cx, p['y'] - cy, p['w'], p['h']))
    for (x, y, s) in FIXED_VIAS.get(fp_name, []):
        out.append((x - cx, y - cy, s, s))
    return out


def box(fp_name, swap=None):
    """Placement box (w, h) including clearance, plus origin offset (ox, oy)."""
    if swap is not None:
        return swap['W']+CLR, swap['H']+CLR, 0.0, 0.0
    if fp_name in SWAP_DIMS and fp_name not in _fps():
        # placeholder only for parts with no real footprint yet
        w, h = SWAP_DIMS[fp_name]
        return w+CLR, h+CLR, 0.0, 0.0
    w, h, ox, oy = measured(fp_name)
    g = GEOM.get(fp_name)
    if g:                       # never smaller than the datasheet body
        w, h = max(w, g[0]-CLR), max(h, g[1]-CLR)
    return w+CLR, h+CLR, ox, oy

def edge_orientation(fp_name, w, h):
    """Returns (needs_edge, edge_w, depth). edge_w runs along the outline."""
    spec = EDGE_SPEC.get(fp_name)
    if spec is None or spec['mate'] != 'edge':
        return False, 0.0, 0.0
    ew = spec['edge_w'] + CLR
    # whichever of the box dimensions matches the mating-face width
    if abs(w - ew) <= abs(h - ew): return True, w, h
    return True, h, w

if __name__ == '__main__':
    print(f"{'footprint':<30}{'box w x h':>16}{'origin off':>16}{'edge?':>8}{'edge_w':>8}{'depth':>7}")
    print('-'*86)
    for name in sorted(set(list(_fps().keys()) + list(EDGE_SPEC.keys()))):
        w, h, ox, oy = box(name)
        e, ew, dp = edge_orientation(name, w, h)
        print(f"{name:<30}{w:7.2f}x{h:<8.2f}{ox:7.2f},{oy:<8.2f}{str(e):>8}{ew:>8.2f}{dp:>7.2f}")
