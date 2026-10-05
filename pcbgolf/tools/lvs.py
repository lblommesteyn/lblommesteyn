"""Layout-vs-schematic: does the board connect what the schematic connects?

Nothing here checked this end to end.  validate.py confirms every pad names a
net that exists, ratsnest.py that copper joins each net's pads, drc.py that
different nets stay apart -- but none of them asks whether the right pads are
on the right net in the first place.  A package substitution that renumbers
pins, or a remap keyed on auto-generated net names that get renumbered, can
wire a board perfectly and wrongly.

Comparison is by pin SETS, not net names, so renumbered N$xxx names cannot
hide or fake a difference:

  * every pad is translated back to the schematic pin it stands in for -- a
    substituted package through mkboard.PINMAP, otherwise by pad name;
  * the MCU is checked separately, since LQFP-100 pins are reassigned by
    signal: each board pad's net must contain exactly the non-MCU pins of the
    schematic net remap_lqfp100.json assigns to that pin;
  * parts deliberately not fitted (--dropped) are removed from the schematic
    side before comparing.
"""
import sys, os, json, argparse
D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, D)
from sexpr import load
import mkboard

MCU = 'U3'


def schematic(netlist, dropped):
    """name -> frozenset((ref, pin)) for nets mkboard would emit."""
    out = {}
    for nm, pins in json.load(open(netlist))['nets'].items():
        ps = frozenset((p[0], str(p[1])) for p in pins if p[0] not in dropped)
        if len(pins) >= 2 and ps:
            out[nm] = ps
    return out


def _original_footprints():
    """ref -> footprint in the upstream design.

    Each part's pins have to be translated from ITS original package.
    Inverting the substitution table instead says "every SOT23-5 used to be a
    SOIC-8", which pushed the Q2-Q9 MOSFETs -- SOT23-5 all along -- through the
    op-amp pin map and reported 60 phantom mismatches.
    """
    src = load(mkboard.SRC)
    out = {}
    for f in src.find_all('footprint'):
        ref = next((str(q[2]) for q in f.find_all('property')
                    if q[1] == 'Reference'), None)
        if ref: out[ref] = str(f[1]).split(':')[-1]
    return out


def board(path):
    """board net name -> set((ref, schematic pin)), plus raw MCU pad nets."""
    pcb = load(path)
    orig = _original_footprints()
    swaps = mkboard._pinswap()
    nets, mcu, libs = {}, {}, {}
    for f in pcb.find_all('footprint'):
        ref = next((str(q[2]) for q in f.find_all('property')
                    if q[1] == 'Reference'), '?')
        lib = str(f[1]).split(':')[-1]
        libs[ref] = (orig.get(ref), lib)
        pinmap = mkboard.PINMAP.get((orig.get(ref), lib))
        refswap = swaps.get(ref, {})
        for pad in f.find_all('pad'):
            nn = pad.find('net')
            if nn is None or len(nn) < 3 or not str(nn[2]): continue
            pname, net = str(pad[1]), str(nn[2])
            if ref == MCU:
                mcu.setdefault(pname, set()).add(net)
                nets.setdefault(net, set())
                continue
            if pname in refswap:
                pin = refswap[pname]
            else:
                pin = pinmap.get(pname, f'?{pname}') if pinmap else pname
            nets.setdefault(net, set()).add((ref, pin))
    return nets, mcu, libs


def check(path, netlist=None, dropped=('R11',), verbose=20):
    netlist = netlist or os.path.join(D, 'netlist.json')
    sch = schematic(netlist, set(dropped))
    bn, mcu, libs = board(path)
    remap = json.load(open(mkboard.pinfile('remap_lqfp100.json')))['pin_to_net']
    errs = []

    # 0. pins a substitute serves with one contact (mkboard.PIN_MERGE): legal
    #    only if the schematic already has both on one net
    for ref, key in sorted(libs.items()):
        merge = mkboard.PIN_MERGE.get(key)
        if not merge: continue
        for a, b in merge.items():
            na = [nm for nm, ps in sch.items() if (ref, a) in ps]
            nb = [nm for nm, ps in sch.items() if (ref, b) in ps]
            if na != nb:
                errs.append(f"{ref}: {a} merged into {b} but they are on different "
                            f"schematic nets {na} / {nb}")
            print(f"  merged   {ref}.{a} -> {ref}.{b} (both on {na[0] if na == nb else '?'})")
        sch = {nm: frozenset((r, merge.get(p, p)) if r == ref else (r, p) for r, p in ps)
               for nm, ps in sch.items()}

    # 1. non-MCU connectivity, compared as a partition
    strip = lambda s: frozenset(x for x in s if x[0] != MCU)
    S = {}
    for nm, ps in sch.items():
        k = strip(ps)
        if k: S[k] = nm
    B = {}
    for nm, ps in bn.items():
        k = frozenset(ps)
        if k: B[k] = nm
    for k, nm in S.items():
        if k not in B:
            errs.append(f"schematic net {nm} has no board net with exactly its pins "
                        f"({len(k)} pins: {sorted(k)[:6]}{' ...' if len(k) > 6 else ''})")
    for k, nm in B.items():
        if k not in S:
            errs.append(f"board net {nm} matches no schematic net "
                        f"({sorted(k)[:6]}{' ...' if len(k) > 6 else ''})")

    # 2. MCU pins: each pad's net must be the schematic net the remap names
    for pad, nets_on in sorted(mcu.items(), key=lambda kv: int(kv[0])
                               if kv[0].isdigit() else 0):
        if len(nets_on) != 1:
            errs.append(f"{MCU} pad {pad} on several nets {sorted(nets_on)}"); continue
        bnet = next(iter(nets_on))
        want = remap.get(pad)
        if want is None:
            errs.append(f"{MCU} pad {pad} is on {bnet} but the remap leaves it unconnected")
            continue
        if want not in sch:
            errs.append(f"{MCU} pad {pad}: remap names {want}, not in the schematic"); continue
        if frozenset(bn.get(bnet, ())) != strip(sch[want]):
            errs.append(f"{MCU} pad {pad} is on board net {bnet}, whose other pins "
                        f"differ from schematic net {want}")
    for pad, want in remap.items():
        if pad not in mcu and want in sch:
            errs.append(f"{MCU} pad {pad} should carry {want} but is unconnected")

    print(f"  {os.path.basename(path)}")
    print(f"  schematic nets      : {len(sch)}  (not fitted: {', '.join(dropped) or '-'})")
    print(f"  board nets          : {len(bn)}")
    print(f"  MCU pads netted     : {len(mcu)}")
    for r, m in mkboard._pinswap().items():
        print(f"  declared swaps      : {r} " + ' '.join(f'{a}<-{b}' for a, b in sorted(m.items())))
    print(f"  mismatches          : {len(errs)}")
    for e in errs[:verbose]: print("    " + e)
    print(f"  => {'PASS' if not errs else 'FAIL'}")
    return not errs, errs


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('pcb', nargs='+')
    ap.add_argument('--dropped', default='R11')
    a = ap.parse_args()
    ok = True
    for p in a.pcb:
        ok &= check(p, dropped=[r for r in a.dropped.split(',') if r])[0]; print()
    sys.exit(0 if ok else 1)
