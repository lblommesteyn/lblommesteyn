"""Render a .kicad_pcb's pads and outline to SVG, read from the file itself."""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sexpr import load

def rot(x, y, d):
    a = math.radians(d); c, s = math.cos(a), math.sin(a)
    return (x*c + y*s, -x*s + y*c)

def render(path, out, scale=11):
    pcb = load(path)
    xs, ys = [], []
    for g in pcb.find_all('gr_line'):
        if g.val('layer') != 'Edge.Cuts': continue
        for k in ('start','end'):
            q = g.find(k); xs.append(q[1]); ys.append(q[2])
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    W, H = x1-x0, y1-y0
    pad_ = 18
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{int(2*W*scale+3*pad_)}" '
           f'height="{int(H*scale+2*pad_+28)}">',
           '<rect width="100%" height="100%" fill="#faf9f7"/>',
           f'<text x="{pad_}" y="17" font-family="monospace" font-size="13">'
           f'{os.path.basename(path)} — {W:.2f} x {H:.2f} mm</text>']
    for si, side in enumerate(('F', 'B')):
        ox = pad_ + si*(W*scale + pad_); oy = pad_ + 16
        svg.append(f'<rect x="{ox}" y="{oy}" width="{W*scale}" height="{H*scale}" '
                   f'fill="#1e8449" fill-opacity="0.08" stroke="#1e8449"/>')
        svg.append(f'<text x="{ox}" y="{oy-3}" font-family="monospace" font-size="11" '
                   f'fill="#555">{"TOP (F.Cu)" if side=="F" else "BOTTOM (B.Cu)"}</text>')
        for f in pcb.find_all('footprint'):
            fl = f.val('layer')
            if (fl == 'B.Cu') != (side == 'B'): continue
            at = f.find('at'); fx, fy = at[1], at[2]
            ang = at[3] if len(at) > 3 else 0
            col = '#2f6fb3' if side == 'B' else '#c94f3d'
            for p in f.find_all('pad'):
                pat = p.find('at'); sz = p.find('size')
                if not pat or not sz: continue
                gx, gy = rot(pat[1], pat[2], ang); gx += fx; gy += fy
                w, h = sz[1], sz[2]
                pa = (pat[3] if len(pat) > 3 else 0)
                if not isinstance(pa, (int, float)): pa = 0
                if abs((pa - ang) % 180 - 90) < 1: w, h = h, w
                X = ox + (gx - x0 - w/2)*scale
                Y = oy + (gy - y0 - h/2)*scale
                svg.append(f'<rect x="{X:.1f}" y="{Y:.1f}" width="{w*scale:.1f}" '
                           f'height="{h*scale:.1f}" fill="{col}" fill-opacity="0.75"/>')
    svg.append('</svg>')
    open(out,'w').write('\n'.join(svg))
    return out

if __name__ == '__main__':
    print(render(sys.argv[1], sys.argv[2]))
