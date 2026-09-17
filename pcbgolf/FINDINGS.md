# PCBGolf: what the numbers actually say

Tooling and measurements for [commaai/PCBGolf](https://github.com/commaai/PCBGolf).
Everything below is measured from the repo files by the scripts in `tools/`, not
recalled. Score is the official one:

```
score = PCBA bounding-box volume (mm^3) + 50 x vias + 5000 x copper layers
```

## 0. What the repo actually contains

Parsing `pcbgolf.kicad_pcb` (`tools/pcb.py`):

| property | value |
|---|---|
| copper layers declared | 2 (`F.Cu`, `B.Cu`) |
| track segments | **0** |
| vias | **0** |
| zones | **0** |
| `Edge.Cuts` geometry | **none** — there is no board outline |
| footprints | 245, all on the front |
| pads | 1078 |
| nets (from the schematics) | 297, of which 196 have 2+ pins |
| connected pins | 1053 |

So the repo is **a schematic plus a rough placement, not a finished board**. There
is no reference score to beat and no reference routing to improve on: every
entrant draws the PCB from scratch. The `.kicad_pcb` carries no netlist either —
connectivity exists only in the five `.kicad_sch` sheets, so `tools/netlist.py`
rebuilds it geometrically (wire/junction/label/power-symbol union-find). It
resolves **1053/1053 pins onto wires, 100% hit rate**, which is the check that
the netlist is right.

## 1. The exchange rates that decide every other choice

This is the single most useful thing to internalise. At a board height of
Z = 7 mm (see §3):

| you spend | it costs | equivalent to |
|---|---|---|
| 1 via | 50 pts | **7.1 mm^2 of board area** |
| 1 copper layer | 5000 pts | **714 mm^2 of board**, or 100 vias |
| 1 mm^2 of board | 7 pts | |
| 1 mm of height (at 1300 mm^2) | 1300 pts | 26 vias |

Two consequences that run against normal PCB instinct:

* **Vias are expensive.** A 400-via board spends 20,000 pts on vias alone —
  more than its entire volume. Via-averse routing (pours on the outer layers so
  pads connect without a via, power as fat outer-layer traces) is worth more
  than shaving millimetres off the outline.
* **Going 2-layer only pays if it costs fewer than 200 extra vias.** That is a
  tight budget for a board with a USB hub, 4 CAN channels, SDMMC and ~50 GPIO.

## 2. Fine-pitch BGA is a *losing* move here

This inverts the obvious "shrink the MCU" advice. The reference MCU is an
STM32H725ZGT (LQFP-144, 20x20 mm, measured courtyard **23.3 x 23.3 = 543 mm^2** —
43% of all component area on the board). ST also sells the same die in
LQFP100 (14x14), VFQFN68 (8x8), TFBGA100 (8x8), UFBGA169 (7x7) and
WLCSP115 (3.75x4.15).

| package | courtyard | area saved vs LQFP100 | escape vias | via cost | net |
|---|---|---|---|---|---|
| LQFP-144 (stock) | 543 mm^2 | -287 mm^2 | 0 | 0 | baseline |
| **LQFP-100 14x14** | **256 mm^2** | — | **0** | **0** | **best** |
| TFBGA100 8x8 (0.8 mm) | 72 mm^2 | +184 mm^2 = 1288 pts | ~36-64 | 1800-3200 | **-500 to -1900** |
| UFBGA169 7x7 (0.5 mm) | 56 mm^2 | +200 mm^2 = 1400 pts | ~110 | 5500 | **-4100** |
| WLCSP115 (0.4 mm) | 20 mm^2 | +236 mm^2 = 1652 pts | ~115 + HDI | 5750 | **-4100** |

A BGA would only win if Z were above ~17 mm, and it is 7. **LQFP-100
(STM32H725VGT6) is the right call** — same die, same 1 MB flash, 82 GPIO against
the 50 the design actually uses, zero escape vias, and no HDI cost at JLCPCB.

Pin-usage evidence (`tools/nets.py`): of the LQFP-144's 144 pads, **40 are
single-pin nets (unused)**; 42 are power/ground and ~50 are real signals.
Moving to LQFP100 needs pin remapping (PF11, PG9, PG10 are not bonded out on
LQFP100), but FDCAN3 is also mapped to PD12/PD13 which *is* available, and the
rules explicitly allow firmware changes.

## 3. Z is floored by the barrel jack — not by the USB-C ports

Measured from the STEP models (`tools/step_bbox.py`) and footprints:

| part | footprint | height above board |
|---|---|---|
| `DCJACK_2MM_SMT` (PJ-002AH-SMT) | 15.65 x 9.40 | **~9 mm — tallest part** |
| `USB-C-FEMALE-VERT-GCT` x4 (OBD-C) | 8.93 x 5.80 | 8.80 mm (**vertical mount**) |
| `2X04` CAN header | 9.90 x 4.82 | ~8.5 mm |
| everything else | | <= 3.2 mm |

The four OBD-C receptacles are **vertical**: the cable plugs in perpendicular to
the board. Swapping them for ordinary horizontal or mid-mount USB-C receptacles
(identical mating interface, 3.26 mm body) takes them off the Z critical path —
but they get *deeper* in XY (9.2 mm vs 5.8 mm), so it is a genuine trade, not a
free win.

The real floor is the DC jack. A 5.5 mm OD barrel plug needs a 5.5 mm bore, so
the receptacle body cannot be much under 6.5 mm in its smallest dimension, in
any orientation. Mid-mounting it in a board cutout puts the barrel axis on the
board plane, which makes **Z ~ 7.0 mm** and — critically — gives ~2.7 mm of free
height on *both* faces. Every other part fits inside that, so
**double-sided assembly becomes free in volume terms.**

That is the single biggest structural win available, and it is why the optimised
placement below is ~44% smaller in area than the stock one.

## 4. Free BOM wins found by reading the design

| what | from | to | saves |
|---|---|---|---|
| MCU package | LQFP-144 (543 mm^2) | LQFP-100 `STM32H725VGT6` | **287 mm^2** |
| 4x current-sense op-amp | SOIC-8 `NCS20071SN2T1G` (40 mm^2 ea) | SC-70-5 `NCS20071XV5T2G` | **131 mm^2** |
| 125 R + 40 C | 0402 | 0201 | **~210 mm^2** |
| 13 bulk caps | 0805 | 0603 | **~25 mm^2** |

The op-amp one is the funniest: the schematic symbol is literally named
**`NCS20071XV`** — the SC-70 variant — but the fitted MPN is `NCS20071SN2T1G`,
the SOIC-8. Same die, 5.5x the area. Four of them.

Also found, though not directly exploitable: the **USB2517 is a 7-port hub using
only 5 downstream ports** (DN1-4 for the OBD-C ports, DN7 for the STM32; DN5/DN6
are unconnected). There is no single-chip 5-port USB 2.0 hub, so cascading two
4-port QFN24 hubs is the only way to shrink it, and it saves ~50 mm^2 at the cost
of an extra hub tier — roughly a wash. Keep the USB2517.

## 5. Measured placements

`tools/gridpack.py` is a legal-by-construction placer: connectors are seated on
the perimeter with their mating face outward and become obstacles, then every
other part is dropped into the lowest-leftmost free cell on either board face via
an integral-image free-region test. Output is always overlap-free, so it can be
handed straight to a router. Ordering, rotation, board side, and connector edge
assignment are annealed against `W*H*Z + lambda*HPWL`.

| BOM | tightest legal board | Z | volume |
|---|---|---|---|
| stock | 42 x 36 mm (1512 mm^2) | 10.6 mm | 16,027 mm^3 |
| optimised | **36 x 36 mm (1296 mm^2)** | **7.0 mm** | **9,072 mm^3** |

See `placement_stock.svg` / `placement_opt.svg`.

A hard constraint worth knowing: the eight connectors need **~74 mm of board
edge** between them. That alone floors the outline at roughly 20x20 mm however
small the electronics get.

## 6. Ideas that did *not* survive contact with the numbers

* **Folded flex PCB.** Proposed as the moonshot; it is not worth it. The 74 mm
  connector-edge requirement floors the footprint anyway, folding *adds* stack
  height against a 7 mm flat envelope, a 4-layer FPC pays the same 20,000 pt
  layer penalty, and the assembly risk is severe. Killed.
* **BGA MCU.** Net negative by 500-4100 pts (§2).
* **Dropping to 2 copper layers.** Only wins under a 200-extra-via budget (§1) —
  possible but unproven; see the routing experiment.
* **Using plated through-hole pins as free layer transitions.** Real but tiny:
  only the connectors have TH pins.

## 8. The biggest untapped lever: jumper the crossings, don't via them

A via costs a flat 50 points. A 0201 zero-ohm jumper costs only the board area
it occupies: 1.15 x 0.65 = 0.75 mm^2, which at Z = 7 mm is **5.2 points**.

> **A 0-ohm 0201 jumper is 9.6x cheaper than a via for resolving a crossing.**

Jumpers are not vias, so they do not enter the score's via term at all. They
only work for same-layer crossings (they cannot change layer), which points at a
specific architecture:

**2 copper layers, single-sided assembly, bottom layer a near-solid ground
plane, all signals on top, planar crossings resolved with 0201 jumpers.**

That design pays 10,000 for layers, almost nothing for vias (only ground
stitching), and is *electrically better* than the alternatives: USB 2.0
high-speed pairs and CAN get a proper unbroken reference plane, which a
double-sided 2-layer board does not give you.

| architecture | area | volume | via pts | layer pts | score |
|---|---|---|---|---|---|
| 4L, double-sided, 350 vias | 1296 | 9,072 | 17,500 | 20,000 | 46,572 |
| 4L, double-sided, 250 vias | 1296 | 9,072 | 12,500 | 20,000 | 41,572 |
| 2L, double-sided, 350 vias | 1296 | 9,072 | 17,500 | 10,000 | 36,572 |
| **2L, 1-sided asm, solid GND, 80 vias** | 2392 | 16,744 | 4,000 | 10,000 | **30,744** |

Single-sided assembly nearly doubles the area — the placer's tightest legal
single-sided board is **52 x 46 mm = 2392 mm^2** against 36 x 36 = 1296 mm^2
double-sided (`placement_1side.svg`) — and that costs ~7,700 points of volume.
But it buys back 10,000 in layers and ~13,500 in vias. The area penalty is worth
paying.

Adding jumpers is cheap: 300 of them add 224 mm^2, which is 1,570 points.

| jumpers | area | volume | score @ 80 vias | score @ 150 vias |
|---|---|---|---|---|
| 0 | 2392 | 16,744 | 30,744 | 34,244 |
| 150 | 2504 | 17,529 | 31,529 | 35,029 |
| 300 | 2616 | 18,314 | **32,314** | 35,814 |
| 450 | 2728 | 19,099 | 33,099 | 36,599 |

Caveat on density: the placer hits 81% geometric packing on that single-sided
board, which is tighter than one-layer signal routing will really allow. At a
more honest 60-65% the board is nearer 3,000-3,200 mm^2 and the score lands
around **36,000-38,000**. Treat ~32,000 as the optimistic end and ~38,000 as the
one to plan against.

### The ground-via budget is what really sets the via term

Measured pad counts (`tools/netlist.py`): **1053 connected pads = 237 GND +
151 power + 665 signal**. With signals on top and a solid ground plane on the
bottom, the ground pads are what force vias:

| ground strategy | vias | via points |
|---|---|---|
| one via per GND pad (best signal integrity) | 237 | 11,850 |
| one via per component's GND (shared, adjacent pads) | 138 | 6,900 |
| shared + top-side pour islands, aggressive | ~60-90 | 3,000-4,500 |

The 237 GND pads sit on only **138 components**, so via sharing is the single
biggest via-reduction move available. Scores for the 52 x 46 board with 300
jumpers (area 2616 mm^2, Z = 7):

| ground vias | volume | via pts | layers | score |
|---|---|---|---|---|
| 60 | 18,312 | 3,000 | 10,000 | **31,312** |
| 90 | 18,312 | 4,500 | 10,000 | 32,812 |
| 120 | 18,312 | 6,000 | 10,000 | 34,312 |
| 237 | 18,312 | 11,850 | 10,000 | 40,162 |

### The genuine contest

The one architecture that could beat it is **2 layers, double-sided, 1296 mm^2**,
which only needs to stay under **264 vias** to score below 32,314 (at 200 vias it
scores 29,072). Its volume advantage is large. The open question is whether a
double-sided 2-layer board can be routed that sparsely *and* still give the
480 Mbps USB pairs a usable return path — the solid-ground single-sided design
wins on signal integrity by a wide margin. That is the trade to settle with a
real routing attempt, not arithmetic.

Two things to confirm with comma before betting on this:

1. That a few hundred 0-ohm jumpers is considered legitimate design rather than
   gaming the metric. It is normal practice on 1- and 2-layer boards, and the
   rules only require JLCPCB-manufacturable, assemblable and working — but it is
   the kind of thing worth asking about rather than discovering at review time.
2. That re-orienting the OBD-C receptacles from vertical to horizontal/mid-mount
   counts as "mechanically compatible" (the USB-C plug interface is identical;
   only the board-attach orientation changes).

A one-copper-layer board would score 5,000 lower still and cannot contain any
vias at all, but with no reference plane for 480 Mbps USB it would fail the
"must work and be usable" rule. Not recommended.

## 7. Where the score actually goes

With the optimised 36x36 mm, Z=7 mm board:

| term | value | share |
|---|---|---|
| volume | 9,072 | 23% |
| 4 copper layers | 20,000 | 50% |
| ~200-400 vias | 10,000-20,000 | 27% |
| **total** | **~39,000-49,000** | |

**Half the score is the layer count, and most of the rest is vias.** Volume —
the thing the challenge is named after — is the smallest term. Anyone optimising
purely for a small outline is fighting for the least valuable 23%.
