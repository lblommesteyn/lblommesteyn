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

*Superseded in part by §12: the jack is now a CUI PJ-063AH, measured at 9.0 mm,
and Z is 12.0 mm. The mid-mount jack below was never adopted: no part with a
model to measure it by was found.*

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

## 8b. The LQFP-100 swap, audited pin by pin

The STM32H725ZGT6 (LQFP-144, 20x20 mm) becomes an STM32H725VGT6 (LQFP-100,
14x14 mm): same die, same 1 MB flash, same 550 MHz core, 82 GPIO against the 50
this design uses. It takes the board from 50.05 x 52.78 mm to 44.05 x 46.78 mm
and 8,646 mm^3 out of the volume — the single largest win in the project, and
also the riskiest claim in the submission, so here is the whole audit.

The pinout came from the KiCad symbol library (`MCU_ST_STM32H7`), which carries
a symbol per package, so the comparison is mechanical rather than from memory.
What LQFP-100 has: ports A, B and C complete; port D without PD6/PD7; port E
only PE2/PE4/PE5/PE7/PE8; **no port F and no port G**.

`remap_lqfp100.py` keeps every signal already on a surviving pin and moves the
rest. 45 signals stayed, **15 moved, 0 failed**:

| was | now | signal | why |
|---|---|---|---|
| PD6, PD7 | PA2, PA3 | CH2_SBU1_RELAY, CAN2_EN | plain GPIO |
| PE0, PE1, PE15, PE3 | PA7, PA8, PA9, PA10 | CH4_SBU2_IGN/RELAY, BTN, LED_G | plain GPIO |
| PF7, PF8, PF9, PF10 | PB14, PB15, PC5, PA15 | N$29–N$32 | **wrong: these are ADC inputs** (see §12) |
| PF11 | PB0 | CH3_IMON | **ADC-capable pin required** |
| PG10, PG9 | PD12, PD13 | CAN2_RX, CAN2_TX | **FDCAN alternate function required** |
| PD12, PD13 | PC6, PC7 | CH3_SBU1_IGN, CH3_SBU2_RELAY | displaced by the above |

**Correction.** This table called the PF7-PF10 moves "plain GPIO". They are
not: N$29-N$32 are four of the eight SBU voltage-sense lines (through R13-R20),
and PF7-PF10 are ADC3 inputs. Three of the four landed on PB14, PB15 and PA15,
which have no ADC, so three SBU voltages could not be read. Every LQFP-100
board up to and including the first submission had this. The pin-assignment
optimiser (§13) puts all eight back on ADC pins and checks it.

Two of the moves are not interchangeable with GPIO and were placed
deliberately: `CH3_IMON` is an analogue current-sense input and had to land on
an ADC channel, and CAN2 had to land on pins with an FDCAN alternate function,
which is why PD12/PD13 were taken and their GPIO occupants pushed to PC6/PC7.
`PA13`, `PA14`, `PB2`, `PC13`, `PC14` and `PC15` are reserved (SWD, BOOT, LSE,
RTC) and excluded from reassignment.

### Two pins exist on LQFP-144 and not on LQFP-100

Both were checked rather than assumed, because a missing supply pin would be a
dead board:

* **VDD50USB** (LQFP-144 pin 90, tied to +3V3 in the original) does not exist on
  LQFP-100. The part keeps **VDD33USB**, which the board supplies at +3V3 on
  pin 76. Tying VDD50USB to 3.3 V is how the original bypasses the internal USB
  regulator and supplies VDD33USB externally; on LQFP-100 that pin is simply not
  brought out. Same configuration, one fewer pin. **No change needed.**
* **PDR_ON** (LQFP-144 pin 142) does not exist either, and this one has a
  consequence. R11 pulls PDR_ON to +3V3 to enable the internal power-down
  reset; with no pin to pull, R11 strapped nothing and left net N$120 with a
  single pad, which reads as a broken connection. On LQFP-100 the power-down
  reset is permanently enabled internally, so **R11 is not fitted** and the net
  goes with it. `mkboard --drop R11` takes the part and its net out together,
  and the board then has zero single-pad nets.

