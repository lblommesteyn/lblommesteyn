"""Export a Specctra .dsn straight from a .kicad_pcb.

Every component gets its own image whose pads are already at absolute board
coordinates, and is then placed at (0,0) front with zero rotation.  That way no
mirroring or rotation convention has to be agreed with the router: the geometry
in the DSN is literally the geometry in the board file.
"""
import sys, os, math, argparse
D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, D)
from sexpr import load, Node

# (resolution um 10) declares one coordinate unit to be 1/10 um, so mm must be
# scaled by 10000, not 1000.  With SC=1000 the board was handed to the router
# 10x smaller than life -- 48x50mm became 4.8x5.0mm -- with the clearance and
# track width shrunk to match.  Geometrically similar, so it routed and looked
# fine, but the router's own absolute tolerances and grid rounding then sat 10x
# coarser relative to the features, which is where sub-rule clearances came
# from.
SC = 10000.0    # mm -> 1/10 um, matching (resolution um 10)

def q(v): return f"{v*SC:.1f}"

def rot(x, y, deg):
    a = math.radians(deg); c, s = math.cos(a), math.sin(a)
    return (x*c + y*s, -x*s + y*c)

def pad_polygon(cx, cy, w, h, ang):
    """Rotated-rectangle corners, counter-clockwise, in board mm."""
    pts = []
    for dx, dy in ((-w/2,-h/2), (w/2,-h/2), (w/2,h/2), (-w/2,h/2)):
        rx, ry = rot(dx, dy, ang)
        pts.append((cx + rx, cy + ry))
    return pts

# JLCPCB minimum distance from a non-plated hole's edge to copper
NPTH_COPPER = 0.20

