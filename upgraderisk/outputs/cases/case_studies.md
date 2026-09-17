# Prospective case studies (rolling-origin holdout)

Each case is a real PJM upgrade at a real archived observation date. The model outputs are those of the benchmark model refitted before that month on outcomes knowable then; it saw nothing published after the as-of date. Analogs are earlier upgrades whose outcome was already known on that date. What happened is taken from PJM's current table (2026).

## b2986 — PSEG, 230.0 kV Transmission Structures (as of 2018-01-25)
*Replace the existing Roseland – Branchburg – Pleasant Valley 230 kV corridor with new structures.*

- **At 2018-01-25 PJM's table said:** in service 2022-06-01, cost $546.00M, status Engineering & Procurement, listed for 0 months, date revised 0 time(s), slipped 0 months so far.
- **Model would have said:** P(slip > 12 months) **40%** (survival 75%, classifier 5%); completion P50 **2025-01-24**, P90 2025-01-24 (survival model); P(cost increase > 25 %) **44%**; cost P50 $514.72M (P10–P90 $340.54M–$884.40M); P(cancelled) 24%.
- **Drivers:** pct_complete=0.0 (+0.75), log_cost=6.3 (+0.74), months_since_initial_teac=0.5 (+0.51), months_to_expected_isd=52.2 (-0.40)
- **Analogs known then:** s0387 (PSEG, late -25 mo); b1304.1 (PSEG, late +1 mo); b2218 (PSEG, cancelled); b2436.84 (PSEG, late -1 mo)
- **What happened:** cancelled / withdrawn.

## b2443 — Dominion, 230.0 kV Transmission Line (as of 2018-01-25)
*Construct new underground 230kV line from Gelebe to Station C.*

- **At 2018-01-25 PJM's table said:** in service 2023-05-31, cost $320.00M, status Engineering & Procurement, listed for 29 months, date revised 2 time(s), slipped 60 months so far.
- **Model would have said:** P(slip > 12 months) **36%** (survival 68%, classifier 4%); completion P50 **2025-01-24**, P90 2025-01-24 (survival model); P(cost increase > 25 %) **68%**; cost P50 $295.97M (P10–P90 $182.41M–$660.36M); P(cancelled) 15%.
- **Drivers:** pct_complete=3.0 (+0.85), log_cost=5.8 (+0.62), equipment=Transmission Line (+0.28), months_to_expected_isd=64.1 (-0.27)
- **Analogs known then:** b2582 (Dominion, late -5 mo); b2585 (Dominion, cancelled); b1792 (Dominion, late -25 mo); b1254.1 (BGE, cancelled)
- **What happened:** cancelled / withdrawn.

## b2837 — PSEG, 138.0 kV Transmission Line (as of 2018-01-25)
*Convert the F-1358/Z1326 and K1363/Y-1325 (Trenton - Burlington) 138 kV circuits to 230 kV circuits*

- **At 2018-01-25 PJM's table said:** in service 2022-06-01, cost $312.00M, status Engineering & Procurement, listed for 11 months, date revised 0 time(s).
- **Model would have said:** P(slip > 12 months) **44%** (survival 86%, classifier 3%); completion P50 **2025-01-24**, P90 2025-01-24 (survival model); P(cost increase > 25 %) **66%**; cost P50 $296.25M (P10–P90 $160.24M–$499.91M); P(cancelled) 18%.
- **Drivers:** task=Convert (+0.72), pct_complete=5.0 (+0.61), log_cost=5.7 (+0.59), months_to_expected_isd=52.2 (-0.25)
- **Analogs known then:** b2256 (AEP, late +0 mo); b2218 (PSEG, cancelled); b2436.84 (PSEG, late -1 mo); b2436.85 (PSEG, late -1 mo)
- **What happened:** in service 2021-05-07 (-13 months vs the date published then).

## b2838 — PPL, 230.0 kV Substation (as of 2018-01-25)
*Build a new 230/69 kV substation by tapping the Montour - Susquehanna 230 kV double circuits and Berwick - Hunlock & Berwick - Colombia 69 kV circuits*

- **At 2018-01-25 PJM's table said:** in service 2020-08-01, cost $57.00M, status Engineering & Procurement, listed for 9 months, date revised 0 time(s), slipped -13 months so far.
- **Model would have said:** P(slip > 12 months) **35%** (survival 68%, classifier 2%); completion P50 **2023-06-09**, P90 2025-01-24 (survival model); P(cost increase > 25 %) **35%**; cost P50 $50.49M (P10–P90 $44.04M–$59.78M); P(cancelled) 4%.
- **Drivers:** log_cost=4.1 (+0.67), pct_complete=30.0 (-0.53), months_since_initial_teac=12.0 (+0.33), months_to_expected_isd=30.2 (-0.27)
- **Analogs known then:** b2006 (PPL, late +1 mo); b2006.2 (PPL, late -0 mo); s0957.1 (PPL, late -2 mo); s0974.3 (PPL, late -84 mo)
- **What happened:** in service 2022-05-20 (+22 months vs the date published then), final cost $57.00M (+0%).

