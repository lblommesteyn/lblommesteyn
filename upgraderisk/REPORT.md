# Predicting transmission network-upgrade delay and cost-overrun risk from public PJM data

*Research prototype. Every number below comes from real PJM publications (archived snapshots of PJM's own project
status tables); nothing is simulated. It is a statistical estimate from public tables, not an engineering or schedule
assessment, and it does not replace PJM's or a transmission owner's process.*

## 0. Verdict

The go/no-go threshold was met by a wide margin (2,568 resolved upgrades in a real chronological
holdout), so the full benchmark was run. Against the success criterion ("materially beats owner / type / age
baselines") the result is mixed and mostly negative:

* **Slip > 12 months:** the honest model (survival model + calibrated classifier, refitted each test month on outcomes
  knowable then) reaches AUROC 0.62 and Brier 0.172 against 0.57 / 0.185 for the best simple
  baseline (owner rate) and 0.187 for the base rate. That is a real but modest improvement, driven by an upgrade's own
  public history; on upgrades never seen before, AUROC is 0.50 — no skill.
* **Cost increase > 25 %:** AUROC 0.61 for the classifier versus 0.62 for a three-feature logistic
  regression (voltage, cost, horizon); no model beats the base-rate Brier of 0.175. Not material.
* **Completion date:** PJM's own published date is a better point estimate (MAE 9.3 months) than any model's
  median (10.6); the survival model's P10–P90 band covers 78% of outcomes at P90, which is its useful output.
* **Cancellation:** AUROC 0.72, the strongest single signal in the data.
* A leaky first pass (fixed cutoff, labels from the full record) scored slip AUROC 0.835; that number is what a careless
  benchmark on this data would report, and it is not real.

What limits a stronger benchmark, all traceable to public-data gaps (section 7): the 12-month label lag combined with
sparse archived snapshots (labelled training pools run at a 4–7 % slip rate while the 2018–2019 test months run
17–26 %, partly a genuine regime change), no public snapshot between 2019-12 and 2026-09, a holdout limited to baseline
upgrades, and no public milestone, permitting or procurement data. The prototype is therefore a working
point-in-time pipeline with an honest, modest slip signal — not a tool that materially out-forecasts PJM's own tables.

## 1. Question

Given a network upgrade at time *t*, using only information public at *t*: what is the probability the upgrade slips
more than 12 months past the in-service date PJM was publishing at *t*; what is the probability its cost estimate
ends up more than 25 % above the estimate published at *t*; and what completion-date and final-cost ranges are
consistent with the public record.

## 2. Data (all public, PJM)

PJM's "Transmission Construction Status" / "Project Status & Cost Allocation" table is republished continuously,
and only the current version is served. The longitudinal table **upgrade × observation_date** was reconstructed from:

| Source | Snapshots | Dates | What it carries |
|---|---|---|---|
| Wayback captures of the legacy `construct-status.aspx` page (baseline tab; rows embedded in ASP.NET ViewState or an inline JSON block) | 38 | 20150908 – 20191215 | upgrade ID, TO projected in-service date, PJM required date, status (EP / UC / On Hold …), % complete, cost estimate ($M), owner, voltage, equipment, task, driver, initial/latest TEAC date, last-updated |
| Wayback captures of the legacy `cost-allocation-view.aspx` page (all baseline upgrades, in-service ones included) | 25 | 20150909 – 20180726 | cost estimate, cost-allocation shares, required date, cancelled flag (used for cost history only; never as a status reference) |
| Wayback captures of the XML data files behind the legacy page (`TOUP_planned_baseline / network / TO.xml`) | 23 | 2010, 2013, 2016 – 2017 | same fields as the page for the baseline, network and supplemental tabs |
| Live export of PJM's current Project Status & Cost Allocation grid (`/planning/m/project-construction`) | 1 | 2026-09-17 | 16,262 upgrades with status, actual in-service date, current cost, TEAC cost, board-approval and TEAC dates |

The fetch runs on a GitHub Actions runner (this sandbox cannot reach pjm.com or archive.org); the decoded rows are
committed under `data/raw/pjm_snapshots/` with a manifest (URL, capture timestamp, sha256). Captures from
2010–2014 were ActiveX pages whose data lived in XML files, of which Wayback holds a few; 2019 cost-allocation captures
are truncated by the archive and were dropped.

Long table: **141,267 rows, 16,262 distinct upgrade IDs.** Observation dates are the
38 construction-status snapshot dates (2015-09-08 … 2019-12-15).

### Point-in-time rules (enforced in code and tests)

* The reference row for an upgrade at *t* is the latest **status-bearing** snapshot published within the 45 days
  before *t*. An upgrade absent from recent status snapshots has left the active list and gets no example (the
  cost-allocation view's bare "Active" flag is never treated as a status).
* Features use only rows with `snapshot_date <= t`. `tests/test_vintage.py` rebuilds the features from a table truncated
  at *t* and asserts equality; it also asserts every completion-known date lies after the observation.
* Labels use rows published after *t* plus PJM's current record: in-service date, final cost, cancellation.
* A model "trained at cutoff *c*" only sees labels that were **knowable by *c*** (`pit.known_by`): a 12-month slip
  label is decidable once the 12-month window has closed or the project was seen finished after it; a cost label
  once the project finished or its estimate first exceeded the +25 % line; the survival target is censored at *c*.
  Without this, a model recognises an upgrade seen in training and recalls its eventual fate.
* Examples whose 12-month window had already closed at *t* carry no slip label (the outcome was not a forecast).
* Owner / voltage / equipment historical rates used as features are computed from earlier examples whose labels were
  known at *t*, shrunk toward the global known rate.

### Outcome definitions

* `delay_12m`: in-service date (PJM's record) more than 12 months after the projected date published at *t*; also 1
  when the project was still unbuilt 12 months after that date. Cancelled projects: no slip label.
* `cost_overrun_25`: final cost (or, if unfinished, latest estimate) more than 25 % above the estimate at *t*. Cancelled
  projects and projects whose final cost field is zero: no cost label.
* `months_late`, `pct_overrun`: continuous versions for completed projects.
* `cancelled`: 1 if cancelled/withdrawn, 0 if completed, missing while unresolved.
* Survival target: months from *t* to in-service, censored at the last observation.
* Censoring: 6,574 of 38,634 examples (17%) are unresolved in
  PJM's current table; 17% of completed examples have a recorded in-service date at or before the
  observation date (PJM's table lagged the energisation, or the date refers to a first partial energisation) — they are
  kept, labelled from the recorded date.

### Dataset

* 38,634 examples (3,390 upgrades); 2,568 upgrades resolved (in service or cancelled) — the go/no-go threshold was 200.
* Slip label available for 25,162 examples, base rate 19.1%; cost label for 24,005, base rate 17.8%.
* Months late (completed, relative to the date published at *t*): P10 -9, P50 0, P90 20 months.

By project type (the 2018–2019 snapshots cover the baseline tab only, so the holdout is baseline upgrades):

| upgrade_type       |   rows |   upgrades |   delay |   over |
|:-------------------|-------:|-----------:|--------:|-------:|
| Baseline           |  26157 |       1600 |   0.141 |  0.191 |
| Network            |   6851 |        905 |   0.505 |  0.071 |
| Supplemental       |   5590 |        880 |   0.31  |  0.167 |
| Transmission Owner |     36 |          5 |   0.222 |  0.222 |

## 3. Models

Baselines: always-on-time (PJM's own date and cost), base rate, project-age × slip-so-far heuristic, point-in-time
owner / voltage-class / equipment rates, logistic regression on (voltage, cost, horizon), logistic regression on all
numeric features. Models: bagged LightGBM classifiers with isotonic calibration on the later quarter of the training
window (slip, cost, cancellation), LightGBM quantile regressors (P10/P50/P90 months late and % cost change), and a
discrete-time (monthly) hazard model for time-to-in-service (P(not in service by PJM's date + 12 months), median).

## 4. Benchmark (rolling-origin chronological holdout)

Test period: observations after **2017-12-31** (6,877 examples, 943 upgrades, 559 examples of
upgrades never observed before their origin). For each test month, every baseline and model is refitted on all examples
observed before that month using only labels knowable by then (31,757 rows at the first origin, 37,458 at the
last), then scores that month. Test labels come from the full record. Origins:

| origin     |   n_train |   n_test |   delay_labels_train |   overrun_labels_train |   cancel_labels_train |   train_delay_rate |   events_train |   seconds |
|:-----------|----------:|---------:|---------------------:|-----------------------:|----------------------:|-------------------:|---------------:|----------:|
| 2018-01-25 |     31757 |     1328 |                 4295 |                   9840 |                 12139 |          0.054482  |          10889 |      66.6 |
| 2018-02-18 |     33085 |      666 |                 4319 |                  10208 |                 12573 |          0.0541792 |          11322 |      54.4 |
| 2018-06-09 |     33751 |      631 |                 6727 |                  12158 |                 14582 |          0.0396908 |          13225 |      59.5 |
| 2018-07-10 |     34382 |     1344 |                 7036 |                  13061 |                 15692 |          0.0544343 |          14335 |      65.9 |
| 2019-08-19 |     35726 |     1160 |                12986 |                  16959 |                 20504 |          0.0691514 |          19147 |      80   |
| 2019-10-23 |     36886 |      572 |                13290 |                  17292 |                 20867 |          0.0705794 |          19510 |      78   |
| 2019-12-13 |     37458 |     1176 |                13722 |                  18099 |                 21801 |          0.0744061 |          20444 |      83.9 |

A first pass with a single fixed cutoff and labels taken from the full record (the leaky protocol) gave a slip AUROC of
0.835; restricting training labels to what was knowable at the cutoff dropped it to 0.58, because most of that
"skill" was the model recognising an upgrade seen in training and recalling its eventual fate. The numbers below use
the honest protocol only.

Rolling-origin chronological benchmark: 7 test months from 2018-01-25 to 2019-12-13; at each, models are refitted on examples observed earlier (31757–37458 rows) using only labels knowable by then, and score that month's 1328/666/631/1344/1160/572/1176 examples (pooled: 6877 examples, 943 upgrades, 559 examples of upgrades unseen before their origin).

| model                       |   delay_auroc |   delay_brier |   delay_ece |   delay_prauc |   over_auroc |   over_brier |   over_prauc |   cancel_auroc |   cod_mae |   p50_cov |   p90_cov |   new_delay_auroc |   new_over_auroc |
|:----------------------------|--------------:|--------------:|------------:|--------------:|-------------:|-------------:|-------------:|---------------:|----------:|----------:|----------:|------------------:|-----------------:|
| always_on_time              |         0.5   |         0.201 |       0.189 |         0.209 |        0.5   |        0.211 |        0.219 |        nan     |     9.269 |     0.556 |     0.556 |             0.5   |            0.5   |
| base_rate                   |         0.542 |         0.187 |       0.149 |         0.228 |        0.493 |        0.175 |        0.216 |        nan     |     9.28  |     0.444 |     0.76  |             0.445 |            0.452 |
| project_age                 |         0.537 |         0.188 |       0.154 |         0.237 |        0.524 |        0.178 |        0.227 |        nan     |     9.375 |     0.431 |     0.761 |             0.424 |            0.492 |
| rate_to                     |         0.567 |         0.185 |       0.144 |         0.254 |        0.574 |        0.172 |        0.311 |        nan     |     9.629 |     0.469 |     0.752 |             0.519 |            0.522 |
| rate_voltage_class          |         0.532 |         0.186 |       0.141 |         0.224 |        0.483 |        0.175 |        0.21  |        nan     |     9.275 |     0.439 |     0.758 |             0.482 |            0.496 |
| rate_equipment              |         0.563 |         0.188 |       0.154 |         0.244 |        0.522 |        0.177 |        0.235 |        nan     |     9.301 |     0.451 |     0.743 |             0.541 |            0.578 |
| logit_voltage_cost_duration |         0.49  |         0.198 |       0.179 |         0.208 |        0.621 |        0.176 |        0.283 |        nan     |    11.093 |     0.292 |     0.622 |             0.538 |            0.517 |
| logit_numeric               |         0.499 |         0.201 |       0.19  |         0.225 |        0.628 |        0.206 |        0.277 |        nan     |    13.431 |     0.144 |     0.497 |             0.508 |            0.516 |
| gbm                         |         0.592 |         0.196 |       0.177 |         0.258 |        0.611 |        0.19  |        0.296 |          0.718 |    13.89  |     0.183 |     0.534 |             0.497 |            0.568 |
| dt_survival                 |         0.616 |         0.213 |       0.177 |         0.284 |        0.493 |        0.175 |        0.216 |        nan     |    10.6   |     0.587 |     0.776 |             0.497 |            0.452 |
| blend                       |         0.62  |         0.172 |       0.103 |         0.286 |        0.611 |        0.19  |        0.296 |          0.718 |    10.6   |     0.587 |     0.776 |             0.497 |            0.568 |

Headline (blend = survival model + calibrated classifier): **slip > 12 months AUROC 0.620 / Brier 0.172**
(base rate Brier 0.187; best simple baseline `rate_to` AUROC 0.567; survival model alone 0.616,
classifier alone 0.592). **Cost +25 % AUROC 0.611 / Brier 0.190** (base rate
0.175, best baseline 0.574). Completion-month MAE of the survival P50: 10.6 months vs
9.3 for PJM's published date; P50 coverage 0.59, P90 coverage 0.78.
Cancellation AUROC (classifier): 0.718.

Follow-up: at a 2018 origin the archive offered at most about 28 months of observed follow-up (the first snapshot is
2015-09); completion quantiles are never quoted beyond that (shown as "≥"), and slip probabilities for windows ending
beyond it are extrapolations of the hazard, which is a further reason the survival estimates are pessimistic for
multi-year projects. Why the classifier is weak here: a slip label only becomes knowable when the 12-month window has closed, so at any
origin the labelled pool is older, shorter-horizon cohorts with a 4–7 % slip rate, while the test months run 17–26 %.
The survival model uses every earlier observation with censoring and is the more honest formulation for this label.

**Upgrades unseen before the cutoff**: slip AUROC 0.497, cost AUROC 0.568
(n = 364). What skill there is comes from an upgrade's own public history (how long it has been
listed, how often its date moved, its owner's track record); for an upgrade with no history the models have none.

### By test month (slip label)

| origin     |    n |   rate |   blend_auroc |   blend_brier |   surv_auroc |   gbm_auroc |   rate_to_auroc |   base_brier |
|:-----------|-----:|-------:|--------------:|--------------:|-------------:|------------:|----------------:|-------------:|
| 2018-01-01 |  932 |  0.167 |         0.642 |         0.146 |        0.638 |       0.652 |           0.536 |        0.152 |
| 2018-02-01 |  468 |  0.167 |         0.653 |         0.151 |        0.652 |       0.662 |           0.546 |        0.152 |
| 2018-06-01 |  506 |  0.196 |         0.644 |         0.163 |        0.641 |       0.555 |           0.511 |        0.182 |
| 2018-07-01 | 1054 |  0.19  |         0.687 |         0.162 |        0.696 |       0.541 |           0.521 |        0.172 |
| 2019-08-01 |  946 |  0.258 |         0.609 |         0.207 |        0.604 |       0.568 |           0.535 |        0.227 |
| 2019-10-01 |  465 |  0.245 |         0.613 |         0.185 |        0.609 |       0.578 |           0.564 |        0.216 |
| 2019-12-01 |  968 |  0.233 |         0.614 |         0.183 |        0.604 |       0.573 |           0.579 |        0.204 |

### Breakdowns (blend, slip label; classifier, cost label)

By transmission owner:

| group      |    n |   rate |   auroc |   brier |   mae_p50 |
|:-----------|-----:|-------:|--------:|--------:|----------:|
| AEP        | 1935 |  0.288 |   0.552 |   0.245 |    11.264 |
| Dominion   |  974 |  0.12  |   0.661 |   0.108 |     8.198 |
| PSEG       |  666 |  0.111 |   0.548 |   0.111 |     9.703 |
| APS        |  574 |  0.435 |   0.633 |   0.294 |     7.141 |
| PENELEC    |  418 |  0.083 |   0.602 |   0.114 |     8.784 |
| EKPC       |  318 |  0.174 |   0.592 |   0.149 |    11.071 |
| PECO       |  220 |  0.026 |   0.728 |   0.035 |     4.198 |
| JCPL       |  192 |  0.34  |   0.398 |   0.264 |    17.689 |
| BGE        |  172 |  0.363 |   0.52  |   0.276 |    13.446 |
| ATSI       |  168 |  0.205 |   0.804 |   0.134 |     9.335 |
| DEOK       |  159 |  0.107 |   0.596 |   0.113 |     8.286 |
| PPL        |  158 |  0.078 |   0.62  |   0.069 |     8.806 |
| Dayton     |  144 |  0.535 |   0.63  |   0.253 |    29.849 |
| DL         |  116 |  0     | nan     | nan     |     4.287 |
| ME         |  105 |  0.471 |   0.636 |   0.374 |    22.951 |
| ComEd      |   99 |  0     | nan     | nan     |     6.842 |
| AEC        |   94 |  0     | nan     | nan     |     6.412 |
| DPL        |   87 |  0.128 |   0.583 |   0.134 |    10.08  |
| Transource |   60 |  0.733 |   0.903 |   0.312 |     3.561 |
| NIPSCO     |   46 |  0     | nan     | nan     |    13.968 |

By voltage class:

| group   |    n |   rate |   auroc |   brier |   mae_p50 |
|:--------|-----:|-------:|--------:|--------:|----------:|
| 100-199 | 3059 |  0.214 |   0.576 |   0.185 |    10.92  |
| 200-399 | 2022 |  0.167 |   0.663 |   0.138 |     9.651 |
| <100    | 1316 |  0.248 |   0.644 |   0.191 |    11.012 |
| 400+    |  443 |  0.264 |   0.677 |   0.2   |    11.351 |

By cost estimate:

| group   |    n |   rate |   auroc |   brier |   mae_p50 |
|:--------|-----:|-------:|--------:|--------:|----------:|
| <1M     | 2965 |  0.199 |   0.611 |   0.167 |    10.622 |
| 1-5M    | 1332 |  0.261 |   0.557 |   0.219 |    11.945 |
| 5-20M   | 1296 |  0.175 |   0.705 |   0.135 |     9.609 |
| 20-100M | 1053 |  0.181 |   0.635 |   0.15  |     9.964 |
| >100M   |  231 |  0.353 |   0.619 |   0.271 |    11.513 |

By horizon to the published in-service date:

| group    |    n |   rate |   auroc |   brier |   mae_p50 |
|:---------|-----:|-------:|--------:|--------:|----------:|
| >24m     | 1930 |  0.266 |   0.539 |   0.214 |    15.08  |
| 12-24m   | 1845 |  0.239 |   0.601 |   0.193 |    10.431 |
| past due | 1193 |  0.1   |   0.87  |   0.079 |     5.546 |
| 0-6m     |  956 |  0.117 |   0.625 |   0.107 |     7.381 |
| 6-12m    |  953 |  0.216 |   0.586 |   0.186 |     9.805 |

By status at observation:

| group                     |    n |   rate |   auroc |   brier |   mae_p50 |
|:--------------------------|-----:|-------:|--------:|--------:|----------:|
| Engineering & Procurement | 5651 |  0.236 |   0.593 |   0.191 |    11.333 |
| Under Construction        |  911 |  0.082 |   0.635 |   0.083 |     6.938 |
| On Hold                   |  315 |  0.111 |   0.031 |   0.188 |    24.792 |

Cost label by owner (classifier):

| group      |    n |   rate |   auroc |   brier |   mae_p50 |
|:-----------|-----:|-------:|--------:|--------:|----------:|
| AEP        | 1935 |  0.095 |   0.631 |   0.153 |    14.136 |
| Dominion   |  974 |  0.247 |   0.711 |   0.175 |    11.712 |
| PSEG       |  666 |  0     | nan     | nan     |    11.618 |
| APS        |  574 |  0.55  |   0.419 |   0.377 |    10.645 |
| PENELEC    |  418 |  0.401 |   0.49  |   0.292 |     9.312 |
| EKPC       |  318 |  0.05  |   0.364 |   0.142 |    25.362 |
| PECO       |  220 |  0.497 |   0.409 |   0.36  |     7.981 |
| JCPL       |  192 |  0.453 |   0.493 |   0.304 |    21.788 |
| BGE        |  172 |  0.517 |   0.491 |   0.433 |    15.762 |
| ATSI       |  168 |  0.592 |   0.629 |   0.33  |    13.839 |
| DEOK       |  159 |  0.317 |   0.729 |   0.193 |    13.224 |
| PPL        |  158 |  0     | nan     | nan     |    12.065 |
| Dayton     |  144 |  0     | nan     | nan     |    39.756 |
| DL         |  116 |  0     | nan     | nan     |     3.351 |
| ME         |  105 |  0.447 |   0.812 |   0.226 |    29.358 |
| ComEd      |   99 |  0.093 |   0.521 |   0.101 |     7.294 |
| AEC        |   94 |  0.138 |   0.641 |   0.129 |    10.1   |
| DPL        |   87 |  0.678 |   0.729 |   0.311 |    14.363 |
| Transource |   60 |  0.733 |   0.881 |   0.351 |    11.158 |
| NIPSCO     |   46 |  0.043 |   0.682 |   0.076 |     5.481 |

### Feature importance (gain, slip classifier)

|                                |     0 |
|:-------------------------------|------:|
| status                         | 68696 |
| driver_short                   | 34191 |
| task                           | 26383 |
| months_required_minus_expected | 25696 |
| months_to_expected_isd         | 17018 |
| log_cost                       | 16951 |
| equipment                      | 15910 |
| to                             | 15779 |
| pct_complete                   | 15232 |
| rate_status_cost_overrun_25    | 12952 |
| slip_so_far_months             | 11650 |
| voltage_kv                     | 11362 |
| months_since_initial_teac      |  9163 |
| state                          |  8700 |
| months_since_last_teac         |  7953 |

## 5. Case studies


Each case is a real PJM upgrade at a real archived observation date. The model outputs are those of the benchmark model refitted before that month on outcomes knowable then; it saw nothing published after the as-of date. Analogs are earlier upgrades whose outcome was already known on that date. What happened is taken from PJM's current table (2026).

## b2986 — PSEG, 230.0 kV Transmission Structures (as of 2018-01-25)
*Replace the existing Roseland – Branchburg – Pleasant Valley 230 kV corridor with new structures.*

- **At 2018-01-25 PJM's table said:** in service 2022-06-01, cost $546.00M, status Engineering & Procurement, listed for 0 months, date revised 0 time(s), slipped 0 months so far.
- **Model would have said:** P(slip > 12 months) **40%** (survival 75%, classifier 5%); completion P50 **≥ 2020-06-12**, P90 ≥ 2020-06-12 (survival model); P(cost increase > 25 %) **44%**; cost P50 $514.72M (P10–P90 $340.54M–$884.40M); P(cancelled) 24%. *The 12-month window ends beyond the 29 months of follow-up the archive offered at this origin, so the slip probability is an extrapolation; '≥' marks a quantile beyond that follow-up.*
- **Drivers:** pct_complete=0.0 (+0.75), log_cost=6.3 (+0.74), months_since_initial_teac=0.5 (+0.51), months_to_expected_isd=52.2 (-0.40)
- **Analogs known then:** s0387 (PSEG, late -25 mo); b1304.1 (PSEG, late +1 mo); b2218 (PSEG, cancelled); b2436.84 (PSEG, late -1 mo)
- **What happened:** cancelled / withdrawn.

## b2443 — Dominion, 230.0 kV Transmission Line (as of 2018-01-25)
*Construct new underground 230kV line from Gelebe to Station C.*

- **At 2018-01-25 PJM's table said:** in service 2023-05-31, cost $320.00M, status Engineering & Procurement, listed for 29 months, date revised 2 time(s), slipped 60 months so far.
- **Model would have said:** P(slip > 12 months) **36%** (survival 68%, classifier 4%); completion P50 **≥ 2020-06-13**, P90 ≥ 2020-06-13 (survival model); P(cost increase > 25 %) **68%**; cost P50 $295.97M (P10–P90 $182.41M–$660.36M); P(cancelled) 15%. *The 12-month window ends beyond the 29 months of follow-up the archive offered at this origin, so the slip probability is an extrapolation; '≥' marks a quantile beyond that follow-up.*
- **Drivers:** pct_complete=3.0 (+0.85), log_cost=5.8 (+0.62), equipment=Transmission Line (+0.28), months_to_expected_isd=64.1 (-0.27)
- **Analogs known then:** b2582 (Dominion, late -5 mo); b2585 (Dominion, cancelled); b1792 (Dominion, late -25 mo); b1254.1 (BGE, cancelled)
- **What happened:** cancelled / withdrawn.

## b2837 — PSEG, 138.0 kV Transmission Line (as of 2018-01-25)
*Convert the F-1358/Z1326 and K1363/Y-1325 (Trenton - Burlington) 138 kV circuits to 230 kV circuits*

- **At 2018-01-25 PJM's table said:** in service 2022-06-01, cost $312.00M, status Engineering & Procurement, listed for 11 months, date revised 0 time(s).
- **Model would have said:** P(slip > 12 months) **44%** (survival 86%, classifier 3%); completion P50 **≥ 2020-06-12**, P90 ≥ 2020-06-12 (survival model); P(cost increase > 25 %) **66%**; cost P50 $296.25M (P10–P90 $160.24M–$499.91M); P(cancelled) 18%. *The 12-month window ends beyond the 29 months of follow-up the archive offered at this origin, so the slip probability is an extrapolation; '≥' marks a quantile beyond that follow-up.*
- **Drivers:** task=Convert (+0.72), pct_complete=5.0 (+0.61), log_cost=5.7 (+0.59), months_to_expected_isd=52.2 (-0.25)
- **Analogs known then:** b2256 (AEP, late +0 mo); b2218 (PSEG, cancelled); b2436.84 (PSEG, late -1 mo); b2436.85 (PSEG, late -1 mo)
- **What happened:** in service 2021-05-07 (-13 months vs the date published then).

## b2838 — PPL, 230.0 kV Substation (as of 2018-01-25)
*Build a new 230/69 kV substation by tapping the Montour - Susquehanna 230 kV double circuits and Berwick - Hunlock & Berwick - Colombia 69 kV circuits*

- **At 2018-01-25 PJM's table said:** in service 2020-08-01, cost $57.00M, status Engineering & Procurement, listed for 9 months, date revised 0 time(s), slipped -13 months so far.
- **Model would have said:** P(slip > 12 months) **35%** (survival 68%, classifier 2%); completion P50 **≥ 2020-06-12**, P90 ≥ 2020-06-12 (survival model); P(cost increase > 25 %) **35%**; cost P50 $50.49M (P10–P90 $44.04M–$59.78M); P(cancelled) 4%. *The 12-month window ends beyond the 29 months of follow-up the archive offered at this origin, so the slip probability is an extrapolation; '≥' marks a quantile beyond that follow-up.*
- **Drivers:** log_cost=4.1 (+0.67), pct_complete=30.0 (-0.53), months_since_initial_teac=12.0 (+0.33), months_to_expected_isd=30.2 (-0.27)
- **Analogs known then:** b2006 (PPL, late +1 mo); b2006.2 (PPL, late -0 mo); s0957.1 (PPL, late -2 mo); s0974.3 (PPL, late -84 mo)
- **What happened:** in service 2022-05-20 (+22 months vs the date published then), final cost $57.00M (+0%).

## b1570.2 — Dayton, 69.0 kV Transmission Line (as of 2018-01-25)
*Add Marysville - Union REA 69 kV line*

- **At 2018-01-25 PJM's table said:** in service 2021-06-01, cost $0.00M, status Engineering & Procurement, listed for 52 months, date revised 1 time(s), slipped 84 months so far.
- **Model would have said:** P(slip > 12 months) **50%** (survival 97%, classifier 3%); completion P50 **≥ 2020-06-12**, P90 ≥ 2020-06-12 (survival model); P(cost increase > 25 %) **77%**; cost P50 $0.00M (P10–P90 $0.00M–$0.00M); P(cancelled) 8%. *The 12-month window ends beyond the 29 months of follow-up the archive offered at this origin, so the slip probability is an extrapolation; '≥' marks a quantile beyond that follow-up.*
- **Drivers:** pct_complete=2.0 (+0.57), equipment=Transmission Line (+0.46), slip_so_far_months=84.0 (+0.32), months_to_expected_isd=40.2 (-0.22)
- **Analogs known then:** b2336 (EKPC, late -29 mo); b2664 (EKPC, late -23 mo); b2326 (EKPC, late -14 mo); b2344.6 (AEP, late -5 mo)
- **What happened:** in service 2026-09-17 (+64 months vs the date published then).

## b2970.5 — APS, 230.0 kV Substation (as of 2019-08-19)
*Convert Garfield 138/12.5 kV substation to 230/12.5 kV*

- **At 2019-08-19 PJM's table said:** in service 2020-11-01, cost $2.20M, status Engineering & Procurement, listed for 0 months, date revised 0 time(s), slipped 0 months so far.
- **Model would have said:** P(slip > 12 months) **21%** (survival 39%, classifier 2%); completion P50 **2021-04-24**, P90 ≥ 2023-07-30 (survival model); P(cost increase > 25 %) **30%**; cost P50 $2.23M (P10–P90 $2.10M–$2.74M); P(cancelled) 4%. *The 12-month window ends beyond the 47 months of follow-up the archive offered at this origin, so the slip probability is an extrapolation; '≥' marks a quantile beyond that follow-up.*
- **Drivers:** driver_short=Baseline Load Growth (-0.50), months_required_minus_expected=-5.0 (-0.31), pct_complete=0.0 (+0.30), n_status_cost_overrun_25=11794.0 (-0.19)
- **Analogs known then:** b2261 (APS, late -0 mo); b2362.1 (APS, late -1 mo); b2763 (APS, cancelled); s1039 (APS, late -0 mo)
- **What happened:** not yet in service as of the last observation (2026-09-17).

## b2686.12 — Dominion, 115.0 kV Transmission Line (as of 2018-01-25)
*Upgrading sections of the Somerset - Doubleday 115 kV circuit*

- **At 2018-01-25 PJM's table said:** in service 2020-06-01, cost $0.00M, status Engineering & Procurement, listed for 27 months, date revised 0 time(s).
- **Model would have said:** P(slip > 12 months) **30%** (survival 59%, classifier 1%); completion P50 **≥ 2020-06-12**, P90 ≥ 2020-06-12 (survival model); P(cost increase > 25 %) **48%**; cost P50 $0.00M (P10–P90 $0.00M–$0.00M); P(cancelled) 8%. *The 12-month window ends beyond the 29 months of follow-up the archive offered at this origin, so the slip probability is an extrapolation; '≥' marks a quantile beyond that follow-up.*
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
- **Model would have said:** P(slip > 12 months) **49%** (survival 96%, classifier 2%); completion P50 **≥ 2020-06-12**, P90 ≥ 2020-06-12 (survival model); P(cost increase > 25 %) **69%**; cost P50 $3.57M (P10–P90 $3.38M–$3.60M); P(cancelled) 56%. *The 12-month window ends beyond the 29 months of follow-up the archive offered at this origin, so the slip probability is an extrapolation; '≥' marks a quantile beyond that follow-up.*
- **Drivers:** pct_complete=1.0 (+0.67), equipment=Capacitor (-0.46), months_to_expected_isd=28.2 (-0.29), n_status_delay_12m=2040.0 (-0.27)
- **Analogs known then:** b2754.2 (JCPL, cancelled); b2754.3 (JCPL, cancelled); b2590 (PSEG, cancelled); b2357 (JCPL, late +5 mo)
- **What happened:** cancelled / withdrawn.

## b2666.8 — APS, 138.0 kV Circuit Breaker (as of 2018-01-25)
*Replace Yukon 138kV breaker 'Y-9(SPRINGD)' with an 80kA breaker*

- **At 2018-01-25 PJM's table said:** in service 2019-06-01, cost $0.82M, status On Hold, listed for 27 months, date revised 0 time(s).
- **Model would have said:** P(slip > 12 months) **41%** (survival 79%, classifier 3%); completion P50 **≥ 2020-06-12**, P90 ≥ 2020-06-12 (survival model); P(cost increase > 25 %) **8%**; cost P50 $0.82M (P10–P90 $0.80M–$0.97M); P(cancelled) 12%. *The 12-month window ends beyond the 29 months of follow-up the archive offered at this origin, so the slip probability is an extrapolation; '≥' marks a quantile beyond that follow-up.*
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


## 6. Prototype

* CLI: `python scripts/predict_cli.py <upgrade id> --as-of YYYY-MM-DD` or `--custom '{...}'` — prints PJM's date and
  cost, model P50/P90 completion, P(slip), cost range, P(cost +25 %), P(cancelled), risk drivers and resolved analogs.
* Page: `outputs/ui/index.html` (built by `scripts/05_build_ui.py`; published at
  https://claude.ai/artifact/S6TrxGcBmkz11WUbTUPxgJ) — every holdout example, searchable, with the same fields and a
  "reveal what happened" control.

## 7. Limits and what would change the picture

* Coverage is baseline upgrades in the holdout and 2015–2019 observation dates; network and supplemental upgrades are
  in training only through the 2016–2017 XML files. Snapshot density is uneven (monthly in 2016–2017, quarterly later).
* Between the last archived snapshot (2019-12) and the live export (2026-09) there is no intermediate public snapshot,
  so cost paths after 2019 are unobserved (labels still resolve via the 2026 record).
* PJM's in-service dates lag or refer to partial energisations for some multi-part upgrades; owner-level results for
  small owners are noisy.
* Labels are relative to PJM's published date at *t*, which is itself revised; the "slip" is measured against what the
  public could see then, which is the deployment-relevant quantity.
* Private data that would help most: TO construction schedules and milestone reports, permitting dockets, procurement
  lead times, and the RTEP cost/scope change memos in structured form.
