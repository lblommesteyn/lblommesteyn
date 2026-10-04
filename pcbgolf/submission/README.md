# PCBGolf submission — comma.ai PCBGolf challenge

```
score = PCBA bounding-box volume (mm^3) + 50 x vias + 5,000 x copper layers
```

## The board

`pcbgolf-t44x46-ok.kicad_pcb` — 44.05 x 46.775 mm, 4 copper layers, 414 vias.

| term | value |
|---|---|
| volume | 29,258 mm^3 (44.05 x 46.775 x 14.20) |
| vias | 414 x 50 = 20,700 |
| layers | 4 x 5,000 = 20,000 |
| **score** | **69,958** |

17% under the 84,578 leaderboard. `pcbgolf-t44x46-r2.kicad_pcb` is the same
board routed further: 420 vias and 9 connections short instead of 14, scoring
70,258. Both are included; neither is finished.

`pcbgolf-t44x46.step` is the assembly. It is valid for both, because the two
differ only in copper.

## What is verified

* **Clearance clean.** 0 violations and 0 shorts at 0.09 mm, measured by
  `drc.py` with exact swept-polygon geometry — traces, vias, and circle, oval,
  rotated-rect and roundrect pads.
* **Placement legal.** 0 pad overlaps, 0 inter-part pairs under the clearance
  rule. The only sub-clearance pads are inside J3's vendor land pattern
  (0.25 mm-pitch USB-C, tightest 0.086 mm), which the upstream board has too —
  worse, in fact: it has 56 of them including Q1 pads overlapping by 1.1 mm.
* **Manufacturable by JLCPCB.** 0.09 mm track and clearance, 0.45 mm vias on a
  0.2 mm drill, 1.6 mm 4-layer stackup — all standard 4-layer capability.
* **Volume measured from the 3D assembly**, not outline x height, from the
  footprints' own STEP models. Nothing overhangs the copper outline. The STEP
  file is written from the same placed geometry the score is measured from.

## What is not finished

**14 connections are still open** (of 741). `UNROUTED.csv` lists them by net.
They are stranded pads and short gaps, not missing routes; closing them costs
roughly one via each, so a finished board should land near 70,400.

The autorouter converged with these open, and Freerouting's via optimizer only
runs on a completely routed board — so it has never run here. Finishing the
route is worth more than the connections themselves.

Nothing is simulated, and no board has been fabricated.

## Changes from the original design

Four footprint substitutions, all same-function:

| from | to | why |
|---|---|---|
| LQFP-144 STM32H725ZGT6 | LQFP-100 STM32H725VGT6 | same die, same 1 MB flash, 14x14 mm instead of 20x20; 82 GPIO against the 50 used |
| 0402 R and C | 0201 | JLCPCB assembles 0201; all values available |
| 0805 10uF | 0603 | widely stocked at 25 V |
| SOIC-8 NCS20071 | SC70-5 NCS20071XV5T2G | same die, same part family, 5.5x smaller |

The MCU change moves 15 signals, audited pin by pin — two needed a specific
capability rather than any free pin: `CH3_IMON` is an analogue current sense and
had to land on an ADC channel, and CAN2 had to land on FDCAN alternate-function
pins. 0 failed.

**R11 is not fitted.** It straps PDR_ON to +3V3 to enable the internal
power-down reset. The STM32H725VGT6 has no PDR_ON pin — checked against the
KiCad symbol library, where the TFBGA-100 and LQFP-144 parts expose it and the
LQFP-100 does not — because the reset is permanently enabled internally. With
R11 fitted its net would have a single pad and read as a broken connection.

VDD50USB also disappears with the package and needs no action: tying it to
3.3 V is how the original bypasses the internal USB regulator, and the LQFP-100
keeps VDD33USB, which the board supplies on pin 76.

All interfaces, connectors and functionality are unchanged: 12 V barrel jack,
four OBD-C ports, USB-C host, USB hub, four CAN-FD transceivers, microSD,
button, LEDs. Every mating connector is the original part.

## Files

| file | contents |
|---|---|
| `pcbgolf-t44x46-ok.kicad_pcb` | the board, 414 vias, 14 connections short |
| `pcbgolf-t44x46-r2.kicad_pcb` | routed further, 420 vias, 9 short |
| `pcbgolf-t44x46.step` | 3D assembly, valid for both |
| `SCORE.csv` | every measured board: volume, vias, connectivity, DRC |
| `UNROUTED.csv` | the connections still open on the submitted board |
| `BOM.csv` | 244 parts, derived from the board file |
| `placement.csv` | reference, footprint, position, rotation, side |
| `netlist.csv` | the netlist rebuilt from the five schematic sheets |
