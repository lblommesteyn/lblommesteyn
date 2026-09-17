"""Render a packed placement to SVG (top and bottom side)."""
import sys, os, json
D = os.path.dirname(os.path.abspath(__file__))

COLOR = {0: '#c94f3d', 1: '#2f6fb3'}

def render(pj, out, title):
    P = json.load(open(pj))
    W, H = P['W'], P['H']
    S = 12          # px per mm
    pad = 16
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{int(2*W*S+3*pad)}" '
           f'height="{int(H*S+2*pad+26)}" viewBox="0 0 {int(2*W*S+3*pad)} {int(H*S+2*pad+26)}">']
    svg.append('<rect width="100%" height="100%" fill="#faf9f7"/>')
    svg.append(f'<text x="{pad}" y="16" font-family="monospace" font-size="13" fill="#222">'
               f'{title} — {W:.0f} x {H:.0f} mm, Z={P["Z"]}mm, volume {P["vol"]:.0f} mm3</text>')
    for si, side in enumerate((0, 1)):
        ox = pad + si*(W*S + pad)
        oy = pad + 14
        svg.append(f'<rect x="{ox}" y="{oy}" width="{W*S}" height="{H*S}" fill="#1e8449" '
                   f'fill-opacity="0.10" stroke="#1e8449" stroke-width="1.5"/>')
        svg.append(f'<text x="{ox}" y="{oy-3}" font-family="monospace" font-size="11" fill="#555">'
                   f'{"TOP (F.Cu)" if side==0 else "BOTTOM (B.Cu)"}</text>')
        for p in P['parts']:
            if p['side'] != side: continue
            w, h = p['w'], p['h']
            if p['rot'] % 180: w, h = h, w
            x = ox + (p['x'] - w/2)*S
            y = oy + (H - p['y'] - h/2)*S
            c = '#8e44ad' if p['edge'] else COLOR[side]
            svg.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w*S:.1f}" height="{h*S:.1f}" '
                       f'fill="{c}" fill-opacity="0.55" stroke="{c}" stroke-width="0.6"/>')
            if w*S > 26 and h*S > 11:
                svg.append(f'<text x="{x+w*S/2:.1f}" y="{y+h*S/2+3:.1f}" text-anchor="middle" '
                           f'font-family="monospace" font-size="8" fill="#111">{p["ref"]}</text>')
    svg.append('</svg>')
    open(out, 'w').write('\n'.join(svg))
    return out

if __name__ == '__main__':
    for pj, out, t in ((os.path.join(D,'place_stock.json'), os.path.join(D,'..','placement_stock.svg'), 'STOCK BOM'),
                       (os.path.join(D,'place_opt.json'), os.path.join(D,'..','placement_opt.svg'), 'OPTIMISED BOM')):
        if os.path.exists(pj):
            print(render(pj, out, t))
