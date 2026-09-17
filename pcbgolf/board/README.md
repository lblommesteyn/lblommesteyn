# Generated boards

| file | board | layers | status |
|---|---|---|---|
| `pcbgolf-stock-2L.kicad_pcb` | 42.65 x 46.65 mm | 2 | placed + netlisted, **not routed** |

## How it is built

`tools/mkboard.py` does not synthesise footprints. It loads the upstream
`pcbgolf.kicad_pcb` — a known-valid KiCad 10 file — keeps every footprint block
verbatim, and changes only:

* the footprint's position, rotation and board side,
* pad net assignments,
* the copper stackup and the `Edge.Cuts` outline.

`tools/sexpr.py`'s serialiser is verified **lossless on all 34 upstream KiCad
files** (the PCB, 5 schematics, 28 footprints): 223,805 tokens round-trip with
zero differences. So the only new content in the output is what `mkboard.py`
deliberately writes.

## Flip convention

Placing a footprint on the back mirrors local **Y** (X unchanged), swaps
`F.*` layers for `B.*`, and sets the pad angle to `(rho - a_local) mod 360`;
on the front it is `(rho + a_local) mod 360`.

This was **derived from pcbnew itself**, not guessed: KiCad 7's
`FOOTPRINT::Flip()` and `SetOrientationDegrees()` were run on a deliberately
asymmetric test footprint and the resulting files inspected.
`tools/test_flip.py` asserts `orient_footprint()` reproduces all seven of those
ground-truth cases exactly, plus two invariants.

```
python3 tools/test_flip.py     # 9/9 pass
python3 tools/validate.py board/pcbgolf-stock-2L.kicad_pcb
```

## Validation

`validate.py` checks round-trip, layer stack, outline, every pad inside the
outline, every pad net index consistent with the net table, and that no
back-side footprint carries a stray `F.*` layer. Current result: **PASS**,
245 footprints (127 front / 118 back), 1078 pads, 196 nets, 0 pads outside.

## Not done yet

* **Routing.** Zero tracks, zero vias. The score depends on this.
* The **optimised BOM board** needs footprints that do not exist in
  `pcbgolf.pretty`: LQFP-100, SC-70-5, 0201, 0603, mid-mount USB-C, low-profile
  barrel jack, right-angle 2x4. Building it against the stock footprints fails
  validation exactly as it should — the LQFP-144 overhangs the space reserved
  for an LQFP-100 by 3.05 mm.
* **LQFP-100 pin remapping.** PF11/PG9/PG10 are not bonded out on LQFP100, so
  CH3_IMON and the FDCAN3 pair must move (FDCAN3 is also on PD12/PD13).
* **STEP export.**
