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

## 5. Measured boards (this supersedes every earlier projection)

Everything from here on is measured from generated, validated `.kicad_pcb`
files, not modelled. **The earlier projections in this file were optimistic and
have been replaced.** Three corrections account for most of the difference.

### Correction 1: a double-sided board's height is top + board + bottom

I had been computing Z as if only the top side carried parts. It does not:

```
Z = tallest top part + 1.6 mm board + tallest bottom part
```

The first generated board scored Z = **19.4 mm**, because the packer balanced the
two sides by *area* and cheerfully put a vertical USB-C (8.8 mm) on the bottom
while the barrel jack (9.0 mm as then estimated; really 11.0 mm) sat on top. The packer now optimises `W x H x Z`
with Z derived from the side assignment, and pins parts above a swept height
threshold to one side. That brings the stock BOM to **Z = 14.35 mm** — well above
the 10.6 mm I had assumed, because something has to be on the bottom.

### Correction 1b: the part heights themselves were estimates

Worse: the barrel jack's height in `parts.py` was an unverified **9.00 mm**, and
it is the part that sets Z for the entire design. Measuring the footprint's own
STEP model puts it at **11.00 mm**, so every volume reported before this point
was understated by roughly 5,300 mm^3.

Getting it right needed KiCad's 3D placement convention, which is not documented
in a form worth trusting, so it was derived the same way as the footprint flip
convention: seven single-footprint boards (front/back x rotated/not x
rotated-model/plain-offset) exported with `kicad-cli pcb export step` and read
back with OpenCascade. The convention is

```
R_model = Rz(-rz) . Ry(-ry) . Rx(-rx)                      # the (rotate xyz) field
front:   p = Rz(rho) . (R_model.p + offset)        + (x, -y, T)
back:    p = Rz(rho) . (diag(1,-1,-1).R_model.p
                        + (ox, -oy, -oz))          + (x, -y, 0)
```

with the PCB Y axis negated. `test_bbox3d.py` pins all seven cases to within the
exporter's own mesh tolerance. Re-measuring every footprint that ships a model
then reproduced **18 of 28** `parts.py` heights exactly, which is what makes the
remaining corrections credible. The jack is the only large one.

Two more things fall out of measuring instead of assuming:

* The score is the **PCBA** bounding box, so a body overhanging the copper
  outline would count — the jack's shell is 12.6 mm wide against a 9.4 mm pad
  span. `bbox3d.py` measures the real assembly on every board: nothing
  overhangs, so the XY figures stand and only Z was wrong.
* Through-hole lead tails exit the far side of the board. Parts with a 3D model
  already show their own (the vertical USB-C reaches 1.30 mm below its mounting
  face, the jack 0.81 mm — both inside a 1.6 mm board). The 2x4 header has no
  model; a 2.54 mm male header's 3.0 mm tail protrudes 1.4 mm, which `parts.py`
  now carries as `LEAD_TAIL`.

`step_assembly.py` writes the submitted STEP from the same placed geometry
`bbox3d.py` measures, so the file and the reported score cannot disagree.

### Z is now at its floor, and that settles the board thickness

```
Z = 11.00 (barrel jack) + 1.60 (board) + 1.60 (tallest back-side part) = 14.20
```

Front-side height below 11.00 mm is **free**, so every tall part belongs on top;
the back side only ever pays for its own tallest part. That also kills a swap
that looked free — thinning the board. JLCPCB builds 4-layer down to 0.8 mm, but
the header's 3.0 mm lead tail simply takes over as the board gets thinner:

| board thickness | z_top | z_bot | Z | volume |
|---|---|---|---|---|
| 1.6 mm | 11.00 | 1.60 | 14.20 | 29,258 |
| 1.2 mm | 11.00 | 1.80 | 14.00 | 28,846 |
| 1.0 mm | 11.00 | 2.00 | 14.00 | 28,846 |
| 0.8 mm | 11.00 | 2.20 | 14.00 | 28,846 |