Checked against the symbol library: VGHx (TFBGA-100) and ZGTx (LQFP-144) expose
PDR_ON, VGTx (LQFP-100) does not — so this is a property of the package, not a
library omission.

Everything else survives the swap: 90 of 100 pads carry a net, GND and +3V3
lose 7 and 6 pads respectively because the smaller package simply has fewer
VSS/VDD pins, and no other net loses connectivity.

What is **not** proven: nothing here is simulated, and the AF assignments were
checked against the alternate-function requirements rather than against silicon.

## 9. What did not work, and what I got wrong about why

Two of the four entries that used to be in this section were misdiagnoses, and
both pointed away from the same underlying bug. Keeping the whole sequence
because the pattern is the useful part.

**A very high via cost.** At via cost 5000 the router produced a
beautiful-looking 16 vias — by refusing the inner layers (they carried 6% of the
copper) and leaving 376 connections unmade. Trace length is free and a via costs
50, so being via-averse is right in principle, but the cost has to stay low
enough that the router still uses the layers it needs. This one stands.

**Handing the existing routing back — misdiagnosed once.** Returning the
segments and vias already found looked like it failed outright: 734 unrouted and
thousands of violations. I blamed segment granularity, each KiCad segment
becoming a separate two-point wire the router treats as colliding at shared
endpoints, and wrote that up as needing collinear runs merged into polylines.

Wrong. `pcb2dsn` emitted `(wiring ...)` before `(network ...)`, so every wire
named a net the parser had not seen yet; Freerouting logged 203,087 `net not
found` warnings and discarded the lot. Specctra orders the sections structure,
placement, library, network, wiring. With `(wiring)` last the identical file
loads with **0 warnings**. Two-point wires were never the problem, and the
203,087 warnings were in the log the whole time.

**Closing the leftovers with an A* maze router — misdiagnosed twice.** On a
board I believed was saturated, `finish_router` closed 41 of 87 connections for
235 vias, 5.7 each, taking the score from 64,958 to 76,708. Raising the via
price eightfold moved it to 4.1 each. I concluded the approach was "structural,
not a tuning problem" — that a patcher cannot rip up its own work the way a
global router can, so no via price makes a blocked channel passable.

That reasoning is sound and the conclusion was still wrong, because the premise
was. Three separate defects were feeding it:

* It hardcoded 0.1mm traces and 0.6mm vias regardless of the board's rules.
* Its obstacle grid was built for trace clearance, but a via is several times
  wider and spans every layer, so it planted 0.6mm vias in cells cleared only
  for a 0.1mm trace — **83 genuine shorts**, overlapping by up to 0.33mm.
* `mark_rect` located obstacles with a rounding function, which can leave a
  boundary cell unmarked although its centre is inside the forbidden region, by
  up to half a cell: 0.064mm against a 0.09mm clearance budget.

With the rules threaded through, a second via-sized occupancy grid, and marking
that rounds outwards, it adds **zero** clearance violations. It also closes far
fewer connections, because the legal moves really are that constrained — so the
"patcher cannot make room" conclusion was half right, and the half I could
measure was wrong.

**Routing the small board harder — the one that mattered.** Three rounds on
44.05 x 46.78mm went 92 -> 87 -> 83 connections short, the last at JLCPCB's real
limits. I concluded the outline was saturated: "at ~45% courtyard utilisation
the board is not packing-limited, it is routing-limited, and no amount of router
effort changes that. The fix has to be area."

That was wrong, and the whole outline sweep in section 8 was built on it.
`pcb2dsn` wrote coordinates in whole micrometres while declaring `(resolution um
10)`, i.e. 1/10 um units, so **every board went to the router 10x smaller than
life** — 48x50mm became 4.8x5.0mm — with clearance and track width shrunk to
match. Geometrically similar, so it routed and the output looked right, but
Freerouting's absolute tolerances and grid rounding then sat 10x coarser
relative to the features.

