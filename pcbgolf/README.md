# PCBGolf attack toolchain

Quantitative tooling for the [commaai/PCBGolf](https://github.com/commaai/PCBGolf)
challenge: *make the tiniest PCBA you can*.

```
score = PCBA bounding-box volume (mm^3) + 50 x vias + 5,000 x copper layers
```

Leaderboard to beat: **84,578** (abijahkaj), then 116,226 (Dsalzman).
Deadline 12 October 2026.

> ## ⚠️ Status: analysis, not a submission
>
> This repository contains **no `.kicad_pcb` and no STEP file**, so it is not a
> scoreable PCBGolf entry. There is no routed board behind the numbers below.
>
> What *is* here: a measured teardown of the challenge, a rebuilt netlist, legal
> overlap-free placements, and a score model. **Board areas and heights are
> measured; via counts are modelled, not measured** — see
> [FINDINGS §10](FINDINGS.md) for everything that is not yet proven.
>
> The scores below are therefore *projections* for architectures that have not
> been built or routed.

**[FINDINGS.md](FINDINGS.md) is the writeup** — what was measured, which ideas
survived, and which died.

## Headline results

| design | volume | vias | layers | score | vs 84,578 |
|---|---|---|---|---|---|
| stock BOM, just repacked, 4L, 400 vias | 20,479 | 20,000 | 20,000 | 60,479 | −28% |
| optimised BOM, 4L double-sided, 300 vias | 11,760 | 15,000 | 20,000 | 46,760 | −45% |
| 2L single-sided + 0-ohm jumpers, 90 vias | 23,494 | 4,500 | 10,000 | 37,994 | −55% |
| **optimised BOM, 2L double-sided, 300 vias** | 11,760 | 15,000 | 10,000 | **36,760** | **−57%** |

The stock BOM — change no parts at all, just pack it onto 42×46 mm — already
scores ~60,000. **Via counts are modelled, not yet measured** (see FINDINGS §10);
the board areas are measured from legal, overlap-free placements.

The three biggest findings:

1. **Volume is the smallest term.** At a 7 mm-tall board one via costs the same
   as 7.1 mm^2 of board, and one copper layer costs 714 mm^2. Optimising purely
   for a small outline fights for the least valuable ~23% of the score.
2. **Fine-pitch BGA is net-negative** — escape vias cost more than the area they
   save. LQFP-100 beats TFBGA100 and UFBGA169.
3. **A 0201 zero-ohm jumper costs 5.2 points; a via costs 50.** Resolving planar
   crossings with jumpers instead of vias is 9.6x cheaper and doesn't touch the
   via term at all.

## Tools

| file | does |
|---|---|
| `sexpr.py` | KiCad s-expression parser |
| `pcb.py` | board / footprint / courtyard extraction |
| `fplib.py` | real pad geometry from `pcbgolf.pretty` |
| `netlist.py` | rebuilds the netlist from the 5 schematic sheets (the `.kicad_pcb` has none) — 1053/1053 pins resolve onto wires |
| `step_bbox.py` | component heights from the shipped STEP models |
| `parts.py` | replacement candidates + component heights |
| `geom2.py` | corrected placement geometry: full envelopes, footprint-origin offsets, per-connector edge rules |
| `gridpack.py` | legal-by-construction placer (perimeter connectors as obstacles + integral-image bottom-left fill, annealed) |
| `dsn.py` / `ses.py` | Specctra export + session analysis for autorouted via counts |
| `scorecard.py` | score model driven by measured placements |
| `render.py` | SVG renders of a placement |
| `make_package.py` | regenerates `submission/` and builds the distributable zip |

Requires `numpy`. Expects `commaai/PCBGolf` checked out at
`/home/user/commaai/pcbgolf` (paths at the top of `pcb.py` / `fplib.py` /
`netlist.py`).

```
python3 tools/netlist.py      # rebuild + sanity-check the netlist
python3 tools/run_grid.py     # placement sweep
python3 tools/scorecard.py    # score table
python3 tools/render.py       # placement SVGs
python3 tools/make_package.py # regenerate submission/ + zip
```
