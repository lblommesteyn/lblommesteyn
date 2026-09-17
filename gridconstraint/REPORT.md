# Predicting transmission constraints for proposed grid projects from public pre-study information

*Research report — gridconstraint prototype. All results below are on a simulated ISO over a real public PJM-footprint case; see section 1 for why, and section 8 for what a real-data run needs.*

## 0. Headline

**For unseen projects (queued after 2022-06-30), the actual constrained facility appeared in the model's top-5 predictions 51.0% of the time and in the top-10 58.1% of the time**, using only information public on the day the project entered the queue. But the best simple baseline (B4 geography + size (logistic)) reached 50.3% / 57.4%: **on the headline metric the learned method does not materially beat geography, queue-density or simple-ML baselines, so the success condition is not met in this world.**

What the learned method does add, on the same held-out projects: (i) on facilities *not directly connected* to the POI — the non-trivial part — hit@5 44.9% vs 40.8% for the best baseline and recall@10 26.4% vs 19.2%; (ii) probabilistic skill roughly doubles (Brier skill 0.095 vs 0.048); (iii) the expected number of constrained facilities tracks the actual number much better (correlation 0.410 vs 0.213). Recall@10 over all constrained facilities is 31.6% against a candidate ceiling of 87.4%.

**Which private data is missing?** Handing the model the hidden case's exact impedances (true distribution factors) raises hit@5 only from 51.6% to 54.2% and recall@10 from 31.0% to 35.1%. Topology is not the bottleneck; **facility headroom** (ratings, planning dispatch, contingency definitions) is — and no public feed carries it.

**The picture changes with fresher information.** Evaluated with everything public up to the day before the study was published (the wording of the goal; 10–26 months later than the queue date; 698 test projects), the learned model reaches hit@5 **60.4%** and hit@10 **69.9%** against 53.2% / 63.7% for the best simple baseline (B5 simple tabular GBM (23 features)), with recall@10 37.1% vs 31.5%. On non-adjacent facilities: hit@5 55.0% vs 45.2%, recall@10 34.9% vs 28.7%. Public evidence about a facility's headroom (recent studies, queue movements, market binding) decays quickly in this world, so its value depends on how recent it is.

It is **not** an empirical result about PJM: the labels are simulated studies (section 1). It is the answer to *"if an ISO's studies are produced by a PJM-style thermal procedure on a case whose topology is public but whose impedances, ratings and dispatch are not, how much of the outcome can public information recover?"* In this world the answer is: the location-driven part almost entirely, the headroom-driven part barely — and section 5.10 shows how much that changes when facility headroom persists between studies.

## 1. Problem and honesty statement

**Question.** Can information that is public *before* an ISO interconnection study is published —
queue history, earlier published studies, nodal congestion, outages, generation/load and
approximate topology — predict which transmission facilities a proposed generator, battery or
large load will be found to constrain, how severely, and at what upgrade burden?

**What could and could not be done here.** The build sandbox's egress policy allowed only PyPI
and GitHub. PJM (queue export, study PDFs, Data Miner), MISO, LBNL, EIA, HIFLD/ArcGIS, Zenodo,
FERC eLibrary and state PUC dockets all returned 403 from both `curl` and the web-fetch tool.
Real study reports — the labels — were therefore unobtainable. Rather than stop, the project
was built in two tracks:

* **Track A (real-data pipeline, runnable outside the sandbox).** Fetchers for PJM's queue
  export, study PDFs and Data Miner feeds (`gridconstraint/data/sources.py`), a parser written
  against real PJM System Impact Study phrasing (tested on fixture text in that style), a facility
  normaliser, and point-in-time features that only depend on dated public tables.
* **Track B (executed here).** A *simulated ISO* over a **real public PJM-footprint nodal case**
  (ICARUS PJM nodal testbed: 17,467 buses, 21,554 branches with reactances and MVA ratings).
  The simulator runs a PJM-style study procedure for every queue project, renders the results as
  PDFs with realistic naming noise, and publishes market, outage and upgrade data derived from the
  same hidden case. Models see only the public side. The benchmark therefore tests the *method*
  end-to-end (including parsing and normalisation) under a known ground truth, and the oracle
  ablation quantifies which private planning data the public side cannot substitute for.

Every number in this report is a result on the simulated ISO. Nothing here is an empirical
claim about PJM's actual studies.

## 2. Data

### 2.1 Real public inputs (mirrored on GitHub)

