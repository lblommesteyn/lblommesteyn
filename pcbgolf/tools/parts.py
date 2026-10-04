"""Curated part geometry + replacement candidates for PCBGolf.

W/H are placement footprint (pad bbox grown by courtyard clearance), Z is height
above the board surface in mm. Sources: KiCad footprints in pcbgolf.pretty
(measured), STEP models in pcbgolf.3dshapes (measured), and part datasheets.
"""

# footprint -> (W, H, Z_above_board, note)
GEOM = {
    '0402-R':                  (1.95, 0.97, 0.35, 'OCC STEP z=0.35'),
    '0402-C':                  (1.95, 0.97, 0.5, 'OCC STEP z=0.50'),
    '0805-C':                  (3.00, 1.60, 1.25, 'OCC STEP z=1.25'),
    '0603-L':                  (2.95, 1.97, 0.8, 'OCC STEP z=0.80'),
    '0806':                    (2.75, 2.00, 1.05, 'OCC STEP z=1.05'),
    'SOT23-3':                 (3.10, 3.40, 1.2, 'OCC STEP z=1.20'),
    'SOT23-5':                 (2.85, 4.20, 1.55, 'OCC STEP z=1.55'),
    'SOT23-6':                 (2.90, 3.60, 1.55, 'OCC STEP z=1.55'),
    'SOIC-8_3.9x4.9mm_P1.27mm':(7.40, 5.40, 1.75, 'OCC STEP z=1.75'),
    'TDFN8_2X3MC_MCH':         (4.00, 2.15, 0.93, 'OCC STEP z=0.93'),
    'WQFN20':                  (3.40, 4.80, 0.77, 'OCC STEP z=0.77'),
    'QFN64-9X9':               (9.40, 9.80, 0.95, 'OCC STEP z=0.95'),
    'LQFP-144_20x20mm_P0.5mm': (23.30, 23.30, 1.5, 'OCC STEP z=1.50'),
    'XTAL-3.2X2.5':            (4.00, 3.20, 0.64, 'OCC STEP z=0.64'),
    'L-1008':                  (4.40, 2.60, 1.2, 'OCC STEP z=1.20'),
    'CHIPLED':                 (1.60, 3.70, 1.1, 'OCC STEP z=1.10'),
    'CREE-RGB-CLMVC':          (2.90, 2.30, 1, 'OCC STEP z=1.00'),
    'SOD-123F':                (1.60, 4.25, 1.1, 'OCC STEP z=1.10'),
    'DO-214AA(SMB)':           (7.00, 3.15, 2.15, 'OCC STEP z=2.15'),
    'PP-1212-8':               (4.26, 2.78, 1.12, 'OCC STEP z=1.12'),
    'CHOKE-3.2X2.5':           (4.45, 2.90, 2.33, 'OCC STEP z=2.33'),
    'EVQ-Q2':                  (10.40, 5.60, 3.1, 'OCC STEP z=3.10'),
    '0472192001':              (15.60, 10.70, 2.01, 'OCC STEP z=2.01'),
    'USB-C-FEMALE-VERT-GCT':   (8.93, 5.80, 8.8, 'VERTICAL USB-C; OCC STEP z=+8.80/-1.30'),
    'DX07S024XJ1R1100':        (10.70, 6.86, 3.37, 'JAE USB-C horizontal, host; OCC STEP z=3.37'),
    'DCJACK_2MM_SMT':          (15.65, 9.40, 11.01, '2.0mm barrel jack, tallest part; OCC STEP z=+11.01/-0.81'),
    '2X04':                    (9.90, 4.82, 8.50, '2.54mm 2x4 vertical header'),
    'M2_BOLT':                 (4.60, 4.60, 0.00, 'mounting hole'),
}

