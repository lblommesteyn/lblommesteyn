"""Final score model driven by MEASURED placements + measured/estimated via counts."""
import sys, os, json
D = os.path.dirname(os.path.abspath(__file__))

def score(area, Z, vias, layers):
    return area*Z + 50*vias + 5000*layers

def row(name, area, Z, vias, L, note=''):
    s = score(area, Z, vias, L)
    print(f"{name:<40} {area:>7.0f} {Z:>6.2f} {area*Z:>9.0f} {vias:>6} {50*vias:>8} "
          f"{L:>3} {5000*L:>7} {s:>9.0f}  {note}")

if __name__ == '__main__':
    print(f"{'DESIGN':<40} {'area':>7} {'Z':>6} {'volume':>9} {'vias':>6} {'via pts':>8} "
          f"{'L':>3} {'L pts':>7} {'SCORE':>9}")
    print('-'*118)
    # measured placements
    stock = json.load(open(os.path.join(D,'place_stock.json')))
    opt   = json.load(open(os.path.join(D,'place_opt.json')))
    sesv = {}
    for L in (2,4):
        p = os.path.join(D, f'out_{L}L.ses')
        if os.path.exists(p):
            sys.path.insert(0, D)
            from ses import analyse
            try: sesv[L] = analyse(p)['vias']
            except Exception: pass
    print("# measured placement, measured via count where routing completed")
    for L in (2,4):
        v = sesv.get(L)
        if v is not None:
            row(f'STOCK BOM, {L} layer (ROUTED)', stock['area'], stock['Z'], v, L, 'freerouting')
    print("# same placements, via count swept")
    for v in (200, 300, 400, 500, 600):
        row(f'STOCK BOM 42x36, 4L, {v} vias', stock['area'], stock['Z'], v, 4)
    print()
    for v in (200, 300, 400, 500, 600):
        row(f'OPTIMISED 36x36, 4L, {v} vias', opt['area'], opt['Z'], v, 4)
    print()
    for v in (300, 450, 600, 800):
        row(f'OPTIMISED 36x36, 2L, {v} vias', opt['area'], opt['Z'], v, 2)
    print('-'*118)
    print("break-even: 2L beats 4L only if it needs fewer than "
          f"{(5000*2)/50:.0f} extra vias")
    print(f"at Z={opt['Z']}mm, one via (50 pts) == {50/opt['Z']:.1f} mm2 of board; "
          f"one copper layer (5000 pts) == {5000/opt['Z']:.0f} mm2 == 100 vias")
