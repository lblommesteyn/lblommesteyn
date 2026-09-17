# Prospective case studies

Each case: (1) what was public on the queue date, (2) the model's ranked prediction made from that information only, (3) the ISO study revealed later, (4) why the model was right or wrong (the explanation may quote hidden-world diagnostics such as the true distribution factor; those were never available to the model).

## Q23-2333 — clear hit (top-1 correct, several facilities)

**Project**: battery (storage), 107 MW at Todd 100 kV, queued 2023-08-23. Prediction made as of 2023-08-24; study published 2025-10-26.

**Public context at the time**: no prior study at this POI; 0 earlier queue entries at the POI (0 MW active); 0 MW active queue within 50 km; POI congestion component +0.0 $/MWh (24-month mean); 10 analog projects within 80 km.

**Model output**: difficulty **very high** (expected 7.7 constrained facilities, P(no constraint) = 0.00).

| rank | predicted facility | p | ±sd | evidence | outcome |
|---|---|---|---|---|---|
| 1 | Carquinez - Molalla 100 kV | 0.51 | 0.17 | public-topology distribution factor (N-1) 0.42; public-topology distribution factor 0.27; 1 hops from POI | **HIT** |
| 2 | Forbing Road - Creelman 100 kV | 0.29 | 0.08 | public-topology distribution factor (N-1) 0.20; public-topology distribution factor 0.12; 3 hops from POI | **HIT** |
| 3 | Molalla - Creelman 100 kV | 0.29 | 0.08 | public-topology distribution factor (N-1) 0.20; public-topology distribution factor 0.12; 10 km from POI | **HIT** |
| 4 | Niguel - West Mount Vernon 100 kV | 0.29 | 0.08 | public-topology distribution factor (N-1) 0.20; public-topology distribution factor 0.13; named by 21% (similarity-weighted) of analog projects | **HIT** |
| 5 | Todd - Carquinez 100 kV | 0.29 | 0.14 | public-topology distribution factor (N-1) 0.72; 0 hops from POI; public-topology distribution factor 0.46 | **HIT** |
| 6 | Findlay Wind Farm - Hambrick 100 kV | 0.29 | 0.13 | public-topology distribution factor (N-1) 0.24; public-topology distribution factor 0.15; 3 hops from POI | **HIT** |
| 7 | Findlay Wind Farm - Forbing Road 100 kV | 0.24 | 0.11 | public-topology distribution factor (N-1) 0.20; public-topology distribution factor 0.12; baseline upgrade within 3 years | **HIT** |
| 8 | Delta Person Llc - Todd 100 kV | 0.24 | 0.11 | public-topology distribution factor (N-1) 0.46; 0 hops from POI; public-topology distribution factor 0.26 | **HIT** |
| 9 | Sam Dam - Todd 100 kV | 0.24 | 0.13 | public-topology distribution factor (N-1) 0.36; 0 hops from POI; public-topology distribution factor 0.18 | **HIT** |
| 10 | Dorchester - Delta Person Llc 100 kV | 0.24 | 0.09 | public-topology distribution factor (N-1) 0.46; public-topology distribution factor 0.26; 1 hops from POI | **HIT** |

**Revealed ISO study** (2025-10-26): 26 constrained facilities, total allocated upgrade cost $185.2M (1738 $/kW).

