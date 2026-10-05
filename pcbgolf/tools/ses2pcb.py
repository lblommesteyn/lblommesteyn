"""Import a routed Specctra .ses back into the .kicad_pcb as tracks and vias.

pcb2dsn.py emits absolute board coordinates with every component placed at
(0,0), so session coordinates are already in the board's frame - no transform.
"""
import sys, os, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sexpr import load, dumps, Node, Q

def n(tag, *vals):
    x = Node(); x.append(tag); x.extend(vals); return x

def uuid_for(i):
    h = f"{i:032x}"
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"

def detect_scale(wires, vias, outline):
    """Work out the session's unit from the geometry itself.

    Specctra's (resolution um 10) is read inconsistently - freerouting emits
    1/10 um while a naive writer emits um - so rather than trust the header,
    pick the scale that lands the routing inside the known board outline.
    """
    xs, ys = [], []
    for (_, _, pts, _) in wires:
        for (x, y) in pts: xs.append(x); ys.append(y)
    for (_, x, y) in vias: xs.append(x); ys.append(y)
    if not xs: return 1e-4
    x0, y0, x1, y1 = outline
    pad = 1.0
    best, bestpen = None, None
    for S in (1e-3, 1e-4, 1e-5, 1e-6, 1e-2):
        a, b = min(xs)*S, min(ys)*S
        c, d = max(xs)*S, max(ys)*S
        pen = (max(0.0, x0-pad-a) + max(0.0, y0-pad-b) +
               max(0.0, c-(x1+pad)) + max(0.0, d-(y1+pad)))
        # also prefer a scale that actually fills the board rather than a speck
        cover = ((c-a)*(d-b)) / max((x1-x0)*(y1-y0), 1e-9)
        pen += abs(1.0 - min(cover, 1/cover if cover else 0)) * 10
        if bestpen is None or pen < bestpen: best, bestpen = S, pen
    return best

def load_session(path):
    ses = load(path)
    out = []          # (net, layer, [pts], width)
    vias = []         # (net, x, y)
    for net in ses.descend('net'):
        name = str(net[1]) if len(net) > 1 else ''
        for w in net.find_all('wire'):
            p = w.find('path')
            if not p: continue
            layer = str(p[1]); width = float(p[2])
            nums = [v for v in p[3:] if isinstance(v, (int, float))]
            pts = [(nums[i], nums[i+1]) for i in range(0, len(nums)-1, 2)]
            if len(pts) >= 2: out.append((name, layer, pts, width))
        for v in net.find_all('via'):
            nums = [x for x in v[1:] if isinstance(x, (int, float))]
            if len(nums) >= 2: vias.append((name, nums[0], nums[1]))
    return out, vias

def apply(pcb_path, ses_path, out_path, via_size=0.6, via_drill=0.3):
    pcb = load(pcb_path)
    wires, vias = load_session(ses_path)
    xs, ys = [], []
    for g in pcb.find_all('gr_line'):
        if g.val('layer') != 'Edge.Cuts': continue
        for k in ('start','end'):
            q = g.find(k); xs.append(q[1]); ys.append(q[2])
    outline = (min(xs), min(ys), max(xs), max(ys))
    S = detect_scale(wires, vias, outline)
    nets = {str(x[2]): int(x[1]) for x in pcb.find_all('net')}
    # drop the existing routing, except locked copper (usbc_bridge.py,
    # preroute.py): the router saw it as protected wiring and may or may not
    # echo it back in the session, so it is kept from the board and any
    # session copy of it is skipped
    def is_locked(c):
        return c.val('locked') == 'yes'
    keep = [c for c in pcb if not (isinstance(c, Node) and c.tag in ('segment','via')
                                   and not is_locked(c))]
    del pcb[1:]; pcb.extend(keep[1:])
    have_seg, have_via = set(), set()
    for c in pcb:
        if not isinstance(c, Node): continue
        if c.tag == 'segment':
            a, b = c.find('start'), c.find('end')
            k1 = (round(a[1], 2), round(a[2], 2), round(b[1], 2), round(b[2], 2), c.val('layer'))
            k2 = (round(b[1], 2), round(b[2], 2), round(a[1], 2), round(a[2], 2), c.val('layer'))
            have_seg.update((k1, k2))
        elif c.tag == 'via':
            a = c.find('at'); have_via.add((round(a[1], 2), round(a[2], 2)))
    uid = 1
    nseg = 0
    for (name, layer, pts, width) in wires:
        ni = nets.get(name)
        if ni is None: continue
        for i in range(len(pts)-1):
            (x0,y0),(x1,y1) = pts[i], pts[i+1]
            if abs(x0-x1) < 1e-9 and abs(y0-y1) < 1e-9: continue
            if (round(x0*S, 2), round(y0*S, 2), round(x1*S, 2), round(y1*S, 2), layer) in have_seg:
                continue
            pcb.append(n('segment',
                         n('start', round(x0*S,4), round(y0*S,4)),
                         n('end',   round(x1*S,4), round(y1*S,4)),
                         n('width', round(width*S,4)),
                         n('layer', Q(layer)),
                         n('net', ni),
                         n('uuid', Q(uuid_for(uid)))))
            uid += 1; nseg += 1
    nvia = 0
    cu = [str(l[1]) for l in pcb.find('layers')[1:] if len(l) > 2 and l[2] == 'signal']
    for (name, x, y) in vias:
        ni = nets.get(name)
        if ni is None: continue
        if (round(x*S, 2), round(y*S, 2)) in have_via: continue
        pcb.append(n('via',
                     n('at', round(x*S,4), round(y*S,4)),
                     n('size', via_size), n('drill', via_drill),
                     n('layers', Q(cu[0]), Q(cu[-1])),
                     n('net', ni),
                     n('uuid', Q(uuid_for(uid)))))
        uid += 1; nvia += 1
    open(out_path,'w').write(dumps(pcb)+'\n')
    return dict(segments=nseg, vias=nvia, wires=len(wires), scale=S)

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('pcb'); ap.add_argument('ses'); ap.add_argument('-o','--out', required=True)
    ap.add_argument('--via-size', type=float, default=0.6,
                    help='via pad diameter (JLCPCB 4-layer minimum is 0.45)')
    ap.add_argument('--via-drill', type=float, default=0.3,
                    help='via drill diameter (JLCPCB minimum is 0.2)')
    a = ap.parse_args()
    r = apply(a.pcb, a.ses, a.out, a.via_size, a.via_drill)
    for k,v in r.items(): print(f"  {k}: {v}")
