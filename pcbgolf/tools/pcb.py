"""Extract a structured model of the PCBGolf board from KiCad files."""
import math, json, os
from sexpr import load, Node

PCB = '/home/user/commaai/pcbgolf/pcbgolf.kicad_pcb'

def rot(x, y, deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    # KiCad rotates counter-clockwise; Y axis points down
    return (x * c + y * s, -x * s + y * c)

class Fp:
    __slots__ = ('ref','value','mpn','lib','x','y','angle','side','pads','npads',
                 'crtyd','padbb','nets','model','fab')
    def bbox_wh(self, box):
        if not box: return (0.0, 0.0)
        return (box[2]-box[0], box[3]-box[1])
    def as_dict(self):
        cw, ch = self.bbox_wh(self.crtyd)
        pw, ph = self.bbox_wh(self.padbb)
        return dict(ref=self.ref, value=self.value, mpn=self.mpn, lib=self.lib,
                    x=self.x, y=self.y, angle=self.angle, side=self.side,
                    npads=self.npads, crtyd=self.crtyd, padbb=self.padbb,
                    crtyd_w=round(cw,3), crtyd_h=round(ch,3),
                    crtyd_area=round(cw*ch,3), pad_w=round(pw,3), pad_h=round(ph,3),
                    nets=sorted(self.nets), model=self.model)

def _bbox_of_graphics(fpnode, layers, angle, ox, oy):
    """Bounding box (global mm) of graphic items on the given layers."""
    lo = [1e9, 1e9]; hi = [-1e9, -1e9]
    def add(px, py):
        gx, gy = rot(px, py, angle)
        gx += ox; gy += oy
        lo[0] = min(lo[0], gx); lo[1] = min(lo[1], gy)
        hi[0] = max(hi[0], gx); hi[1] = max(hi[1], gy)
    found = False
    for tag in ('fp_line','fp_rect','fp_poly','fp_circle','fp_arc'):
        for g in fpnode.find_all(tag):
            lay = g.val('layer')
            if lay not in layers: continue
            found = True
            for key in ('start','end','center','mid'):
                p = g.find(key)
                if p: add(p[1], p[2])
            if tag == 'fp_circle':
                c = g.find('center'); e = g.find('end')
                if c and e:
                    r = math.hypot(e[1]-c[1], e[2]-c[2])
                    add(c[1]-r, c[2]-r); add(c[1]+r, c[2]+r)
            pts = g.find('pts')
            if pts:
                for xy in pts.find_all('xy'):
                    add(xy[1], xy[2])
    return [round(v,4) for v in (lo[0],lo[1],hi[0],hi[1])] if found else None

def _pad_bbox(fpnode, angle, ox, oy):
    lo = [1e9, 1e9]; hi = [-1e9, -1e9]
    found = False
    for p in fpnode.find_all('pad'):
        at = p.find('at'); sz = p.find('size')
        if not at or not sz: continue
        found = True
        pa = at[3] if len(at) > 3 else 0.0
        if not isinstance(pa, (int, float)): pa = 0.0
        w, h = sz[1], sz[2]
        # pad corners in footprint frame
        for dx, dy in ((-w/2,-h/2),(w/2,-h/2),(w/2,h/2),(-w/2,h/2)):
            rx, ry = rot(dx, dy, pa - angle)  # pad 'at' angle is absolute in KiCad
            px, py = at[1] + rx, at[2] + ry
            gx, gy = rot(px, py, angle)
            gx += ox; gy += oy
            lo[0] = min(lo[0], gx); lo[1] = min(lo[1], gy)
            hi[0] = max(hi[0], gx); hi[1] = max(hi[1], gy)
    return [round(v,4) for v in (lo[0],lo[1],hi[0],hi[1])] if found else None

def load_board(path=PCB):
    pcb = load(path)
    fps = []
    for f in pcb.find_all('footprint'):
        o = Fp()
        o.lib = f[1] if isinstance(f[1], str) else ''
        at = f.find('at')
        o.x, o.y = at[1], at[2]
        o.angle = at[3] if len(at) > 3 else 0.0
        o.side = 'B' if f.val('layer') == 'B.Cu' else 'F'
        o.ref = o.value = o.mpn = ''
        for p in f.find_all('property'):
            if p[1] == 'Reference': o.ref = str(p[2])
            elif p[1] == 'Value': o.value = str(p[2])
            elif p[1] == 'MPN': o.mpn = str(p[2])
        pads = f.find_all('pad')
        o.npads = len(pads)
        o.nets = set()
        for p in pads:
            n = p.find('net')
            if n and len(n) > 2: o.nets.add(str(n[2]))
        crt = 'B.CrtYd' if o.side == 'B' else 'F.CrtYd'
        fab = 'B.Fab' if o.side == 'B' else 'F.Fab'
        o.crtyd = _bbox_of_graphics(f, {crt}, o.angle, o.x, o.y)
        o.fab = _bbox_of_graphics(f, {fab}, o.angle, o.x, o.y)
        o.padbb = _pad_bbox(f, o.angle, o.x, o.y)
        m = f.find('model')
        o.model = m[1] if m and isinstance(m[1], str) else None
        fps.append(o)

    # board outline
    lo = [1e9,1e9]; hi=[-1e9,-1e9]
    edges = []
    for tag in ('gr_line','gr_rect','gr_arc','gr_circle','gr_poly'):
        for g in pcb.find_all(tag):
            if g.val('layer') != 'Edge.Cuts': continue
            pts = []
            for key in ('start','end','center','mid'):
                p = g.find(key)
                if p: pts.append((p[1],p[2]))
            if tag=='gr_circle' and len(pts)>=2:
                r = math.hypot(pts[1][0]-pts[0][0], pts[1][1]-pts[0][1])
                pts += [(pts[0][0]-r,pts[0][1]-r),(pts[0][0]+r,pts[0][1]+r)]
            pp = g.find('pts')
            if pp:
                pts += [(xy[1],xy[2]) for xy in pp.find_all('xy')]
            edges.append((tag, pts))
            for (px,py) in pts:
                lo[0]=min(lo[0],px); lo[1]=min(lo[1],py)
                hi[0]=max(hi[0],px); hi[1]=max(hi[1],py)

    vias = pcb.find_all('via')
    segs = pcb.find_all('segment')
    cu = [l for l in (pcb.find('layers') or Node())[1:] if isinstance(l,Node) and len(l)>2 and l[2]=='signal']
    thickness = None
    gen = pcb.find('general')
    if gen: thickness = gen.val('thickness')
    return dict(fps=fps, outline=[round(v,3) for v in (lo[0],lo[1],hi[0],hi[1])],
                edges=edges, nvias=len(vias), nsegs=len(segs),
                cu_layers=[str(l[1]) for l in cu], thickness=thickness, raw=pcb)

if __name__ == '__main__':
    b = load_board()
    ox0,oy0,ox1,oy1 = b['outline']
    W,H = ox1-ox0, oy1-oy0
    print(f"Board outline: {W:.2f} x {H:.2f} mm  (area {W*H:.0f} mm^2)")
    print(f"Copper layers: {b['cu_layers']}  thickness {b['thickness']} mm")
    print(f"Vias: {b['nvias']}   track segments: {b['nsegs']}")
    print(f"Footprints: {len(b['fps'])}   front: {sum(1 for f in b['fps'] if f.side=='F')}  back: {sum(1 for f in b['fps'] if f.side=='B')}")
    tot_pads = sum(f.npads for f in b['fps'])
    print(f"Total pads: {tot_pads}")
    from collections import Counter
    c = Counter(f.lib.split(':')[-1] for f in b['fps'])
    print("\nFootprint histogram:")
    for k,v in c.most_common():
        print(f"   {v:4d}  {k}")