| facility (study) | loading % | pre-project % | true DFAX % | contingency | in candidates | model rank | model p |
|---|---|---|---|---|---|---|---|
| Delta Person Llc - Todd 100 kV | 148.8 | 128.1 | 23.8 | Dorchester - Midvalley 230 kV | yes | 8 | 0.24 |
| Brightwater - West Mount Vernon 100 kV | 140.9 | 111.1 | 32.2 | Carquinez - Molalla 100 kV | yes | 15 | 0.14 |
| Sam Dam - Todd 100 kV | 136.6 | 117.9 | 21.0 | Dorchester - Demoss 230 kV | yes | 9 | 0.24 |
| Todd - Carquinez 100 kV | 136.6 | 118.8 | 46.3 | Dorchester - Midvalley 230 kV | yes | 5 | 0.29 |
| Carquinez - Molalla 100 kV | 124.8 | 111.6 | 28.4 | Dorchester - Midvalley 230 kV | yes | 1 | 0.51 |
| Waldo - Moss Lake 230 kV | 119.1 | 115.8 | 18.9 | Galion Generating Station 500/230 kV Transformer | yes | 69 | 0.02 |
| Sam Dam - Brownstown 100 kV | 118.7 | 110.4 | 9.1 | Dorchester - Demoss 230 kV | yes | 16 | 0.09 |
| Dorchester 230/100 kV Transformer | 117.4 | 100.7 | 32.2 | Dorchester - Demoss 230 kV | yes | 26 | 0.08 |
| Niguel - West Mount Vernon 100 kV | 116.3 | 109.6 | 13.2 | Tecumseh - Galion Generating Station 500 kV | yes | 4 | 0.29 |
| Brownstown - Wisdom 100 kV | 116.3 | 107.0 | 9.1 | Dorchester - Demoss 230 kV | yes | 25 | 0.08 |
| Brightwater - Carquinez 100 kV | 116.2 | 88.0 | 32.2 | Carquinez - Molalla 100 kV | yes | 14 | 0.14 |
| Findlay Wind Farm 230/100 kV Transformer | 114.6 | 110.0 | 10.1 | Dorchester - Midvalley 230 kV | yes | 42 | 0.04 |
| Dorchester - Delta Person Llc 100 kV | 114.1 | 96.2 | 22.1 | Dorchester - Demoss 230 kV | yes | 10 | 0.24 |
| Rockview - Niguel 100 kV | 112.2 | 108.2 | 6.8 | Tecumseh - Troy Energy Llc 500 kV | yes | 31 | 0.07 |
| Findlay Wind Farm - Hambrick 100 kV | 111.1 | 104.1 | 16.8 | Dorchester - Midvalley 230 kV | yes | 6 | 0.29 |
| Charles R Lowman - Germantown Sw Yd 100 kV | 110.4 | 106.8 | 6.8 | Tecumseh - Troy Energy Llc 500 kV | yes | 12 | 0.14 |
| Molalla - Creelman 100 kV | 110.3 | 96.2 | 21.8 | Findlay Wind Farm - Hambrick 100 kV | yes | 3 | 0.29 |
| Forbing Road - Creelman 100 kV | 110.3 | 97.3 | 21.8 | Findlay Wind Farm - Hambrick 100 kV | yes | 2 | 0.29 |
| Molalla - Hambrick 100 kV | 109.8 | 91.5 | 22.9 | Findlay Wind Farm - Forbing Road 100 kV | yes | 21 | 0.09 |
| Moss Lake - Galion Generating Station 230 kV | 107.8 | 104.7 | 18.9 | Galion Generating Station 500/230 kV Transformer | yes | 68 | 0.02 |
| Germantown Sw Yd - West Batesville 100 kV | 107.2 | 105.2 | 5.0 | Adams - Calera T.S 230 kV | yes | 32 | 0.07 |
| Chaska Sw Station - Galion Generating Station 230 kV | 106.8 | 104.1 | 21.3 | Midvalley - Galion Generating Station 230 kV | yes | 54 | 0.04 |
| Chaska Sw Station - Findlay Wind Farm 230 kV | 105.9 | 103.1 | 21.3 | Midvalley - Galion Generating Station 230 kV | yes | 57 | 0.03 |
| Findlay Wind Farm - Midvalley 230 kV | 105.2 | 101.5 | 18.0 | Dorchester - Midvalley 230 kV | yes | 52 | 0.04 |
| Findlay Wind Farm - Forbing Road 100 kV | 102.5 | 91.7 | 21.8 | Findlay Wind Farm - Hambrick 100 kV | yes | 7 | 0.24 |
| West Salem - Wisdom 100 kV | 102.5 | 93.8 | 9.1 | Dorchester - Demoss 230 kV | yes | 18 | 0.09 |

**Why**: 10 of 26 true facilities were in the top-10 (first hit at rank 1). Missed Brightwater - West Mount Vernon 100 kV (rank 11, p=0.14): never named in a prior study; never bound in sampled market hours; facility sat at 111% pre-project (hair-trigger headroom invisible publicly). Missed Brightwater - Carquinez 100 kV (rank 11, p=0.14): never named in a prior study; never bound in sampled market hours. Missed Dorchester 230/100 kV Transformer (rank 25, p=0.08): never named in a prior study; never bound in sampled market hours; facility sat at 101% pre-project (hair-trigger headroom invisible publicly). Missed Waldo - Moss Lake 230 kV (rank 63, p=0.02): never named in a prior study; never bound in sampled market hours; facility sat at 116% pre-project (hair-trigger headroom invisible publicly).

## Q23-2305 — clear hit (top-1 correct, several facilities)

**Project**: gen (gas), 1500 MW at Phoenix 138 kV, queued 2023-04-16. Prediction made as of 2023-04-17; study published 2025-02-01.

**Public context at the time**: previously studied POI; 12 earlier queue entries at the POI (0 MW active); 0 MW active queue within 50 km; POI congestion component +0.0 $/MWh (24-month mean); 10 analog projects within 80 km.

**Model output**: difficulty **very high** (expected 8.9 constrained facilities, P(no constraint) = 0.00).