At the correct scale the same 44x46 board routes to **14 connections short**
instead of 78. Growing the board had looked like it was buying completion; it
was buying back some of what the scale bug was taking away.

### The pattern

Every one of these was a confident, specific, plausible conclusion supported by
real measurements, and three of them were wrong in the same direction: I
explained away a symptom with a mechanism I found convincing instead of
following the evidence that was already in front of me. The 203,087 warnings
were in the log. "More area causes more overlaps" is not a coherent sentence and
should have sent me straight to the placement pipeline, where
`build_board` was sizing parts by their swapped footprints and then building the
board with the originals. And a clearance checker that disagreed with the
autorouter by two orders of magnitude was far more likely to be wrong than the
autorouter.

`drc.py` is the clearest case: four successive geometries, each producing a
confident violation count — **2241, 779, 132, 128** — against a true answer of
**0**. Wrong trace width, then square vias, then axis-aligned pads when the
USB-C shield lands sit at 39 degrees, then a roundrect inset computed by pulling
corners toward the centroid instead of offsetting the sides. Only checking one
pair by hand against the footprint definition ever distinguished them.

## 10. Score, honestly

*Superseded by §14: every board in this section predates the fixes in §12
and is not valid.*

Leaderboard to beat: **84,578** (abijahkaj); second 116,226 (Dsalzman).

Every row is measured from a board file in `board/`: volume from the 3D assembly
box, vias counted from the file, connectivity from `ratsnest.py`, clearance from
`drc.py`. All of them are clearance-clean — **0 violations, 0 shorts**.

| board | outline | volume | vias | short | score | margin |
|---|---|---|---|---|---|---|
| **LQFP-100, 4L** | 44.05 x 46.78 | 29,258 | 420 | **9** | **70,258** | **17%** |
| LQFP-100, 4L | 44.05 x 46.78 | 29,258 | 414 | 14 | 69,958 | 17% |
| LQFP-100, 4L | 45.25 x 47.78 | 30,698 | 391 | 11 | 70,248 | 17% |
| LQFP-100, 4L | 46.05 x 48.78 | 31,895 | 362 | 20 | 69,994 | 17% |
| LQFP-100, 4L | 48.05 x 50.78 | 34,644 | 399 | 3 | 74,594 | 12% |
| LQFP-144, 4L | 50.05 x 52.78 | 37,904 | 351 | 23 | 75,454 | 11% |

**None of them is finished.** 3 to 20 connections remain open, so every score
above is for a board that does not yet work. Closing the rest costs roughly a
via each, so the honest expectation is **71,000-ish, about 16% under the
leaderboard**, with the last connections done by hand in KiCad.
`submission/UNROUTED.csv` names them.

### Area and vias trade off about 1:1 here

The four LQFP-100 outlines land within 300 points of each other. The 44x46 board
saves 2,636 mm^3 against 46x48 and spends 58 more vias getting there, which is
2,900 points — so the outline barely matters at this design's operating point,
and the sweep was chasing a flat optimum. Worth knowing before spending more
effort on packing.

### Where the score goes

On the 44x46 board: volume 29,258 (42%), layers 20,000 (28%), vias 21,000 (30%).

* **Height is at its floor.** Z = 11.00 (barrel jack) + 1.60 (board) + 1.60
  (tallest back-side part) = 14.20. The jack is 78% of the stack and is fixed by
  the mating-compatibility rule. Front-side height under 11mm is free, and
  thinning the board does not help because the 2x4 header's 3.0mm lead tail
  takes over below 1.2mm.
* **Vias are now the biggest movable term** and the one lever never pulled:
  Freerouting's optimizer stage only runs on a fully routed board, so it has
  been skipped on every run here. Reaching zero unrouted is worth more than the
  connections themselves.
* **Two layers would save 10,000** and does not converge: 193 connections short
  at best.

### What 84,578 is made of

The jack sets a floor for everyone: 11.00mm plus a 1.60mm board is 12.60mm even
with a bare back side. Solving `84,578 = volume + 5,000 L + 50 V`:

