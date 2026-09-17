# Parser inspection sample (5 random studies)

For each: raw PDF text (section 3.1), parsed+normalised facilities, hidden truth.

## Q19-1178 (template B)

```
Generator Deliverability and Single Contingency Analysis
No overloads identified.
```

Parsed -> normalised:

| facility string | fid | conf | loading |
|---|---|---|---|

Truth fids: 

## Q16-0587 (template C)

```
Generator Deliverability and Single Contingency Analysis
1. Facility: Prince William Dp / Fletchers Ridge 138 KV L
Contingency: Pine Tree Acres / Novec Paradise 138 KV
Loading: 102.9% (Rating: 291 MVA)
DFAX: 6.0%
Pre-project loading: 100.7%
2. Facility: Cwec Dewey / Woods Dp 138 KV Cir. 1
Contingency: Cwec Dewey / Woods Dp 138 KV
Loading: 100.1% (Rating: 492 MVA)
DFAX: 12.6%
Pre-project loading: 97.5%
```

Parsed -> normalised:

| facility string | fid | conf | loading |
|---|---|---|---|
| Prince William Dp / Fletchers Ridge 138 KV L | L:10072:10272:138 | 1.00 | 102.9 |
| Cwec Dewey / Woods Dp 138 KV Cir. 1 | L:10303:10307:138 | 1.00 | 100.1 |

Truth fids: L:10072:10272:138 (102.9%), L:10303:10307:138 (100.1%)

## Q21-1876 (template A)

```
Generator Deliverability and Single Contingency Analysis
Monitored Facility Contingency Loading (%) Rating (MVA) DFAX (%)
Hunter'S Crk / Mt.Pleasant 230 kV line Icegen / Trigen St. Louis 230 kV line 105.2 1,503 6.1
Trigen St. Louis / Hunter'S Crk 230 kV Icegen / Trigen St. Louis 230 kV 104.9 1,532 6.1
```

Parsed -> normalised:

| facility string | fid | conf | loading |
|---|---|---|---|
| Hunter'S Crk / Mt.Pleasant 230 kV line | L:21272:21394:230 | 1.00 | 105.2 |
| Trigen St. Louis / Hunter'S Crk 230 kV | L:19865:21272:230 | 1.00 | 104.9 |

Truth fids: L:21272:21394:230 (105.2%), L:19865:21272:230 (104.9%)

## Q22-2113 (template C)

```
Load Deliverability Analysis
1. Facility: Third & Hatch-Rio Bravo 138 KV L
Contingency: Bennett-Pitts Substation 138 KV line
Loading: 127.1% (Rating: 212 MVA)
DFAX: 100.0%
Pre-project loading: 23.3%
2. Facility: Bennett-Pitts 138 KV
Contingency: Third & Hath-Rio Bravo 138 KV
Loading: 114.3% (Rating: 236 MVA)
DFAX: 100.0%
Pre-project loading: 20.9%
3. Facility: Pitts-Lampson 138 KV line
Contingency: Third & Hatch-Rio Bravo 138 KV Line
Loading: 112.7% (Rating: 233 MVA)
DFAX: 100.0%
Pre-project loading: 18.3%
4. Facility: Lampson-Third & Hatch 138 KV Line
Contingency: Bennett Substation-Pitts 138 KV line
Loading: 112.0% (Rating: 223 MVA)
DFAX: 100.0%
Pre-project loading: 13.6%
```

Parsed -> normalised:

| facility string | fid | conf | loading |
|---|---|---|---|
| Third & Hatch-Rio Bravo 138 KV L | L:17784:17786:138 | 1.00 | 127.1 |
| Bennett-Pitts 138 KV | L:17776:17777:138 | 1.00 | 114.3 |
| Pitts-Lampson 138 KV line | L:17777:17785:138 | 1.00 | 112.7 |
| Lampson-Third & Hatch 138 KV Line | L:17784:17785:138 | 1.00 | 112.0 |

Truth fids: L:17784:17786:138 (127.1%), L:17776:17777:138 (114.3%), L:17777:17785:138 (112.7%), L:17784:17785:138 (112.0%)

## Q13-0290 (template B)

