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

GEN_LIB = os.path.join(os.path.dirname(D), 'pcbgolf-gen.pretty')

# source footprint -> generated replacement (in pcbgolf-gen.pretty)
DEFAULT_SUBS = {
    '0402-R': '0201-R',
    '0402-C': '0201-C',
    '0805-C': '0603-C',
    'SOIC-8_3.9x4.9mm_P1.27mm': 'SOT23-5',     # OPA197IDR -> OPA197IDBVR
    # LQFP-144 -> LQFP-100 needs the pad nets reassigned, not copied by name
    'LQFP-144_20x20mm_P0.5mm': 'LQFP-100_14x14',
    # CUI PJ-063AH: same 5.5/2.0mm plug, 9.0mm tall instead of 11.0. Its pins
    # reach 3.0mm below the top face, which sets the board at 0.8-1.4mm for the
    # same Z; at 1.2mm the through-hole 2X04's 3.0mm tail ties with them, so
    # the THT header stays (2X04-SMD costs area for no height).
    'DCJACK_2MM_SMT': 'DCJACK_PJ063AH',
}

# footprint -> json file holding {pin number: net} for a repinned package
REPIN = {'LQFP-100_14x14': 'remap_lqfp100.json'}

# (original footprint, substitute) -> {substitute pad: original pin}.  For a
# package change that keeps the same die but renumbers the pins, the net for a
# pad comes from the ORIGINAL pin it stands in for, not from a pad that merely
# shares its number.  Unlisted original pins (NC) are simply not brought out.
PINMAP = {
    ('SOIC-8_3.9x4.9mm_P1.27mm', 'SOT23-5'):
        {'1': '6', '2': '4', '3': '3', '4': '2', '5': '7'},
    # PJ-063AH: 1 centre pin, 2 sleeve. MP are mechanical tabs, left unconnected.
    ('DCJACK_2MM_SMT', 'DCJACK_PJ063AH'): {'1': 'PWR1', '2': 'GND'},
}

# Schematic pins a substitute serves with one contact: {pin: pin it merges
# into}. Only valid when both are on the same net, which lvs.py checks. The
# PJ-002AH brings its sleeve out on two pads (GND, GNDBREAK), both on GND; the
# PJ-063AH has one sleeve terminal.
PIN_MERGE = {
    ('DCJACK_2MM_SMT', 'DCJACK_PJ063AH'): {'GNDBREAK': 'GND'},
}

_KEEP = ('property', 'path', 'sheetname', 'sheetfile', 'uuid', 'attr',
         'descr', 'tags', 'duplicate_pad_numbers_are_jumpers')

_REPIN_CACHE = {}

def _repin(lib_name):
    if lib_name not in REPIN: return None
    if lib_name not in _REPIN_CACHE:
        import json as _j
        path = os.path.join(D, REPIN[lib_name])
        _REPIN_CACHE[lib_name] = _j.load(open(path))['pin_to_net']
    return _REPIN_CACHE[lib_name]


def _pinswap():
    """ref -> {pad: schematic pin}, from pinswap.json (written by pinopt.py).
    Read at build time, not import time, since pinopt rewrites it."""
    import json as _j
    f = os.path.join(D, 'pinswap.json')
    return _j.load(open(f)) if os.path.exists(f) else {}


def substitute(orig, gen_name):
    """Swap a footprint's body for a generated one, keeping its identity
    (reference, value, MPN, sheet path) and dropping pads the new package
    does not have."""
    # A substitute may be one of our generated land patterns or a footprint the
    # upstream library already ships (SOT23-5 for the OPA197IDBVR); prefer the
    # upstream one, which carries a real 3D model.
    up = os.path.join(os.path.dirname(SRC), 'pcbgolf.pretty', gen_name + '.kicad_mod')
    if os.path.exists(up):
        path, libname = up, 'pcbgolf'
    else:
        path, libname = os.path.join(GEN_LIB, gen_name + '.kicad_mod'), 'pcbgolf-gen'
    new = load(path)
    out = Node(); out.append('footprint'); out.append(Q(f'{libname}:{gen_name}'))
    for c in orig[2:]:
        if isinstance(c, Node) and c.tag in _KEEP:
            out.append(c)
    for c in new[2:]:
        if isinstance(c, Node) and c.tag in ('fp_line','fp_rect','fp_poly','fp_circle',
                                             'fp_arc','pad','attr','model'):
            out.append(c)
    if out.find('layer') is None:
        out.insert(2, n('layer', Q('F.Cu')))
    if out.find('at') is None:
        out.insert(3, n('at', 0, 0))
    return out


