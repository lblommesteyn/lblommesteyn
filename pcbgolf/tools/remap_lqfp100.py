"""Remap the design's MCU signals from LQFP-144 onto LQFP-100 (STM32H725VGTx).

The pin list comes from KiCad's own STM32H725VGTx symbol, so the package pinout
is authoritative. The alternate-function constraints below are from the
STM32H723/725 reference manual and are the part a careless remap would get
wrong: a CAN pin cannot move to an arbitrary GPIO.
"""
import sys, os, json, re
D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, D)

PINS = json.load(open(os.path.join(D, 'lqfp100_pins.json')))      # number -> name
NAME2NUM = {}
for num, nm in PINS.items():
    m = re.match(r'^(P[A-H]\d+)', nm)
    key = m.group(1) if m else nm.split('/')[0]
    NAME2NUM.setdefault(key, num)

# Alternate-function constraints on LQFP-100. Only the pins that actually exist
# on this package are listed.
FDCAN3_RX = ['PD12']          # also PF6, PG10 - neither bonded out on LQFP100
FDCAN3_TX = ['PD13']          # also PF7, PG9  - neither bonded out
ADC_PINS  = (['PA%d' % i for i in range(8)] + ['PB0','PB1'] +
             ['PC%d' % i for i in range(6)])

# Keep these out of the reassignment pool: PA13/PA14 are SWDIO/SWCLK and
# clobbering them loses the debug port; PB2 is BOOT1; PC13-15 are the RTC/LSE
# pins and are low-drive.
RESERVED = {'PA13', 'PA14', 'PB2', 'PC13', 'PC14', 'PC15'}

# Pins that are power/configuration, not GPIO. These map by NAME to the same
# name on the smaller package - never reassigned to a spare GPIO.
def is_power(name):
    return bool(re.match(r'^(VDD|VSS|VCAP|VBAT|VREF|VLX|VFB|NRST|BOOT0|PDR_ON)', name))

# signal -> required pin class
REQUIRED = {
    'CAN2_RX': ('fdcan3_rx', FDCAN3_RX),
    'CAN2_TX': ('fdcan3_tx', FDCAN3_TX),
    'CH3_IMON': ('adc', ADC_PINS),
}

def load_u3():
    """pin name on LQFP-144 -> net, split into GPIO signals and power pins."""
    d = json.load(open(os.path.join(D, 'netlist.json')))
    gpio, power, allnets = {}, {}, {}
    for net, pl in d['nets'].items():
        for (ref, num, pname, et) in pl:
            if ref != 'U3': continue
            m = re.match(r'^(P[A-H]\d+)', pname)
            key = m.group(1) if m else pname.split('(')[0].strip()
            allnets.setdefault(key, (net, len(pl)))
            if len(pl) < 2: continue
            if m: gpio.setdefault(key, net)
            else: power.setdefault(key, net)
    return gpio, power, allnets

def main():
    sig, power, allnets = load_u3()
    # power pins map by name; report any the smaller package lacks
    pmap, pmissing = {}, []
    for pin, net in sorted(power.items()):
        if pin in NAME2NUM: pmap[pin] = net
        else: pmissing.append((pin, net))
    print(f"power/config pins: {len(pmap)} map straight across, {len(pmissing)} absent on LQFP-100")
    for pin, net in pmissing:
        served = any(p in NAME2NUM and n == net for p, n in power.items() if p != pin)
        unused = allnets.get(pin, (None, 0))[1] < 2
        note = ('net is unused (single-pin) - safe to drop' if unused else
                'net is already carried by another pin - safe to drop' if served else
                'no pin on this package; function is internal on LQFP-100 - '
                'drop it and remove its external part')
        print(f"   {pin:<12} ({net}) -> {note}")
    print()
    used, moved, failed = {}, [], []
    taken = set()

    # 1. keep every signal whose pin exists on LQFP-100
    for pin, net in sorted(sig.items()):
        if pin in NAME2NUM:
            used[pin] = net; taken.add(pin)
    # 2. relocate the rest
    free_adc = [p for p in ADC_PINS if p in NAME2NUM and p not in taken and p not in RESERVED]
    free_any = [p for p in sorted(NAME2NUM, key=lambda s: (s[1], int(s[2:]) if s[2:].isdigit() else 0))
                if re.match(r'^P[A-H]\d+$', p) and p not in taken and p not in RESERVED]
    for pin, net in sorted(sig.items()):
        if pin in NAME2NUM: continue
        cls = REQUIRED.get(net)
        if cls:
            kind, cands = cls
            opts = [c for c in cands if c in NAME2NUM]
            # a constrained pin may need to displace a plain-GPIO signal
            pick = next((c for c in opts if c not in taken), None)
            if pick is None and opts:
                for c in opts:
                    holder = used.get(c)
                    if holder and holder not in REQUIRED:
                        # bump the plain-GPIO holder to a free pin
                        alt = next((f for f in free_any if f not in taken), None)
                        if alt:
                            used[alt] = holder; taken.add(alt)
                            moved.append((c, alt, holder, 'displaced'))
                            pick = c; break
            if pick is None:
                failed.append((pin, net, kind)); continue
            used[pick] = net; taken.add(pick)
            moved.append((pin, pick, net, kind))
        else:
            pool = free_adc if net.endswith('_IMON') else free_any
            pick = next((p for p in pool if p not in taken), None)
            if pick is None:
                failed.append((pin, net, 'gpio')); continue
            used[pick] = net; taken.add(pick)
            moved.append((pin, pick, net, 'gpio'))

    print(f"MCU signals: {len(sig)}   kept in place: {len(sig)-len(moved)}   moved: {len(moved)}")
    print(f"\n{'from':>8} -> {'to':<8} {'net':<22} {'why'}")
    print('-'*60)
    for a, b, net, why in sorted(moved):
        print(f"{a:>8} -> {b:<8} {net:<22} {why}")
    if failed:
        print("\nCOULD NOT PLACE:")
        for p, n, k in failed: print(f"   {p} ({n}) needs {k}")
    # emit pin-number mapping for the new footprint
    # pin number -> net, which is what the board builder needs. Power names
    # repeat across several pins (VDD x8, VSS x6), so every one gets the net.
    pin_to_net = {}
    for pin, net in used.items():
        if pin in NAME2NUM: pin_to_net[NAME2NUM[pin]] = net
    for num, nm in PINS.items():
        base = re.match(r'^([A-Z0-9+_]+)', nm)
        key = base.group(1) if base else nm
        if key in pmap: pin_to_net[num] = pmap[key]
    out = pin_to_net
    json.dump(dict(pin_to_net=out, moved=moved, failed=failed,
                   power_absent=pmissing),
              open(os.path.join(D, 'remap_lqfp100.json'), 'w'), indent=1)
    print(f"\n{len(out)} signals assigned to LQFP-100 pins -> remap_lqfp100.json")
    return failed

if __name__ == '__main__':
    sys.exit(1 if main() else 0)
