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