| rank | predicted facility | p | ±sd | evidence | outcome |
|---|---|---|---|---|---|
| 1 | Tumbler Ridge - Grafton 138 kV | 0.51 | 0.19 | estimated flow contribution 300 MW; public-topology distribution factor (N-1) 0.20; 4 km from POI | **HIT** |
| 2 | Tumbler Ridge - Cooper 138 kV | 0.39 | 0.18 | estimated flow contribution 846 MW; public-topology distribution factor (N-1) 0.56; 1 hops from POI | **HIT** |
| 3 | New London Avenue - Ponchatoula 138 kV | 0.14 | 0.01 | public-topology distribution factor (N-1) 0.56; estimated flow contribution 837 MW; public-topology distribution factor 0.28 | **HIT** |
| 4 | Tumbler Ridge - Phoenix 138 kV | 0.14 | 0.04 | estimated flow contribution 1498 MW; public-topology distribution factor (N-1) 1.00; 0 hops from POI | **HIT** |
| 5 | Danish Creamery - Ponchatoula 138 kV | 0.14 | 0.01 | public-topology distribution factor (N-1) 0.56; estimated flow contribution 837 MW; public-topology distribution factor 0.28 | **HIT** |
| 6 | Zobel - Bennett 138 kV | 0.14 | 0.16 | estimated flow contribution 308 MW; public-topology distribution factor (N-1) 0.21; named by 1 prior projects at this POI | - |
| 7 | Bennett - Cooper 138 kV | 0.09 | 0.02 | estimated flow contribution 514 MW; public-topology distribution factor (N-1) 0.34; named by 29% (similarity-weighted) of analog projects | **HIT** |
| 8 | Tumbler Ridge - West County Energy Center 138 kV | 0.09 | 0.02 | estimated flow contribution 458 MW; public-topology distribution factor (N-1) 0.31; 1 hops from POI | **HIT** |
| 9 | Sahtlam - Grafton 138 kV | 0.08 | 0.01 | public-topology distribution factor (N-1) 0.20; estimated flow contribution 300 MW; 2 hops from POI | **HIT** |
| 10 | Santiam - New London Avenue 138 kV | 0.07 | 0.02 | public-topology distribution factor (N-1) 0.23; estimated flow contribution 342 MW; public-topology distribution factor 0.12 | **HIT** |

**Revealed ISO study** (2025-02-01): 25 constrained facilities, total allocated upgrade cost $180.4M (120 $/kW).

| facility (study) | loading % | pre-project % | true DFAX % | contingency | in candidates | model rank | model p |
|---|---|---|---|---|---|---|---|
| Tumbler Ridge - Phoenix 138 kV | 248.5 | 39.6 | 99.9 | New Hope Ap - Red Tail 345 kV | yes | 4 | 0.14 |
| Santiam - West County Energy Center 138 kV | 196.8 | 38.7 | 25.3 | Tumbler Ridge - New London Avenue 138 kV | yes | 13 | 0.07 |
| Tumbler Ridge - West County Energy Center 138 kV | 193.4 | 40.6 | 25.3 | Tumbler Ridge - New London Avenue 138 kV | yes | 8 | 0.09 |
| Tumbler Ridge - New London Avenue 138 kV | 187.3 | 34.3 | 35.8 | Tumbler Ridge - Cooper 138 kV | yes | 11 | 0.07 |
| Tumbler Ridge - Cooper 138 kV | 184.6 | 26.5 | 41.3 | Tumbler Ridge - New London Avenue 138 kV | yes | 2 | 0.39 |
| New London Avenue - Ponchatoula 138 kV | 183.1 | 4.3 | 39.3 | Tumbler Ridge - Cooper 138 kV | yes | 3 | 0.14 |
| Danish Creamery - Ponchatoula 138 kV | 179.7 | 3.4 | 39.3 | Tumbler Ridge - Cooper 138 kV | yes | 5 | 0.14 |
| Laclede - Albreda Tans Mtn Tap 138 kV | 175.1 | 84.6 | 19.6 | El Centro - Cooper 345 kV | yes | 51 | 0.04 |
| Laclede - New London Avenue 138 kV | 173.4 | 85.6 | 19.6 | El Centro - Cooper 345 kV | yes | 53 | 0.04 |
| Santiam - New London Avenue 138 kV | 162.8 | 37.7 | 22.9 | Tumbler Ridge - New London Avenue 138 kV | yes | 10 | 0.07 |
| Lenkurt - Division Creek 138 kV | 154.4 | 80.6 | 15.2 | El Centro - Cooper 345 kV | yes | 103 | 0.03 |
| Division Creek - Albreda Tans Mtn Tap 138 kV | 151.8 | 81.2 | 15.2 | El Centro - Cooper 345 kV | yes | 97 | 0.03 |
| Sahtlam - Grafton 138 kV | 146.5 | 32.6 | 18.2 | Tumbler Ridge - Cooper 138 kV | yes | 9 | 0.08 |
| Tumbler Ridge - Grafton 138 kV | 144.4 | 34.9 | 18.2 | Tumbler Ridge - Cooper 138 kV | yes | 1 | 0.51 |
| Batesville Generation Facility - Blewett 138 kV | 143.7 | 71.1 | 8.4 | El Centro - Cooper 345 kV | yes | 58 | 0.04 |
| Blewett - Salt Fork Wind 138 kV | 137.8 | 73.2 | 8.4 | El Centro - Cooper 345 kV | yes | 41 | 0.04 |
| Hawaiian Comm & Sugar Puunene Mill - Cordrey 138 kV | 137.0 | 80.8 | 8.4 | El Centro - Cooper 345 kV | yes | 89 | 0.04 |
| Hawaiian Comm & Sugar Puunene Mill - Salt Fork Wind 138 kV | 136.5 | 78.1 | 8.4 | El Centro - Cooper 345 kV | yes | 40 | 0.04 |
| Strasburg - North Creek 138 kV | 128.5 | 57.9 | 9.7 | Strasburg - Marathon Electric 138 kV | yes | 35 | 0.04 |
| Bennett - Cooper 138 kV | 127.2 | 56.1 | 18.2 | El Centro - Cooper 345 kV | yes | 7 | 0.09 |
| Crabb River Road - Rhinelander Paper 138 kV | 126.0 | 64.6 | 16.4 | El Centro - Cooper 345 kV | yes | 62 | 0.04 |
| Creedmoor - West Fairbault 138 kV | 125.9 | 26.8 | 14.8 | Tumbler Ridge - Cooper 138 kV | yes | 22 | 0.07 |
| American - Smi 138 kV | 124.0 | 69.7 | 7.5 | American - Sahtlam 138 kV | yes | 464 | 0.00 |
| Interchange - Complejo De Aguirre 230 138 kV | 124.0 | 80.4 | 8.4 | El Centro - Cooper 345 kV | yes | 37 | 0.04 |
| Strasburg - Moshers 138 kV | 123.7 | 63.1 | 9.0 | El Centro - Cooper 345 kV | yes | 83 | 0.04 |

