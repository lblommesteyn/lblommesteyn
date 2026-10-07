"""Build one board variant end to end, ready to route.

    python3 build_variant.py W H LAYERS TAG

Places the current design (LQFP-100, OPA197 in SOT-23-5, 0201/0603 passives,
CUI PJ-063AH jack) in a W x H mm slot, optimises pin assignment into its own
pin set (tools/pinsets/TAG, see mkboard.pinfile), builds the board at 1.2 mm,
legalises it, draws the USB-C D+/D- bridges, and reports DRC and volume.
Writes board/pcbgolf-TAG.kicad_pcb and tools/place_TAG.json. Route it with

    PCBGOLF_PINSET=TAG python3 route.py ../board/pcbgolf-TAG.kicad_pcb \\
        -o ../board/pcbgolf-TAG-c1.kicad_pcb --passes 80 --tag TAG-c1
"""
import sys, os, io, contextlib
D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, D)

THICKNESS = 1.2
DESIGN = {'LQFP-144_20x20mm_P0.5mm': 'LQFP-100_14x14',
          'SOIC-8_3.9x4.9mm_P1.27mm': 'SOT23-5',
          '0402-R': '0201-R', '0402-C': '0201-C', '0805-C': '0603-C',
          'DCJACK_2MM_SMT': 'DCJACK_PJ063AH'}


def build(W, H, layers, tag):
    os.environ['PCBGOLF_PINSET'] = tag
    os.chdir(D)
    import build_board as B, mkboard, bbox3d, pinopt, legalize, usbc_bridge, drc
    from sexpr import dumps
    board = os.path.join(os.path.dirname(D), 'board')
    pcb0 = os.path.join(board, f'pcbgolf-{tag}-pre.kicad_pcb')
    pl0, pl = f'place_{tag}-pre.json', f'place_{tag}.json'
    info, _ = B.build(B.pick(DESIGN), 12.0, [(W, H)], layers, pcb0, pl0,
                      clearance=0.10, tall=1.60, analytical=True)
    if not info:
        print('  => FAILED'); return None
    pinopt.main(pl0, pl, THICKNESS)
    mkboard._REPIN_CACHE.clear()
    b, _ = mkboard.build(pl, 'netlist.json', layers, subs=True, drop=['R11'],
                         thickness=THICKNESS)
    out = os.path.join(board, f'pcbgolf-{tag}.kicad_pcb')
    open(out, 'w').write(dumps(b) + '\n')
    os.remove(pcb0)
    # the final board is rebuilt from the placement file, which never received
    # build_board's legalisation moves: legalise this board itself
    with contextlib.redirect_stdout(io.StringIO()):
        moved = legalize.legalize(out, out, 0.10)
    print('  legalised final board, moved', moved)
    usbc_bridge.bridge(out, out)
    with contextlib.redirect_stdout(io.StringIO()):
        nv, _ = drc.check(out, 0.09, 0)
    print('  DRC violations before routing:', nv)
    d = bbox3d.bbox(out)
    print(f"  => {tag}: {d['W']} x {d['H']}  Z {d['Z']}  volume {d['volume']}")
    return out


if __name__ == '__main__':
    W, H, L, tag = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
    build(W, H, L, tag)
