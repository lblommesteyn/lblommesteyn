"""Pin and gate swapping, borrowed from FPGA place-and-route.

The placement fixes where every part sits. What it does not fix is which pin
each signal uses, wherever firmware or a configuration register makes that a
free choice -- and the rules allow firmware changes. Three such freedoms:

1. MCU pins. The LQFP-100 remap kept each signal on its original pin where it
   could, which ignores where the signal is going. Every GPIO-class signal can
   move to any free GPIO pin, and every analog input to any free ADC pin. This
   is solved as a min-cost bipartite matching on Euclidean distance from pin to
   destination, and a minimum-total-length Euclidean matching cannot contain a
   crossing pair: any crossing could be uncrossed shorter. Constraints:
     - analog inputs (4x IMON current sense, 8x SBU voltage sense through
       R13-R20) only on ADC pins. The original design put all eight SBU sense
       lines on ADC pins (PF7-10, PC0-3); the first LQFP-100 remap moved three
       of them to PB14/PB15/PA15, which have no ADC. That bug is fixed here.
     - PC2_C/PC3_C are analog pads; analog only.
     - PA15 and PB4 come out of reset with pull-ups (JTAG defaults) and PB3 as
       JTDO, so a power-enable or relay drive must not sit there: it could
       switch a channel before firmware runs. Only CAN enables and the button
       may use them, as in the original design.
     - SWD, BOOT1, the LSE/RTC pins and every fixed-function signal (USB,
       SDMMC, FDCAN, I2C, crystal) stay put.

2. USB2517 ports. Verified against the Linux usb251xb driver: register 0xFA
   swaps D+/D- per port (bit 0 is the upstream port) and 0xFB-0xFE remap
   logical to physical ports in port-mapping mode, both written over the SMBus
   the MCU already drives (HUB_SDA/HUB_SCL). So any of DN1-DN7 can serve any
   of the five consumers (four OBD-C ports and the MCU), with either polarity,
   and the host still sees the original numbering.

3. Orientation. Any part can turn 180 degrees about its envelope centre
   without changing the envelope, so it cannot create an overlap; it does move
   which side each pad's net leaves from. Connectors and through-hole parts are
   left alone.

Outputs: an updated MCU remap, pinswap.json (per-part pad -> schematic pin
permutations, read by mkboard and lvs), a placement with flips applied, and a
firmware table of every pin and register change.
"""
import os, sys, json, math, re, copy, argparse
D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, D)
import numpy as np
from scipy.optimize import linear_sum_assignment
from sexpr import load, dumps
import mkboard, ratsnest

BIG = 12
ANALOG = ['CH1_IMON', 'CH2_IMON', 'CH3_IMON', 'CH4_IMON',
          'N$29', 'N$30', 'N$31', 'N$32', 'N$35', 'N$36', 'N$37', 'N$38']
GPIO_DRIVE = ([f'CH{i}_PWR_EN' for i in range(1, 5)] +
              [f'CH{i}_SBU{j}_{k}' for i in range(1, 5) for j in (1, 2) for k in ('IGN', 'RELAY')])
GPIO_SAFE = ['CAN0_EN', 'CAN1_EN', 'CAN2_EN', 'CAN3_EN', 'LED_R', 'LED_G', 'LED_B', 'BTN']
ADC_PINS = {'PA0', 'PA1', 'PA2', 'PA3', 'PA4', 'PA5', 'PA6', 'PA7', 'PB0', 'PB1',
            'PC0', 'PC1', 'PC2_C', 'PC3_C', 'PC4', 'PC5'}
ANALOG_ONLY = {'PC2_C', 'PC3_C'}
RESET_PULLED = {'PA15', 'PB3', 'PB4'}
RESERVED = {'PA13', 'PA14', 'PB2', 'PC13', 'PC14', 'PC15'}

HUB = 'U4'
HUB_PORTS = {1: ('1', '2'), 2: ('3', '4'), 3: ('6', '7'), 4: ('8', '9'),
             5: ('11', '12'), 6: ('53', '54'), 7: ('55', '56')}      # (DM, DP)
HUB_UP = ('58', '59')
CONSUMERS = {'CH1': ('CH1_D_N', 'CH1_D_P'), 'CH2': ('CH2_D_N', 'CH2_D_P'),
             'CH3': ('CH3_D_N', 'CH3_D_P'), 'CH4': ('CH4_D_N', 'CH4_D_P'),
             'MCU': ('STM_D_N', 'STM_D_P')}

