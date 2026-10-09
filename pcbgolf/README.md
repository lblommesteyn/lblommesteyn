# PCBGolf attack toolchain

Quantitative tooling for the [commaai/PCBGolf](https://github.com/commaai/PCBGolf)
challenge: *make the tiniest PCBA you can*.

```
score = PCBA bounding-box volume (mm^3) + 50 x vias + 5,000 x copper layers
```

Leaderboard to beat: **84,578** (abijahkaj), then 116,226 (Dsalzman).
Deadline 12 October 2026.

> ## Status: complete — 64,038, 24% under the leaderboard
>
> `submission/` holds a fully routed board: 44.0 x 46.0 x 12.0 mm, 4 layers,
> 395 vias, 0 connections missing, 0 DRC violations, LVS pass, every edge
> connector opening on the outline, no colliding bodies. Every figure is
> measured from the file.

**[FINDINGS.md](FINDINGS.md) is the writeup** — what was measured, which ideas
survived, which died, and the conclusions that turned out to be wrong.

## Headline results

| board | outline | Z | volume | vias | short | score | vs 84,578 |
|---|---|---|---|---|---|---|---|
| **4L, submitted** | 44.0 x 46.0 | 12.0 | 24,288 | 395 | **0** | **64,038** | **−24%** |
| 4L, same placement | 44.0 x 46.0 | 12.0 | 24,288 | 398 | 0 | 64,188 | −24% |
| 6L | 46.0 x 48.0 | 12.0 | 26,496 | 369 | **0** | 74,946 | −11% |
| 4L, same placement, another run | 44.0 x 46.0 | 12.0 | 24,288 | 417 | 1 | — | not finished |

All measured by the same checks (`tools/regen_submission.py`, `submission/SCORE.csv`).
A board short of even one connection does not work, so only complete boards
are candidates; the submitted one is the best of them.

Earlier boards in `board/`, including the first submission, are not valid:
their edge connectors faced into the board and their copper crossed
mechanical holes (FINDINGS §12).

### Height

```
Z = 9.0 (CUI PJ-063AH jack) + 1.2 (board) + 1.8 (jack pins and header tails below) = 12.0
```

The PJ-063AH takes the same 5.5/2.0 mm plug as the original jack and stands
2 mm lower. Its pins reach 3.0 mm below the top face, which makes Z = 12.0 for
any board from 0.8 to 1.4 mm.

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
| `drc.py` | copper clearance by exact swept geometry, including copper against non-plated holes |
| `lvs.py` | layout vs schematic: pin-set partitions, through every package pin map, MCU remap and declared swap |
| `mating.py` | finds each edge connector's plug opening from its 3D model and checks it is on the outline |
| `test_mating.py` | checks the recorded opening directions and body faces against the models |
| `interfere.py` | 3D interference between every pair of component bodies |
| `aplace.py` | quadratic placement with spreading, over every edge-connector assignment |
| `pinopt.py` | pin and gate swapping: MCU pins, USB hub ports and polarity, 180-degree flips |
| `pcb2dsn.py` / `ses2pcb.py` | Specctra export (holes as obstacles) and session import |
| `route.py` / `chain.py` | Freerouting runs, verified on import; resumable chunks that survive restarts |
| `cvm.py` | constrained via minimisation: same copper, layers re-chosen by integer programme to delete vias |
| `regen_submission.py` | regenerates `submission/` from the routed boards that pass every check |

Requires `numpy`, and `cadquery-ocp` for the 3D measurement and STEP export.
Expects `commaai/PCBGolf` checked out at
`/home/user/commaai/pcbgolf` (paths at the top of `pcb.py` / `fplib.py` /
`netlist.py`).

```
python3 tools/netlist.py      # rebuild + sanity-check the netlist
python3 tools/run_grid.py     # placement sweep
python3 tools/scorecard.py    # score table
python3 tools/render.py       # placement SVGs
python3 tools/regen_submission.py  # regenerate submission/ from the routed boards
```
