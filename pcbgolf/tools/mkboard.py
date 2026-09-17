"""Build a real .kicad_pcb from a placement + the rebuilt netlist.

Rather than synthesising footprints, this mutates the upstream pcbgolf.kicad_pcb
(a known-valid KiCad 10 file): it keeps every footprint block verbatim and only
changes position, rotation, side and pad net assignment, then adds the net table
and an Edge.Cuts outline.  sexpr.dumps() is verified lossless on all 34 upstream
KiCad files, so the only new content is what this module writes.
"""
import sys, os, json, math, argparse
D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, D)
from sexpr import load, dumps, Node, Q


def _rot(x, y, deg):
    a = math.radians(deg); c, s = math.cos(a), math.sin(a)
    return (x*c + y*s, -x*s + y*c)

SRC = '/home/user/commaai/pcbgolf/pcbgolf.kicad_pcb'
ORIGIN = (50.0, 50.0)        # board lower-left in KiCad page coords

FRONT_TO_BACK = {'F.Cu':'B.Cu','F.SilkS':'B.SilkS','F.Mask':'B.Mask','F.Paste':'B.Paste',
                 'F.Adhes':'B.Adhes','F.CrtYd':'B.CrtYd','F.Fab':'B.Fab'}

def n(tag, *vals):
    x = Node(); x.append(tag); x.extend(vals); return x

def build_net_table(netlist):
    """net name -> index. Index 0 is KiCad's reserved unconnected net."""
    names = [nm for nm, pins in netlist['nets'].items() if len(pins) >= 2]
    names.sort()
    return {nm: i+1 for i, nm in enumerate(names)}

def pad_net_map(netlist):
    """(ref, pad_name) -> net name, for multi-pin nets only."""
    m = {}
    for nm, pins in netlist['nets'].items():
        if len(pins) < 2: continue
        for (ref, num, pname, et) in pins:
            m[(ref, str(num))] = nm
    return m

def _set_angle(node, ang):
    """Set the third value of an (at x y [ang]) node, omitting a zero angle."""
    ang = round(ang % 360, 4)
    while len(node) > 3: node.pop()
    if ang: node.append(ang)


def orient_footprint(fp, rho, back):
    """Place a source footprint (always stored at orientation 0) at rotation
    rho, optionally on the back.

    Conventions below were derived empirically from pcbnew (see
    docs/flip-convention.md), not guessed:
      back side : local y -> -y, x unchanged; layers F.* -> B.*;
                  pad angle = (rho - a_local) mod 360
      front side: pad angle = (rho + a_local) mod 360
    """
    own_at = fp.find('at')

    def walk(node, is_pad=False):
        for c in node:
            if not isinstance(c, Node): continue
            if c is own_at: continue
            tag = c.tag
            if tag == 'layer' and len(c) > 1 and isinstance(c[1], str):
                if back: c[1] = Q(FRONT_TO_BACK.get(str(c[1]), str(c[1])))
            elif tag == 'layers':
                for j in range(1, len(c)):
                    if isinstance(c[j], str) and back:
                        c[j] = Q(FRONT_TO_BACK.get(str(c[j]), str(c[j])))
            elif tag in ('start', 'end', 'center', 'mid') and len(c) >= 3:
                if back: c[2] = -c[2]
            elif tag == 'xy' and len(c) >= 3:
                if back: c[2] = -c[2]
            elif tag == 'at' and len(c) >= 3:
                a_local = c[3] if len(c) > 3 else 0.0
                if not isinstance(a_local, (int, float)): a_local = 0.0
                if back:
                    c[2] = -c[2]
                    _set_angle(c, rho - a_local)
                else:
                    _set_angle(c, rho + a_local)
            walk(c)

    for pad in fp.find_all('pad'):
        walk(pad)
    for other in fp:
        if isinstance(other, Node) and other.tag != 'pad' and other is not own_at:
            walk(other)
    if back:
        fp.find('layer')[1] = Q('B.Cu')