## b1570.2 — Dayton, 69.0 kV Transmission Line (as of 2018-01-25)
*Add Marysville - Union REA 69 kV line*

- **At 2018-01-25 PJM's table said:** in service 2021-06-01, cost $0.00M, status Engineering & Procurement, listed for 52 months, date revised 1 time(s), slipped 84 months so far.
- **Model would have said:** P(slip > 12 months) **50%** (survival 97%, classifier 3%); completion P50 **2025-01-24**, P90 2025-01-24 (survival model); P(cost increase > 25 %) **77%**; cost P50 $0.00M (P10–P90 $0.00M–$0.00M); P(cancelled) 8%.
- **Drivers:** pct_complete=2.0 (+0.57), equipment=Transmission Line (+0.46), slip_so_far_months=84.0 (+0.32), months_to_expected_isd=40.2 (-0.22)
- **Analogs known then:** b2336 (EKPC, late -29 mo); b2664 (EKPC, late -23 mo); b2326 (EKPC, late -14 mo); b2344.6 (AEP, late -5 mo)
- **What happened:** in service 2026-09-17 (+64 months vs the date published then).

## b2970.5 — APS, 230.0 kV Substation (as of 2019-08-19)
*Convert Garfield 138/12.5 kV substation to 230/12.5 kV*

- **At 2019-08-19 PJM's table said:** in service 2020-11-01, cost $2.20M, status Engineering & Procurement, listed for 0 months, date revised 0 time(s), slipped 0 months so far.
- **Model would have said:** P(slip > 12 months) **21%** (survival 39%, classifier 2%); completion P50 **2021-04-24**, P90 2024-02-21 (survival model); P(cost increase > 25 %) **30%**; cost P50 $2.23M (P10–P90 $2.10M–$2.74M); P(cancelled) 4%.
- **Drivers:** driver_short=Baseline Load Growth (-0.50), months_required_minus_expected=-5.0 (-0.31), pct_complete=0.0 (+0.30), n_status_cost_overrun_25=11794.0 (-0.19)
- **Analogs known then:** b2261 (APS, late -0 mo); b2362.1 (APS, late -1 mo); b2763 (APS, cancelled); s1039 (APS, late -0 mo)
- **What happened:** not yet in service as of the last observation (2026-09-17).

## b2686.12 — Dominion, 115.0 kV Transmission Line (as of 2018-01-25)
*Upgrading sections of the Somerset - Doubleday 115 kV circuit*

- **At 2018-01-25 PJM's table said:** in service 2020-06-01, cost $0.00M, status Engineering & Procurement, listed for 27 months, date revised 0 time(s).
- **Model would have said:** P(slip > 12 months) **30%** (survival 59%, classifier 1%); completion P50 **2022-03-10**, P90 2025-01-24 (survival model); P(cost increase > 25 %) **48%**; cost P50 $0.00M (P10–P90 $0.00M–$0.00M); P(cancelled) 8%.
- **Drivers:** pct_complete=0.0 (+0.68), task=Upgrade (-0.49), months_required_minus_expected=-12.0 (-0.30), months_to_expected_isd=28.2 (-0.24)
- **Analogs known then:** b2719.2 (Dominion, late -10 mo); b2719.3 (Dominion, late -8 mo); b2185 (Dominion, late -9 mo); b2458.3 (Dominion, late -0 mo)
- **What happened:** in service 2020-05-28 (-0 months vs the date published then), final cost $5.30M.

## b3209 — AEP, 69.0 kV Transmission Line (as of 2019-08-19)
*Rebuild the 10.5 mile Berne – South Decatur 69 kV line using 556 ACSR
in order to alleviate the overload and address a deteriorating asset.*

- **At 2019-08-19 PJM's table said:** in service 2022-06-01, cost $16.60M, status Engineering & Procurement, listed for 0 months, date revised 0 time(s), slipped 0 months so far.
- **Model would have said:** P(slip > 12 months) **7%** (survival 12%, classifier 2%); completion P50 **2022-04-24**, P90 2023-07-27 (survival model); P(cost increase > 25 %) **23%**; cost P50 $16.49M (P10–P90 $8.70M–$20.45M); P(cancelled) 2%.
- **Drivers:** months_to_expected_isd=33.4 (-0.35), log_cost=2.9 (-0.28), months_since_initial_teac=3.9 (-0.23), pct_complete=0.0 (+0.22)
- **Analogs known then:** b2715 (AEP, late -12 mo); b2791.1 (AEP, late -29 mo); b2606 (AEP, late +2 mo); b2591 (AEP, cancelled)
- **What happened:** in service 2023-01-20 (+8 months vs the date published then), final cost $16.60M (+0%).