0.2 mm, or 412 mm^3, for an argument about whether four USB-C receptacles and a
barrel jack belong on a 0.8 mm board. Not worth it — stay at 1.6 mm. The
remaining levers are area and vias, not height.

### Correction 2: the placement was not physically legal

`validate.py` checked outline containment and net consistency but never checked
whether parts *collide*. Adding `collide.py` found **73 real pad overlaps**.
Four separate bugs (detailed in the commit log): pad bounding boxes ignored each
pad's own rotation; through-hole parts were collision-checked on one side only;
perimeter connectors recorded a rotation inconsistent with the block reserved;
and far-side blocking was applied to whole envelopes rather than hole locations.

Fixing through-hole handling properly **grew the board**, because a vertical
USB-C's pegs really do occupy both sides.

### Correction 3: measured geometry

| board | outline | area | Z | volume | layers | base score (0 vias) |
|---|---|---|---|---|---|---|
| stock BOM, 2 layer | 48.17 x 50.98 mm | 2456 mm^2 | 14.35 | 35,240 | 2 | **45,240** |
| stock BOM, 4 layer | 48.17 x 50.98 mm | 2456 mm^2 | 14.35 | 35,240 | 4 | 55,240 |
| optimised BOM, 2 layer | 44.05 x 47.10 mm | 2075 mm^2 | 14.15 | 29,358 | 2 | **39,358** |
| LQFP-100 BOM, 4 layer | 44.05 x 46.78 mm | 2060 mm^2 | 14.20 | 29,258 | 4 | 49,258 |

Volumes are the measured 3D assembly box from `bbox3d.py`, not outline x height.

"Optimised" here is only the swaps that need no vendor data: 0402 -> 0201,
0805 -> 0603, and the op-amps into SC-70-5. See section 6 for why the MCU and
connector swaps are not in it.

All three pass `validate.py` (outline, nets, layers) **and** `collide.py`
(0 pad overlaps, 0 pairs below 0.1 mm).

## 6. What could not be done here, and why

* **LQFP-100 MCU swap.** Needs the STM32H725VGT6 pinout: PF11, PG9 and PG10 are
  not bonded out on LQFP100, so CH3_IMON and the FDCAN3 pair must move. Every
  datasheet host (st.com, lcsc.com) is blocked by this environment's egress
  proxy. I will not invent a pinout. This is the single biggest remaining area
  win — the LQFP-144 is 543 mm^2 of courtyard, 22% of the whole board.
* **Mid-mount USB-C, low-profile barrel jack, right-angle 2x4 header.** Their
  land patterns are vendor-specific; inventing pads is not defensible. These are
  what would drop Z from 12.2 mm to roughly 7 mm, worth ~11,000 points.
* `gen_footprints.py` therefore generates only 0201, 0603 and SC-70-5, whose
  land patterns are standard and whose pin numbering is unambiguous.

## 7. The routing result, which changes the recommendation

**2-layer autorouting of this design fails.** Freerouting, with its via-spraying
fanout stage disabled and via cost raised to 5000, was run on the validated
2-layer board (48.18 x 50.98 mm, 196 nets, 1066 pins):

| pass | unrouted (of 748) |
|---|---|
| 1 | 454 |
| 3 | 409 |
| 5 | 411 |
| 7 | 412 |
| 11 | 404 |

It plateaus around 404 and never converges. No session file was produced, so
**the via count — the score term I argued was dominant — is still unmeasured.**

So the earlier recommendation of "2 layers, double-sided, ~300 vias -> 36,760"
is **not supported by evidence**. On this placement, 2 layers does not route.

### Via cost is the parameter that matters, and I had it wrong

Four layers at via cost 5000 was barely better than two: **376 unrouted vs 404**.
A doubling of routing capacity should not buy 7%. The reason showed up in the
copper distribution - the router had refused the inner layers almost entirely:

| layer | copper | share |
|---|---|---|
| B.Cu | 8709 mm | 49% |
| F.Cu | 8147 mm | 45% |
| In2.Cu | 528 mm | 3% |
| In1.Cu | 525 mm | 3% |