def export(pcb_path, out, track=0.15, clearance=0.15, via_dia=0.6, via_drill=0.3):
    pcb = load(pcb_path)
    cu = [str(l[1]) for l in pcb.find('layers')[1:] if len(l) > 2 and l[2] == 'signal']

    xs, ys = [], []
    for g in pcb.find_all('gr_line'):
        if g.val('layer') != 'Edge.Cuts': continue
        for k in ('start','end'):
            p = g.find(k); xs.append(p[1]); ys.append(p[2])
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)

    # nets declared in the board
    netnames = {int(n[1]): str(n[2]) for n in pcb.find_all('net')}

    comps = []          # (ref, [ (pinid, layers, polygon|circle) ])
    net_pins = {}       # net name -> [ "REF-PIN" ]
    for f in pcb.find_all('footprint'):
        ref = next((str(p[2]) for p in f.find_all('property') if p[1]=='Reference'), None)
        if not ref: continue
        at = f.find('at'); fx, fy = at[1], at[2]
        fang = at[3] if len(at) > 3 else 0
        pins = []
        seen = {}
        for pad in f.find_all('pad'):
            ptype = str(pad[2]) if len(pad) > 2 else 'smd'
            pat = pad.find('at'); sz = pad.find('size')
            if not pat or not sz: continue
            name = str(pad[1])
            if ptype == 'np_thru_hole':
                # A mechanical hole has no copper, but the drill goes through
                # every layer, so it is an obstacle on all of them: copper
                # routed across it is cut when the board is drilled. Emitted as
                # an unconnected pin the size of the drill plus the extra
                # hole-to-copper margin over the copper clearance.
                dr = pad.find('drill')
                d = max(dr[1], dr[2] if len(dr) > 2 and isinstance(dr[2], (int, float)) else 0) \
                    if dr is not None else max(sz[1], sz[2])
                name = 'NPTH'
                gx, gy = rot(pat[1], pat[2], fang); gx += fx; gy += fy
                seen[name] = seen.get(name, 0) + 1
                pins.append((f"NPTH{seen[name]}", cu[:],
                             ('circle', gx, gy, d + 2 * max(0.0, NPTH_COPPER - clearance))))
                continue
            if name in ('', '~'):
                # unnamed copper (a mounting tab): an obstacle with no net
                name = 'MECH'
            seen[name] = seen.get(name, 0) + 1
            pid = name if seen[name] == 1 else f"{name}-{seen[name]}"
            gx, gy = rot(pat[1], pat[2], fang); gx += fx; gy += fy
            pang = pat[3] if len(pat) > 3 else 0
            if not isinstance(pang, (int, float)): pang = 0
            # pad angle in the file is absolute already
            lays = [str(v) for v in (pad.find('layers') or Node())[1:]]
            cul = [l for l in lays if l in ('F.Cu','B.Cu')]
            if '*.Cu' in lays or ptype in ('thru_hole','np_thru_hole'):
                cul = cu[:]
            if not cul: continue
            shape = str(pad[3]) if len(pad) > 3 else 'rect'
            if shape == 'circle':
                geom = ('circle', gx, gy, max(sz[1], sz[2]))
            else:
                geom = ('poly', pad_polygon(gx, gy, sz[1], sz[2], pang))
            pins.append((pid, cul, geom))
            nn = pad.find('net')
            if nn is not None and len(nn) > 2:
                net_pins.setdefault(str(nn[2]), []).append(f"{ref}-{pid}")
        if pins: comps.append((ref, pins))

    o = []; a = o.append
    a('(pcb pcbgolf.dsn')
    a('  (parser (string_quote ") (space_in_quoted_tokens on)'
      ' (host_cad "pcbgolf-tools") (host_version "1"))')
    a('  (resolution um 10)')
    a('  (unit um)')
    a('  (structure')
    for i, l in enumerate(cu):
        a(f'    (layer {l} (type signal) (property (index {i})))')
    a(f'    (boundary (path pcb 0  {q(x0)} {q(y0)}  {q(x1)} {q(y0)}'
      f'  {q(x1)} {q(y1)}  {q(x0)} {q(y1)}  {q(x0)} {q(y0)}))')
    a('    (via "V")')
    a(f'    (rule (width {q(track)}) (clearance {q(clearance)})'
      f' (clearance {q(clearance)} (type default_smd))'
      f' (clearance {q(clearance*0.8)} (type smd_smd)))')
    a('  )')
    a('  (placement')
    for ref, pins in comps:
        a(f'    (component "IMG_{ref}" (place {ref} 0 0 front 0))')
    a('  )')
    a('  (library')
    for ref, pins in comps:
        a(f'    (image "IMG_{ref}"')
        for pid, cul, geom in pins:
            a(f'      (pin PS_{ref}_{pid.replace("-","_")} {pid} 0 0)')
        a('    )')
    for ref, pins in comps:
        for pid, cul, geom in pins:
            a(f'    (padstack PS_{ref}_{pid.replace("-","_")}')
            for l in cul:
                if geom[0] == 'circle':
                    _, gx, gy, d = geom
                    a(f'      (shape (circle {l} {q(d)} {q(gx)} {q(gy)}))')
                else:
                    pts = ' '.join(f"{q(px)} {q(py)}" for px, py in geom[1])
                    a(f'      (shape (polygon {l} 0 {pts}))')
            a('      (attach off)')
            a('    )')
    a('    (padstack "V"')
    for l in cu:
        a(f'      (shape (circle {l} {q(via_dia)}))')
    a('      (attach off)\n    )')
    a('  )')
    a('  (network')
    nn = 0
    for name, pins in sorted(net_pins.items()):
        if len(pins) < 2: continue
        nn += 1
        a(f'    (net "{name}"')
        a('      (pins ' + ' '.join(sorted(set(pins))) + ')')
        a('    )')
    a(f'    (class kicad_default "" (circuit (use_via "V"))'
      f' (rule (width {q(track)}) (clearance {q(clearance)})))')
    a('  )')
    # Existing routing, handed back so the router can start from a good state
    # and spend its effort on what is still unconnected.  Left rippable rather
    # than protected, so it can make room for the stragglers.
    segs = pcb.find_all('segment')
    vias_ex = pcb.find_all('via')
    if segs or vias_ex:
        a('  (wiring')
        for sg in segs:
            sn = sg.find('net')
            if sn is None: continue
            nm = netnames.get(int(sn[1]))
            if not nm: continue
            st, en = sg.find('start'), sg.find('end')
            wd = sg.find('width')
            lay = sg.val('layer')
            # locked copper (preroute.py) goes in protected, so the router
            # routes around it instead of ripping it up
            kind = 'protect' if sg.val('locked') == 'yes' else 'route'
            a(f'    (wire (path {lay} {q(wd[1] if wd else track)} '
              f'{q(st[1])} {q(st[2])} {q(en[1])} {q(en[2])}) (net "{nm}") (type {kind}))')
        for v in vias_ex:
            vn = v.find('net')
            if vn is None: continue
            nm = netnames.get(int(vn[1]))
            if not nm: continue
            at = v.find('at')
            kind = 'protect' if v.val('locked') == 'yes' else 'route'
            a(f'    (via "V" {q(at[1])} {q(at[2])} (net "{nm}") (type {kind}))')
        a('  )')
    a(')')
    open(out, 'w').write('\n'.join(o))
    return dict(components=len(comps), nets=nn,
                wires=len(segs), vias_in=len(vias_ex),
                pins=sum(len(p) for _, p in comps),
                layers=len(cu), board=f"{x1-x0:.2f} x {y1-y0:.2f}", out=out)

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('pcb'); ap.add_argument('-o','--out', required=True)
    ap.add_argument('--track', type=float, default=0.15)
    ap.add_argument('--clearance', type=float, default=0.15)
    ap.add_argument('--via-dia', type=float, default=0.6,
                    help='via pad diameter (JLCPCB 4-layer minimum is 0.45)')
    ap.add_argument('--via-drill', type=float, default=0.3,
                    help='via drill diameter (JLCPCB minimum is 0.2)')
    a = ap.parse_args()
    r = export(a.pcb, a.out, a.track, a.clearance, a.via_dia, a.via_drill)
    for k, v in r.items(): print(f"  {k}: {v}")