## b2404 — Dominion, 230.0 kV Circuit Breaker (as of 2018-01-25)
*Replace the Beaumeade 230 kV breaker '227T2095' with 63kA rated breaker*

- **At 2018-01-25 PJM's table said:** in service 2018-07-20, cost $0.27M, status Engineering & Procurement, listed for 29 months, date revised 1 time(s), slipped 2 months so far.
- **Model would have said:** P(slip > 12 months) **5%** (survival 10%, classifier 0%); completion P50 **2018-06-25**, P90 2019-07-07 (survival model); P(cost increase > 25 %) **24%**; cost P50 $0.28M (P10–P90 $0.27M–$0.37M); P(cancelled) 1%.
- **Drivers:** pct_complete=30.0 (-0.46), equipment=Circuit Breaker (-0.33), months_to_expected_isd=5.8 (-0.28), to=Dominion (-0.20)
- **Analogs known then:** b1698.7 (Dominion, late -8 mo); b1698.5 (Dominion, late -7 mo); b2369 (Dominion, late -8 mo); b2370 (Dominion, late -10 mo)
- **What happened:** in service 2018-07-03 (-1 months vs the date published then), final cost $0.27M (+0%).

## b2676 — JCPL, 230.0 kV Capacitor (as of 2018-01-25)
*Install one (1) 72 MVAR fast switched capacitor at the Englishtown 230 kV substation*

- **At 2018-01-25 PJM's table said:** in service 2020-06-01, cost $3.50M, status Engineering & Procurement, listed for 27 months, date revised 0 time(s).
- **Model would have said:** P(slip > 12 months) **49%** (survival 96%, classifier 2%); completion P50 **2025-01-24**, P90 2025-01-24 (survival model); P(cost increase > 25 %) **69%**; cost P50 $3.57M (P10–P90 $3.38M–$3.60M); P(cancelled) 56%.
- **Drivers:** pct_complete=1.0 (+0.67), equipment=Capacitor (-0.46), months_to_expected_isd=28.2 (-0.29), n_status_delay_12m=2040.0 (-0.27)
- **Analogs known then:** b2754.2 (JCPL, cancelled); b2754.3 (JCPL, cancelled); b2590 (PSEG, cancelled); b2357 (JCPL, late +5 mo)
- **What happened:** cancelled / withdrawn.

## b2666.8 — APS, 138.0 kV Circuit Breaker (as of 2018-01-25)
*Replace Yukon 138kV breaker 'Y-9(SPRINGD)' with an 80kA breaker*

- **At 2018-01-25 PJM's table said:** in service 2019-06-01, cost $0.82M, status On Hold, listed for 27 months, date revised 0 time(s).
- **Model would have said:** P(slip > 12 months) **41%** (survival 79%, classifier 3%); completion P50 **2022-10-21**, P90 2025-01-24 (survival model); P(cost increase > 25 %) **8%**; cost P50 $0.82M (P10–P90 $0.80M–$0.97M); P(cancelled) 12%.
- **Drivers:** pct_complete=1.0 (+0.85), months_to_expected_isd=16.2 (-0.46), state=PA (+0.31), equipment=Circuit Breaker (-0.31)
- **Analogs known then:** b2143 (APS, cancelled); b2142 (APS, cancelled); b2431 (APS, cancelled); b2430 (APS, cancelled)
- **What happened:** cancelled / withdrawn.

## b2993 — AEP, 69.0 kV Transmission Line (as of 2018-06-09)
*Rebuild the Torrey – South Gambrinus Switch – Gambrinus Road 69kV line section (1.3 miles) with 1033 ACSR ‘Curlew’ conductor and steel poles.*

- **At 2018-06-09 PJM's table said:** in service 2018-12-01, cost $2.80M, status Engineering & Procurement, listed for 0 months, date revised 0 time(s), slipped 0 months so far.
- **Model would have said:** P(slip > 12 months) **10%** (survival 19%, classifier 1%); completion P50 **2019-01-08**, P90 2020-08-18 (survival model); P(cost increase > 25 %) **44%**; cost P50 $2.86M (P10–P90 $2.21M–$5.12M); P(cancelled) 3%.
- **Drivers:** task=Rebuild (+0.69), pct_complete=0.0 (+0.53), n_status_cost_overrun_25=7769.0 (-0.28), n_to_cost_overrun_25=3541.0 (-0.24)
- **Analogs known then:** b2258 (AEP, late +2 mo); s1335.2 (AEP, late +0 mo); s1322 (AEP, late +1 mo); s1371 (AEP, late +1 mo)
- **What happened:** in service 2019-05-24 (+6 months vs the date published then), final cost $4.60M (+64%).


Slip calls at the 50 % threshold correct in 5/8 labelled cases (the benchmark tables are the evaluation; these are illustrations).