**Why**: 9 of 25 true facilities were in the top-10 (first hit at rank 1). Missed Strasburg - Moshers 138 kV (rank 57, p=0.04): never named in a prior study; never bound in sampled market hours. Missed Creedmoor - West Fairbault 138 kV (rank 10, p=0.07): never named in a prior study; never bound in sampled market hours. Missed Interchange - Complejo De Aguirre 230 138 kV (rank 31, p=0.04): never bound in sampled market hours. Missed Laclede - New London Avenue 138 kV (rank 31, p=0.04): never bound in sampled market hours.

## Q22-2120 — miss (no true facility in top-5)

**Project**: gen (solar), 475 MW at Oakwood 138 kV, queued 2022-06-30. Prediction made as of 2022-07-01; study published 2023-07-21.

**Public context at the time**: no prior study at this POI; 0 earlier queue entries at the POI (0 MW active); 0 MW active queue within 50 km; POI congestion component +0.0 $/MWh (24-month mean); 10 analog projects within 80 km.

**Model output**: difficulty **very high** (expected 13.4 constrained facilities, P(no constraint) = 0.00).

| rank | predicted facility | p | ±sd | evidence | outcome |
|---|---|---|---|---|---|
| 1 | Monohans - Oakwood 138 kV | 0.92 | 0.02 | estimated flow contribution 475 MW; public-topology distribution factor (N-1) 1.00; 0 hops from POI | - |
| 2 | Craney Island - Alvey 138 kV | 0.83 | 0.02 | estimated flow contribution 475 MW; public-topology distribution factor (N-1) 1.00; 1 hops from POI | - |
| 3 | Solway - Lake Kingman 138 kV | 0.73 | 0.03 | estimated flow contribution 475 MW; public-topology distribution factor (N-1) 1.00; public-topology distribution factor 0.40 | - |
| 4 | Craney Island - Solway 138 kV | 0.73 | 0.01 | estimated flow contribution 475 MW; public-topology distribution factor (N-1) 1.00; 2 hops from POI | - |
| 5 | Sewell'S Point - Monohans 138 kV | 0.51 | 0.24 | estimated flow contribution 475 MW; public-topology distribution factor (N-1) 1.00; 1 hops from POI | - |
| 6 | Alvey - Oakwood 138 kV | 0.51 | 0.24 | estimated flow contribution 475 MW; public-topology distribution factor (N-1) 1.00; 0 hops from POI | - |
| 7 | Ennis - Frio Town 138 kV | 0.51 | 0.06 | estimated flow contribution 276 MW; public-topology distribution factor (N-1) 0.58; public-topology distribution factor 0.38 | - |
| 8 | Monohans - Alvey 138 kV | 0.51 | 0.25 | estimated flow contribution 270 MW; public-topology distribution factor (N-1) 0.57; 1 hops from POI | - |
| 9 | Sewell'S Point - Frio Town 138 kV | 0.51 | 0.03 | estimated flow contribution 276 MW; public-topology distribution factor (N-1) 0.58; 8 km from POI | - |
| 10 | Tanners Point - Sewell'S Point 138 kV | 0.39 | 0.21 | public-topology distribution factor (N-1) 0.42; 8 km from POI; 2 hops from POI | - |

