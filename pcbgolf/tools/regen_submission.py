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
    # file, via cost, rules, unrouted
    ('pcbgolf-finished-4L.kicad_pcb', 250, '0.100 mm', 9),
    ('pcbgolf-v800-4L.kicad_pcb', 800, '0.100 mm', 155),
    ('pcbgolf-v400-4L.kicad_pcb', 400, '0.100 mm', 50),
    ('pcbgolf-v250-4L.kicad_pcb', 250, '0.100 mm', 23),
    ('pcbgolf-fine-4L.kicad_pcb', 120, '0.100 mm', 16),
    ('pcbgolf-routed-4L.kicad_pcb', 120, '0.127 mm', 48),
    ('pcbgolf-routed-2L.kicad_pcb', 120, '0.127 mm', 193),
]

def main():
    os.makedirs(SUB, exist_ok=True)
    rows = []
    for fn, vc, rules, unrouted in VARIANTS:
        p = os.path.join(BOARD, fn)
        if not os.path.exists(p): continue
        s = score_board.score(p)
        routed = 748 - unrouted
        rate = s['vias']/routed if routed else 0
        est = s['score'] + 50*rate*unrouted
        rows.append(dict(board=fn, via_cost=vc, rules=rules, layers=s['layers'],
                         outline=f"{s['W']} x {s['H']}", area=s['area'], Z=s['Z'],
                         volume=s['volume'], vias=s['vias'], segments=s['segments'],
                         track_mm=s['track_mm'],
                         routed=f"{routed}/748", unrouted=unrouted,
                         score=int(s['score']), vs_leader=int(s['score']-LEAD),
                         margin=f"{1-s['score']/LEAD:.0%}",
                         score_if_finished=int(est),
                         margin_if_finished=f"{1-est/LEAD:.0%}",
                         # extrapolating the finish cost at the run's own via
                         # rate only holds when the router nearly finished; the
                         # leftovers on a badly-stuck board are the hard ones
                         estimate_valid='yes' if unrouted <= 0.05*748 else 'NO'))
    with open(os.path.join(SUB,'SCORE.csv'),'w',newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader()
        for r in rows: w.writerow(r)
    print(f"SCORE.csv: {len(rows)} measured boards")

    # placement + netlist from the best-scoring board
    usable = [r for r in rows if r['estimate_valid'] == 'yes']
    if not usable:
        usable = rows
        print("WARNING: no board is within 5% of complete")
    best = min(usable, key=lambda r: r['score_if_finished'])
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
    return best, rows

if __name__ == '__main__':
    best, rows = main()
    print(f"\nbest by finished-score: {best['board']} -> {best['score']} now, "
          f"~{best['score_if_finished']} finished ({best['margin_if_finished']})")
