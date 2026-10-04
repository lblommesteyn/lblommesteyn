# PCBGolf attack toolchain

Quantitative tooling for the [commaai/PCBGolf](https://github.com/commaai/PCBGolf)
challenge: *make the tiniest PCBA you can*.

```
score = PCBA bounding-box volume (mm^3) + 50 x vias + 5,000 x copper layers
```

Leaderboard to beat: **84,578** (abijahkaj), then 116,226 (Dsalzman).
Deadline 12 October 2026.

> ## Status: routed boards, measured scores
>
> There are generated, validated `.kicad_pcb` files in [`board/`](board), a
> STEP assembly built from the real component models, and scores measured from
> them rather than modelled. Every figure below comes from a file in this
> repository.
>
> Two things are not finished: the best routed board still has a couple of dozen
> connections the autorouter left open, and the LQFP-100 pin remap has been
> checked signal-by-signal but not simulated.

**[FINDINGS.md](FINDINGS.md) is the writeup** — what was measured, which ideas
survived, and which died.

## Headline results

Measured from the boards in [`board/`](board). Volume is the 3D assembly
bounding box from `bbox3d.py`, not outline x height; vias are counted from the
file.

| design | outline | Z | volume | vias | layers | score | vs 84,578 |
|---|---|---|---|---|---|---|---|
| stock BOM, 4L, via cost 250 | 50.05 x 52.78 | 14.35 | 37,904 | 351 | 4 | 75,454 | −11% |
| stock BOM, 4L, via cost 400 | 50.05 x 52.78 | 14.35 | 37,904 | 317 | 4 | 73,754 | −13% |
| **LQFP-100 BOM, 4L** *(routing)* | 44.05 x 46.78 | 14.20 | 29,258 | — | 4 | — | — |

The LQFP-100 board is the submission candidate: same die and flash in a 14x14 mm
package instead of 20x20, which takes 8,646 mm^3 out of the volume. Its route is
the number still outstanding.

### Height is the floor, not the lever

```
Z = 11.00 (barrel jack) + 1.60 (board) + 1.60 (tallest back-side part) = 14.20
```

The jack is 78% of the stack, and it is fixed: the mating plug has to stay
compatible, so the part stays. Front-side height under 11 mm is therefore
**free**, and the only height that costs anything is the back side's tallest
part. Thinning the board does not help either — the 2x4 header's 3.0 mm lead
tail takes over below 1.2 mm, so 0.8 mm FR4 buys 0.2 mm of Z (see FINDINGS).

Everything left is area and vias.

The three biggest findings:


1. **Volume is the smallest term.** At the real 14.2 mm stack one via costs the
   same as 3.5 mm^2 of board, and one copper layer costs 352 mm^2. Optimising
   purely for a small outline fights for the least valuable ~44% of the score.
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