**Revealed ISO study** (2023-07-21): 7 constrained facilities, total allocated upgrade cost $2.3M (5 $/kW).

| facility (study) | loading % | pre-project % | true DFAX % | contingency | in candidates | model rank | model p |
|---|---|---|---|---|---|---|---|
| Alpine 138/1 kV Transformer | 122.0 | 111.7 | 9.3 | Baraga Vlg - Geysers Tap 2 345 kV | yes | 407 | 0.00 |
| Alpine 345/1 kV Transformer | 121.3 | 111.0 | 9.3 | Baraga Vlg - Geysers Tap 2 345 kV | yes | 487 | 0.00 |
| Geysers Tap 2 - Tyler 138 kV | 112.0 | 103.1 | 6.8 | Mountain Lake - Waldron 138 kV | yes | 285 | 0.00 |
| Harrisburg - Westchase 138 kV | 105.9 | 96.5 | 5.8 | Anasco 6101 - Whirlwind 345 kV | yes | 233 | 0.00 |
| Trabue - Westchase 138 kV | 104.8 | 94.2 | 5.8 | Anasco 6101 - Whirlwind 345 kV | yes | 209 | 0.00 |
| Anasco 6101 - Whirlwind 345 kV | 101.0 | 94.0 | 20.3 | Challenge - Brick Church 345 kV | yes | 180 | 0.01 |
| Hull Street Road - Collins Lake 138 kV | 100.4 | 91.8 | 9.4 | Anasco 6101 - Whirlwind 345 kV | yes | 104 | 0.02 |

**Why**: Missed Alpine 138/1 kV Transformer (rank 317, p=0.00): public-topology DFAX only 0.03 vs true 9.3%; never named in a prior study; never bound in sampled market hours; facility sat at 112% pre-project (hair-trigger headroom invisible publicly). Missed Geysers Tap 2 - Tyler 138 kV (rank 285, p=0.00): never bound in sampled market hours; facility sat at 103% pre-project (hair-trigger headroom invisible publicly). Missed Anasco 6101 - Whirlwind 345 kV (rank 168, p=0.01): never bound in sampled market hours. Missed Alpine 345/1 kV Transformer (rank 418, p=0.00): public-topology DFAX only 0.02 vs true 9.3%; never named in a prior study; never bound in sampled market hours; facility sat at 111% pre-project (hair-trigger headroom invisible publicly). False alarm Monohans - Oakwood 138 kV (p=0.92): evidence was estimated flow contribution 475 MW; public-topology distribution factor (N-1) 1.00. False alarm Craney Island - Alvey 138 kV (p=0.83): evidence was estimated flow contribution 475 MW; public-topology distribution factor (N-1) 1.00.

## Q23-2363 — miss (no true facility in top-5)

**Project**: battery (storage), 128 MW at Phillippi 138 kV, queued 2023-12-17. Prediction made as of 2023-12-18; study published 2025-10-23.

**Public context at the time**: no prior study at this POI; 0 earlier queue entries at the POI (0 MW active); 0 MW active queue within 50 km; POI congestion component +0.0 $/MWh (24-month mean); 10 analog projects within 80 km.

**Model output**: difficulty **high** (expected 5.5 constrained facilities, P(no constraint) = 0.00).

