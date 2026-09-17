# Prospective case studies (holdout, observations after 2017-12-31)

Each case is a real PJM upgrade at a real historical observation date. The model is the bundle trained on outcomes knowable at the cutoff; it saw nothing published after the as-of date. Outcomes are taken from PJM's current table (2026).

## b2986 — PSEG, 230.0 kV Transmission Structures (as of 2018-01-25)
*Replace the existing Roseland – Branchburg – Pleasant Valley 230 kV corridor with new structures.*

- **At 2018-01-25 PJM's table said:** in service 2022-06-01, cost $546.00M, status Engineering & Procurement, listed for 0 months, date revised 0 time(s), slipped 0 months so far.
- **Model would have said:** P(delay > 12 months) **1%**; completion P50 **2020-07-12**, P90 2021-12-01; P(cost increase > 25%) **67%**; cost P50 $496.23M (P10–P90 $263.92M–$649.41M); P(cancelled) 0%.
- **Drivers:** log_cost=6.304448802421981 (+1.10), pct_complete=0.0 (+0.75), driver_short=TO Criteria Violatio (-0.50), months_to_expected_isd=52.172484599589325 (-0.41)
- **What happened:** cancelled / withdrawn.

## b2443 — Dominion, 230.0 kV Transmission Line (as of 2018-01-25)
*Construct new underground 230kV line from Gelebe to Station C.*

- **At 2018-01-25 PJM's table said:** in service 2023-05-31, cost $320.00M, status Engineering & Procurement, listed for 29 months, date revised 2 time(s), slipped 60 months so far.
- **Model would have said:** P(delay > 12 months) **2%**; completion P50 **2021-01-25**, P90 2022-09-15; P(cost increase > 25%) **91%**; cost P50 $313.55M (P10–P90 $153.48M–$828.09M); P(cancelled) 0%.
- **Drivers:** pct_complete=3.0 (+1.03), log_cost=5.771441123130016 (+0.77), equipment=Transmission Line (+0.42), cost_growth_so_far=1.0592020592020592 (+0.33)
- **What happened:** cancelled / withdrawn.

## b2837 — PSEG, 138.0 kV Transmission Line (as of 2018-01-25)
*Convert the F-1358/Z1326 and K1363/Y-1325 (Trenton - Burlington) 138 kV circuits to 230 kV circuits*

- **At 2018-01-25 PJM's table said:** in service 2022-06-01, cost $312.00M, status Engineering & Procurement, listed for 11 months.
- **Model would have said:** P(delay > 12 months) **0%**; completion P50 **2020-06-13**, P90 2021-11-24; P(cost increase > 25%) **89%**; cost P50 $352.67M (P10–P90 $142.99M–$376.10M); P(cancelled) 0%.
- **Drivers:** log_cost=5.746203190540153 (+0.98), pct_complete=5.0 (+0.68), driver_short=TO Criteria Violatio (-0.54), months_to_expected_isd=52.172484599589325 (-0.31)
- **What happened:** in service 2021-05-07 (-13 months vs the date published then).

## b2838 — PPL, 230.0 kV Substation (as of 2018-01-25)
*Build a new 230/69 kV substation by tapping the Montour - Susquehanna 230 kV double circuits and Berwick - Hunlock & Berwick - Colombia 69 kV circuits*

- **At 2018-01-25 PJM's table said:** in service 2020-08-01, cost $57.00M, status Engineering & Procurement, listed for 9 months, date revised 0 time(s), slipped -13 months so far.
- **Model would have said:** P(delay > 12 months) **0%**; completion P50 **2018-11-18**, P90 2020-01-17; P(cost increase > 25%) **59%**; cost P50 $50.26M (P10–P90 $47.33M–$61.45M); P(cancelled) 0%.
- **Drivers:** log_cost=4.060443010546419 (+0.93), pct_complete=30.0 (-0.65), driver_short=TO Criteria Violatio (-0.45), months_since_initial_teac=12.02464065708419 (+0.32)
- **What happened:** in service 2022-05-20 (+22 months vs the date published then), final cost $57.00M (+0%).