It produced only **16 vias across 372 routed connections**, and could not finish.
That was my parameter choice. For this score function a via costs 50 points and
trace length costs *nothing*, so a via-averse router is right in principle - but
the cost has to stay low enough that it will still use the layers it needs.

Dropping via cost from 5000 to 120 roughly halves the problem:

| via cost | unrouted (of 748) | note |
|---|---|---|
| 5000 | 376, plateaued | refuses inner layers |
| 120 | **181 and still falling** at pass 11 | cut off by my 70-minute timeout |

At 120 it was still improving when the budget ran out. But the greedy board
then **stalled at 154 unrouted** - passes 19 and 20 ended with an identical
score. That is a placement limit, not a patience limit.

### Placement is what unlocked it

`aplace.py` (quadratic wirelength minimisation with iterative spreading) cut
measured HPWL from 6940 mm to 4281 mm. Same router, same settings, same design:

| pass | greedy placement | analytical placement |
|---|---|---|
| 1 | 454 unrouted | 297 |
| 3 | 409 | 223 |
| 20 | 154 (stalled) | - |
| 35 | - | 67 |
| 40 | - | **51** |

The analytical board reaches **51 unrouted of 748 (93% routed)** where the
greedy one stalls at 154. The volume cost of that placement is 2,293 points;
it is plainly worth it.

### A tooling trap worth recording

Freerouting writes its session file **only when it stops on its own terms**.
Two multi-hour runs produced nothing at all because a timeout killed them first.
Worse, `--router.autorouter.max_passes` is silently rejected as an *unknown
command line argument* - the pass cap only takes effect through the
`FREEROUTING__ROUTER__AUTOROUTER__MAX_PASSES` environment variable. Check the
startup line: "Parsed 4 router setting(s)" means it registered, 3 means the cap
was ignored and the run will overshoot into your timeout and write nothing.

### Why it fails: the placement, not just the layer count

The packer sorts parts by descending size and bottom-left fills. That is dense
but, from a routing point of view, close to random: measured half-perimeter
wirelength was **6940 mm over 189 nets**, a mean net span of 37 mm on a 48 mm
board. A spectral layout of the netlist — parts that share nets pulled together —
gives a target layout with HPWL of **977 mm**, seven times shorter.

`embed.py` now computes that spectral layout and `gridpack.place_near()` packs
each part at the free slot nearest its target instead of bottom-left. That cut
measured HPWL from 6940 to **4515 mm**. Still far from the 977 mm the targets
imply, because packing pressure pushes parts away from their targets, but it is
the right direction and it is the lever that decides routability.

## 8. Measured routed boards

Every row below is a generated board, routed to the router's own convergence,
imported back and scored. No projections.

| variant | rules | routed | vias | volume | layers | **score** | vs 84,578 |
|---|---|---|---|---|---|---|---|
| 2 layer | 0.127 mm | 555/748 (74%) | 181 | 37,904 | 10,000 | 56,954 | -33% |
| 4 layer | 0.127 mm | 700/748 (94%) | 361 | 37,904 | 20,000 | 75,954 | -10% |
| 4 layer | 0.100 mm | **732/748 (98%)** | 410 | 37,904 | 20,000 | 78,404 | -7% |
| 4 layer, via cost 400 | 0.100 mm | 698/748 (93%) | **317** | 37,904 | 20,000 | **73,754** | **-13%** |
| 4 layer, via cost 250 | 0.100 mm | 725/748 (97%) | 351 | 37,904 | 20,000 | 75,454 | -11% |

All are 50.05 x 52.775 mm, Z = 14.35 mm, and pass `validate.py` (including the
routing-inside-outline check) and `collide.py`. **These volumes are 5,283 mm^3
higher than first reported**, for the jack-height reason in correction 1b; the
scores below supersede every earlier figure in this file.

**The 2-layer score is a mirage.** It is cheap precisely because a quarter of
the board is not connected. Passes 25-30 oscillate 193/195/196/193/195/193 - it
converged at 74%, it was not cut short. Two layers is not finishable with this
placement, so the 10,000-point layer saving is not available.