| rank | predicted facility | p | ±sd | evidence | outcome |
|---|---|---|---|---|---|
| 1 | Phillippi - Mill 138 kV | 0.51 | 0.09 | public-topology distribution factor (N-1) 1.00; 0 hops from POI; estimated flow contribution 128 MW | - |
| 2 | Juneau - Mill 138 kV | 0.51 | 0.09 | public-topology distribution factor (N-1) 1.00; 1 hops from POI; estimated flow contribution 128 MW | - |
| 3 | Juneau - Santa Rosa 138 kV | 0.39 | 0.06 | public-topology distribution factor (N-1) 1.00; estimated flow contribution 128 MW; 2 hops from POI | - |
| 4 | Santa Rosa - Valhalla 138 kV | 0.29 | 0.05 | public-topology distribution factor (N-1) 1.00; estimated flow contribution 128 MW; public-topology distribution factor 0.34 | - |
| 5 | Santa Rosa - T.S. Power 138 kV | 0.29 | 0.05 | public-topology distribution factor (N-1) 1.00; estimated flow contribution 128 MW; public-topology distribution factor 0.65 | - |
| 6 | Ohio Falls - Valhalla 138 kV | 0.24 | 0.02 | public-topology distribution factor (N-1) 1.00; estimated flow contribution 128 MW; public-topology distribution factor 0.34 | - |
| 7 | Everett - T.S. Power 138 kV | 0.24 | 0.02 | public-topology distribution factor (N-1) 1.00; estimated flow contribution 128 MW; public-topology distribution factor 0.65 | - |
| 8 | North Bartow - Ohio Falls 138 kV | 0.24 | 0.02 | public-topology distribution factor (N-1) 1.00; estimated flow contribution 128 MW; public-topology distribution factor 0.34 | - |
| 9 | Scull - Phillippi 138 kV | 0.15 | 0.06 | 0 km from POI; 0 hops from POI | - |
| 10 | North Bartow - Cedar Station 138 kV | 0.09 | 0.02 | public-topology distribution factor (N-1) 1.00; estimated flow contribution 128 MW; public-topology distribution factor 0.34 | - |

**Revealed ISO study** (2025-10-23): 1 constrained facilities, total allocated upgrade cost $0.4M (3 $/kW).

| facility (study) | loading % | pre-project % | true DFAX % | contingency | in candidates | model rank | model p |
|---|---|---|---|---|---|---|---|
| Durham - Bl England Station 138 kV | 104.5 | 64.6 | 76.4 | Lewis - Oneida 138 kV | yes | 51 | 0.02 |

**Why**: Missed Durham - Bl England Station 138 kV (rank 43, p=0.02): public-topology DFAX only 0.00 vs true 76.4%; never named in a prior study; never bound in sampled market hours. False alarm Phillippi - Mill 138 kV (p=0.51): evidence was public-topology distribution factor (N-1) 1.00; 0 hops from POI. False alarm Juneau - Mill 138 kV (p=0.51): evidence was public-topology distribution factor (N-1) 1.00; 1 hops from POI.

## Q22-2121 — non-generator project (load)

**Project**: load (load), 821 MW at North Bonneville 138 kV, queued 2022-06-30. Prediction made as of 2022-07-01; study published 2023-06-29.

**Public context at the time**: no prior study at this POI; 0 earlier queue entries at the POI (0 MW active); 0 MW active queue within 50 km; POI congestion component +0.0 $/MWh (24-month mean); 10 analog projects within 80 km.

**Model output**: difficulty **very high** (expected 13.1 constrained facilities, P(no constraint) = 0.00).

| rank | predicted facility | p | ±sd | evidence | outcome |
|---|---|---|---|---|---|
| 1 | Fountain Head - Susquehanna 138 kV | 0.92 | 0.02 | estimated flow contribution 563 MW; public-topology distribution factor (N-1) 0.69; public-topology distribution factor 0.37 | **HIT** |
| 2 | Norwalk - Fountain Head 138 kV | 0.92 | 0.02 | estimated flow contribution 563 MW; public-topology distribution factor (N-1) 0.69; public-topology distribution factor 0.37 | **HIT** |
| 3 | Pg Pulp - Olympus 138 kV | 0.92 | 0.02 | estimated flow contribution 458 MW; public-topology distribution factor (N-1) 0.56; public-topology distribution factor 0.26 | **HIT** |
| 4 | Union Carbide - Koenig Lane 138 kV | 0.73 | 0.06 | estimated flow contribution 259 MW; public-topology distribution factor (N-1) 0.32; public-topology distribution factor 0.17 | **HIT** |
| 5 | Koenig Lane - Red Mountain 138 kV | 0.73 | 0.05 | estimated flow contribution 259 MW; public-topology distribution factor (N-1) 0.32; 4 km from POI | **HIT** |
| 6 | Red Mountain - Norwalk 138 kV | 0.73 | 0.24 | estimated flow contribution 563 MW; public-topology distribution factor (N-1) 0.69; public-topology distribution factor 0.37 | **HIT** |
| 7 | Bear Garden - Pg Pulp 138 kV | 0.51 | 0.22 | public-topology distribution factor (N-1) 1.00; estimated flow contribution 821 MW; 1 hops from POI | **HIT** |
| 8 | Susquehanna - Yermo 138 kV | 0.51 | 0.08 | estimated flow contribution 352 MW; public-topology distribution factor (N-1) 0.43; public-topology distribution factor 0.23 | **HIT** |
| 9 | Schultz - North Bonneville 138 kV | 0.51 | 0.21 | estimated flow contribution 821 MW; public-topology distribution factor (N-1) 1.00; 0 hops from POI | **HIT** |
| 10 | Schultz - Red Mountain 138 kV | 0.51 | 0.21 | public-topology distribution factor (N-1) 1.00; estimated flow contribution 821 MW; 1 hops from POI | **HIT** |

