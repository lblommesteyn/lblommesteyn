"""Export a STEP assembly of the PCBA: board slab plus a box per component.

The challenge asks for "a STEP file of the final assembly", which is what the
bounding-box volume is measured from. Each part is emitted as a B-rep box at its
placed position, with the measured height from parts.py, on the correct side.
"""
import sys, os, math, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sexpr import load
from parts import GEOM
import geom2
from collide import rot

class Step:
    def __init__(self):
        self.lines = []
        self.n = 0
    def e(self, body):
        self.n += 1
        self.lines.append(f"#{self.n}={body};")
        return self.n
    def pt(self, x, y, z):
        return self.e(f"CARTESIAN_POINT('',({x:.4f},{y:.4f},{z:.4f}))")
    def dir(self, x, y, z):
        return self.e(f"DIRECTION('',({x:.6f},{y:.6f},{z:.6f}))")

def box_brep(s, x0, y0, z0, dx, dy, dz, name):
    """A closed box as an axis-aligned B-rep solid."""
    p = [[None]*2 for _ in range(4)]
    corners = [(x0, y0), (x0+dx, y0), (x0+dx, y0+dy), (x0, y0+dy)]
    for i, (cx, cy) in enumerate(corners):
        p[i][0] = s.pt(cx, cy, z0)
        p[i][1] = s.pt(cx, cy, z0+dz)
    vs = [[s.e(f"VERTEX_POINT('',#{p[i][k]})") for k in (0, 1)] for i in range(4)]
    # keep the real coordinates: a STEP LINE needs the edge's actual direction,
    # not a placeholder, or the solid is geometrically inconsistent
    xyz = {}
    for i, (cx, cy) in enumerate(corners):
        xyz[vs[i][0]] = (cx, cy, z0)
        xyz[vs[i][1]] = (cx, cy, z0+dz)

    def edge(v1, v2):
        ax_, ay_, az_ = xyz[v1]
        bx_, by_, bz_ = xyz[v2]
        ux, uy, uz = bx_-ax_, by_-ay_, bz_-az_
        L = math.sqrt(ux*ux + uy*uy + uz*uz) or 1.0
        d = s.e(f"VECTOR('',#{s.dir(ux/L, uy/L, uz/L)},{L:.4f})")
        base = s.pt(ax_, ay_, az_)
        ln = s.e(f"LINE('',#{base},#{d})")
        return s.e(f"EDGE_CURVE('',#{v1},#{v2},#{ln},.T.)")

    faces = []
    def face(vlist, nx, ny, nz, px, py, pz):
        eds = []
        for i in range(len(vlist)):
            eds.append(edge(vlist[i], vlist[(i+1) % len(vlist)]))
        oes = [s.e(f"ORIENTED_EDGE('',*,*,#{ed},.T.)") for ed in eds]
        loop = s.e("EDGE_LOOP('',(" + ",".join(f"#{o}" for o in oes) + "))")
        bnd = s.e(f"FACE_OUTER_BOUND('',#{loop},.T.)")
        ax = s.e(f"AXIS2_PLACEMENT_3D('',#{s.pt(px,py,pz)},#{s.dir(nx,ny,nz)},"
                 f"#{s.dir(*( (1.0,0.0,0.0) if abs(nz)>0.5 else (0.0,0.0,1.0) ))})")
        pl = s.e(f"PLANE('',#{ax})")
        faces.append(s.e(f"ADVANCED_FACE('',(#{bnd}),#{pl},.T.)"))

    face([vs[0][0], vs[1][0], vs[2][0], vs[3][0]], 0,0,-1, x0, y0, z0)
    face([vs[0][1], vs[3][1], vs[2][1], vs[1][1]], 0,0,1,  x0, y0, z0+dz)
    face([vs[0][0], vs[0][1], vs[1][1], vs[1][0]], 0,-1,0, x0, y0, z0)
    face([vs[1][0], vs[1][1], vs[2][1], vs[2][0]], 1,0,0,  x0+dx, y0, z0)
    face([vs[2][0], vs[2][1], vs[3][1], vs[3][0]], 0,1,0,  x0, y0+dy, z0)
    face([vs[3][0], vs[3][1], vs[0][1], vs[0][0]], -1,0,0, x0, y0, z0)
    shell = s.e("CLOSED_SHELL('',(" + ",".join(f"#{f}" for f in faces) + "))")
    return s.e(f"MANIFOLD_SOLID_BREP('{name}',#{shell})")