PINS = json.load(open(os.path.join(D, 'lqfp100_pins.json')))


def pin_name(num):
    nm = PINS[num]
    m = re.match(r'^(P[A-H]\d+(_C)?)', nm)
    return m.group(1) if m else nm.split('(')[0].split('/')[0]


def pad_table(board):
    pcb = load(board)
    nets, pads, _, _ = ratsnest.items_of(pcb)
    # positions of EVERY pad, netted or not: the free MCU pins have no net yet
    # and are exactly the ones being assigned
    import collide
    pos = {(p['ref'], p['pad']): (p['x'], p['y']) for p in collide.pads_of(pcb)}
    bynet = {}
    for p in pads:
        bynet.setdefault(nets.get(p['net']), []).append((p['ref'], p['pad']))
    return pos, bynet


def centroid(pts):
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def hpwl(pos, bynet):
    tot = 0.0
    for nm, pins in bynet.items():
        if nm is None or len(pins) < 2 or len(pins) > BIG: continue
        xs = [pos[p][0] for p in pins]; ys = [pos[p][1] for p in pins]
        tot += (max(xs) - min(xs)) + (max(ys) - min(ys))
    return tot


def build(placement, thickness, out):
    pcb, _ = mkboard.build(placement, os.path.join(D, 'netlist.json'), 4, subs=True,
                           drop=['R11'], thickness=thickness)
    open(out, 'w').write(dumps(pcb) + '\n')
    return out


# ----------------------------------------------------------------- flips
def flip_pass(P, pos, bynet, skip):
    """Turn parts 180 degrees where it shortens their nets. Returns count."""
    H = P['H']; ox, oy = mkboard.ORIGIN
    owner = {}
    for nm, pins in bynet.items():
        for p in pins: owner[p] = nm
    nflip = 0
    for part in P['parts']:
        ref = part['ref']
        if ref in skip or part.get('edge') or part.get('thru'): continue
        mine = [k for k in pos if k[0] == ref]
        if not mine: continue
        c = (ox + part['x'], oy + (H - part['y']))
        def cost(flipped):
            tot = 0.0
            for k in mine:
                nm = owner.get(k)
                if nm is None: continue
                others = [q for q in bynet[nm] if q[0] != ref]
                if not others or len(bynet[nm]) > BIG: continue
                pk = pos[k] if not flipped else (2*c[0] - pos[k][0], 2*c[1] - pos[k][1])
                tot += dist(pk, centroid([pos[q] for q in others]))
            return tot
        if cost(True) < cost(False) - 1e-6:
            part['rot'] = (float(part.get('rot', 0)) + 180.0) % 360
            for k in mine:
                pos[k] = (2*c[0] - pos[k][0], 2*c[1] - pos[k][1])
            nflip += 1
    return nflip


# ----------------------------------------------------------------- MCU
def mcu_assign(remap, pos, bynet):
    new = dict(remap)
    signals = [s for s in ANALOG + GPIO_DRIVE + GPIO_SAFE]
    cur = {}
    for num, net in remap.items():
        if net in signals and pin_name(num) not in ('BOOT0',):
            cur.setdefault(net, num)
    missing = [s for s in signals if s not in cur]
    if missing:
        raise SystemExit(f'signals not on the MCU remap: {missing}')
    used_fixed = {pin_name(n) for n, net in remap.items() if net not in signals}
    pool = [n for n in PINS if re.match(r'^P[A-E]\d+', pin_name(n))
            and pin_name(n) not in RESERVED and pin_name(n) not in used_fixed]
    # BOOT0 shares the BTN net; keep it, and steer the BTN GPIO toward it
    targets = {}
    for s in signals:
        pts = [pos[p] for p in bynet[s] if p[0] != 'U3']
        if s == 'BTN':
            pts += [pos[('U3', n)] for n in remap if remap[n] == 'BTN' and pin_name(n) == 'BOOT0']
        targets[s] = centroid(pts)
    INF = 1e6
    C = np.zeros((len(signals), len(pool)))
    for i, s in enumerate(signals):
        for j, n in enumerate(pool):
            nm = pin_name(n)
            if s in ANALOG and nm not in ADC_PINS: C[i, j] = INF; continue
            if s not in ANALOG and nm in ANALOG_ONLY: C[i, j] = INF; continue
            if s in GPIO_DRIVE and nm in RESET_PULLED: C[i, j] = INF; continue
            C[i, j] = dist(pos[('U3', n)], targets[s])
    r, c = linear_sum_assignment(C)
    if any(C[i, j] >= INF for i, j in zip(r, c)):
        raise SystemExit('MCU assignment infeasible under the constraints')
    for n, net in list(new.items()):
        if net in signals and pin_name(n) != 'BOOT0':
            del new[n]
    changes = []
    for i, j in zip(r, c):
        s, n = signals[i], pool[j]
        new[n] = s
        if cur[s] != n:
            changes.append((s, pin_name(cur[s]), pin_name(n)))
    before = sum(dist(pos[('U3', cur[s])], targets[s]) for s in signals)
    after = sum(C[i, j] for i, j in zip(r, c))
    return new, changes, before, after


