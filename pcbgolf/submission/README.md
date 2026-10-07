# PCBGolf submission — comma.ai PCBGolf challenge

```
score = PCBA bounding-box volume (mm^3) + 50 x vias + 5,000 x copper layers
```

## The board

`pcbgolf-u44x46-4L-v320f.kicad_pcb` — 44.0 x 46.0 mm, 4 copper layers, 1.2 mm
FR4, **fully routed**.

| term | value |
|---|---|
| volume | 24,288 mm^3 (44.0 x 46.0 x 12.0) |
| vias | 397 x 50 = 19,850 |
| layers | 4 x 5,000 = 20,000 |
| **score** | **64,138** |

24% under the 84,578 leaderboard. `pcbgolf-u44x46-4L-v320f.step` is the assembly.

Routed by Freerouting at via cost 320, with the last two connections closed
by `finish_router.py`.

## What is verified

Every check runs on the file in this folder (`tools/regen_submission.py`
refuses to package a board that fails any of them):

* **Complete.** 0 connections missing (`ratsnest.py`; `UNROUTED.csv` is empty).
* **Wired as the schematic.** LVS passes (`lvs.py`): every net compared as a
  pin set through each package pin map, the LQFP-100 remap and the declared
  hub port swaps.
* **Clearance clean.** 0 violations at 0.09 mm by exact swept geometry
  (`drc.py`), and all copper at least 0.2 mm from every non-plated hole.
  No two parts' pads closer than 0.10 mm (`collide.py`).
* **Can be plugged in.** The USB-C, the DC jack and the microSD socket each
  open through the board edge, found from the parts' own 3D models
  (`mating.py`); the opening faces sit on the outline.
* **Assembles.** No two component bodies touch in 3D (`interfere.py`), with
  through-hole pins and the jack's pins below a 1.2 mm board included.
* **Volume measured from the 3D assembly**, from the parts' STEP models; the
  STEP file here is written from the same placed geometry. Nothing overhangs
  the outline. (A STEP reader's own bounding box shows 44.01 x 46.01 x 12.01:
  OpenCASCADE's 0.005 mm tolerance on each face.)
* **Within JLCPCB's standard 4-layer capability**: 0.09 mm track and space,
  0.45 mm vias on a 0.2 mm drill, 1.2 mm board.
* **USB-C D+/D- bridges** inside the four vertical receptacles are drawn by
  hand (`usbc_bridge.py`) and locked; the router worked around them.

Nothing is simulated and no board has been fabricated.

## Changes from the original design

| part | from | to | why |
|---|---|---|---|
| U3 MCU | STM32H725ZGT6, LQFP-144 | STM32H725VGT6, LQFP-100 | same die and 1 MB flash, 14x14 mm instead of 20x20; 82 GPIO against 50 used |
| U9-U12 op-amps | OPA197IDR, SOIC-8 | OPA197IDBVR, SOT-23-5 | same part (upstream's corrected 36 V op-amp) in its smaller package |
| J1 DC jack | CUI PJ-002AH-SMT | CUI PJ-063AH | same 5.5 / 2.0 mm plug, 24 V 8 A; 9.0 mm tall instead of 11.0 |
| 0402 R and C | 0402 | 0201 | JLCPCB assembles 0201; all values available |
| 0805 10 uF | 0805 | 0603 | widely stocked at 25 V |
| R11 | fitted | not fitted | it straps LQFP-144's PDR_ON pin, which LQFP-100 does not have |

`BOM.csv` lists every part with its original and new footprint and MPN.

The PJ-002AH brings its sleeve out on two pads (GND and GNDBREAK), both on GND
in the schematic; the PJ-063AH has one sleeve terminal. Every mating connector
keeps its interface: the four vertical OBD-C USB-C ports, the USB-C, the 2x4
CAN header and the microSD socket are the original parts.

## Firmware changes

`FIRMWARE_PINMAP.md` lists them. In short:

* MCU signals moved to shorten routing — each to a pin of the same class
  (analog inputs only to ADC pins; power enables and relay drives kept off the
  pins that come out of reset driven or pulled). This also fixes the first
  LQFP-100 remap, which had put three SBU voltage-sense lines on pins with no
  ADC.
* The USB2517 hub's downstream ports are reassigned and some D+/D- pairs
  swapped through its PORT_MAP (0xFB-0xFE) and PORT_SWAP (0xFA) registers,
  written over the SMBus the MCU already drives. The host still sees the
  original port numbering.

## Notes

* The eight status LEDs (LED10-LED17) are on the bottom side. They work and
  are visible from below; moving them to the top costs about 50 mm^2.
* Both crystals sit within 2.6-5.2 mm of their oscillator pins.
* `SCORE.csv` lists every routed board measured, with the checks each passed.