## b1570.2 — Dayton, 69.0 kV Transmission Line (as of 2018-01-25)
*Add Marysville - Union REA 69 kV line*

- **At 2018-01-25 PJM's table said:** in service 2021-06-01, cost $0.00M, status Engineering & Procurement, listed for 52 months, date revised 1 time(s), slipped 84 months so far.
- **Model would have said:** P(delay > 12 months) **1%**; completion P50 **2019-02-27**, P90 2020-10-13; P(cost increase > 25%) **100%**; cost P50 $0.00M (P10–P90 $0.00M–$0.00M); P(cancelled) 0%.
- **Drivers:** pct_complete=2.0 (+0.84), equipment=Transmission Line (+0.65), slip_so_far_months=84.0082135523614 (+0.34), months_since_initial_teac=80.49281314168378 (+0.34)
- **What happened:** in service 2026-09-17 (+64 months vs the date published then).

## b2970.5 — APS, 230.0 kV Substation (as of 2019-08-19)
*Convert Garfield 138/12.5 kV substation to 230/12.5 kV*

- **At 2019-08-19 PJM's table said:** in service 2020-11-01, cost $2.20M, status Engineering & Procurement, listed for 0 months, date revised 0 time(s), slipped 0 months so far.
- **Model would have said:** P(delay > 12 months) **0%**; completion P50 **2019-11-03**, P90 2020-10-24; P(cost increase > 25%) **43%**; cost P50 $2.25M (P10–P90 $2.18M–$2.30M); P(cancelled) 0%.
- **Drivers:** pct_complete=0.0 (+0.59), months_to_expected_isd=14.455852156057494 (-0.45), task=Convert (-0.40), months_required_minus_expected=-5.026694045174538 (-0.31)
- **What happened:** not yet in service as of the last observation (2026-09-17).

## b2686.12 — Dominion, 115.0 kV Transmission Line (as of 2018-01-25)
*Upgrading sections of the Somerset - Doubleday 115 kV circuit*

- **At 2018-01-25 PJM's table said:** in service 2020-06-01, cost $0.00M, status Engineering & Procurement, listed for 27 months.
- **Model would have said:** P(delay > 12 months) **0%**; completion P50 **2018-04-25**, P90 2019-12-15; P(cost increase > 25%) **89%**; cost P50 $0.00M (P10–P90 $0.00M–$0.00M); P(cancelled) 0%.
- **Drivers:** pct_complete=0.0 (+0.66), driver_short=TO Criteria Violatio (-0.55), equipment=Transmission Line (+0.41), task=Upgrade (-0.32)
- **What happened:** in service 2020-05-28 (-0 months vs the date published then), final cost $5.30M.

## b3209 — AEP, 69.0 kV Transmission Line (as of 2019-08-19)
*Rebuild the 10.5 mile Berne – South Decatur 69 kV line using 556 ACSR
in order to alleviate the overload and address a deteriorating asset.*

- **At 2019-08-19 PJM's table said:** in service 2022-06-01, cost $16.60M, status Engineering & Procurement, listed for 0 months, date revised 0 time(s), slipped 0 months so far.
- **Model would have said:** P(delay > 12 months) **0%**; completion P50 **2020-08-08**, P90 2021-12-11; P(cost increase > 25%) **27%**; cost P50 $16.66M (P10–P90 $8.13M–$25.11M); P(cancelled) 0%.
- **Drivers:** state=IN (+0.67), pct_complete=0.0 (+0.65), driver_short=TO Criteria Violatio (-0.56), log_cost=2.8678989020441064 (+0.47)
- **What happened:** in service 2023-01-20 (+8 months vs the date published then), final cost $16.60M (+0%).