# ----------------------------------------------------------------- hub
def hub_assign(pos, bynet):
    def tgt(net):
        return centroid([pos[p] for p in bynet[net] if p[0] != HUB])
    cons = list(CONSUMERS)
    ports = list(HUB_PORTS)
    C = np.zeros((len(cons), len(ports))); SW = {}
    for i, cn in enumerate(cons):
        dn, dp = CONSUMERS[cn]
        for j, pt in enumerate(ports):
            pm, pp = HUB_PORTS[pt]
            straight = dist(pos[(HUB, pm)], tgt(dn)) + dist(pos[(HUB, pp)], tgt(dp))
            swapped = dist(pos[(HUB, pm)], tgt(dp)) + dist(pos[(HUB, pp)], tgt(dn))
            C[i, j] = min(straight, swapped); SW[(i, j)] = swapped < straight
    r, c = linear_sum_assignment(C)
    plan = {cons[i]: (ports[j], SW[(i, j)]) for i, j in zip(r, c)}
    # upstream: polarity only
    um, up = HUB_UP
    s_up = dist(pos[(HUB, um)], tgt('USB_D_N')) + dist(pos[(HUB, up)], tgt('USB_D_P'))
    w_up = dist(pos[(HUB, um)], tgt('USB_D_P')) + dist(pos[(HUB, up)], tgt('USB_D_N'))
    up_swap = w_up < s_up
    # original wiring, for comparison
    orig = {'CH1': 1, 'CH2': 2, 'CH3': 3, 'CH4': 4, 'MCU': 7}
    before = sum(C[cons.index(k), ports.index(v)] if not SW[(cons.index(k), ports.index(v))]
                 else dist(pos[(HUB, HUB_PORTS[v][0])], tgt(CONSUMERS[k][0])) +
                      dist(pos[(HUB, HUB_PORTS[v][1])], tgt(CONSUMERS[k][1]))
                 for k, v in orig.items()) + s_up
    after = sum(C[i, j] for i, j in zip(r, c)) + min(s_up, w_up)
    # pad -> schematic pin permutation over all port pins
    perm = {}
    sch_of = {'CH1': 1, 'CH2': 2, 'CH3': 3, 'CH4': 4, 'MCU': 7}
    used_sch = set()
    for cn, (pt, sw) in plan.items():
        pm, pp = HUB_PORTS[pt]
        sm, sp = HUB_PORTS[sch_of[cn]]
        perm[pm], perm[pp] = (sp, sm) if sw else (sm, sp)
        used_sch.add(sch_of[cn])
    free_phys = [p for p in ports if p not in {v[0] for v in plan.values()}]
    free_sch = [p for p in ports if p not in used_sch]
    for a, b in zip(free_phys, free_sch):
        perm[HUB_PORTS[a][0]], perm[HUB_PORTS[a][1]] = HUB_PORTS[b]
    if up_swap:
        perm[um], perm[up] = up, um
    perm = {k: v for k, v in perm.items() if k != v}
    return plan, up_swap, perm, before, after