| if they used | volume left | area at Z = 12.6 | roughly |
|---|---|---|---|
| 2 layers, 200 vias | 64,578 | 5,125 mm^2 | 72 mm square |
| 2 layers, 400 vias | 54,578 | 4,331 mm^2 | 66 mm square |
| 4 layers, 300 vias | 49,578 | 3,935 mm^2 | 63 mm square |
| 4 layers, 500 vias | 39,578 | 3,141 mm^2 | 56 mm square |

So 84,578 is consistent with a board 56-72mm square — larger than anything here.
The leader is not winning on area; they are winning on having a board that
routes completely, which is exactly the gap that remains.

## 11. Status

*Superseded by §14.*

Verified:

* netlist rebuilt from the schematics, 1053/1053 pins resolving onto wires
* a lossless KiCad serialiser (34 files, 223,805 tokens, zero differences)
* the back-side flip convention derived from pcbnew and asserted against it
* the 3D placement convention derived from `kicad-cli` and asserted against it,
  every part height measured from its own STEP model
* placements legal by construction: 0 pad overlaps, 0 inter-part pairs under the
  clearance rule, the only sub-clearance pads being J3's vendor land pattern,
  which the upstream board also has
* routed copper clearance-clean on every board, by exact swept-polygon geometry
* the LQFP-100 remap audited pin by pin, 0 failures, and the one part it orphans
  (R11) taken off the board
* a STEP assembly written from the same placed geometry the score is measured
  from, so the file and the number cannot disagree

Not done:

* **No board is fully routed.** The best is 9 connections short.
* The via optimizer has never run, because it requires a complete board.
* Placement quality is still the limit. Measured HPWL is 4281mm against a
  977mm spectral target, and nothing here closes that gap.
* Nothing is simulated and no board has been fabricated.

## 12. Defects found by checking the assembly, not the copper

Every check up to here looked at copper and pads: clearance, connectivity,
pad overlap. None asked whether the assembled board can be plugged in, or
whether a drill goes through a trace. Three new checks did, and each found a
defect present on every board so far, the submitted one included.

### Every edge connector faced into the board

`mating.py` finds each connector's plug opening from its own 3D model: it
casts a grid of rays inward through each vertical face of the placed body and
marks a ray as part of an opening when it runs at least 3 mm deeper than a ray
on each of its four sides — a hole in a wall. (Counting deep rays alone is
fooled by the jack's curved shell, whose rays graze past it; the walled-cavity
test gives one face per connector and zero for the other three.) Depth maps of
each model confirm it by eye: the jack's bore with its centre pin, the USB-C
mouth with its tongue, the microSD card slot.

On the submitted board the USB-C (J3), the DC jack (J1) and the microSD socket
(J2) all opened **into** the board. The placer only knew each connector's box
and chose 0 or 90 degrees by box shape, so which end faced out was chance, and
it lost three times. Nothing could have been plugged in.

`geom2.EDGE_SPEC` now records each connector's opening direction and the
distance from its envelope centre to the body face, `test_mating.py` checks
both against the models, and the placer turns each connector so it opens
through its edge, then pushes it out until the **body face** (not the
footprint envelope, which reaches 0.25-1.5 mm past it) is on the outline. That
last part matters for USB-C: the plug's overmold reaches below the board's top
face, so board in front of the receptacle stops the plug before it seats.

### Copper ran through mechanical holes

`pcb2dsn` skipped non-plated holes, so the router never saw them. On the
submitted board 140 traces and 12 vias cross the peg holes of the jack and the
USB-C receptacles, where the drill would cut them. `drc.py` did not check
holes either, so it reported the board clean. Holes are now router obstacles
sized for JLCPCB's 0.2 mm hole-to-copper rule, and `drc.py`, `collide.py` and
`legalize.py` all treat them as keep-outs on every layer.

### The placer had silently stopped placing

`aplace` (quadratic placement) failed to legalise at every outline, and
`build_board` fell back to the bottom-left packer without saying so: HPWL
6,174 mm instead of ~4,100. The trigger was the through-hole jack and header
reserving room on the far side that the fixed side split did not budget for.
The packer now lets a part that is not pinned to the top take the other side
when its own is full, and `aplace` searches all 64 assignments of the three
edge connectors to board edges.

