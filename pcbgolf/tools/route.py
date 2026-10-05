"""Route a board with Freerouting and verify the result, end to end.

One command instead of a shell paragraph per experiment, so that every run
records the same things:

    python3 route.py BOARD.kicad_pcb -o OUT.kicad_pcb [--passes 26] [--via-cost 250]
        [--ripup N] [--optimize] [--opt-timeout 00:30:00] [--threads 3] [--resume]

--resume hands the board's existing copper back to the router (pcb2dsn emits
it as a (wiring) section).  Settings go in as FREEROUTING__ROUTER__* env vars;
the log is checked for "Unknown router setting" so a misspelt one fails loudly
rather than being ignored, which is how a pass cap once went unapplied.

After import: validate, LVS, DRC, ratsnest and the score, one summary line.
"""
import os, sys, re, subprocess, argparse, shutil, json, time
D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, D)

SCRATCH = os.environ.get('PCBGOLF_SCRATCH',
          '/tmp/claude-0/-home-user-lblommesteyn/2caecacf-01d9-5802-a2b6-a2ddf9735640/scratchpad')
JAR = os.path.join(SCRATCH, 'fr/scripts/benchmark/binaries/freerouting-2.5.0-RC5.jar')
JAVA = '/usr/lib/jvm/java-25-openjdk-amd64/bin/java'


def run(board, out, passes=26, via_cost=250, ripup=None, optimize=False,
        opt_timeout='00:30:00', opt_passes=None, threads=3, resume=False,
        track=0.09, clearance=0.09, via_dia=0.45, via_drill=0.2, tag=None,
        base=None, extra=None):
    import pcb2dsn, ses2pcb
    tag = tag or os.path.splitext(os.path.basename(out))[0]
    dsn = os.path.join(SCRATCH, f'{tag}.dsn')
    ses = os.path.join(SCRATCH, f'{tag}.ses')
    log = os.path.join(SCRATCH, f'{tag}.log')
    if os.path.exists(ses): os.remove(ses)

    src = board
    if not resume:
        # strip routing so the router starts clean
        from sexpr import load, dumps
        pcb = load(board)
        pcb[:] = [c for c in pcb if not (isinstance(c, list) and c and
                                         c[0] in ('segment', 'via', 'arc'))]
        src = os.path.join(SCRATCH, f'{tag}.unrouted.kicad_pcb')
        open(src, 'w').write(dumps(pcb) + '\n')
    pcb2dsn.export(src, dsn, track, clearance, via_dia, via_drill)

    env = dict(os.environ)
    env.update({
        'FREEROUTING__ROUTER__FANOUT__ENABLED': 'false',
        'FREEROUTING__ROUTER__SCORING__VIA_COSTS': str(via_cost),
        'FREEROUTING__ROUTER__SCORING__PLANE_VIA_COSTS': str(via_cost),
        'FREEROUTING__ROUTER__AUTOROUTER__MAX_PASSES': str(passes),
        'FREEROUTING__ROUTER__MAX_THREADS': str(threads),
    })
    if ripup is not None:
        env['FREEROUTING__ROUTER__SCORING__START_RIPUP_COSTS'] = str(ripup)
    if optimize:
        env['FREEROUTING__ROUTER__OPTIMIZER__ENABLED'] = 'true'
        env['FREEROUTING__ROUTER__OPTIMIZER__ENABLE_PREFLIGHT_GUARDS'] = 'false'
        env['FREEROUTING__ROUTER__OPTIMIZER__TIMEOUT'] = opt_timeout
        if opt_passes is not None:
            env['FREEROUTING__ROUTER__OPTIMIZER__MAX_PASSES'] = str(opt_passes)
    # arbitrary extra settings, 'optimizer.max_passes=20' style
    for kv in (extra or []):
        k, v = kv.split('=', 1)
        env['FREEROUTING__ROUTER__' + k.replace('.', '__').upper()] = v
    want = sum(1 for k in env if k.startswith('FREEROUTING__ROUTER__'))

    t0 = time.time()
    with open(log, 'w') as lf:
        rc = subprocess.call([JAVA, '-Dgui.enabled=false', '-jar', JAR,
                              '-de', dsn, '-do', ses], cwd=SCRATCH, env=env,
                             stdout=lf, stderr=subprocess.STDOUT)
    mins = (time.time() - t0) / 60
    text = open(log, errors='replace').read()
    unknown = re.findall(r'Unknown router setting[^\n]*', text)
    parsed = re.search(r'Parsed (\d+) router setting', text)
    if unknown:
        raise SystemExit('settings rejected:\n  ' + '\n  '.join(unknown))
    if not parsed or int(parsed.group(1)) != want:
        raise SystemExit(f'expected {want} settings parsed, log says '
                         f'{parsed.group(1) if parsed else "none"}')
    stages = re.findall(r'(Auto-routing stage completed[^\n]*|Skipping optimization[^\n]*|'
                        r'[Oo]ptimi[sz]ation stage [^\n]*|[Oo]ptimizer [^\n]*completed[^\n]*)', text)
    if not os.path.exists(ses):
        print(f'[{tag}] NO SESSION after {mins:.0f} min, rc={rc}')
        for s in stages: print('   ', s[:170])
        return None

    ses2pcb.apply(base or board, ses, out, via_dia, via_drill)
    return summarize(out, tag, mins, stages)


def summarize(out, tag='', mins=0.0, stages=()):
    import io, contextlib, validate, lvs, drc, ratsnest, score_board
    q = io.StringIO()
    with contextlib.redirect_stdout(q):
        v_ok = validate.check(out)
        l_ok, l_err = lvs.check(out, verbose=0)
        n_drc, bad = drc.check(out, 0.09, 0)
        miss, _ = ratsnest.analyse(out, verbose=0)
        sc = score_board.score(out)
    shorts = sum(1 for b in bad if b[0] < 0)
    res = dict(board=os.path.basename(out), minutes=round(mins), vias=sc['vias'],
               short=miss, drc=n_drc, shorts=shorts, validate=bool(v_ok),
               lvs=bool(l_ok), volume=sc['volume'], score=sc['score'],
               margin=sc['margin'])
    for s in stages: print('   ', s[:170])
    print(f"[{tag}] vias {res['vias']}  short {miss}  drc {n_drc}/{shorts} shorts  "
          f"validate {'ok' if v_ok else 'FAIL'}  lvs {'ok' if l_ok else 'FAIL'}  "
          f"score {res['score']:.0f} ({res['margin']})  {res['minutes']} min")
    with open(os.path.join(SCRATCH, 'routes.jsonl'), 'a') as f:
        f.write(json.dumps(dict(res, tag=tag)) + '\n')
    return res


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('board'); ap.add_argument('-o', '--out', required=True)
    ap.add_argument('--passes', type=int, default=26)
    ap.add_argument('--via-cost', type=int, default=250)
    ap.add_argument('--ripup', type=int)
    ap.add_argument('--optimize', action='store_true')
    ap.add_argument('--opt-timeout', default='00:30:00')
    ap.add_argument('--opt-passes', type=int)
    ap.add_argument('--threads', type=int, default=3)
    ap.add_argument('--resume', action='store_true')
    ap.add_argument('--base', help='unrouted board to import the session onto')
    ap.add_argument('--set', action='append', default=[],
                    help="any router setting, e.g. --set optimizer.max_passes=20")
    ap.add_argument('--tag')
    a = ap.parse_args()
    run(a.board, a.out, a.passes, a.via_cost, a.ripup, a.optimize, a.opt_timeout,
        a.opt_passes, a.threads, a.resume, base=a.base, extra=a.set, tag=a.tag)
