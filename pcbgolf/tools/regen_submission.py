"""Regenerate submission/ from an actually-routed board."""
import sys, os, csv, json
D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, D)
from sexpr import load
import score_board
SUB = os.path.join(os.path.dirname(D), 'submission')
BOARD = os.path.join(os.path.dirname(D), 'board')
LEAD = 84578

import glob

# Routed boards to consider: every chunk the routing chains wrote (chain.py),
# for the current design. Older boards in board/ predate the connector,
# mechanical-hole and pin-assignment fixes and fail the checks below.
PATTERNS = ['pcbgolf-q4-c*.kicad_pcb', 'pcbgolf-q6-c*.kicad_pcb', 'pcbgolf-[rsu]*-c*.kicad_pcb', 'pcbgolf-[rsu]*-v*.kicad_pcb']


def pinset_of(fn):
    """The pin set a board was built with: tools/pinsets/<tag> when the board
    is named after one (pcbgolf-<tag>-cN), else the files in tools/."""
    d = os.path.join(D, 'pinsets')
    tags = sorted(os.listdir(d), key=len, reverse=True) if os.path.isdir(d) else []
    return next((t for t in tags if fn.startswith(f'pcbgolf-{t}-')), None)


def use_pinset(tag):
    import mkboard
    if tag: os.environ['PCBGOLF_PINSET'] = tag
    else: os.environ.pop('PCBGOLF_PINSET', None)
    mkboard._REPIN_CACHE.clear()
VIA_COST, RULES = 250, '0.090 mm'


def _quiet(fn, *a, **k):
    import io, contextlib
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **k)