## b2404 — Dominion, 230.0 kV Circuit Breaker (as of 2018-01-25)
*Replace the Beaumeade 230 kV breaker '227T2095' with 63kA rated breaker*

- **At 2018-01-25 PJM's table said:** in service 2018-07-20, cost $0.27M, status Engineering & Procurement, listed for 29 months, date revised 1 time(s), slipped 2 months so far.
- **Model would have said:** P(delay > 12 months) **0%**; completion P50 **2017-11-07**, P90 2018-06-17; P(cost increase > 25%) **15%**; cost P50 $0.28M (P10–P90 $0.26M–$0.31M); P(cancelled) 0%.
- **Drivers:** pct_complete=30.0 (-0.67), equipment=Circuit Breaker (-0.35), months_to_expected_isd=5.782340862422998 (-0.29), log_cost=0.23901690047049992 (-0.28)
- **What happened:** in service 2018-07-03 (-1 months vs the date published then), final cost $0.27M (+0%).

## b2676 — JCPL, 230.0 kV Capacitor (as of 2018-01-25)
*Install one (1) 72 MVAR fast switched capacitor at the Englishtown 230 kV substation*

- **At 2018-01-25 PJM's table said:** in service 2020-06-01, cost $3.50M, status Engineering & Procurement, listed for 27 months.
- **Model would have said:** P(delay > 12 months) **0%**; completion P50 **2018-07-30**, P90 2020-01-21; P(cost increase > 25%) **96%**; cost P50 $3.39M (P10–P90 $3.11M–$3.70M); P(cancelled) 64%.
- **Drivers:** pct_complete=1.0 (+0.73), equipment=Capacitor (-0.49), cost_growth_so_far=1.3333333333333335 (+0.39), months_to_expected_isd=28.188911704312115 (-0.37)
- **What happened:** cancelled / withdrawn.

## b2666.8 — APS, 138.0 kV Circuit Breaker (as of 2018-01-25)
*Replace Yukon 138kV breaker 'Y-9(SPRINGD)' with an 80kA breaker*

- **At 2018-01-25 PJM's table said:** in service 2019-06-01, cost $0.82M, status On Hold, listed for 27 months.
- **Model would have said:** P(delay > 12 months) **0%**; completion P50 **2018-05-28**, P90 2019-04-27; P(cost increase > 25%) **3%**; cost P50 $0.82M (P10–P90 $0.77M–$0.90M); P(cancelled) 0%.
- **Drivers:** pct_complete=1.0 (+0.98), months_to_expected_isd=16.164271047227928 (-0.52), equipment=Circuit Breaker (-0.41), slip_so_far_months=None (-0.31)
- **What happened:** cancelled / withdrawn.

## b2993 — AEP, 69.0 kV Transmission Line (as of 2018-06-09)
*Rebuild the Torrey – South Gambrinus Switch – Gambrinus Road 69kV line section (1.3 miles) with 1033 ACSR ‘Curlew’ conductor and steel poles.*

- **At 2018-06-09 PJM's table said:** in service 2018-12-01, cost $2.80M, status Engineering & Procurement, listed for 0 months, date revised 0 time(s), slipped 0 months so far.
- **Model would have said:** P(delay > 12 months) **0%**; completion P50 **2018-08-07**, P90 2018-12-25; P(cost increase > 25%) **67%**; cost P50 $3.01M (P10–P90 $2.30M–$5.27M); P(cancelled) 0%.
- **Drivers:** driver_short=TO Criteria Violatio (-0.60), pct_complete=0.0 (+0.57), equipment=Transmission Line (+0.49), months_to_expected_isd=5.749486652977413 (-0.40)
- **What happened:** in service 2019-05-24 (+6 months vs the date published then), final cost $4.60M (+64%).


Delay calls at the 50% threshold correct in 5/8 labelled cases (the benchmark tables are the proper evaluation; these are illustrations).