# Replacement candidates: from_fp -> list of dicts
# d_vias = extra vias this part forces (BGA escape etc.)
SWAPS = {
    '0402-R': [dict(to='0201-R', W=1.15, H=0.65, Z=0.30, d_vias=0,
                    part='0201 thick-film', risk='low',
                    note='JLCPCB assembles 0201; all resistor values available')],
    '0402-C': [dict(to='0201-C', W=1.15, H=0.65, Z=0.35, d_vias=0,
                    part='0201 X5R/X7R', risk='low',
                    note='100nF/12pF/220pF fine in 0201; keep 10uF at 0402')],
    '0805-C': [dict(to='0603-C', W=2.20, H=1.30, Z=0.95, d_vias=0,
                    part='0603 10uF 25V X5R', risk='low',
                    note='10uF 0603 widely stocked; derate check on 12V rail')],
    'SOIC-8_3.9x4.9mm_P1.27mm': [
        dict(to='SC70-5', W=2.60, H=2.90, Z=1.10, d_vias=0,
             part='NCS20071XV5T2G', risk='none',
             note='SAME die in SC-70-5. The schematic symbol is literally named '
                  '"NCS20071XV" but the fitted MPN is the SOIC-8 SN2 part: free 33 mm^2 each.'),
        dict(to='SOT23-5', W=2.85, H=4.20, Z=1.55, d_vias=0,
             part='NCS20071SN1T1G', risk='none',
             note='SAME die, SOT23-5 instead of SOIC-8.')],
    'LQFP-144_20x20mm_P0.5mm': [
        dict(to='LQFP-100_14x14', W=16.20, H=16.20, Z=1.60, d_vias=0,
             part='STM32H725VGT6', risk='low',
             note='same die/flash, 82 GPIO vs 50 needed; no escape vias'),
        dict(to='VFQFN-68_8x8', W=8.60, H=8.60, Z=0.90, d_vias=0,
             part='STM32H725R.V6 (VFQFN68)', risk='high',
             note='~50 GPIO available vs 50 needed - verify every AF mapping'),
        dict(to='TFBGA-100_8x8', W=8.60, H=8.60, Z=1.20, d_vias=64,
             part='STM32H725VGH6', risk='med',
             note='0.8mm pitch, dogbone escape, 4 layers min'),
        dict(to='UFBGA-169_7x7', W=7.60, H=7.60, Z=0.80, d_vias=110,
             part='STM32H725AGI6', risk='high',
             note='0.5mm pitch, needs via-in-pad / HDI'),
        dict(to='WLCSP-115_3.75x4.15', W=4.35, H=4.75, Z=0.60, d_vias=115,
             part='STM32H725 WLCSP115', risk='extreme',
             note='0.4mm pitch, HDI microvias mandatory'),
    ],
    'USB-C-FEMALE-VERT-GCT': [
        dict(to='USB-C-HORIZ-SMT', W=9.20, H=7.60, Z=3.26, d_vias=0,
             part='GCT USB4085 / Amphenol 12401548E4-2A', risk='low',
             note='same USB-C receptacle, edge/top mount instead of vertical'),
        dict(to='USB-C-MIDMOUNT', W=9.20, H=7.60, Z=1.85, d_vias=0,
             part='mid-mount USB-C (board in cutout)', risk='med',
             note='3.26mm body straddles PCB: ~1.85 above / ~1.4 below'),
    ],
    'DCJACK_2MM_SMT': [
        dict(to='DCJACK-LOWPROFILE', W=14.00, H=9.00, Z=7.00, d_vias=0,
             part='low-profile 2.0/5.5mm SMT jack', risk='low',
             note='5.5mm bore is a hard floor -> ~6.5mm body'),
        dict(to='DCJACK-MIDMOUNT', W=14.00, H=9.00, Z=4.00, d_vias=0,
             part='2.0/5.5mm jack in PCB cutout', risk='med',
             note='barrel centred on board plane: ~3.4 above / ~3.4 below'),
    ],
    '2X04': [
        dict(to='2X04-RA', W=10.20, H=8.90, Z=5.20, d_vias=0,
             part='2.54mm 2x4 right-angle header', risk='low',
             note='same 2.54mm mating interface, lies down instead of up'),
    ],
    'QFN64-9X9': [
        dict(to='QFN64-keep', W=9.40, H=9.80, Z=1.00, d_vias=0,
             part='USB2517 (keep)', risk='none',
             note='only 5 of 7 downstream ports used, but no 5-port single chip exists'),
    ],
}

# Heights for the generated/imported footprints (mm above the board).
GEN_Z = {
    '0201-R': 0.30, '0201-C': 0.35, '0603-C': 0.95,
    'SC70-5': 1.10,                 # SC-70-5 body 1.10 max
    'LQFP-100_14x14': 1.60,         # LQFP 1.40 body + standoff, as LQFP-144
    'USB-C-MIDMOUNT': 3.26,         # Amphenol 12401548E4-2A right-angle USB-C
    '2X04-RA': 5.10,                # 2.54mm right-angle header, two rows
}
# The substituted footprints have no 3D model, so their XY extent has to come
# from the swap table; a zero-size placeholder would drop them out of the
# assembly bounding box and the exported STEP.
_SWAP_WH = {}
for _lst in SWAPS.values():
    for _s in _lst:
        _SWAP_WH.setdefault(_s['to'], (_s['W'], _s['H'], _s['Z']))

for _k, _v in GEN_Z.items():
    _wh = _SWAP_WH.get(_k)
    if _wh:
        GEOM.setdefault(_k, (_wh[0], _wh[1], _v, 'generated footprint; swap-table courtyard'))
    else:
        GEOM.setdefault(_k, (0.0, 0.0, _v, 'generated/imported footprint'))

# Through-hole lead tails stick out the far side of the board, and the PCBA
# bounding box has to contain them.  Parts that ship a 3D model already show
# their own leads (the vertical USB-C reaches 1.30 mm below its mounting face,
# the barrel jack 0.81 mm -- both inside a 1.6 mm board).  These have no model,
# so the tail length is taken from the standard part the land pattern implies:
# a 2.54 mm male header has a 3.0 mm tail under a 2.5 mm insulator.
LEAD_TAIL = {
    '2X04':    3.00,   # 2.54mm 2x4 male header, 6.0 mate + 2.5 body + 3.0 tail
    '2X04-RA': 3.00,   # same pin stock, right-angle body
}

_missing_wh = [k for k, v in GEOM.items() if v[2] > 0 and (v[0] <= 0 or v[1] <= 0)]
if _missing_wh:                                  # pragma: no cover - guard
    raise AssertionError('footprints with height but no XY extent: %s' % _missing_wh)


def geom(fp):
    return GEOM.get(fp.split(':')[-1])
