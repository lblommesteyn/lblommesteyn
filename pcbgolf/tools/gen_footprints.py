"""Generate the KiCad footprints the optimised BOM needs that the upstream
library does not ship.

Only parts whose land pattern is standard and whose pin numbering is unambiguous
are generated here.  Connectors (mid-mount USB-C, low-profile barrel jack,
right-angle header) are deliberately NOT generated: their pad patterns are
vendor-specific and inventing them would not be defensible.
"""
import os, sys, math, argparse
D = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(D), 'pcbgolf-gen.pretty')

def fp(name, descr, pads, body, courtyard):
    """pads: [(number, x, y, w, h)] ; body/courtyard: (w, h)"""
    L = []
    L.append(f'(footprint "{name}"')
    L.append('\t(version 20260206)')
    L.append('\t(generator "pcbgolf-tools")')
    L.append('\t(generator_version "10.0")')
    L.append('\t(layer "F.Cu")')
    L.append(f'\t(descr "{descr}")')
    L.append('\t(attr smd)')
    bw, bh = body
    cw, ch = courtyard
    for (x0,y0,x1,y1,lay,wid) in (
        (-cw/2,-ch/2, cw/2,-ch/2,'F.CrtYd',0.05), ( cw/2,-ch/2, cw/2, ch/2,'F.CrtYd',0.05),
        ( cw/2, ch/2,-cw/2, ch/2,'F.CrtYd',0.05), (-cw/2, ch/2,-cw/2,-ch/2,'F.CrtYd',0.05),
        (-bw/2,-bh/2, bw/2,-bh/2,'F.Fab',0.1),    ( bw/2,-bh/2, bw/2, bh/2,'F.Fab',0.1),
        ( bw/2, bh/2,-bw/2, bh/2,'F.Fab',0.1),    (-bw/2, bh/2,-bw/2,-bh/2,'F.Fab',0.1)):
        L.append('\t(fp_line')
        L.append(f'\t\t(start {x0:g} {y0:g})')
        L.append(f'\t\t(end {x1:g} {y1:g})')
        L.append(f'\t\t(stroke (width {wid}) (type solid))')
        L.append(f'\t\t(layer "{lay}")')
        L.append('\t)')
    for (num, x, y, w, h) in pads:
        L.append(f'\t(pad "{num}" smd roundrect')
        L.append(f'\t\t(at {x:g} {y:g})')
        L.append(f'\t\t(size {w:g} {h:g})')
        L.append('\t\t(layers "F.Cu" "F.Paste" "F.Mask")')
        L.append('\t\t(roundrect_rratio 0.25)')
        L.append('\t)')
    L.append(')')
    return '\n'.join(L)

def chip(name, descr, pad_w, pad_h, dx, body_w, body_h, crt_w, crt_h):
    return fp(name, descr,
              [("1", -dx, 0, pad_w, pad_h), ("2", dx, 0, pad_w, pad_h)],
              (body_w, body_h), (crt_w, crt_h))

def sc70_5():
    # SOT-353 / SC-70-5: 0.65mm pitch, pins 1,2,3 bottom (L->R), 4 top-right, 5 top-left
    pw, ph, y = 0.35, 0.65, 0.975
    pads = [("1", -0.65,  y, pw, ph), ("2", 0.0,  y, pw, ph), ("3", 0.65,  y, pw, ph),
            ("4",  0.65, -y, pw, ph), ("5", -0.65, -y, pw, ph)]
    return fp("SC70-5", "SC-70-5 / SOT-353, 0.65mm pitch", pads, (2.0, 1.25), (2.6, 2.9))

def lqfp(name, npins, pitch, span, body, pad_w, pad_l):
    """Square QFP. Pin 1 bottom-left, numbering counter-clockwise."""
    per = npins // 4
    pads = []
    first = -(per-1)*pitch/2
    n = 1
    for i in range(per):                       # left, bottom->top
        pads.append((str(n), -span/2, -(first + i*pitch), pad_l, pad_w)); n += 1
    for i in range(per):                       # bottom, left->right
        pads.append((str(n), first + i*pitch, span/2, pad_w, pad_l)); n += 1
    for i in range(per):                       # right, top->bottom
        pads.append((str(n), span/2, first + (per-1-i)*pitch, pad_l, pad_w)); n += 1
    for i in range(per):                       # top, right->left
        pads.append((str(n), -(first + i*pitch), -span/2, pad_w, pad_l)); n += 1
    c = body + 2.0
    return fp(name, f"LQFP-{npins} {body}x{body}mm P{pitch}mm", pads, (body, body), (c, c))

if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    made = {
        '0201-R': chip('0201-R', '0201 (0603 metric) resistor', 0.40, 0.40, 0.30, 0.60, 0.30, 1.15, 0.65),
        '0201-C': chip('0201-C', '0201 (0603 metric) capacitor', 0.40, 0.40, 0.30, 0.60, 0.30, 1.15, 0.65),
        '0603-C': chip('0603-C', '0603 (1608 metric) capacitor', 0.90, 0.95, 0.7875, 1.60, 0.80, 2.60, 1.40),
        'SC70-5': sc70_5(),
    }
    for name, txt in made.items():
        p = os.path.join(OUT, name + '.kicad_mod')
        open(p, 'w').write(txt + '\n')
        print(f"  wrote {name}.kicad_mod")