def build(placement, netlist, layers=2, src=SRC, title='pcbgolf', subs=None,
          drop=(), thickness=1.6):
    pcb = load(src)
    subs = DEFAULT_SUBS if subs is True else (subs or {})
    P = json.load(open(placement))
    NL = json.load(open(netlist))
    drop = set(drop)
    if drop:
        # A part that is not fitted must also leave the net table, or its net
        # survives with a single pad and reads as a broken connection.
        NL = dict(NL, nets={nm: [pin for pin in pins if pin[0] not in drop]
                            for nm, pins in NL['nets'].items()})
        P = dict(P, parts=[q for q in P['parts'] if q['ref'] not in drop])
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
        orig_lib = str(c[1]).split(':')[-1]
        if subs:
            gen = subs.get(orig_lib)
            if gen:
                c = substitute(c, gen)
        pinmap = PINMAP.get((orig_lib, str(c[1]).split(':')[-1]))
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
        refswap = _pinswap().get(ref, {})
        for pad in c.find_all('pad'):
            pname = str(pad[1])
            if refswap and pname in refswap:
                # a declared, firmware-configured swap (pinswap.json): this pad
                # carries the net of the schematic pin it stands in for
                nm = pmap.get((ref, refswap[pname]))
            elif pinmap is not None:
                orig_pin = pinmap.get(pname)
                nm = pmap.get((ref, orig_pin)) if orig_pin else None
            else:
                nm = pmap.get((ref, pname))
            old = pad.find('net')
            if old is not None: pad.remove(old)
            lib_now = str(c[1]).split(':')[-1]
            rp = _repin(lib_now)
            if rp is not None:
                nm = rp.get(pname)          # repinned package: net comes from
                                            # the pin number, not the old name
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
            # the pad's true extent at its (absolute) angle: a long pad is not
            # a circle of its long side, which grew the outline for pads that
            # were really 0.9mm inside it
            pa = math.radians(pat[3] if len(pat) > 3 and isinstance(pat[3], (int, float)) else 0)
            hw, hh = sz[1] / 2, sz[2] / 2
            ex = abs(hw * math.cos(pa)) + abs(hh * math.sin(pa)) + EDGE_CLR
            ey = abs(hw * math.sin(pa)) + abs(hh * math.cos(pa)) + EDGE_CLR
            px0 = min(px0, gx - ex); py0 = min(py0, gy - ey)
            px1 = max(px1, gx + ex); py1 = max(py1, gy + ey)
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
        if th is not None: th[1] = thickness
    return pcb, dict(footprints=kept, dropped=dropped, not_fitted=sorted(drop),
                     thickness=thickness, nets=len(nets),
                     pads_netted=netted, pads_unnetted=unnetted,
                     W=round(W, 3), H=round(H, 3), area=round(W*H, 1),
                     layers=layers)

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--placement', default=os.path.join(D, 'place_1side.json'))
    ap.add_argument('--netlist', default=os.path.join(D, 'netlist.json'))
    ap.add_argument('--layers', type=int, default=2)
    ap.add_argument('--subs', action='store_true',
                    help='apply the DEFAULT_SUBS footprint substitutions')
    ap.add_argument('--drop', default='',
                    help='comma-separated refs to leave off the board entirely')
    ap.add_argument('--thickness', type=float, default=1.6)
    ap.add_argument('-o', '--out', required=True)
    a = ap.parse_args()
    pcb, info = build(a.placement, a.netlist, a.layers,
                      subs=True if a.subs else None,
                      drop=[r.strip() for r in a.drop.split(',') if r.strip()],
                      thickness=a.thickness)
    open(a.out, 'w').write(dumps(pcb) + '\n')
    print(f"wrote {a.out}")
    for k, v in info.items(): print(f"  {k}: {v}")