### The via-cost frontier

Via cost is the one knob that moves the score directly, and it trades against
completion. Lower cost routes more of the board but spends more vias:

| via cost | unrouted | vias | score | + estimated cost of finishing the rest |
|---|---|---|---|---|
| 120 | **16** | 410 | 78,404 | 78,852 (-7%) |
| 250 | 23 | 351 | 75,454 | 76,010 (-10%) |
| 400 | 50 | **317** | **73,754** | 74,889 (-11%) |
| 800 | 155 | 188 | 67,304 | *not valid — 21% incomplete* |

Counter-intuitively the *less* complete board scores better even after charging
it the cost of closing its remainder at its own observed via rate. 93 fewer vias
is 4,650 points; the extra 34 connections cost roughly 1,100 to finish. So the
right operating point is a high via cost plus a hand-finish, not a low via cost
that lets the router close everything itself.

**Finer design rules trade vias for completion.** Dropping track and clearance
from 0.127 mm to 0.100 mm (both JLCPCB-manufacturable) took unrouted from 48 to
16, but the router spent 49 more vias getting there - 2,450 points. Worth it:
a board that does not connect is not a submission.

## 9. Two things that did not work

**Handing the existing routing back to finish the remainder.** Freerouting's DSN
parser accepts a `(wiring ...)` scope, so the obvious way to close the last 48
connections is to return the 4703 segments and 361 vias already found and let the
router spend everything on what is left. It fails badly: **734 unrouted and 7603
violations**. Each KiCad segment becomes a separate two-point wire and the router
treats every shared endpoint as a collision. Doing this properly needs collinear
runs merged into single polyline wires first.

**A very high via cost.** At via cost 5000 the router produced a beautiful-looking
16 vias - by refusing the inner layers (they carried 6% of the copper) and leaving
376 connections unmade. For this score function trace length is free and a via
costs 50, so being via-averse is right in principle, but the cost has to stay low
enough that the router still uses the layers it needs.

## 10. Score, honestly


Leaderboard to beat: **84,578** (abijahkaj); second 116,226 (Dsalzman).

| design | volume | layers | vias | score | vs 84,578 |
|---|---|---|---|---|---|
| optimised, 2 layer, 0 vias (floor) | 25,312 | 10,000 | 0 | 35,312 | -58% |
| optimised, 2 layer, 300 vias | 25,312 | 10,000 | 15,000 | 50,312 | -41% |
| stock, 2 layer, 300 vias | 30,328 | 10,000 | 15,000 | 55,328 | -35% |
| stock, 4 layer, 300 vias | 30,328 | 20,000 | 15,000 | 65,328 | -23% |
| stock, 4 layer, 600 vias | 30,328 | 20,000 | 30,000 | 80,328 | -5% |

The geometry is measured; **the via numbers are still assumptions**. The bottom
row is the sobering one: a 4-layer board that needs 600 vias barely beats the
leaderboard. Via count is not a detail, it is the result.

### What 84,578 is made of

Solving the score equation: at 4 layers and 515 vias the volume must be
38,828 mm^3 — 4,087 mm^2 at 9.5 mm tall, about 64 mm square or 68 x 60. So the
leader is paying roughly 46% volume, 30% vias, 24% layers. They spend more on
vias and layers combined than on their entire volume, and they are doing it on a
board that **actually routes**, which this one does not yet.

## 9. Status

Done and verified:

* netlist rebuilt from the schematics, 1053/1053 pins resolving onto wires
* a lossless KiCad serialiser (34 files, 223,805 tokens, zero differences)
* the back-side flip convention derived from pcbnew and asserted against it
* legal, validated, collision-free boards for the stock and optimised BOMs
* a full Specctra export/import loop and a scorer

Not done:

* **Routing.** This is the whole score. 2 layers does not converge; 4 layers is
  running.
* Placement quality is the blocker, and the spectral-target work above is the
  start of fixing it, not the end.
* STEP export.
* The MCU and connector swaps, blocked on datasheet access.