```
Generator Deliverability and Single Contingency Analysis
Aes Columbia Power 138/1kV Auto: 706.0% loading (131 MVA) following the outage of the Western Fher – Aes
Columbia Power 230 KV; DFAX = 100.0%.
The Aes Columbia Power 230/1 kV TX is overloaded to 361.7% of its 256 MVA emergency rating for the loss of the
Aes Columbia Power Substation – Western Fher 230 KV. The project contributes 100.0% DFAX (936.8 MW) to this
overload.
Western Fher 230-138 kV Transformer: 200.4% loading (154 MVA) following the outage of the Western Fher 345-230
kV Autotransformer; DFAX = 22.1%.
For the loss of Aes Columbia Power 230-1 kV Transformer Bank, the Western Fher – Ae Columbia Power 230 KV
Line loads to 200.3% of its 463 MVA rating. Project DFAX: 100.0%.
For the loss of Western Fher – Aes Columbia Power 230 KV, the Cairo Bend – Aes Columbia Power Substation 138
KV loads to 174.4% of its 239 MVA rating. Project DFAX: 45.9%.
For the loss of Western Fher – Aes Columbia Power 230 KV, the Brassua Hydroelectric Project – Aes Columbia
Power 138 KV loads to 172.3% of its 230 MVA rating. Project DFAX: 45.1%.
Cypress Gardens – Cairo Bend 138 KV L: 170.8% loading (242 MVA) following the outage of the Western Fher – Aes
Columbia Power 230 KV; DFAX = 45.9%.
Cochrane Dam – Brassua Hydroelectric Project 138 KV: 168.3% loading (234 MVA) following the outage of the
Western Fher – Aes Columbia Power 230 KV; DFAX = 45.1%.
For the loss of Western Fher – Aes Columbia Power 230 KV, the Milstead – Cypress Gardens 138 KV Line loads to
165.9% of its 247 MVA rating. Project DFAX: 45.9%.
For the loss of Western Fher Substation – Aes Columbia Power 230 KV Line, the Cochrane Dam – Military Ighway
138 KV line loads to 162.3% of its 240 MVA rating. Project DFAX: 45.1%.
Western Fher – Military Highway Substation 138 KV Line: 153.3% loading (233 MVA) following the outage of the
Western Fher – Aes Columbia Power 230 KV; DFAX = 42.9%.
For the loss of Aes Columbia Power 230-1 kV Autotransformer, the Western Fher 345/230kV Transformer loads to
128.0% of its 432 MVA rating. Project DFAX: 55.2%.
For the loss of Western Fher – Aes Columbia Power 230 KV L, the Three Points – Erie West Substation 138 KV loads
to 102.8% of its 217 MVA rating. Project DFAX: 21.1%.
```

Parsed -> normalised:

| facility string | fid | conf | loading |
|---|---|---|---|
| Aes Columbia Power 230/1 kV TX | X:19648:230:1 | 1.00 | 361.7 |
| Western Fher – Ae Columbia Power 230 KV Line | L:7764:19648:230 | 1.00 | 200.3 |
| Cairo Bend – Aes Columbia Power Substation 138 KV | L:7768:19648:138 | 1.00 | 174.4 |
| Brassua Hydroelectric Project – Aes Columbia Power 138 KV | L:7767:19648:138 | 1.00 | 172.3 |
| Milstead – Cypress Gardens 138 KV Line | L:7770:7772:138 | 1.00 | 165.9 |
| Cochrane Dam – Military Ighway 138 KV line | L:7749:7750:138 | 1.00 | 162.3 |
| Western Fher 345/230kV Transformer | X:7764:345:230 | 1.00 | 128.0 |
| Three Points – Erie West Substation 138 KV | L:7739:7854:138 | 1.00 | 102.8 |
| Aes Columbia Power 138/1kV Auto | X:19648:138:1 | 1.00 | 706.0 |
| Western Fher 230-138 kV Transformer | X:7764:230:138 | 1.00 | 200.4 |
| Cypress Gardens – Cairo Bend 138 KV L | L:7768:7772:138 | 1.00 | 170.8 |
| Cochrane Dam – Brassua Hydroelectric Project 138 KV | L:7749:7767:138 | 1.00 | 168.3 |
| Western Fher – Military Highway Substation 138 KV Line | L:7750:7764:138 | 1.00 | 153.3 |

Truth fids: X:19648:138:1 (706.0%), X:19648:230:1 (361.7%), X:7764:230:138 (200.4%), L:7764:19648:230 (200.3%), L:7768:19648:138 (174.4%), L:7767:19648:138 (172.3%), L:7768:7772:138 (170.8%), L:7749:7767:138 (168.3%), L:7770:7772:138 (165.9%), L:7749:7750:138 (162.3%), L:7750:7764:138 (153.3%), X:7764:345:230 (128.0%), L:7739:7854:138 (102.8%)

