"""Finish a nearly-routed board by letting Freerouting re-solve a window.

Routing each missing connection alone around fixed copper fails because the
way through is taken, and resuming Freerouting on the whole board re-rips
everything at low cost and undoes good routing. This does neither: for each
gap it locks all copper outside a window around it, so Freerouting receives
it as protected wiring, strips everything inside the window, and lets
Freerouting route the window from scratch -- gridless, at the board's own
minimum pitch, with its full rip-up-and-reroute schedule confined to the
window. The old routing is a legal solution of the window except the gap, so
the window is never harder than the board was. A result is kept only if no
connection is lost, the gap count falls, and drc.py finds nothing.

    PCBGOLF_PINSET=TAG python3 winroute.py BOARD.kicad_pcb -o OUT.kicad_pcb
"""
import os, sys, argparse, io, contextlib, copy, time
D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, D)
from sexpr import load, dumps, Q
import route, drc, ratsnest, ripup
from finish_router import n as N

TMPLOCK = 'pcbgolf_tmp_lock'


def missing_of(path):
    with contextlib.redirect_stdout(io.StringIO()):
        return ratsnest.analyse(path, verbose=0)[0]


def lock_outside(pcb, box):
    """Lock every unlocked segment/via not wholly inside box (marked so the
    lock can be undone), and delete the unlocked copper inside."""
    bx0, by0, bx1, by1 = box
    inside = lambda x, y: bx0 <= x <= bx1 and by0 <= y <= by1
    keep = []
    for c in pcb:
        if isinstance(c, list) and c and c[0] in ('segment', 'via'):
            if c.val('locked') == 'yes':
                keep.append(c); continue
            pts = ([(c.find('start')[1], c.find('start')[2]), (c.find('end')[1], c.find('end')[2])]
                   if c[0] == 'segment' else [(c.find('at')[1], c.find('at')[2])])
            if all(inside(*p) for p in pts):
                continue                                   # ripped
            c2 = copy.deepcopy(c)
            lk = c2.find('locked')
            if lk is None:
                c2.insert(1, N('locked', 'yes'))
            c2.append(N_tag())
            keep.append(c2); continue
        keep.append(c)
    pcb[:] = keep


def N_tag():
    return N('tstamp', Q(TMPLOCK))


def unlock(pcb):
    for c in pcb:
        if isinstance(c, list) and c and c[0] in ('segment', 'via'):
            t = c.find('tstamp')
            if t is not None and str(t[1]) == TMPLOCK:
                c.remove(t)
                lk = c.find('locked')
                if lk is not None: c.remove(lk)


def run(path, outp, margins=(2.0, 3.5, 5.0), passes=30, via_cost=400, verbose=True):
    S = route.SCRATCH
    cur = load(path)
    open(outp, 'w').write(dumps(cur) + '\n')
    m0 = missing_of(outp)
    if verbose: print(f"  {os.path.basename(path)}: {m0} missing, {len(cur.find_all('via'))} vias")
    xs, ys = [], []
    for g in cur.find_all('gr_line'):
        if g.val('layer') != 'Edge.Cuts': continue
        for k in ('start', 'end'): q = g.find(k); xs.append(q[1]); ys.append(q[2])
    tried = set()
    while m0 > 0:
        progress = False
        for (net, nnum, a, b) in ripup.gaps(cur):
            key = (net, round(a[0], 1), round(a[1], 1))
            if key in tried: continue
            tried.add(key)
            for m in margins:
                box = (min(a[0], b[0]) - m, min(a[1], b[1]) - m,
                       max(a[0], b[0]) + m, max(a[1], b[1]) + m)
                work = copy.deepcopy(cur)
                lock_outside(work, box)
                tin = os.path.join(S, 'winroute.in.kicad_pcb')
                tout = os.path.join(S, 'winroute.out.kicad_pcb')
                open(tin, 'w').write(dumps(work) + '\n')
                t0 = time.time()
                with contextlib.redirect_stdout(io.StringIO()):
                    res = route.run(tin, tout, passes=passes, via_cost=via_cost, threads=2,
                                    tag='winroute', base=tin)
                if res is None or not os.path.exists(tout):
                    if verbose: print(f"    {net} +{m}mm: no session"); continue
                cand = load(tout); unlock(cand)
                open(tout, 'w').write(dumps(cand) + '\n')
                m1 = missing_of(tout)
                with contextlib.redirect_stdout(io.StringIO()):
                    nv, _ = drc.check(tout, 0.09, 0)
                nvia = len(cand.find_all('via'))
                if verbose:
                    print(f"    {net} +{m}mm: missing {m0} -> {m1}, DRC {nv}, vias {nvia} "
                          f"({time.time()-t0:.0f}s)")
                if nv == 0 and m1 < m0:
                    cur, m0 = cand, m1
                    open(outp, 'w').write(dumps(cur) + '\n')
                    progress = True
                    break
            if progress: break
        if not progress: break
    if verbose: print(f"  -> {m0} missing, {len(cur.find_all('via'))} vias: {outp}")
    return m0


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('pcb'); ap.add_argument('-o', '--out', required=True)
    ap.add_argument('--passes', type=int, default=30)
    ap.add_argument('--via-cost', type=int, default=400)
    a = ap.parse_args()
    run(a.pcb, a.out, passes=a.passes, via_cost=a.via_cost)