**Revealed ISO study** (2023-06-29): 25 constrained facilities, total allocated upgrade cost $157.2M (191 $/kW).

| facility (study) | loading % | pre-project % | true DFAX % | contingency | in candidates | model rank | model p |
|---|---|---|---|---|---|---|---|
| Fountain Head - Susquehanna 138 kV | 187.1 | 22.8 | 64.5 | Bear Garden - Pg Pulp 138 kV | yes | 1 | 0.92 |
| Norwalk - Fountain Head 138 kV | 182.1 | 20.7 | 64.5 | Bear Garden - Pg Pulp 138 kV | yes | 2 | 0.92 |
| Newton - Beaverton 138 kV | 176.3 | 115.8 | 18.0 | Olympus 138/1 kV Transformer | yes | 23 | 0.14 |
| Red Mountain - Norwalk 138 kV | 174.7 | 17.6 | 64.5 | Bear Garden - Pg Pulp 138 kV | yes | 6 | 0.73 |
| Bayou Cove Peaking Power - Beaverton 138 kV | 173.8 | 115.1 | 18.0 | Olympus 138/1 kV Transformer | yes | 27 | 0.07 |
| Bayou Cove Peaking Power - Montour Station 138 kV | 172.3 | 116.7 | 20.5 | Olympus 138/1 kV Transformer | yes | 19 | 0.14 |
| Union Carbide - Koenig Lane 138 kV | 148.8 | 2.4 | 35.5 | Bear Garden - Pg Pulp 138 kV | yes | 4 | 0.73 |
| Schultz - Red Mountain 138 kV | 148.4 | 7.7 | 100.0 | Bear Garden - Pg Pulp 138 kV | yes | 10 | 0.51 |
| Schultz - North Bonneville 138 kV | 143.0 | 5.5 | 100.0 | Bear Garden - Pg Pulp 138 kV | yes | 9 | 0.51 |
| South Street - Pg Pulp 138 kV | 140.8 | 85.2 | 25.8 | Olympus 138/1 kV Transformer | yes | 17 | 0.24 |
| Union Carbide - Englewood 138 kV | 139.7 | 7.5 | 35.5 | Bear Garden - Pg Pulp 138 kV | yes | 12 | 0.39 |
| North Bonneville - Bear Garden 138 kV | 138.6 | 4.1 | 100.0 | Schultz - Red Mountain 138 kV | yes | 11 | 0.51 |
| South Street - Newton 138 kV | 138.2 | 85.6 | 25.8 | Olympus 138/1 kV Transformer | yes | 14 | 0.24 |
| Koenig Lane - Red Mountain 138 kV | 138.1 | 0.9 | 35.5 | Bear Garden - Pg Pulp 138 kV | yes | 5 | 0.73 |
| Bear Garden - Pg Pulp 138 kV | 137.1 | 7.1 | 100.0 | Schultz - Red Mountain 138 kV | yes | 7 | 0.51 |
| Newton - Pine Tree Acres Wm Lfgte 138 kV | 135.0 | 82.4 | 12.4 | Bayou Cove Peaking Power - Beaverton 138 kV | yes | 26 | 0.07 |
| Mossyrock Pp - Pine Tree Acres Wm Lfgte 138 kV | 132.6 | 82.3 | 12.4 | Bayou Cove Peaking Power - Beaverton 138 kV | no | - | nan |
| Mossyrock Pp - Pheasant Branch 138 kV | 129.8 | 82.7 | 12.4 | Bayou Cove Peaking Power - Beaverton 138 kV | yes | 68 | 0.02 |
| Pheasant Branch - Lena 138 kV | 121.9 | 78.1 | 10.8 | Bayou Cove Peaking Power - Montour Station 138 kV | no | - | nan |
| Sampson - Lena 138 kV | 120.3 | 78.6 | 10.8 | Bayou Cove Peaking Power - Montour Station 138 kV | yes | 134 | 0.01 |
| Pg Pulp - Olympus 138 kV | 117.4 | 78.2 | 30.1 | South Street - Newton 138 kV | yes | 3 | 0.92 |
| Olympus 138/1 kV Transformer | 117.4 | 78.2 | 30.1 | South Street - Newton 138 kV | yes | 16 | 0.24 |
| Olympus 345/1 kV Transformer | 117.4 | 78.2 | 30.1 | South Street - Newton 138 kV | yes | 30 | 0.06 |
| Susquehanna - Yermo 138 kV | 109.6 | 56.1 | 35.4 | Bear Garden - Pg Pulp 138 kV | yes | 8 | 0.51 |
| Inver Hills - Derby 345 kV | 109.2 | 106.5 | 5.5 | Montour Station - Talenenergy Martins Creek Llc Williamsport 345 kV | yes | 95 | 0.01 |