Fixed on the way, each of which had been quietly wrong:

* far-side reservations for through-hole pads were mirrored about the part
  centre (a Y-down rotation applied in a Y-up frame), and took quarter turns as
  degrees, so a rotated part's holes were reserved as if turned 1 degree;
* the perimeter scan overwrote its own edge length with a hole area, so each
  connector only ever tried the corner slot of each edge;
* a substituted part took its through-hole flag and holes from the footprint
  it replaced (the SMD header was treated as through-hole);
* `mkboard` and `validate` sized every pad as a circle of its long side, which
  grew the outline by up to 0.45 mm around pads that were 0.9 mm inside it —
  and growing the outline set the connectors back from it again.

`interfere.py` adds the last missing check: every pair of component bodies,
placed from their own STEP models (or the scored fallback box), must not
touch. It finds nothing on the current boards, but nothing had looked.

### A lower jack, measured

The CUI PJ-063AH takes the same plug as the PJ-002AH (2.0 mm centre pin,
5.5 mm barrel) and is rated 24 V / 8 A. KiCad's model of it stands 9.0 mm
above the board against 11.0 mm, with its pins 3.0 mm below the top face. It
is through-hole, so the stack is 9.0 + T + max(1.6, 3.0 - T), which is 12.0 mm
for any board from 0.8 to 1.4 mm. The board is 1.2 mm, where the through-hole
2x4 header's 3.0 mm tail ties with the jack's pins, so the SMD header (which
saves no height there and costs area) is dropped. The PJ-002AH brings its
sleeve out twice (GND and GNDBREAK, both on GND); the PJ-063AH has one sleeve
terminal, and `lvs.py` checks the two schematic pins are on one net before
accepting the merge. The model is vendored in `pcbgolf-gen.3dshapes/`.

At 44 x 46 mm that is 24,288 mm^3, against 29,258 for the submitted board.

## 13. Pin and gate swapping, and the upstream op-amp fix

**The op-amps.** Upstream fixed a wrong part number (commaai/pcbgolf 7b5f429):
U9-U12 sit on +12 V, so the 5.5 V NCS20071 became the 36 V OPA197IDR, SOIC-8 —
and the old schematic had SOT-553 pin numbers on that SOIC footprint. The
netlist was rebuilt from the fixed schematic. OPA197 also ships as
OPA197IDBVR (SOT-23-5, 1 OUT, 2 V-, 3 +IN, 4 -IN, 5 V+), which is what the board
uses, through an explicit SOIC-to-SOT pin map that `lvs.py` checks. The
submitted board predates the fix and fails LVS by 36 pins.

**Pin assignment** (`pinopt.py`), borrowed from FPGA place-and-route: where
firmware or a register makes a pin a free choice, choose it by where the
signal goes.

* MCU: every GPIO-class signal may take any free GPIO pin and every analog
  input any free ADC pin, solved as a minimum-length bipartite matching (which
  cannot contain a crossing pair). Analog inputs only on ADC pins — this is
  what fixes the SBU sense lines (§8b). Power enables and relay drives stay
  off PA15/PB3/PB4, which come out of reset pulled or driven as JTAG, so a
  channel cannot switch before firmware runs. SWD, BOOT, LSE/RTC and every
  fixed-function pin stay put.
* USB hub: the USB2517's PORT_SWAP (0xFA) and PORT_MAP (0xFB-0xFE) registers,
  verified against the Linux `usb251xb` driver, let any downstream port serve
  any consumer with either D+/D- polarity, set over the SMBus the MCU already
  drives. The host still sees the original numbering.
* Orientation: any part away from the edge may turn 180 degrees about its
  envelope centre, which cannot create an overlap.

`FIRMWARE_PINMAP.md` lists every pin and register change for the current
board. On q44x46 it cut pad-to-pad HPWL from 4,073 to 3,732 mm.

## 14. A complete board, and what it took

