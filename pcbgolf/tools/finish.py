"""Drive a converged route to completion: rip up, resume, keep the best, repeat.

Freerouting stops with a handful of connections it cannot fit, because the
space they need is held by nets it routed earlier. Each round here clears other
nets' copper from a corridor around every remaining gap (ripup.py), hands the
board back to the router with its remaining copper (route.py --resume), and
keeps the result only if it is better -- fewer open connections, then fewer
vias. The corridor widens when a round makes no progress, and narrows back
after one that does, so it disturbs as little as it can.

    python3 finish.py BOARD -o OUT [--rounds 8] [--passes 14]
"""
import os, sys, shutil, argparse, json
D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, D)
import route, ripup


def key(r):
    return (r['short'], r['vias'])


def finish(board, out, rounds=8, passes=16, via_cost=250, radii=(0.5, 0.9, 1.4),
           base=None):
    S = route.SCRATCH
    tag0 = os.path.splitext(os.path.basename(out))[0]
    best_path = os.path.join(S, f'{tag0}.best.kicad_pcb')
    shutil.copy(board, best_path)
    best = route.summarize(best_path, f'{tag0}.start')
    if not best['lvs'] or best['shorts']:
        raise SystemExit('starting board fails LVS or has shorts; refusing to iterate on it')
    ri = 0
    for r in range(1, rounds + 1):
        if best['short'] == 0:
            break
        rad = radii[min(ri, len(radii) - 1)]
        ripped = os.path.join(S, f'{tag0}.r{r}.ripped.kicad_pcb')
        ripup.ripup(best_path, ripped, radius=rad, verbose=False, mode='ends')
        cand = os.path.join(S, f'{tag0}.r{r}.kicad_pcb')
        res = route.run(ripped, cand, passes=passes, via_cost=via_cost, resume=True,
                        base=base or board, tag=f'{tag0}.r{r}')
        if res is None:
            print(f'  round {r}: radius {rad}: no session'); ri += 1; continue
        ok = res['lvs'] and res['shorts'] == 0 and res['validate']
        better = ok and key(res) < key(best)
        print(f"  round {r}: radius {rad} -> short {res['short']}, vias {res['vias']}"
              f"{'  KEPT' if better else ''}")
        if better:
            best = res; shutil.copy(cand, best_path); ri = max(0, ri - 1)
        else:
            ri += 1
    shutil.copy(best_path, out)
    print(f"[{tag0}] final: short {best['short']}  vias {best['vias']}  "
          f"score {best['score']:.0f} ({best['margin']})")
    return best


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('board'); ap.add_argument('-o', '--out', required=True)
    ap.add_argument('--rounds', type=int, default=8)
    ap.add_argument('--passes', type=int, default=16)
    ap.add_argument('--via-cost', type=int, default=250)
    ap.add_argument('--base', help='unrouted board for session import')
    a = ap.parse_args()
    finish(a.board, a.out, a.rounds, a.passes, a.via_cost, base=a.base)