def build(placement, netlist, layers=2, src=SRC, title='pcbgolf'):
    pcb = load(src)
    P = json.load(open(placement))
    NL = json.load(open(netlist))
    nets = build_net_table(NL)
    pmap = pad_net_map(NL)
    W, H = P['W'], P['H']
    ox, oy = ORIGIN

    # --- copper layer stack ---
    lay = pcb.find('layers')
    del lay[1:]
    cu = ['F.Cu'] + [f'In{i}.Cu' for i in range(1, layers-1)] + ['B.Cu']
    idx = 0
    for name in cu:
        lay.append(n(str(idx), Q(name), 'signal')); idx += 2
    for i, (name, kind, *rest) in enumerate([
            ('F.Adhes','user','F.Adhesive'), ('B.Adhes','user','B.Adhesive'),
            ('F.Paste','user'), ('B.Paste','user'),
            ('F.SilkS','user','F.Silkscreen'), ('B.SilkS','user','B.Silkscreen'),
            ('F.Mask','user'), ('B.Mask','user'),
            ('Dwgs.User','user','User.Drawings'), ('Cmts.User','user','User.Comments'),
            ('Eco1.User','user','User.Eco1'), ('Eco2.User','user','User.Eco2'),
            ('Edge.Cuts','user'), ('Margin','user'),
            ('F.CrtYd','user','F.Courtyard'), ('B.CrtYd','user','B.Courtyard'),
            ('F.Fab','user'), ('B.Fab','user')]):
        node = n(str(idx), Q(name), kind)
        for r in rest: node.append(Q(r))
        lay.append(node); idx += 2

    # --- net table, inserted right after (setup ...) ---
    setup_i = next(i for i, c in enumerate(pcb) if isinstance(c, Node) and c.tag == 'setup')
    net_nodes = [n('net', 0, Q(''))]
    for nm, i in sorted(nets.items(), key=lambda kv: kv[1]):
        net_nodes.append(n('net', i, Q(nm)))
    for k, nd in enumerate(net_nodes):
        pcb.insert(setup_i + 1 + k, nd)

    # --- footprints ---
    placed = {p['ref']: p for p in P['parts']}
    kept, dropped, netted, unnetted = 0, 0, 0, 0
    keep = []
    for c in pcb:
        if not (isinstance(c, Node) and c.tag == 'footprint'):
            keep.append(c); continue
        ref = ''
        for pr in c.find_all('property'):
            if pr[1] == 'Reference': ref = str(pr[2])
        p = placed.get(ref)
        if p is None:
            dropped += 1; continue
        back = bool(p['side'])
        rot = float(p.get('rot', 0)) % 360
        orient_footprint(c, rot, back)
        at = c.find('at')
        # The placer positions a part's ENVELOPE CENTRE, but KiCad positions the
        # footprint ORIGIN, which can be far from it (the microSD's pads sit
        # 6.9mm off its origin).  Shift by the rotated origin offset; on the back
        # the local Y axis is mirrored, so the offset's Y flips with it.
        offx, offy = p.get('ox', 0.0), p.get('oy', 0.0)
        if back: offy = -offy
        dx, dy = _rot(offx, offy, rot)
        # placement coords are Y-up from the board origin; KiCad is Y-down
        at[1] = round(ox + p['x'] - dx, 4)
        at[2] = round(oy + (H - p['y']) - dy, 4)
        _set_angle(at, rot)
        for pad in c.find_all('pad'):
            pname = str(pad[1])
            nm = pmap.get((ref, pname))
            old = pad.find('net')
            if old is not None: pad.remove(old)
            if nm and nm in nets:
                pad.append(n('net', nets[nm], Q(nm))); netted += 1
            else:
                unnetted += 1
        kept += 1
        keep.append(c)
    del pcb[1:]
    pcb.extend(keep[1:] if keep and keep[0] is pcb[0] else keep)

    # --- board outline ---
    # The packer works on a 0.25mm grid, so a part seated flush with the edge can
    # poke out by a fraction of a cell.  Grow the outline to actually contain
    # every pad plus EDGE_CLR, and report the true size rather than the nominal.
    EDGE_CLR = 0.3
    px0, py0, px1, py1 = ox, oy, ox + W, oy + H
    for c in keep:
        if not (isinstance(c, Node) and c.tag == 'footprint'): continue
        at = c.find('at'); fx, fy = at[1], at[2]
        ang = at[3] if len(at) > 3 else 0
        for pad in c.find_all('pad'):
            pat = pad.find('at'); sz = pad.find('size')
            if not pat or not sz: continue
            gx, gy = _rot(pat[1], pat[2], ang); gx += fx; gy += fy
            r = max(sz[1], sz[2]) / 2 + EDGE_CLR
            px0 = min(px0, gx - r); py0 = min(py0, gy - r)
            px1 = max(px1, gx + r); py1 = max(py1, gy + r)
    ox, oy = px0, py0
    W, H = px1 - px0, py1 - py0
    corners = [(ox, oy), (ox + W, oy), (ox + W, oy + H), (ox, oy + H)]
    for i in range(4):
        x0, y0 = corners[i]; x1, y1 = corners[(i+1) % 4]
        pcb.append(n('gr_line', n('start', x0, y0), n('end', x1, y1),
                     n('stroke', n('width', 0.1), n('type', 'default')),
                     n('layer', Q('Edge.Cuts'))))

    gen = pcb.find('general')
    if gen is not None:
        th = gen.find('thickness')
        if th is not None: th[1] = 1.6
    return pcb, dict(footprints=kept, dropped=dropped, nets=len(nets),
                     pads_netted=netted, pads_unnetted=unnetted,
                     W=round(W, 3), H=round(H, 3), area=round(W*H, 1),
                     layers=layers)

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--placement', default=os.path.join(D, 'place_1side.json'))
    ap.add_argument('--netlist', default=os.path.join(D, 'netlist.json'))
    ap.add_argument('--layers', type=int, default=2)
    ap.add_argument('-o', '--out', required=True)
    a = ap.parse_args()
    pcb, info = build(a.placement, a.netlist, a.layers)
    open(a.out, 'w').write(dumps(pcb) + '\n')
    print(f"wrote {a.out}")
    for k, v in info.items(): print(f"  {k}: {v}")