**Submitted: 44 x 46 x 12.0 mm, 4 layers, 397 vias, 0 short — 64,138**
(24,288 + 19,850 + 20,000), 24% under 84,578. 0 DRC violations, LVS pass,
connector openings on the outline, no colliding bodies. The first complete
board was 46 x 48 on 6 layers at 74,946; the 4-layer one replaced it.

Four things got it there, none of them more router passes.

**Routing uninterrupted.** `chain.py` routed in resumable chunks so a
restart cost one chunk. But Freerouting's rip-up cost is start x pass
number and its maze randomisation starts at pass 4, and a resumed run counts
passes from 1 again: every chunk opened by cheaply tearing up what it was
handed. Chunked, 46 x 48 stalled at 46 short and 48 x 50 at 49; the same
boards routed in one run reached 3 short each. (Continuing the cost by
raising the start value overshoots, because the cost is linear in the local
pass number: by the end of a chunk it was 7x the uninterrupted schedule and
the router stopped rearranging anything.)

**Crystals beside their chips.** The packer places largest first, so a
crystal landed wherever room was left: 10-13 mm of trace from its chip on
every placement, and the hub crystal was the one connection the router could
not close. Crystals now pack straight after the ICs, on the same side, aimed
at the chip's oscillator pins: 2.6-5.2 mm.

**Room under the USB-C bridges.** Inside each vertical USB-C receptacle the
D+ and D- pairs cross between the pad rows, so one needs a via in a 0.78 mm
channel: the connections the router most often left open. The placer now
keeps the far side clear under that channel (`geom2.FIXED_VIAS`), and
`usbc_bridge.py` draws the bridges by hand. (The 46 x 48 board was routed before
`route.py` was fixed to keep locked copper, so the router drew its own
bridges there; the submitted 4-layer board carries the hand-drawn ones.)

**Clearance, not overlap, in legalisation.** `legalize.py` only separated
pads that overlapped, and judged a top connector's bottom shell pads as
top-side. A 0.079 mm gap passed placement and failed the 0.09 mm copper rule
after routing.

What did not help: rip-up around the last gaps followed by the A* finisher
made every board worse (1 short became 5-14); Freerouting's via optimizer
accepts the complete board and stops after one pass with no change, its
2.5% improvement threshold unmet.

**Several runs, not one.** With the USB-C bridges locked in (and `route.py`
fixed to keep them), three uninterrupted runs of the same 44 x 46 4-layer
board ended 2 short, 1 short and complete. Freerouting's multi-threaded runs
differ from one to the next, so on a board this close to its limit the
cheapest finisher is another run, not a smarter one.

**After completion: area and vias, and what each is worth.** Z is fixed at
12.0 by the jack (9.0 above the board, pins 3.0 below its top face), so only
area and vias move. A 43 x 45 board saves 1,068 mm^3 but routed with 414-419
vias, so finished it would gain about 200 points: area and vias still trade
about 1:1. Raising Freerouting's via cost on the 44 x 46 placement: 320 gave
395 vias, 2 short, which `finish_router.py` closed (397 vias, 64,138, now
submitted); 400 gave 373 vias but 6 short; 600 never got close. Freerouting's
optimizer, given a near-zero improvement threshold and 60 passes, still
stops after two with no change.

**Two layers, revisited.** Dropping to 2 layers saves 10,000 points, which
pays for about 830 mm^2 more board at Z = 12. With everything above in place
(bridges, crystals, clearance), 2-layer boards at 50 x 52 and 54 x 56 were
built clean (0 DRC violations, LVS pass) and routed uninterrupted: 54 x 56
stagnated at 52 connections short (310 vias) after 5 hours; 50 x 52 was still
55-67 short at pass 69. Four layers stays.

**Via cost, more runs.** Three more runs at via cost 400 on the 44 x 46
placement ended 5 short (398 vias), 3 short (389), and 3 short (373, the first
run). The finisher took one of them to 2 short at 392 vias -- worth at most
~150 points if finished. Freerouting's run-to-run variance (373-398 vias at
the same settings) is as large as the effect of the setting.