**Why**: 10 of 23 true facilities were in the top-10 (first hit at rank 1). Missed Olympus 345/1 kV Transformer (rank 30, p=0.06): never bound in sampled market hours. Missed Mossyrock Pp - Pheasant Branch 138 kV (rank 59, p=0.02): public-topology DFAX only 0.00 vs true 12.4%; never bound in sampled market hours. Missed Newton - Pine Tree Acres Wm Lfgte 138 kV (rank 26, p=0.07): public-topology DFAX only 0.00 vs true 12.4%; never bound in sampled market hours. Missed Sampson - Lena 138 kV (rank 134, p=0.01): public-topology DFAX only 0.00 vs true 10.8%; never named in a prior study; never bound in sampled market hours.

## Q24-2447 — no constraints found by ISO; model expected few

**Project**: gen (wind), 150 MW at Commonwealth Edison Des Plaines 230 kV, queued 2024-08-03. Prediction made as of 2024-08-04; study published 2025-07-30.

**Public context at the time**: no prior study at this POI; 2 earlier queue entries at the POI (0 MW active); 0 MW active queue within 50 km; POI congestion component +0.0 $/MWh (24-month mean); 10 analog projects within 80 km.

**Model output**: difficulty **low** (expected 0.3 constrained facilities, P(no constraint) = 0.76).

| rank | predicted facility | p | ±sd | evidence | outcome |
|---|---|---|---|---|---|
| 1 | Valley Home Tap 1 - Ioco 100 kV | 0.01 | 0.00 | named by 18% (similarity-weighted) of analog projects; 5 km from POI | - |
| 2 | Felida - Moize Creek 230 kV | 0.00 | 0.00 | 9 km from POI; 1 hops from POI; last named 0.4 years ago | - |
| 3 | Clifton Wilson - Commonwealth Edison Des Plaines 230 kV | 0.00 | 0.00 | 0 km from POI; 0 hops from POI | - |
| 4 | Commonwealth Edison Des Plaines - Gray Summit 230 kV | 0.00 | 0.00 | 0 km from POI; 0 hops from POI | - |
| 5 | Commonwealth Edison Des Plaines - Francisco 230 kV | 0.00 | 0.00 | 0 km from POI; 0 hops from POI | - |
| 6 | Commonwealth Edison Des Plaines - Scot 230 kV | 0.00 | 0.00 | 0 km from POI; 0 hops from POI | - |
| 7 | Felida - Commonwealth Edison Des Plaines 230 kV | 0.00 | 0.00 | 0 km from POI; 0 hops from POI | - |
| 8 | Flax Hill - Commonwealth Edison Des Plaines 230 kV | 0.00 | 0.00 | 0 km from POI; 0 hops from POI | - |
| 9 | Commonwealth Edison Des Plaines - San Andres 230 kV | 0.00 | 0.00 | 0 km from POI; 0 hops from POI | - |
| 10 | Ioco - Thayer North 100 kV | 0.00 | 0.00 | named by 9% (similarity-weighted) of analog projects; 3 km from POI | - |

**Revealed ISO study** (2025-07-30): 4 constrained facilities, total allocated upgrade cost $0.7M (5 $/kW).

| facility (study) | loading % | pre-project % | true DFAX % | contingency | in candidates | model rank | model p |
|---|---|---|---|---|---|---|---|
| Adams - West Batesville 230 kV | 100.6 | 99.9 | 7.7 | Tecumseh - Beaver 500 kV | no | - | nan |
| Galion Generating Station 500/230 kV Transformer | 100.6 | 99.9 | 10.4 | Tecumseh - Beaver 500 kV | no | - | nan |
| Adams - Calera T.S 230 kV | 100.3 | 99.6 | 15.2 | Tecumseh - Beaver 500 kV | no | - | nan |
| Lehma - Huntingdon District 100 kV | 100.2 | 98.8 | 5.2 | Dekalb - Mcmichen 500 kV | no | - | nan |

**Why**: False alarm Valley Home Tap 1 - Ioco 100 kV (p=0.01): evidence was named by 18% (similarity-weighted) of analog projects; 5 km from POI. False alarm Felida - Moize Creek 230 kV (p=0.00): evidence was 9 km from POI; 1 hops from POI. The ISO found no constraints; the model's low expected count and high P(no constraint) agree with that.
