# Parser inspection sample (5 random studies)

For each: raw PDF text (section 3.1), parsed+normalised facilities, hidden truth.

## Q19-1211 (template C)

```
Generator Deliverability and Single Contingency Analysis
1. Facility: DENVER TERMINAL / POKAGON 100kV
Contingency: BONNET CEEK / POKAGON 100kV
Loading: 126.0% (Rating: 126 MVA)
DFAX: 100.0%
Pre-project loading: 9.7%
2. Facility: BONNET CREEK / POKAGON 100kV
Contingency: DENVER TERMINAL / POKAGON 100kV
Loading: 120.3% (Rating: 132 MVA)
DFAX: 100.0%
Pre-project loading: 9.2%
```

Parsed -> normalised:

| facility string | fid | conf | loading |
|---|---|---|---|
| DENVER TERMINAL / POKAGON 100kV | L:22598:22599:100 | 1.00 | 126.0 |
| BONNET CREEK / POKAGON 100kV | L:20996:22599:100 | 1.00 | 120.3 |

Truth fids: L:22598:22599:100 (126.0%), L:20996:22599:100 (120.3%)

## Q16-0675 (template A)

```
Generator Deliverability and Single Contingency Analysis
Monitored Facility Contingency Loading (%) Rating (MVA) DFAX (%)
Enka - Houghton Rock 138kV Hooversville - Halldale Tap 138kV line 102.3 191 66.7
Houghton Rock - Halldale Tap 138kV Halldale Tap - Hooversville 138kV 100.2 200 66.7
```

Parsed -> normalised:

| facility string | fid | conf | loading |
|---|---|---|---|
| Enka - Houghton Rock 138kV | L:8133:8261:138 | 1.00 | 102.3 |
| Houghton Rock - Halldale Tap 138kV | L:8133:8151:138 | 1.00 | 100.2 |

Truth fids: L:8133:8261:138 (102.3%), L:8133:8151:138 (100.2%)

## Q21-1654 (template C)

```
Generator Deliverability and Single Contingency Analysis
1. Facility: Taylorville S - Drusilla 100 kV
Contingency: Byron 230-1 kV Autotransformer
Loading: 226.6% (Rating: 129 MVA)
DFAX: 100.0%
Pre-project loading: 116.4%
2. Facility: Taylorville South - Bideford Ip 100 kV
Contingency: Taylorville South 230-1 kV Transformer Bank
Loading: 10
```

Parsed -> normalised:

| facility string | fid | conf | loading |
|---|---|---|---|
| Taylorville S - Drusilla 100 kV | L:23490:23515:100 | 1.00 | 226.6 |
| Taylorville South - Bideford Ip 100 kV | L:23490:23511:100 | 1.00 | 103.2 |

Truth fids: L:23490:23515:100 (226.6%), L:23490:23511:100 (103.2%)

## Q22-2179 (template C)

```
Generator Deliverability and Single Contingency Analysis
1. Facility: Twisp / Vly Springs 138 KV line
Contingency: Ss3144 Tap / Greenwater 138 KV Line
Loading: 124.4% (Rating: 192 MVA)
DFAX: 100.0%
Pre-project loading: 5
```

Parsed -> normalised:

| facility string | fid | conf | loading |
|---|---|---|---|
| Twisp / Vly Springs 138 KV line | L:17799:17801:138 | 1.00 | 124.4 |
| Tracy Defense Depot / Alder Creek-Bradshaw 138 KV | L:17345:17365:138 | 1.00 | 109.0 |
| Alder Creek-Bradshaw / La Fresa 138 KV line | L:17365:17366:138 | 1.00 | 106.1 |
| La Fresa / Munk 138 KV line | L:17366:17367:138 | 1.00 | 103.5 |
| Keifer-Jackson / Beaver Dam E 138 KV | L:17146:17162:138 | 1.00 | 102.7 |
| Greenwater / Ss3144 Tap 138 KV | L:17461:17749:138 | 1.00 | 102.6 |

Truth fids: L:17799:17801:138 (124.4%), L:17345:17365:138 (109.0%), L:17365:17366:138 (106.1%), L:17366:17367:138 (103.5%), L:17146:17162:138 (102.7%), L:17461:17749:138 (102.6%)

## Q14-0343 (template C)

```
Generator Deliverability and Single Contingency Analysis
1. Facility: ORCHARD ROAD – FORT HUMBUG 500kV
Contingency: FORT HUMBUG – WEST CAMPUS 345kV
Loading: 105.0% (Rating: 3,014 MVA)
DFAX: 12.6%
Pre-project loading: 104.9%
2. Facility: W CAMPUS – FT HUMBUG 345kV
Contingency: FORT HUMBUG – ORCHARD RD 500kV
Loading: 103.7% (Rating: 2,193 MVA)
DFAX: 8.4%
Pre-project loading: 103.6%
3. Facility: LITTLE CHUTE – TALENENERGY MARTINS CREEK LLC HARRISBURG 345kV
Contingency: FT HUMBUG SUBSTATION – CORONET 500kV
Loading: 102.6% (Rating: 1,626 MVA)
DFAX: 7.0%
Pre-project loading: 102.5%
```

Parsed -> normalised:

| facility string | fid | conf | loading |
|---|---|---|---|
| ORCHARD ROAD – FORT HUMBUG 500kV | L:7672:8103:500 | 1.00 | 105.0 |
| W CAMPUS – FT HUMBUG 345kV | L:7673:8103:345 | 0.96 | 103.7 |
| LITTLE CHUTE – TALENENERGY MARTINS CREEK LLC HARRISBURG 345kV | L:6388:7122:345 | 1.00 | 102.6 |

Truth fids: L:7672:8103:500 (105.0%), L:7673:8103:345 (103.7%), L:6388:7122:345 (102.6%)