def main(placement, out_placement, thickness=0.8):
    S = os.environ.get('PCBGOLF_SCRATCH',
        '/tmp/claude-0/-home-user-lblommesteyn/2caecacf-01d9-5802-a2b6-a2ddf9735640/scratchpad')
    remap_f = os.path.join(D, 'remap_lqfp100.json')
    swap_f = os.path.join(D, 'pinswap.json')
    orig_f = os.path.join(D, 'remap_lqfp100.orig.json')
    if not os.path.exists(orig_f):
        json.dump(json.load(open(remap_f)), open(orig_f, 'w'), indent=1)
    remap_doc = json.load(open(orig_f))
    remap = remap_doc['pin_to_net']
    # start from no hub swaps and the original remap
    json.dump({}, open(swap_f, 'w'))
    json.dump(remap_doc, open(remap_f, 'w'), indent=1)
    mkboard._REPIN_CACHE.clear() if hasattr(mkboard, '_REPIN_CACHE') else None

    P = json.load(open(placement))
    b0 = build(placement, thickness, os.path.join(S, 'pinopt.before.kicad_pcb'))
    pos, bynet = pad_table(b0)
    h0 = hpwl(pos, bynet)

    f1 = flip_pass(P, pos, bynet, skip={'U3', HUB})
    new_remap, mcu_changes, mb, ma = mcu_assign(remap, pos, bynet)
    # apply the MCU change to positions: a net now leaves from a different pad
    inv = {}
    for n, net in new_remap.items(): inv.setdefault(net, []).append(('U3', n))
    for net in set(new_remap.values()):
        if net in bynet:
            bynet[net] = [p for p in bynet[net] if p[0] != 'U3'] + inv[net]
    plan, up_swap, perm, hb, ha = hub_assign(pos, bynet)
    for cn, (pt, sw) in plan.items():
        pass
    # apply hub permutation to bynet
    if perm:
        sch2net = {}
        for nm, pins in bynet.items():
            for p in pins:
                if p[0] == HUB: sch2net[p[1]] = nm
        for nm in list(bynet):
            bynet[nm] = [p for p in bynet[nm] if p[0] != HUB]
        for pad in set(sch2net) | set(perm):
            sch = perm.get(pad, pad)
            nm = sch2net.get(sch)
            if nm is not None: bynet[nm].append((HUB, pad))
    f2 = flip_pass(P, pos, bynet, skip={'U3', HUB})
    h1 = hpwl(pos, bynet)

    remap_doc = dict(remap_doc, pin_to_net=new_remap)
    json.dump(remap_doc, open(remap_f, 'w'), indent=1)
    json.dump({HUB: perm} if perm else {}, open(swap_f, 'w'), indent=1)
    json.dump(P, open(out_placement, 'w'))

    fw = os.path.join(os.path.dirname(D), 'FIRMWARE_PINMAP.md')
    with open(fw, 'w') as f:
        f.write('# Firmware changes required by this board\n\n')
        f.write('Generated by tools/pinopt.py. Every change here is a free choice that '
                'firmware or a configuration register makes, chosen to shorten and '
                'uncross the routing.\n\n')
        f.write('## STM32H725VGT6 (LQFP-100) pin moves\n\n| signal | was (LQFP-100 remap) | now |\n|---|---|---|\n')
        for s, a, b in sorted(mcu_changes):
            f.write(f'| {s} | {a} | {b} |\n')
        f.write('\nAnalog inputs (IMON, SBU sense via R13-R20) are all on ADC-capable pins.\n')
        f.write('\n## USB2517 hub configuration (over SMBus, HUB_SDA/HUB_SCL)\n\n')
        f.write('| consumer | physical port | D+/D- swapped |\n|---|---|---|\n')
        for cn, (pt, sw) in sorted(plan.items()):
            f.write(f'| {cn} | DN{pt} | {"yes" if sw else "no"} |\n')
        f.write(f'| upstream (J3) | UP | {"yes" if up_swap else "no"} |\n\n')
        bits = sum(1 << pt for cn, (pt, sw) in plan.items() if sw) | (1 if up_swap else 0)
        f.write(f'- PORT_SWAP (0xFA) = 0x{bits:02X}  (bit 0 = upstream, bit n = DNn)\n')
        f.write('- Set port-mapping mode (CFG3 bit 3) and program PORT_MAP 0xFB-0xFE so the '
                'logical port numbers match the original DN1-DN4 = CH1-CH4, DN7 = MCU.\n')

    print(f"flips: {f1} + {f2}")
    print(f"MCU: {len(mcu_changes)} signals moved; pin-to-destination length "
          f"{mb:.0f} -> {ma:.0f} mm")
    print(f"hub: " + ", ".join(f"{k}->DN{v[0]}{'(swap)' if v[1] else ''}" for k, v in sorted(plan.items()))
          + f"; upstream {'swapped' if up_swap else 'straight'}; length {hb:.0f} -> {ha:.0f} mm")
    print(f"signal-net HPWL {h0:.0f} -> {h1:.0f} mm (predicted)")
    return dict(h0=h0, h1=h1)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('placement'); ap.add_argument('-o', '--out', required=True)
    ap.add_argument('--thickness', type=float, default=0.8)
    a = ap.parse_args()
    main(a.placement, a.out, a.thickness)
