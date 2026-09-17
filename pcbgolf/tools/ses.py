"""Count vias / unrouted nets in a Specctra .ses session file."""
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sexpr import load

def analyse(path):
    s = load(path)
    vias = 0; wires = 0; wlen = 0.0
    nets = set(); layers = set()
    for net in s.descend('net'):
        name = net[1] if len(net) > 1 else '?'
        nets.add(str(name))
        for w in net.find_all('wire'):
            wires += 1
            p = w.find('path')
            if p:
                layers.add(str(p[1]))
                pts = [v for v in p[3:] if isinstance(v, (int, float))]
                for i in range(0, len(pts)-3, 2):
                    dx = pts[i+2]-pts[i]; dy = pts[i+3]-pts[i+1]
                    wlen += (dx*dx+dy*dy) ** 0.5
        vias += len(net.find_all('via'))
    return dict(vias=vias, wires=wires, nets=len(nets),
                wire_len_mm=wlen/1000.0, layers=sorted(layers))

if __name__ == '__main__':
    for p in sys.argv[1:]:
        if not os.path.exists(p):
            print(f"{p}: missing"); continue
        r = analyse(p)
        print(f"{os.path.basename(p):<16} vias={r['vias']:>5}  wires={r['wires']:>6}  "
              f"nets={r['nets']:>4}  copper={r['wire_len_mm']:>8.1f} mm  layers={r['layers']}")