def export(pcb_path, out, thickness=1.6):
    pcb = load(pcb_path)
    xs, ys = [], []
    for g in pcb.find_all('gr_line'):
        if g.val('layer') != 'Edge.Cuts': continue
        for k in ('start','end'):
            q = g.find(k); xs.append(q[1]); ys.append(q[2])
    bx0, by0, bx1, by1 = min(xs), min(ys), max(xs), max(ys)
    W, H = bx1-bx0, by1-by0

    s = Step()
    solids = []
    solids.append(box_brep(s, 0, 0, 0, W, H, thickness, 'PCB'))

    zmax_t = zmax_b = 0.0
    for f in pcb.find_all('footprint'):
        ref = next((str(p[2]) for p in f.find_all('property') if p[1]=='Reference'), '?')
        lib = str(f[1]).split(':')[-1]
        at = f.find('at'); fx, fy = at[1], at[2]
        ang = at[3] if len(at) > 3 else 0
        g3 = GEOM.get(lib)
        if g3: bw, bh, bz = g3[0], g3[1], g3[2]
        else:
            bw, bh, ox, oy = geom2.measured(lib); bz = 1.0
        if bz <= 0: continue
        if abs((ang % 180) - 90) < 1: bw, bh = bh, bw
        back = f.val('layer') == 'B.Cu'
        # KiCad Y is down; STEP Y is up
        cx = fx - bx0
        cy = (by1 - fy)
        z0 = thickness if not back else -bz
        solids.append(box_brep(s, cx-bw/2, cy-bh/2, z0, bw, bh, bz, ref))
        if back: zmax_b = max(zmax_b, bz)
        else: zmax_t = max(zmax_t, bz)

    ctx_pt = s.pt(0,0,0)
    ctx_d1 = s.dir(0,0,1); ctx_d2 = s.dir(1,0,0)
    ax = s.e(f"AXIS2_PLACEMENT_3D('',#{ctx_pt},#{ctx_d1},#{ctx_d2})")
    body = "\n".join(s.lines)
    n = s.n
    header = f"""ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('PCBGolf assembly'),'2;1');
FILE_NAME('{os.path.basename(out)}','',(''),(''),'pcbgolf-tools','','');
FILE_SCHEMA(('AUTOMOTIVE_DESIGN {{ 1 0 10303 214 1 1 1 1 }}'));
ENDSEC;
DATA;
{body}
#{n+1}=(GEOMETRIC_REPRESENTATION_CONTEXT(3)
GLOBAL_UNCERTAINTY_ASSIGNED_CONTEXT((#{n+5}))
GLOBAL_UNIT_ASSIGNED_CONTEXT((#{n+2},#{n+3},#{n+4}))REPRESENTATION_CONTEXT('',''));
#{n+2}=(LENGTH_UNIT()NAMED_UNIT(*)SI_UNIT(.MILLI.,.METRE.));
#{n+3}=(NAMED_UNIT(*)PLANE_ANGLE_UNIT()SI_UNIT($,.RADIAN.));
#{n+4}=(NAMED_UNIT(*)SI_UNIT($,.STERADIAN.)SOLID_ANGLE_UNIT());
#{n+5}=UNCERTAINTY_MEASURE_WITH_UNIT(LENGTH_MEASURE(1.E-07),#{n+2},
'distance_accuracy_value','confusion accuracy');
#{n+6}=ADVANCED_BREP_SHAPE_REPRESENTATION('PCBA',({",".join(f"#{x}" for x in solids)},#{ax}),#{n+1});
#{n+7}=PRODUCT_DEFINITION_SHAPE('','',#{n+8});
#{n+8}=PRODUCT_DEFINITION('design','',#{n+9},#{n+11});
#{n+9}=PRODUCT_DEFINITION_FORMATION('','',#{n+10});
#{n+10}=PRODUCT('PCBA','PCBA','',(#{n+12}));
#{n+11}=PRODUCT_DEFINITION_CONTEXT('part definition',#{n+13},'design');
#{n+12}=PRODUCT_CONTEXT('',#{n+13},'mechanical');
#{n+13}=APPLICATION_CONTEXT('automotive design');
#{n+14}=SHAPE_DEFINITION_REPRESENTATION(#{n+7},#{n+6});
ENDSEC;
END-ISO-10303-21;
"""
    open(out, 'w').write(header)
    Z = zmax_t + thickness + zmax_b
    return dict(solids=len(solids), W=round(W,3), H=round(H,3), Z=round(Z,2),
                volume=round(W*H*Z,1), bytes=len(header))

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('pcb'); ap.add_argument('-o','--out', required=True)
    a = ap.parse_args()
    for k, v in export(a.pcb, a.out).items(): print(f"  {k}: {v}")
