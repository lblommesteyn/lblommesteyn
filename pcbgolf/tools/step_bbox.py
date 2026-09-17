"""Bounding box of a STEP file: point cloud minus placement-origin points,
with LENGTH_UNIT detection and assembly-transform awareness."""
import re, os, json

ENT = re.compile(r"#(\d+)\s*=\s*([A-Z_0-9]+)\s*\((.*?)\)\s*;", re.S)
REF = re.compile(r"#(\d+)")

def parse_entities(txt):
    ents = {}
    for m in ENT.finditer(txt):
        ents[int(m.group(1))] = (m.group(2), m.group(3))
    return ents

def unit_scale(txt):
    t = txt.upper()
    if re.search(r"CONVERSION_BASED_UNIT\s*\(\s*'INCH'", t) or "'INCH'" in t:
        return 25.4
    m = re.search(r"\(\s*\.(MILLI|CENTI|KILO|MICRO)\.\s*\)\s*\*?\s*LENGTH_UNIT", t)
    if 'MILLI' in t and 'LENGTH_UNIT' in t:
        return 1.0
    return 1.0

def bbox(path):
    txt = open(path, 'r', errors='replace').read()
    ents = parse_entities(txt)
    # CARTESIAN_POINTs used as the origin of a placement are not geometry
    placement_pts = set()
    for eid, (typ, args) in ents.items():
        if 'PLACEMENT' in typ:
            r = REF.findall(args)
            if r: placement_pts.add(int(r[0]))
    scale = unit_scale(txt)
    lo = [1e30]*3; hi = [-1e30]*3; n = 0
    for eid, (typ, args) in ents.items():
        if typ != 'CARTESIAN_POINT': continue
        if eid in placement_pts: continue
        nums = re.findall(r"-?\d+\.?\d*(?:E[-+]?\d+)?", args.split('(',1)[-1]) if '(' in args else []
        if len(nums) < 3: continue
        try: v = [float(x)*scale for x in nums[:3]]
        except ValueError: continue
        n += 1
        for i in range(3):
            if v[i] < lo[i]: lo[i] = v[i]
            if v[i] > hi[i]: hi[i] = v[i]
    if n == 0: return None
    return dict(n=n, scale=scale, lo=[round(x,3) for x in lo], hi=[round(x,3) for x in hi],
                size=[round(hi[i]-lo[i],3) for i in range(3)])

if __name__ == '__main__':
    root = '/home/user/commaai/pcbgolf/pcbgolf.3dshapes'
    out = {}
    for d, _, fs in os.walk(root):
        for f in fs:
            if f.lower().endswith(('.step','.stp')):
                b = bbox(os.path.join(d,f))
                if b: out[f] = b
    print(f"{'STEP MODEL':<46}{'X':>8}{'Y':>8}{'Z':>8}  unit  z-range")
    print('-'*95)
    for k in sorted(out, key=lambda k: -out[k]['size'][2]):
        s=out[k]['size']; lo=out[k]['lo']; hi=out[k]['hi']
        print(f"{k[:45]:<46}{s[0]:>8.2f}{s[1]:>8.2f}{s[2]:>8.2f}  {out[k]['scale']:>4.1f}  [{lo[2]:.2f}..{hi[2]:.2f}]")
    json.dump(out, open('/home/user/lblommesteyn/pcbgolf/tools/step_bbox.json','w'), indent=1)
