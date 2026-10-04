"""Regenerate submission/ from an actually-routed board."""
import sys, os, csv, json
D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, D)
from sexpr import load
import score_board
SUB = os.path.join(os.path.dirname(D), 'submission')
BOARD = os.path.join(os.path.dirname(D), 'board')
LEAD = 84578

VARIANTS = [
    # LQFP-100 BOM at 0.09mm rules, 0.45mm vias, correct DSN scale.
    # -r2 is autorouter + resume + finish_router; -ok is without the resume.
    ('pcbgolf-t44x46-r2.kicad_pcb', 250, '0.090 mm'),
    ('pcbgolf-t44x46-ok.kicad_pcb', 250, '0.090 mm'),
    ('pcbgolf-t45x47-r2.kicad_pcb', 250, '0.090 mm'),
    ('pcbgolf-t45x47-ok.kicad_pcb', 250, '0.090 mm'),
    ('pcbgolf-t46x48-ok.kicad_pcb', 250, '0.090 mm'),
    ('pcbgolf-t48x50-best.kicad_pcb', 250, '0.090 mm'),
    # LQFP-144 BOM, the earlier larger boards, for comparison
    ('pcbgolf-v250-4L.kicad_pcb', 250, '0.100 mm'),
    ('pcbgolf-routed-2L.kicad_pcb', 120, '0.127 mm'),
]

def main():
    os.makedirs(SUB, exist_ok=True)
    rows = []
    for fn, vc, rules in VARIANTS:
        p = os.path.join(BOARD, fn)
        if not os.path.exists(p): continue
        s = score_board.score(p)
        import drc
        nviol, viol = drc.check(p, 0.09, 0)
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
    rows = [r for r in rows if r['drc_shorts'] == 0] or rows
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
    back = {}
    for _fp, _lst in SWAPS.items():
        for _c in _lst:
            back.setdefault(_c['to'], (_fp, _c))
    from collections import defaultdict
    rows = defaultdict(list)
    for fp in pcb.find_all('footprint'):
        ref = next((str(q[2]) for q in fp.find_all('property')
                    if q[1] == 'Reference'), '?')
        lib = str(fp[1]).split(':')[-1]
        c = comps.get(ref, {})
        orig, sw = back.get(lib, (lib, None))
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
    return best, rows

if __name__ == '__main__':
    best, rows = main()
    print(f"\nbest by finished-score: {best['board']} -> {best['score']} now, "
          f"~{best['score_if_finished']} finished ({best['margin_if_finished']})")
