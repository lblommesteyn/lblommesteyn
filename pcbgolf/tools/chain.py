"""Route in resumable chunks, so a restart or a time limit costs one chunk.

Freerouting writes its session only when it finishes, so a long uncapped run
that is killed -- by the 2-hour task limit, or by a container restart, which
took out two runs at pass 25 and pass 15 -- loses everything. This runs the
router in chunks of N passes, imports and verifies each chunk's result into
board/, and resumes the next chunk from it. Re-running the same command picks
up from the last finished chunk.

    python3 chain.py BOARD --tag NAME [--chunk 10] [--max-chunks 8] [--via-cost 250]
"""
import os, sys, json, argparse
D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, D)
import route

BOARD_DIR = os.path.join(os.path.dirname(D), 'board')


def chain(board, tag, chunk=10, max_chunks=8, via_cost=250, resume_first=False,
          stall=2, threads=3, ripup_continue=False):
    state_f = os.path.join(route.SCRATCH, f'chain-{tag}.json')
    st = json.load(open(state_f)) if os.path.exists(state_f) else {'done': [], 'best': None}
    base = board
    cur = st['done'][-1]['out'] if st['done'] else board
    flat = 0
    for i in range(len(st['done']), max_chunks):
        out = os.path.join(BOARD_DIR, f'pcbgolf-{tag}-c{i+1}.kicad_pcb')
        # Freerouting's rip-up cost is start x pass number, and a resumed run
        # counts passes from 1 again, so it opens by cheaply ripping up the
        # routing it was handed. Continuing the schedule starts it where the
        # previous chunk stopped.
        done_passes = sum(d.get('passes', chunk) for d in st['done'])
        ripup = 100 * done_passes if (ripup_continue and done_passes) else None
        res = route.run(cur, out, passes=chunk, via_cost=via_cost, ripup=ripup,
                        resume=(i > 0 or resume_first), base=base, tag=f'{tag}-c{i+1}',
                        threads=threads)
        if res is None:
            print(f'[{tag}] chunk {i+1}: no session'); break
        res['out'] = out
        res['passes'] = chunk
        st['done'].append(res)
        prev = st['best']
        if prev is None or (res['short'], res['vias']) < (prev['short'], prev['vias']):
            st['best'] = res; flat = 0
        else:
            flat += 1
        json.dump(st, open(state_f, 'w'), indent=1)
        cur = out
        if res['short'] == 0 or flat >= stall:
            break
    b = st['best']
    if b:
        print(f"[{tag}] best: {os.path.basename(b['out'])}  short {b['short']}  "
              f"vias {b['vias']}  score {b['score']:.0f}")
    return st


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('board'); ap.add_argument('--tag', required=True)
    ap.add_argument('--chunk', type=int, default=10)
    ap.add_argument('--max-chunks', type=int, default=8)
    ap.add_argument('--via-cost', type=int, default=250)
    ap.add_argument('--resume-first', action='store_true')
    ap.add_argument('--threads', type=int, default=3)
    ap.add_argument('--ripup-continue', action='store_true')
    a = ap.parse_args()
    chain(a.board, a.tag, a.chunk, a.max_chunks, a.via_cost, a.resume_first,
          threads=a.threads, ripup_continue=a.ripup_continue)
