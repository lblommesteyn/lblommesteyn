# PCBGolf — best design to date

**Luke Blommesteyn** · github.com/lblommesteyn · for [commaai/PCBGolf](https://github.com/commaai/PCBGolf)

```
score = PCBA bounding-box volume (mm^3) + 50 x vias + 5,000 x copper layers
```

## ⚠️ Read this first

**This is not a scoreable submission.** There is no `.kicad_pcb` and no STEP file
here, because no board has been routed. What follows is a design specified down
to BOM, placement and stackup, with a projected score.

* **Measured:** board outline, component envelopes, heights, placement (legal and
  overlap-free), netlist, part areas.
* **Modelled, not measured:** the via count, which is the load-bearing assumption.

## The design

| | |
|---|---|
| board | **40 x 42 mm** (1680 mm^2) |
| height | **7.0 mm** — floored by the DC barrel jack bore |
| stackup | **2 copper layers**, components both sides |
| volume | 11,760 mm^3 |
| vias | ~300 (modelled) |
| **projected score** | **36,760** |
| vs leaderboard (84,578) | **−57%** |

## Why this shape

At a 7 mm-tall board the exchange rates are:

| you spend | costs | equals |
|---|---|---|
| 1 via | 50 pts | **7.1 mm^2 of board** |
| 1 copper layer | 5,000 pts | **714 mm^2**, or 100 vias |

So volume is the *smallest* of the three terms, and the design is driven by layer
count and via count instead. Three consequences:

1. **2 layers, not 4.** Worth 10,000 points, and only loses if 2-layer routing
   needs more than 200 extra vias.
2. **No BGA.** Escape vias cost more than the area they save — LQFP-100 beats
   TFBGA100 by ~500-1,900 points and UFBGA169 by ~4,100.
3. **Mid-mount the barrel jack.** It is the tallest part; putting its barrel on
   the board plane sets Z = 7.0 mm and makes double-sided assembly free in volume.

Full reasoning, including the ideas that did *not* survive (folded flex, BGA,
single-layer) is in `FINDINGS.md`.

## Files

| file | contents |
|---|---|
| `FINDINGS.md` | the full writeup: what was measured, what was rejected, what is unproven |
| `BOM.csv` | 50 line items, 245 parts, each original MPN mapped to its replacement with risk and rationale |
| `placement.csv` | pick-and-place: ref, footprint, x, y, rotation, side, height |
| `netlist.csv` | 196 multi-pin nets rebuilt from the schematics |
| `SCORE.csv` | score breakdown for the recommended design and variants |
| `placement.svg` | top and bottom side render |
| `tools/` | everything needed to reproduce the above from the upstream repo |

## Reproducing

Needs `numpy` and `commaai/PCBGolf` checked out at `/home/user/commaai/pcbgolf`
(paths at the top of `pcb.py`, `fplib.py`, `netlist.py`).

```
python3 tools/netlist.py    # rebuild netlist; prints 1053/1053 pin hit rate
python3 tools/geom2.py      # component envelopes and edge rules
python3 tools/run_grid.py   # placement sweep
python3 tools/scorecard.py  # score table
```

## What is still needed for a real entry

1. A KiCad exporter — the placer emits coordinates, not a `.kicad_pcb`.
2. Footprints for the swapped parts: LQFP-100, SC-70-5, 0201, mid-mount USB-C,
   low-profile barrel jack. None exist in `pcbgolf.pretty`.
3. Routing. The ~300-via figure is the one number that could move the score by
   ±15,000, and it is unproven.
4. STEP export of the assembly.