| Input | Source | Role |
|---|---|---|
| PJM nodal case (bus/branch/plant/gencost, coordinates) | ICARUS PJM Dataset (Johns Hopkins, CC-BY-4.0), clipped from Breakthrough Energy USATestSystem | hidden planning case; public geometry/voltages derived from it |
| HIFLD substations (names, kV, coordinates) | DHS HIFLD Open via TransmissionMap mirror | substation names (nearest named HIFLD site within 5 km, else a state-matched real name) |
| EIA-860 generators | EIA via TransmissionMap mirror | generator layer schema (the public generator table is the case's plant list in EIA-860 form) |
| PJM zonal hourly load 2002–2018 | PJM Data Miner mirror (panambY) | hourly load shapes for market snapshots |
| PJM Transition Cycle 2 projects (360) | ICARUS 21-zone package | real MW / fuel / state for 211 of the 2024–25 synthetic queue entries |
| MISO queue snapshot (3,846 rows, gridstatus schema) | savabs/queue_attrition mirror | calibration of size-by-fuel, arrival growth and withdrawal-lag distributions |

### 2.2 The simulated ISO ("hidden world")

*Queue.* 2,640 requests 2011–2025 (90/yr rising to 330/yr, then the 2023 cycle pause), type mix
drifting from gas/wind to solar/storage/large load, sizes log-normal per fuel (MISO medians), POIs
chosen by a preference model over real substations (voltage class, herding on prior queue MW,
rural preference for solar/wind, load proximity for storage/large loads, persistent site
attractiveness). POI voltage scales with size. 12 % withdraw before any study.

*Planning case by year.* Load grows by zone (Virginia data-centre growth after 2020), coal/oil
plants retire 4.5 %/yr, in-service queue projects join the fleet, large loads add demand. Each
year the ISO runs a summer-peak soft-limit DC-OPF for dispatch and a full N-1 screen of the
pre-queue case, raising ratings of violated facilities with 2–30 % random headroom (the baseline
RTEP analogue; published as *baseline upgrades*).

*Study procedure (PJM Manual 14B, simplified).* Injection (or withdrawal for loads; both for
storage) at the POI offset by a dispatch-proportional system redispatch; base case includes all
earlier-queued, not-withdrawn projects **and their assigned upgrades assumed in service**; N-0 plus
single contingencies (non-radial ≥100 kV branches the project affects by ≥2 % or within 3 hops);
a facility is attributed when post-contingency loading >100 %, project DFAX ≥5 % and the project
aggravates the flow. Upgrades (reconductor / rebuild / transformer replacement / terminal work)
are costed by voltage class and length with log-normal noise and shared among contributing
queue-ahead projects by DFAX-weighted MW. Withdrawal probability rises with $/kW (and storage);
non-withdrawn projects enter service 1.5–4 years later, at which point their upgrades raise
physical ratings.

*Market.* 12–13 representative hours per year (monthly PJME-shape peaks plus the annual peak),
DC-OPF with $2,000/MWh constraint penalty and $5,000/MWh VOLL, renewable availability by hour,
0.2–0.6 % of lines on planned outage. Published: LMP and congestion component per ≥100 kV
substation, binding constraints with shadow prices (TO-style upper-case names), outage records.

*Reports.* Each study becomes a PDF in one of three layouts (ruled tables; prose "is overloaded
to X % of its Y MVA rating for the loss of…"; field lists), with per-report naming style and
per-mention noise: abbreviations (Street→St, North→N, Junction→Jct…), case, separators,
kV spelling, circuit/unit suffixes, endpoint order swaps, "Substation" tokens, 5 % typos.

### 2.3 Public side (what models see)

`data/public/`: substations (name, kV, coordinates), facilities (line corridors with kV and
straight-line length, transformers with kV pair, bus ties; 3 % of corridors hidden to mimic HIFLD
gaps; **no impedances, no ratings, no circuit counts**), generators (EIA-860 form), queue entries
and dated status events, study index with publication dates + the PDFs, LMP/congestion per
substation-hour, binding constraints with shadow prices, outages, baseline upgrades, zonal
annual peaks.

### 2.4 Point-in-time discipline

`features/pit.py` exposes every dated table through a `PITView(as_of)` whose accessors assert
`date < as_of`. Features for project X are computed as of **its queue date + 1 day** (the strict
prospective setting) — X's own study is never visible, and neither is any study published later.
`tests/test_vintage.py` recomputes features from tables physically truncated at `as_of` and
asserts bit-identical output (invariance to future rows). The chronological split additionally
requires **label vintage**: training labels come from studies *published* ≤ 2020-12-31,
validation from studies published ≤ 2022-06-30, and test projects are those *queued* after
2022-06-30, so every training/validation label was public before every test prediction date.
Projects straddling the boundary are dropped.

## 3. Ground-truth extraction

`extract/pdf_parser.py` unions three independent extractors (pdfplumber tables with
Facility/Contingency/Loading/Rating/DFAX headers; "Facility: … Contingency: … Loading: …" field
lists; prose regexes for the sentence forms) and parses metadata (queue number, MW, POI,
dates, stated facility count, total cost) with cross-checks. `extract/normalize.py` maps each
mention to a canonical id `L:<subA>:<subB>:<kV>` / `X:<sub>:<kVhi>:<kVlo>` / `B:<sub>:<kV>` using
only the public substation and facility lists: kV and transformer-pair parsing, circuit/unit
stripping, separator handling, abbreviation-normalised keys, two fuzzy scorers with a
short-string penalty, kV-compatibility and (tie-break only) POI-proximity adjustments, and a
preference for corridors that exist in the public layer. Extraction quality is scored against the
hidden truth for every study (section 5.1) and a random sample is dumped for manual inspection
(`outputs/case_studies/parse_inspection_sample.md`).

## 4. Candidates, features and models

**Candidates** per project: public facilities within 90 km or 6 public-graph hops of the POI,
plus any facility with public-topology N-1 distribution factor ≥ 0.015, plus facilities named
by prior studies of projects within 60 km; capped at 800 by DFAX. The share of true facilities
inside the candidate set is reported as the *ceiling*.

**Feature families** (all point-in-time): geometry/topology (distance, hops, kV, kind, degree,
approximate N-0/N-1 DFAX from a DC model with impedances *guessed* from kV class and length);
facility history from prior studies (times named, MW-weighted, max loading, mean DFAX, recency,
how many naming projects are active / withdrawn / in service, named by nearby or same-POI
projects, mean allocated cost); retrieval (similarity-weighted share of the 10 most similar prior
projects that named the facility); congestion (binding hours and shadow prices in 24 months and
all-time, LMP congestion at POI and facility ends, gap across the facility); outages and recent
baseline upgrades; queue density (active MW at the POI, within 25/50 km, near the facility ends,
local withdrawal rate); existing generation at facility ends; project size/type/fuel/voltage/time;
latent-factor score (SVD embeddings of a context × facility matrix built from prior study outcomes
and market co-binding, cold-started for unseen POIs from studied POIs within 40 km; fitted per
year on studies published before that year).

**Baselines.** B1 nearest historical projects (retrieval score alone); B2 queue-density
heuristic; B3 historical-congestion heuristic; B4 geography+size logistic regression; B5 simple
tabular GBM (23 features); plus P0 public-topology DFAX alone and L0 latent factors alone.

**Main model.** Bagged LightGBM classifier over (project, candidate) rows, early-stopped on the
validation split, isotonic-calibrated on validation, bag spread as uncertainty. Ablations remove
one feature family at a time. Secondary models: severity bucket (≤105 / 105–120 / >120 % loading)
among true facilities; project-level allocated-cost bucket ($0 / <1M / 1–10M / 10–50M / >50M) and
withdrawal, both from aggregated ranker outputs plus project features.

**Headroom-persistence variant.** A second world with the same seed, queue and procedure but with the yearly
N-1 baseline pass run only every 4 years (`World(harden_every=4)`), so that a facility that sits near its
limit stays there for several years, as on a real grid where ratings and baseline upgrades change slowly.
The base world re-randomises headroom every year (2–30 % margin draws), which is the pessimistic case for
history-based public evidence.


## 5. Results

### 5.1 Ground-truth extraction quality (automated check against the hidden truth, plus manual sample)

Studies: 2168; findings in truth: 16051; parsed: 16437 (extraction recall 100.0%).
Facility identity resolution: precision **100.0%**, recall **99.9%**; 99.1% of studies reconstructed exactly; total-cost match 100.0%; loading MAE 0.000 pts; queue-number match 100.0%.

| layout | n | fid precision | fid recall |
|---|---|---|---|
| A | 1068 | 99.9% | 99.9% |
| B | 431 | 99.9% | 99.8% |
| C | 669 | 100.0% | 99.9% |

Manual inspection of five random reports (`outputs/case_studies/parse_inspection_sample.md`) found no errors; typos in the reports ("Military Ighway", "Ae Columbia") were resolved by the fuzzy matcher.

### 5.2 Main benchmark — features as of the queue date

Test set: **279 projects** queued after 2022-06-30 (155 with at least one constrained facility; ranking metrics are averaged over those). Candidate-set ceiling (share of true facilities the candidate generator can rank at all): **87.4%**. Train: 1106 projects (studies published ≤ 2020-12-31); validation: 363 (≤ 2022-06-30).

| model | hit@1 | hit@3 | hit@5 | hit@10 | recall@5 | recall@10 | precision@5 | MRR | ECE | Brier skill | count corr. |
|---|---|---|---|---|---|---|---|---|---|---|---|
| B1 nearest historical projects | 12.3% | 18.1% | 20.6% | 34.2% | 7.2% | 13.5% | 9.7% | 0.190 | 0.001 | 0.015 | 0.171 |
| B2 queue-density heuristic | 29.0% | 43.2% | 49.0% | 51.6% | 19.0% | 25.0% | 21.9% | 0.391 | 0.002 | 0.007 | -0.201 |
| B3 historical-congestion heuristic | 1.9% | 8.4% | 16.8% | 23.2% | 5.5% | 9.5% | 4.9% | 0.099 | 0.002 | -0.001 | -0.085 |
| B4 geography + size (logistic) | 28.4% | 46.5% | 50.3% | 57.4% | 19.9% | 27.8% | 23.2% | 0.397 | 0.001 | 0.048 | 0.213 |
| B5 simple tabular GBM (23 features) | 24.5% | 41.9% | 49.7% | 59.4% | 18.1% | 28.7% | 22.3% | 0.367 | 0.001 | 0.065 | 0.283 |
| P0 public-topology DFAX only (physics, no learning) | 29.7% | 43.2% | 46.5% | 50.3% | 18.6% | 24.4% | 22.5% | 0.391 | 0.002 | 0.029 | 0.133 |
| L0 latent factors only | 1.3% | 4.5% | 7.7% | 11.6% | 1.9% | 3.5% | 2.3% | 0.052 | 0.002 | 0.002 | 0.105 |
| **MAIN: all public features (bagged GBM, calibrated)** | 29.0% | 44.5% | 51.0% | 58.1% | 20.9% | 31.6% | 23.7% | 0.401 | 0.000 | 0.095 | 0.410 |

Ablations (main model minus one feature family; 1 bag each):

| removed family | hit@5 | hit@10 | recall@10 | MRR |
|---|---|---|---|---|
| congestion | 51.6% | 61.9% | 32.9% | 0.406 |
| prior_studies | 49.7% | 60.0% | 30.0% | 0.414 |
| topology | 53.5% | 59.4% | 27.6% | 0.430 |
| queue | 52.9% | 66.5% | 35.2% | 0.413 |
| outages_baseline | 50.3% | 58.7% | 29.8% | 0.390 |
| latent | 52.3% | 62.6% | 30.4% | 0.387 |

hit@K = at least one true facility in the top K; recall@K = share of the project's true facilities in the top K; MRR = mean reciprocal rank of the first true facility; ECE and Brier skill (1 − Brier/Brier of the base rate) on isotonic-calibrated probabilities (each baseline score was also isotonic-calibrated on the validation split so calibration is compared like for like; with a 0.9 % positive rate, ECE is near zero for every model and Brier skill is the informative number); count corr. = correlation between the sum of a project's probabilities and its actual number of constrained facilities.

### 5.3 Calibration of the main model (test set, 10 bins)

| bin | n | mean predicted | observed rate |
|---|---|---|---|
| 0 | 220997 | 0.004 | 0.004 |
| 1 | 341 | 0.142 | 0.196 |
| 2 | 196 | 0.254 | 0.306 |
| 3 | 39 | 0.374 | 0.333 |
| 5 | 81 | 0.510 | 0.519 |
| 7 | 18 | 0.730 | 0.722 |
| 8 | 9 | 0.830 | 0.778 |
| 9 | 13 | 0.947 | 0.769 |

### 5.4 Breakdowns (test set)

| dimension | value | model | n | hit@1 | hit@5 | hit@10 | recall@10 | MRR |
|---|---|---|---|---|---|---|---|---|
| poi_seen | seen_poi | MAIN all features | 70 | 27.1% | 45.7% | 52.9% | 30.7% | 0.352 |
| poi_seen | seen_poi | B4 geo size logit | 70 | 20.0% | 41.4% | 50.0% | 24.9% | 0.313 |
| poi_seen | seen_poi | P0 public topology dfax | 70 | 21.4% | 37.1% | 41.4% | 20.0% | 0.312 |
| poi_seen | unseen_poi | MAIN all features | 85 | 35.3% | 56.5% | 63.5% | 31.1% | 0.456 |
| poi_seen | unseen_poi | B4 geo size logit | 85 | 35.3% | 57.6% | 63.5% | 30.3% | 0.467 |
| poi_seen | unseen_poi | P0 public topology dfax | 85 | 36.5% | 54.1% | 57.6% | 28.0% | 0.457 |
| mw_bucket | <50MW | MAIN all features | 18 | 5.6% | 38.9% | 44.4% | 22.6% | 0.197 |
| mw_bucket | <50MW | B4 geo size logit | 18 | 22.2% | 27.8% | 44.4% | 14.5% | 0.281 |
| mw_bucket | <50MW | P0 public topology dfax | 18 | 5.6% | 33.3% | 38.9% | 18.7% | 0.171 |
| mw_bucket | 50-200MW | MAIN all features | 97 | 26.8% | 46.4% | 55.7% | 27.7% | 0.362 |
| mw_bucket | 50-200MW | B4 geo size logit | 97 | 20.6% | 44.3% | 52.6% | 24.6% | 0.329 |
| mw_bucket | 50-200MW | P0 public topology dfax | 97 | 25.8% | 39.2% | 44.3% | 20.9% | 0.343 |
| mw_bucket | >200MW | MAIN all features | 40 | 55.0% | 70.0% | 72.5% | 42.2% | 0.619 |
| mw_bucket | >200MW | B4 geo size logit | 40 | 50.0% | 75.0% | 75.0% | 41.7% | 0.615 |
| mw_bucket | >200MW | P0 public topology dfax | 40 | 50.0% | 70.0% | 70.0% | 35.5% | 0.607 |
| project_type | battery | MAIN all features | 37 | 35.1% | 45.9% | 51.4% | 30.7% | 0.402 |
| project_type | battery | B4 geo size logit | 37 | 35.1% | 43.2% | 51.4% | 23.1% | 0.405 |
| project_type | battery | P0 public topology dfax | 37 | 37.8% | 45.9% | 48.6% | 25.2% | 0.417 |
| project_type | gen | MAIN all features | 100 | 30.0% | 53.0% | 61.0% | 30.0% | 0.405 |
| project_type | gen | B4 geo size logit | 100 | 25.0% | 49.0% | 57.0% | 27.8% | 0.376 |
| project_type | gen | P0 public topology dfax | 100 | 25.0% | 44.0% | 49.0% | 22.2% | 0.367 |
| project_type | load | MAIN all features | 18 | 33.3% | 55.6% | 61.1% | 36.4% | 0.445 |
| project_type | load | B4 geo size logit | 18 | 33.3% | 72.2% | 72.2% | 38.0% | 0.497 |
| project_type | load | P0 public topology dfax | 18 | 38.9% | 61.1% | 61.1% | 35.2% | 0.476 |

### 5.5 Secondary tasks

| task | model | n | accuracy | macro-F1 | adjacent acc. | AUC | base rate |
|---|---|---|---|---|---|---|---|
| severity_bucket(<=105,105-120,>120) | gbm | 1016 | 0.416 | 0.374 | — | — | — |
| severity_bucket(<=105,105-120,>120) | majority | 1016 | 0.304 | 0.155 | — | — | — |
| upgrade_cost_bucket | gbm(project-level, uses ranker probs) | 279 | 0.305 | 0.287 | 0.638 | — | — |
| upgrade_cost_bucket | majority | 279 | 0.151 | 0.052 | 0.416 | — | — |
| upgrade_cost_bucket | geo+size+queue only | 279 | 0.280 | 0.257 | 0.613 | — | — |
| withdrawal | gbm(project-level) | 279 | — | — | — | 0.521 | 0.215 |
| withdrawal | geo+size+queue only | 279 | — | — | — | 0.550 | 0.215 |

Cost-bucket and withdrawal models use the ranker's probabilities aggregated per project; training-row probabilities are in-sample (optimistic), which is why the geo+size+queue-only comparison is shown.

### 5.6 What the model uses

| feature | share of gain |
|---|---|
| `apx_dfax_n1` | 20.8% |
| `apx_contrib_mw` | 9.6% |
| `apx_dfax` | 7.3% |
| `dist_km` | 4.6% |
| `dist_far_km` | 4.2% |
| `fac_kv` | 3.7% |
| `fac_cong_vs_poi` | 2.8% |
| `hops` | 2.7% |
| `year` | 2.7% |
| `kv_ratio` | 2.6% |
| `mw` | 2.5% |
| `poi_cong_mean` | 2.3% |
| `analog_mean_nfac` | 2.2% |
| `queue_mw_all_50km` | 2.2% |
| `analog_mean_dist` | 2.1% |

### 5.7 The non-trivial part: facilities not directly connected to the POI

Any geometry rule finds the POI's own outlet lines. Restricting the ranking to candidates that do not touch the POI substation isolates the part of the problem where public *evidence* (history, congestion, queue, learned topology) has to do the work:

| model | subset | n | hit@1 | hit@5 | hit@10 | recall@5 | recall@10 | MRR |
|---|---|---|---|---|---|---|---|---|
| B1 nearest historical projects | all facilities | 155 | 12.3% | 20.6% | 34.2% | 7.2% | 13.5% | 0.190 |
| B1 nearest historical projects | non-adjacent facilities only | 147 | 12.2% | 19.7% | 32.0% | 7.1% | 12.1% | 0.184 |
| B2 queue-density heuristic | all facilities | 155 | 29.0% | 49.0% | 51.6% | 19.0% | 25.0% | 0.391 |
| B2 queue-density heuristic | non-adjacent facilities only | 147 | 21.8% | 36.7% | 41.5% | 11.8% | 17.1% | 0.291 |
| B3 historical-congestion heuristic | all facilities | 155 | 1.9% | 16.8% | 23.2% | 5.5% | 9.5% | 0.099 |
| B3 historical-congestion heuristic | non-adjacent facilities only | 147 | 2.7% | 10.9% | 17.0% | 2.9% | 6.1% | 0.086 |
| B4 geography + size (logistic) | all facilities | 155 | 28.4% | 50.3% | 57.4% | 19.9% | 27.8% | 0.397 |
| B4 geography + size (logistic) | non-adjacent facilities only | 147 | 21.1% | 40.8% | 45.6% | 12.6% | 19.2% | 0.300 |
| B5 simple tabular GBM (23 features) | all facilities | 155 | 24.5% | 49.7% | 59.4% | 18.1% | 28.7% | 0.367 |
| B5 simple tabular GBM (23 features) | non-adjacent facilities only | 147 | 15.6% | 40.8% | 49.7% | 14.0% | 22.5% | 0.281 |
| P0 public-topology DFAX only (physics, no learning) | all facilities | 155 | 29.7% | 46.5% | 50.3% | 18.6% | 24.4% | 0.391 |
| P0 public-topology DFAX only (physics, no learning) | non-adjacent facilities only | 147 | 21.1% | 34.7% | 40.8% | 11.9% | 17.0% | 0.285 |
| L0 latent factors only | all facilities | 155 | 1.3% | 7.7% | 11.6% | 1.9% | 3.5% | 0.052 |
| L0 latent factors only | non-adjacent facilities only | 147 | 0.7% | 7.5% | 12.2% | 1.6% | 3.5% | 0.050 |
| MAIN: all public features (bagged GBM, calibrated) | all facilities | 155 | 29.0% | 51.0% | 58.1% | 20.9% | 31.6% | 0.401 |
| MAIN: all public features (bagged GBM, calibrated) | non-adjacent facilities only | 147 | 21.1% | 44.9% | 51.0% | 16.7% | 26.4% | 0.319 |

### 5.8 Drift across test years

| queue year | model | n | hit@5 | hit@10 | recall@10 | MRR |
|---|---|---|---|---|---|---|
| 2022 | MAIN: all public features (bagged GBM, calibrated) | 78 | 48.7% | 55.1% | 33.8% | 0.369 |
| 2022 | B4 geography + size (logistic) | 78 | 50.0% | 55.1% | 28.2% | 0.380 |
| 2022 | P0 public-topology DFAX only (physics, no learning) | 78 | 42.3% | 46.2% | 25.8% | 0.386 |
| 2023 | MAIN: all public features (bagged GBM, calibrated) | 37 | 67.6% | 73.0% | 34.7% | 0.564 |
| 2023 | B4 geography + size (logistic) | 37 | 64.9% | 70.3% | 33.7% | 0.484 |
| 2023 | P0 public-topology DFAX only (physics, no learning) | 37 | 67.6% | 70.3% | 33.8% | 0.487 |
| 2024 | MAIN: all public features (bagged GBM, calibrated) | 39 | 41.0% | 48.7% | 24.2% | 0.316 |
| 2024 | B4 geography + size (logistic) | 39 | 38.5% | 48.7% | 20.6% | 0.355 |
| 2024 | P0 public-topology DFAX only (physics, no learning) | 39 | 35.9% | 41.0% | 13.3% | 0.319 |
| 2025 | MAIN: all public features (bagged GBM, calibrated) | 1 | 0.0% | 100.0% | 33.3% | 0.167 |
| 2025 | B4 geography + size (logistic) | 1 | 0.0% | 100.0% | 66.7% | 0.167 |
| 2025 | P0 public-topology DFAX only (physics, no learning) | 1 | 0.0% | 0.0% | 0.0% | 0.083 |

### 5.9 Model selection (validation split only)

| config | split | hit@5 | hit@10 | recall@10 | MRR | non-adjacent hit@5 | non-adjacent recall@10 |
|---|---|---|---|---|---|---|---|
| binary_current | valid | 58.8% | 69.7% | 34.8% | 0.488 | 56.4% | 32.3% |
| binary_current | test | 50.3% | 60.0% | 30.8% | 0.405 | 40.8% | 25.5% |
| binary_regularised | valid | 62.3% | 69.3% | 35.4% | 0.483 | 55.0% | 29.7% |
| binary_regularised | test | 52.3% | 57.4% | 29.7% | 0.397 | 40.1% | 25.4% |
| lambdarank | valid | 61.4% | 68.9% | 35.1% | 0.461 | 56.9% | 33.1% |
| lambdarank | test | 54.2% | 63.2% | 33.1% | 0.428 | 47.6% | 29.7% |

### 5.7b Variant — features as of the day before the study was published

Same models, but every public record up to the eve of publication is allowed (typically 10–26 months more queue, study and market history).

Test set: **698 projects** queued after 2022-06-30 (432 with at least one constrained facility; ranking metrics are averaged over those). Candidate-set ceiling (share of true facilities the candidate generator can rank at all): **90.3%**. Train: 1106 projects (studies published ≤ 2020-12-31); validation: 363 (≤ 2022-06-30).

| model | hit@1 | hit@3 | hit@5 | hit@10 | recall@5 | recall@10 | precision@5 | MRR | ECE | Brier skill | count corr. |
|---|---|---|---|---|---|---|---|---|---|---|---|
| B1 nearest historical projects | 13.0% | 26.6% | 30.8% | 42.4% | 11.2% | 17.9% | 12.9% | 0.230 | 0.000 | 0.021 | 0.226 |
| B2 queue-density heuristic | 28.2% | 44.0% | 49.5% | 54.9% | 18.4% | 25.9% | 22.4% | 0.389 | 0.000 | 0.008 | -0.204 |
| B3 historical-congestion heuristic | 3.7% | 8.8% | 16.7% | 26.2% | 4.2% | 9.2% | 4.7% | 0.113 | 0.000 | -0.001 | -0.071 |
| B4 geography + size (logistic) | 28.2% | 46.5% | 51.4% | 58.6% | 19.3% | 26.4% | 23.6% | 0.397 | 0.000 | 0.046 | 0.256 |
| B5 simple tabular GBM (23 features) | 30.8% | 48.4% | 53.2% | 63.7% | 20.2% | 31.5% | 25.3% | 0.425 | 0.000 | 0.096 | 0.425 |
| P0 public-topology DFAX only (physics, no learning) | 28.0% | 42.4% | 46.3% | 53.0% | 18.6% | 25.7% | 22.9% | 0.377 | 0.001 | 0.045 | 0.138 |
| L0 latent factors only | 3.7% | 6.7% | 9.5% | 12.7% | 3.6% | 5.2% | 3.1% | 0.075 | 0.001 | 0.004 | 0.090 |
| **MAIN: all public features (bagged GBM, calibrated)** | 35.6% | 52.1% | 60.4% | 69.9% | 25.5% | 37.1% | 29.2% | 0.471 | 0.000 | 0.132 | 0.530 |

Non-adjacent facilities, pre-publication features:

| model | subset | n | hit@1 | hit@5 | hit@10 | recall@5 | recall@10 | MRR |
|---|---|---|---|---|---|---|---|---|
| B1 nearest historical projects | all facilities | 432 | 13.0% | 30.8% | 42.4% | 11.2% | 17.9% | 0.230 |
| B1 nearest historical projects | non-adjacent facilities only | 418 | 12.9% | 28.9% | 40.2% | 10.6% | 17.8% | 0.220 |
| B2 queue-density heuristic | all facilities | 432 | 28.2% | 49.5% | 54.9% | 18.4% | 25.9% | 0.389 |
| B2 queue-density heuristic | non-adjacent facilities only | 418 | 25.6% | 38.8% | 45.7% | 14.7% | 20.8% | 0.325 |
| B3 historical-congestion heuristic | all facilities | 432 | 3.7% | 16.7% | 26.2% | 4.2% | 9.2% | 0.113 |
| B3 historical-congestion heuristic | non-adjacent facilities only | 418 | 4.1% | 14.1% | 22.2% | 3.3% | 6.7% | 0.105 |
| B4 geography + size (logistic) | all facilities | 432 | 28.2% | 51.4% | 58.6% | 19.3% | 26.4% | 0.397 |
| B4 geography + size (logistic) | non-adjacent facilities only | 418 | 22.0% | 42.1% | 49.0% | 13.7% | 20.8% | 0.316 |
| B5 simple tabular GBM (23 features) | all facilities | 432 | 30.8% | 53.2% | 63.7% | 20.2% | 31.5% | 0.425 |
| B5 simple tabular GBM (23 features) | non-adjacent facilities only | 418 | 24.9% | 45.2% | 58.4% | 17.8% | 28.7% | 0.358 |
| P0 public-topology DFAX only (physics, no learning) | all facilities | 432 | 28.0% | 46.3% | 53.0% | 18.6% | 25.7% | 0.377 |
| P0 public-topology DFAX only (physics, no learning) | non-adjacent facilities only | 418 | 24.4% | 38.3% | 45.5% | 14.7% | 20.8% | 0.321 |
| L0 latent factors only | all facilities | 432 | 3.9% | 9.7% | 12.7% | 3.6% | 5.2% | 0.077 |
| L0 latent factors only | non-adjacent facilities only | 418 | 4.1% | 9.6% | 12.9% | 3.5% | 5.0% | 0.077 |
| MAIN: all public features (bagged GBM, calibrated) | all facilities | 432 | 35.6% | 60.4% | 69.9% | 25.5% | 37.1% | 0.471 |
| MAIN: all public features (bagged GBM, calibrated) | non-adjacent facilities only | 418 | 32.1% | 55.0% | 65.3% | 23.3% | 34.9% | 0.429 |

### 5.10 Sensitivity to headroom persistence (second simulated world)

Variant world: identical seed, queue and procedure, but the yearly N-1 baseline pass runs only every 4 years, so facility headroom persists between studies (test projects: 273; candidate ceiling 87.7%).

| model | hit@5 (yearly re-hardening) | hit@5 (persistent headroom) | hit@10 (yearly) | hit@10 (persistent) | recall@10 (yearly) | recall@10 (persistent) | Brier skill (yearly) | Brier skill (persistent) |
|---|---|---|---|---|---|---|---|---|
| B2 queue-density heuristic | 49.0% | 47.7% | 51.6% | 59.2% | 25.0% | 29.7% | 0.007 | 0.007 |
| B4 geography + size (logistic) | 50.3% | 50.0% | 57.4% | 59.2% | 27.8% | 30.2% | 0.048 | 0.036 |
| B5 simple tabular GBM (23 features) | 49.7% | 47.1% | 59.4% | 60.9% | 28.7% | 31.3% | 0.065 | 0.075 |
| P0 public-topology DFAX only (physics, no learning) | 46.5% | 47.1% | 50.3% | 55.7% | 24.4% | 29.7% | 0.029 | 0.028 |
| MAIN: all public features (bagged GBM, calibrated) | 51.0% | 55.2% | 58.1% | 66.7% | 31.6% | 37.0% | 0.095 | 0.104 |

Non-adjacent facilities, variant world:

| model | subset | n | hit@1 | hit@5 | hit@10 | recall@5 | recall@10 | MRR |
|---|---|---|---|---|---|---|---|---|
| B1 nearest historical projects | all facilities | 174 | 12.1% | 24.7% | 32.2% | 7.4% | 12.5% | 0.200 |
| B1 nearest historical projects | non-adjacent facilities only | 165 | 11.5% | 25.5% | 33.3% | 8.4% | 13.4% | 0.200 |
| B2 queue-density heuristic | all facilities | 174 | 27.6% | 47.7% | 59.2% | 19.6% | 29.7% | 0.385 |
| B2 queue-density heuristic | non-adjacent facilities only | 165 | 25.5% | 40.6% | 47.3% | 18.1% | 23.9% | 0.332 |
| B3 historical-congestion heuristic | all facilities | 174 | 1.7% | 16.7% | 25.3% | 3.5% | 8.1% | 0.106 |
| B3 historical-congestion heuristic | non-adjacent facilities only | 165 | 1.8% | 12.7% | 21.8% | 3.0% | 7.9% | 0.089 |
| B4 geography + size (logistic) | all facilities | 174 | 23.0% | 50.0% | 59.2% | 20.4% | 30.2% | 0.368 |
| B4 geography + size (logistic) | non-adjacent facilities only | 165 | 24.8% | 44.2% | 54.5% | 18.2% | 27.6% | 0.348 |
| B5 simple tabular GBM (23 features) | all facilities | 174 | 25.9% | 47.1% | 60.9% | 18.4% | 31.3% | 0.375 |
| B5 simple tabular GBM (23 features) | non-adjacent facilities only | 165 | 23.0% | 45.5% | 59.4% | 18.3% | 30.2% | 0.342 |
| P0 public-topology DFAX only (physics, no learning) | all facilities | 174 | 26.4% | 47.1% | 55.7% | 20.7% | 29.7% | 0.367 |
| P0 public-topology DFAX only (physics, no learning) | non-adjacent facilities only | 165 | 26.7% | 40.6% | 46.7% | 18.0% | 23.8% | 0.337 |
| L0 latent factors only | all facilities | 174 | 2.3% | 7.5% | 13.8% | 1.5% | 3.6% | 0.062 |
| L0 latent factors only | non-adjacent facilities only | 165 | 3.6% | 7.3% | 13.9% | 2.0% | 4.0% | 0.072 |
| MAIN: all public features (bagged GBM, calibrated) | all facilities | 174 | 33.9% | 55.2% | 66.7% | 24.7% | 37.0% | 0.442 |
| MAIN: all public features (bagged GBM, calibrated) | non-adjacent facilities only | 165 | 27.3% | 52.1% | 63.6% | 23.5% | 35.1% | 0.395 |

## 6. Prospective case studies

`outputs/case_studies/README.md` reconstructs, for eight test projects, the prediction that would have been made on the queue date, then reveals the study and explains each hit and miss (with hidden-world diagnostics quoted only in the explanation). The cases were selected automatically: clear hits, misses, an unseen-POI hit, a non-generator project, and a no-constraint study.

## 7. What private planning data is missing? (oracle ablation)

Give the main model the hidden case's *true* N-0 distribution factors (i.e. exact impedances and topology) as one extra feature:

| model | hit@1 | hit@5 | hit@10 | recall@10 | MRR |
|---|---|---|---|---|---|
| MAIN_public_only | 29.7% | 51.6% | 59.4% | 31.0% | 0.402 |
| MAIN_plus_true_impedances(oracle) | 33.5% | 54.2% | 61.9% | 35.1% | 0.432 |
| true_impedances_only(oracle DFAX rank) | 31.0% | 47.1% | 54.8% | 27.4% | 0.394 |

The gain from true impedances is the part of the gap that better public topology (or a planning-case impedance file) would close; what remains after that is due to facility **headroom** — ratings, the planning dispatch and the contingency definitions — which no public feed carries. In the simulation the public side infers headroom only indirectly (binding hours, prior studies, baseline upgrades), which is why facility-history and congestion families matter in the ablations.

## 8. Limitations, negative-result reading, and the real-data run

* **Everything is simulated except topology, names, load shapes and project characteristics.** The study procedure is a simplified PJM thermal procedure (no voltage, stability, short-circuit, N-1-1, or light-load tests), naming noise is synthetic, market snapshots are sparse (12–13 hours/year), and the queue is synthetic. The benchmark measures methodology, not PJM.
* **Candidate ceiling.** About 14 % of true facilities are outside the candidate set. They are far-field constraints (median distance of true facilities is tens of km, but a quarter are >300 km away) where a 5 % distribution factor arises through long 345/500 kV paths; the guessed-impedance public model under-estimates those. Raising the cap or the DFAX rule trades recall for a much larger candidate table.
* **Label vintage.** Training labels are studies published ≤ 2020-12-31, validation ≤ 2022-06-30, test projects queued after 2022-06-30; 2023–2025 projects whose studies were not published by the end of 2025 are unlabeled and excluded.
* **Real-data run.** `gridconstraint/data/sources.py` documents the PJM feeds. Steps: (1) weekly queue snapshots (or Wayback captures) for dated status; (2) impact/feasibility PDFs with first-seen dates; (3) Data Miner LMP and constraint feeds (free key); (4) HIFLD lines/substations; (5) run scripts 02→06 unchanged. Expect the parser's prose patterns to need extension for older report vintages, and the normaliser to need PJM's TO naming conventions (e.g. "(AEP)" prefixes, "TAP" suffixes).
* **If the real signal is weak**, the oracle ablation is the template for the negative result: quantify the gain from a planning-case impedance file (PJM's RTEP case is available to members under CEII) versus from ratings/dispatch, and report which one the public side cannot substitute.

## 9. Reproduction

`sh scripts/run_all.sh` (≈1.5 h on 4 cores). Tables in `outputs/tables/`, case studies in `outputs/case_studies/`, the prototype interface in `docs/index.html`, the CLI in `gridconstraint/app/predict.py`.