def main():
    os.makedirs(SUB, exist_ok=True)
    rows = []
    import drc, lvs, mating, interfere
    files = sorted({f for pat in PATTERNS for f in glob.glob(os.path.join(BOARD, pat))})
    for p in files:
        fn = os.path.basename(p)
        vc, rules = VIA_COST, RULES
        s = score_board.score(p)
        nviol, viol = _quiet(drc.check, p, 0.09, 0)
        # a board that is wired wrong, cannot be plugged into, or whose parts
        # collide does not work, whatever it scores
        use_pinset(pinset_of(fn))
        lvs_ok, _ = _quiet(lvs.check, p)
        mate_ok = _quiet(mating.check, p)
        clash = _quiet(interfere.check, p)
        nshort = sum(1 for v in viol if v[0] < 0)
        # Take the completion figures from the board itself rather than from
        # the router's log: ratsnest measures which pads are actually joined by
        # copper, and the board file is what gets submitted.  The total is the
        # spanning-tree count, sum over nets of (pads - 1).
        import ratsnest
        unrouted, _ = ratsnest.analyse(p, verbose=0)
        pcb_r = load(p)
        _nets, _pads, _s, _v = ratsnest.items_of(pcb_r)
        from collections import Counter
        per = Counter(q['net'] for q in _pads)
        total = sum(c - 1 for c in per.values() if c >= 2)
        routed = total - unrouted
        rate = s['vias']/routed if routed else 0
        est = s['score'] + 50*rate*unrouted
        rows.append(dict(board=fn, via_cost=vc, rules=rules, layers=s['layers'],
                         outline=f"{s['W']} x {s['H']}", area=s['area'], Z=s['Z'],
                         volume=s['volume'], vias=s['vias'], segments=s['segments'],
                         track_mm=s['track_mm'],
                         routed=f"{routed}/{total}", unrouted=unrouted,
                         score=int(s['score']), vs_leader=int(s['score']-LEAD),
                         margin=f"{1-s['score']/LEAD:.0%}",
                         score_if_finished=int(est),
                         margin_if_finished=f"{1-est/LEAD:.0%}",
                         # extrapolating the finish cost at the run's own via
                         # rate only holds when the router nearly finished; the
                         # leftovers on a badly-stuck board are the hard ones
                         complete='yes' if unrouted == 0 else 'no',
                         drc_violations=nviol, drc_shorts=nshort,
                         lvs='pass' if lvs_ok else 'FAIL',
                         connectors_face_out='yes' if mate_ok else 'NO',
                         body_collisions=len(clash),
                         estimate_valid='yes' if unrouted <= 0.05*total else 'NO'))
    with open(os.path.join(SUB,'SCORE.csv'),'w',newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader()
        for r in rows: w.writerow(r)
    print(f"SCORE.csv: {len(rows)} measured boards")

    # Pick the board to submit. A board with open connections does not work,
    # so a complete one always wins on score alone; only if none is complete
    # does the finished-score estimate decide, and that estimate is only
    # meaningful on a board that nearly finished.
    # A board with a short does not work at all, so it is not a candidate
    # whatever it scores.
    rows = [r for r in rows if r['drc_violations'] == 0 and r['lvs'] == 'pass'
            and r['connectors_face_out'] == 'yes' and r['body_collisions'] == 0]
    if not rows:
        raise SystemExit('no routed board passes DRC, LVS, mating and interference')
    done = [r for r in rows if r['complete'] == 'yes']
    if done:
        best = min(done, key=lambda r: r['score'])
        print(f"complete boards: {len(done)}; best {best['board']} at {best['score']}")
    else:
        usable = [r for r in rows if r['estimate_valid'] == 'yes'] or rows
        if not any(r['estimate_valid'] == 'yes' for r in rows):
            print("WARNING: no board is within 5% of complete")
        best = min(usable, key=lambda r: r['score_if_finished'])
        print(f"WARNING: no complete board. Best candidate {best['board']} is "
              f"{best['unrouted']} connection(s) short.")
    pcb = load(os.path.join(BOARD, best['board']))
    with open(os.path.join(SUB,'placement.csv'),'w',newline='') as f:
        w = csv.writer(f)
        w.writerow(['ref','footprint','x_mm','y_mm','rotation_deg','side'])
        for fp in pcb.find_all('footprint'):
            ref = next((str(p[2]) for p in fp.find_all('property') if p[1]=='Reference'), '?')
            at = fp.find('at')
            w.writerow([ref, str(fp[1]).split(':')[-1], f"{at[1]:.3f}", f"{at[2]:.3f}",
                        at[3] if len(at)>3 else 0,
                        'bottom' if fp.val('layer')=='B.Cu' else 'top'])
    print(f"placement.csv from {best['board']}")

    # The BOM is derived from the board being submitted, not from a placement
    # file: make_package built it from place_opt.json, which is a different
    # BOM and still listed R11 -- a part this board deliberately does not fit.
    # Reading the board makes that impossible.
    import json as _json
    from parts import SWAPS
    NL = _json.load(open(os.path.join(D, 'netlist.json')))
    comps = NL.get('comps', {})
    # Each part's original footprint comes from the upstream board. Inverting
    # the swap table instead says every SOT23-5 used to be a SOIC-8, which
    # would list the Q2-Q9 MOSFETs (SOT23-5 all along) as converted op-amps.
    import lvs as _lvs
    orig_of = _lvs._original_footprints()
    def swap_of(ref, lib):
        o = orig_of.get(ref, lib)
        if o == lib: return o, None
        return o, next(c for c in SWAPS.get(o, []) if c['to'] == lib)
    from collections import defaultdict
    rows = defaultdict(list)
    for fp in pcb.find_all('footprint'):
        ref = next((str(q[2]) for q in fp.find_all('property')
                    if q[1] == 'Reference'), '?')
        lib = str(fp[1]).split(':')[-1]
        c = comps.get(ref, {})
        orig, sw = swap_of(ref, lib)
        rows[(orig, c.get('value', ''), c.get('mpn', ''), lib,
              sw['part'] if sw else '(unchanged)',
              sw['risk'] if sw else '-',
              sw['note'] if sw else '')].append(ref)
    with open(os.path.join(SUB, 'BOM.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['qty', 'refs', 'value', 'orig_footprint', 'orig_mpn',
                    'new_footprint', 'new_part', 'risk', 'rationale'])
        for k, refs in sorted(rows.items(), key=lambda kv: (-len(kv[1]), kv[0][0])):
            orig, val, mpn, lib, part, risk, note = k
            # spell the columns out: a bare k[1:] is 8 fields against a
            # 9-column header, which silently drops orig_footprint and shifts
            # everything after it one place left
            w.writerow([len(refs), ' '.join(sorted(refs)), val, orig, mpn,
                        lib, part, risk, note])
    nparts = sum(len(v) for v in rows.values())
    print(f"BOM.csv: {nparts} parts in {len(rows)} lines, from {best['board']}")
    not_fitted = sorted(set(comps) - {r for v in rows.values() for r in v})
    if not_fitted:
        print(f"  not fitted: {', '.join(not_fitted)}")

    # Exactly what is left to close by hand on the chosen board, so the
    # remaining work is a list rather than a hunt.
    import ratsnest as R
    nmiss, missing = R.analyse(os.path.join(BOARD, best['board']), verbose=0)
    with open(os.path.join(SUB, 'UNROUTED.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['net', 'connections_short', 'pads_on_net'])
        for nm, k, npads in missing:
            w.writerow([nm, k, npads])
    print(f"UNROUTED.csv: {nmiss} connection(s) across {len(missing)} net(s)")

    # the assembly, from the same placed geometry the volume is measured from
    import step_assembly
    for old_f in glob.glob(os.path.join(SUB, '*.kicad_pcb')) + glob.glob(os.path.join(SUB, '*.step')):
        os.remove(old_f)
    import shutil
    shutil.copy(os.path.join(BOARD, best['board']), os.path.join(SUB, best['board']))
    step = os.path.join(SUB, best['board'].replace('.kicad_pcb', '.step'))
    _quiet(step_assembly.export, os.path.join(BOARD, best['board']), step)
    print(f"{os.path.basename(step)} and {best['board']} written to submission/")

    # the firmware pin map that goes with this board's pin assignment
    tag = pinset_of(best['board'])
    fw = (os.path.join(D, 'pinsets', tag, 'FIRMWARE_PINMAP.md') if tag
          else os.path.join(os.path.dirname(D), 'FIRMWARE_PINMAP.md'))
    shutil.copy(fw, os.path.join(SUB, 'FIRMWARE_PINMAP.md'))

    # the schematic netlist, from the netlist the board was built and checked against
    with open(os.path.join(SUB, 'netlist.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['net', 'pin_count', 'pins'])
        for nm, pins in sorted(NL['nets'].items(), key=lambda kv: (-len(kv[1]), kv[0])):
            if len(pins) < 2: continue
            w.writerow([nm, len(pins), ' '.join(f"{r}.{p}" for r, p, _, _ in pins)])
    return best, rows


def make_zip(out):
    """submission/ plus what is needed to open and check the board: the
    generated footprints and 3D models it references, the firmware pin map and
    the writeup."""
    import zipfile
    root = os.path.dirname(D)
    pre = 'pcbgolf-submission/'
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for f in sorted(os.listdir(SUB)):
            z.write(os.path.join(SUB, f), pre + f)
        for f in ('FINDINGS.md',):
            z.write(os.path.join(root, f), pre + f)
        for d in ('pcbgolf-gen.pretty', 'pcbgolf-gen.3dshapes'):
            for f in sorted(os.listdir(os.path.join(root, d))):
                z.write(os.path.join(root, d, f), pre + d + '/' + f)
    return out

if __name__ == '__main__':
    best, rows = main()
    if os.path.exists(os.path.join(SUB, 'README.md')):
        z = make_zip(os.path.join(os.path.dirname(D), 'pcbgolf-submission.zip'))
        print(f"packaged -> {z}")
    print(f"\nbest by finished-score: {best['board']} -> {best['score']} now, "
          f"~{best['score_if_finished']} finished ({best['margin_if_finished']})")
