# PCBGolf attack toolchain

Quantitative tooling for the [commaai/PCBGolf](https://github.com/commaai/PCBGolf)
challenge: *make the tiniest PCBA you can*.

```
score = PCBA bounding-box volume (mm^3) + 50 x vias + 5,000 x copper layers
```

Leaderboard to beat: **84,578** (abijahkaj), then 116,226 (Dsalzman).
Deadline 12 October 2026.

> ## Status: routed, clearance-clean, not finished
>
> `board/` holds generated, validated `.kicad_pcb` files and a STEP assembly
> built from the real component models. Every figure below is measured from a
> file in this repository.
>
> **No board is fully routed.** The best is 9 connections short of 741, so every
> score here is for a board that does not yet work. Closing the rest costs
> roughly a via each; `submission/UNROUTED.csv` names them.

**[FINDINGS.md](FINDINGS.md) is the writeup** — what was measured, which ideas
survived, which died, and the four conclusions that turned out to be wrong.

## Headline results

Volume is the 3D assembly bounding box from `bbox3d.py`, not outline x height.
Connectivity is `ratsnest.py`, clearance is `drc.py`. All are **0 violations,
0 shorts**.

| design | outline | Z | volume | vias | short | score | vs 84,578 |
|---|---|---|---|---|---|---|---|
| **LQFP-100, 4L** | 44.05 x 46.78 | 14.20 | 29,258 | 414 | 14 | **69,958** | **−17%** |
| LQFP-100, 4L | 44.05 x 46.78 | 14.20 | 29,258 | 420 | 9 | 70,258 | −17% |
| LQFP-100, 4L | 46.05 x 48.78 | 14.20 | 31,895 | 362 | 20 | 69,994 | −17% |
| LQFP-100, 4L | 48.05 x 50.78 | 14.20 | 34,644 | 399 | 3 | 74,594 | −12% |
| LQFP-144, 4L | 50.05 x 52.78 | 14.35 | 37,904 | 351 | 23 | 75,454 | −11% |

The LQFP-100 swap is the biggest single win: same die, same flash, a 14x14mm
package instead of 20x20, worth 8,646 mm^3. It is audited pin by pin in
FINDINGS §8b — 15 signals moved, 0 failed, and R11 comes off the board because
the LQFP-100 has no PDR_ON pin for it to strap.

### Height is the floor, not the lever

```
Z = 11.00 (barrel jack) + 1.60 (board) + 1.60 (tallest back-side part) = 14.20
```

The jack is 78% of the stack and fixed: the mating plug has to stay compatible.
So front-side height under 11mm is **free**, and only the back side's tallest
part costs anything. Thinning the board does not help either — the 2x4 header's
3.0mm lead tail takes over below 1.2mm, so 0.8mm FR4 buys 0.2mm of Z.

### Area and vias trade off about 1:1

The four LQFP-100 outlines land within 300 points of each other: 44x46 saves
2,636 mm^3 against 46x48 and spends 58 more vias getting there. The outline
barely matters at this operating point, so the remaining levers are via count
and, above all, finishing the route — Freerouting's via optimizer only runs on a
complete board and has never run here.

The three biggest findings:



1. **Volume is the largest single term but the least movable.** At the real
   14.2 mm stack one via costs the same as 3.5 mm^2 of board and one copper
   layer costs 352 mm^2. Z is pinned by the jack and area trades 1:1 against
   vias, so the outline is not where the score is won.
2. **Fine-pitch BGA is net-negative** — escape vias cost more than the area they
   save. LQFP-100 beats TFBGA100 and UFBGA169.
3. **A 0201 zero-ohm jumper costs 10.6 points; a via costs 50.** Resolving
   planar crossings with jumpers instead of vias is 4.7x cheaper and doesn't
   touch the via term at all.

## Tools

| file | does |
|---|---|
| `sexpr.py` | KiCad s-expression parser |
| `pcb.py` | board / footprint / courtyard extraction |
| `fplib.py` | real pad geometry from `pcbgolf.pretty` |
| `netlist.py` | rebuilds the netlist from the 5 schematic sheets (the `.kicad_pcb` has none) — 1053/1053 pins resolve onto wires |
| `step_bbox.py` | component heights from the shipped STEP models |
| `bbox3d.py` | measured 3D assembly bounding box — the thing actually scored |
| `step_assembly.py` | STEP of the real assembly, from the same geometry `bbox3d` measures |
| `test_bbox3d.py` | pins the KiCad 3D placement convention against `kicad-cli` output |
| `parts.py` | replacement candidates + measured component heights and lead tails |
| `geom2.py` | corrected placement geometry: full envelopes, footprint-origin offsets, per-connector edge rules |
| `gridpack.py` | legal-by-construction placer (perimeter connectors as obstacles + integral-image bottom-left fill, annealed) |
| `dsn.py` / `ses.py` | Specctra export + session analysis for autorouted via counts |
| `scorecard.py` | score model driven by measured placements |
| `render.py` | SVG renders of a placement |
| `mkboard.py` | builds the `.kicad_pcb` by mutating the upstream valid file |
| `validate.py` / `collide.py` | file, outline, net and pad-overlap checks |
| `score_board.py` | the official formula against a real board file |
| `ratsnest.py` | per-net disjoint clusters, i.e. what is still unconnected |
| `make_package.py` | regenerates `submission/` and builds the distributable zip |

Requires `numpy`, and `cadquery-ocp` for the 3D measurement and STEP export.
Expects `commaai/PCBGolf` checked out at
`/home/user/commaai/pcbgolf` (paths at the top of `pcb.py` / `fplib.py` /
`netlist.py`).

```
python3 tools/netlist.py      # rebuild + sanity-check the netlist
python3 tools/run_grid.py     # placement sweep
python3 tools/scorecard.py    # score table
python3 tools/render.py       # placement SVGs
python3 tools/make_package.py # regenerate submission/ + zip
```
