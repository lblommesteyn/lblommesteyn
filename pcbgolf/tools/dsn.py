"""Emit a Specctra .dsn for the packed board so a real autorouter can route it."""
import sys, os, json, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fplib import load_footprints

RES = 10          # dsn units per um -> we emit in um*10? no: (resolution um 10) = 1/10 um
SC  = 1000.0      # mm -> um

def q(v): return f"{v*SC:.1f}"

class DSN:
    def __init__(self, W, H, layers, place, nets, fps, track=0.15, clear=0.15):
        self.W, self.H, self.L = W, H, layers
        self.place, self.nets, self.fps = place, nets, fps
        self.track, self.clear = track, clear
        self.padstacks = {}

    def cu_layers(self):
        if self.L == 2: return ['F.Cu', 'B.Cu']
        if self.L == 4: return ['F.Cu', 'In1.Cu', 'In2.Cu', 'B.Cu']
        return ['F.Cu'] + [f'In{i}.Cu' for i in range(1, self.L-1)] + ['B.Cu']

    def padstack(self, pad):
        thru = pad['type'] != 'smd'
        w, h = pad['w'], pad['h']
        shape = 'circle' if (pad['shape'] == 'circle' or abs(w-h) < 1e-6 and pad['shape'] == 'oval') else 'rect'
        key = (shape, round(w,3), round(h,3), thru)
        if key in self.padstacks: return self.padstacks[key][0]
        name = f"{'T' if thru else 'S'}_{shape}_{round(w*1000)}x{round(h*1000)}_{len(self.padstacks)}"
        self.padstacks[key] = (name, shape, w, h, thru)
        return name

    def emit(self):
        o = []
        a = o.append
        a('(pcb pcbgolf.dsn')
        a('  (parser (string_quote ") (space_in_quoted_tokens on) (host_cad "pcbgolf-tools") (host_version "1"))')
        a('  (resolution um 10)')
        a('  (unit um)')
        a('  (structure')
        for i, l in enumerate(self.cu_layers()):
            a(f'    (layer {l} (type signal) (property (index {i})))')
        a(f'    (boundary (path pcb 0  0 0  {q(self.W)} 0  {q(self.W)} {q(self.H)}  0 {q(self.H)}  0 0))')
        a('    (via "Via_600:300")')
        a(f'    (rule (width {q(self.track)}) (clearance {q(self.clear)})'
          f' (clearance {q(self.clear)} (type default_smd)) (clearance {q(self.clear*0.8)} (type smd_smd)))')
        a('  )')
        a('  (placement')
        for p in self.place:
            img = p['img']
            side = 'back' if p['side'] == 1 else 'front'
            a(f'    (component "{img}" (place {p["ref"]} {q(p["x"])} {q(p["y"])} {side} {p["rot"]}))')
        a('  )')
        a('  (library')
        used = {p['img'] for p in self.place}
        for img in sorted(used):
            fp = self.fps[img]
            a(f'    (image "{img}"')
            for pd in fp['pins']:
                ps = self.padstack(pd)
                a(f'      (pin {ps} {pd["id"]} {q(pd["x"])} {q(pd["y"])})')
            a('    )')
        for (name, shape, w, h, thru) in self.padstacks.values():
            a(f'    (padstack {name}')
            layers = self.cu_layers() if thru else ['F.Cu']
            for l in layers:
                if shape == 'circle':
                    a(f'      (shape (circle {l} {q(max(w,h))}))')
                else:
                    a(f'      (shape (rect {l} {q(-w/2)} {q(-h/2)} {q(w/2)} {q(h/2)}))')
            a('      (attach off)')
            a('    )')
        a(f'    (padstack "Via_600:300"')
        for l in self.cu_layers():
            a(f'      (shape (circle {l} 600))')
        a('      (attach off)\n    )')
        a('  )')
        a('  (network')
        for name, pins in self.nets:
            if len(pins) < 2: continue
            a(f'    (net "{name}"')
            a('      (pins ' + ' '.join(pins) + ')')
            a('    )')
        a('    (class kicad_default "" (circuit (use_via "Via_600:300")) '
          f'(rule (width {q(self.track)}) (clearance {q(self.clear)})))')
        a('  )')
        a(')')
        return '\n'.join(o)

def build(placement_json, layers, out, track=0.15, clear=0.15):
    P = json.load(open(placement_json))
    raw = load_footprints()
    D = os.path.dirname(os.path.abspath(__file__))
    NL = json.load(open(os.path.join(D, 'netlist.json')))

    # unique pin ids per footprint (duplicated pad names get -2, -3 ... suffixes)
    fps = {}
    dupmap = {}
    for name, fp in raw.items():
        pins, seen = [], {}
        for pd in fp['pads']:
            base = pd['name']
            if base in ('', '~'): continue
            seen[base] = seen.get(base, 0) + 1
            pid = base if seen[base] == 1 else f"{base}-{seen[base]}"
            pins.append(dict(id=pid, x=pd['x'], y=-pd['y'], w=pd['w'], h=pd['h'],
                             type=pd['type'], shape=pd['shape']))
            dupmap.setdefault(name, {}).setdefault(base, []).append(pid)
        fps[name] = dict(pins=pins)

    place = []
    for p in P['parts']:
        img = p['src']
        if img not in fps: continue
        place.append(dict(ref=p['ref'], img=img, x=p['x'], y=p['y'],
                          side=p['side'], rot=int(p['rot'])))
    ref2img = {p['ref']: p['img'] for p in place}

    nets = []
    for name, pins in NL['nets'].items():
        ent = []
        for (ref, num, pname, et) in pins:
            img = ref2img.get(ref)
            if not img: continue
            for pid in dupmap.get(img, {}).get(str(num), []):
                ent.append(f"{ref}-{pid}")
        if len(ent) >= 2:
            nets.append((name.replace('"', ''), sorted(set(ent))))
    d = DSN(P['W'], P['H'], layers, place, nets, fps, track, clear)
    open(out, 'w').write(d.emit())
    npins = sum(len(n[1]) for n in nets)
    return dict(components=len(place), nets=len(nets), pins=npins,
                W=P['W'], H=P['H'], layers=layers, out=out)

if __name__ == '__main__':
    D = os.path.dirname(os.path.abspath(__file__))
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(D, 'place_stock.json')
    for L in (2, 4):
        r = build(src, L, os.path.join(D, f'board_{L}L.dsn'))
        print(r)
