# gridconstraint — predicting which transmission facilities a proposed project will constrain

A research prototype that answers, from **public, pre-study information only**:

> Given a proposed generator / battery / large load at substation *L* with size *P* and type *T*,
> which transmission facilities are most likely to be identified as limiting in the ISO's
> interconnection study, how severe, how costly, and how confident is that prediction?

It ships the full chain: point-in-time dataset with vintage guards → study-report parser and
facility-identity normaliser → required baselines → learned facility-risk models (tabular,
retrieval, public-topology physics, latent factors) → chronological benchmark with calibration
and breakdowns → prospective case studies → a prototype interface.

## Read this first: what is real and what is simulated

The build environment could reach **only PyPI and GitHub**. Every ISO and data host
(pjm.com, dataminer2.pjm.com, misoenergy.org, emp.lbl.gov, eia.gov, HIFLD/ArcGIS, Zenodo,
state PUC dockets, FERC eLibrary) returned an egress-policy 403, for both `curl` and the web
fetch tool. The real study PDFs — the ground truth this project is about — could therefore not
be downloaded here.

So the pipeline was built *for* PJM's real data (`gridconstraint/data/sources.py` documents the
fetchers, and the parser is written against PJM System Impact Study phrasing) and *validated*
on a **simulated ISO** that is as close to the real problem as public data allows:

| Component | Status |
|---|---|
| Transmission topology | **Real public data**: ICARUS PJM nodal testbed (Johns Hopkins, 17,467 buses / 21,554 branches with reactances and MVA ratings, clipped from Breakthrough Energy's USATestSystem), HIFLD substation names, EIA-860 generators, PJM zonal hourly load 2002–2018 — all mirrored on GitHub. |
| Queue projects | **Synthetic queue calibrated to real distributions** (MISO queue snapshot for size/fuel/withdrawal statistics; 211 of the 2024–25 projects carry the real MW / fuel / state of PJM Transition Cycle 2 entries). POIs are real substations of the nodal case. |
| ISO studies (ground truth) | **Simulated**: a PJM-style procedure (generator/load deliverability + N-1 contingency screening with the 5 % DFAX attribution rule, queue-ahead projects and their assumed upgrades in the base case, cost allocation, withdrawal/in-service fates, upgrades that change ratings) run on the hidden nodal case, then **rendered to PDF in three report layouts with realistic naming noise**. |
| Market congestion, outages, baseline upgrades | **Simulated** from soft-limit DC-OPF snapshots on the same hidden case (LMPs, binding constraints, shadow prices), planned outages, and yearly N-1 baseline upgrades. |
| Everything the models see | Public-style tables only: substations/lines with voltages (no impedances, no ratings, 3 % of corridors hidden), queue + dated status events, published study PDFs (parsed back), LMP/constraint history, outages, generators, zonal load — each with an availability date. |

The result is a **methodological** answer ("can public information recover the latent electrical
structure that determines study outcomes, and how much better than heuristics?"), not an
empirical claim about PJM. `REPORT.md` states this in every results table and records exactly what
would be needed to run the real thing.

## Results (chronological hold-out, projects queued after 2022-06-30)

Full tables and discussion in `REPORT.md`. On the simulated ISO:

| | hit@5 | hit@10 | recall@10 | MRR | Brier skill |
|---|---|---|---|---|---|
| Main model (all public features, bagged GBM, calibrated) | 51.0 % | 58.1 % | 31.6 % | 0.40 | 0.095 |
| Best simple baseline (geography + size logistic) | 50.3 % | 57.4 % | 27.8 % | 0.40 | 0.048 |
| Queue-density heuristic | 49.0 % | 51.6 % | 25.0 % | 0.39 | 0.007 |
| Public-topology distribution factor only | 46.5 % | 50.3 % | 24.4 % | 0.39 | 0.029 |
| Historical-congestion heuristic | 16.8 % | 23.2 % | 9.5 % | 0.10 | −0.001 |

* **Primary criterion not met**: on "was a true constrained facility in the top-K", the learned model is
  within a point of a geography + size baseline. Location explains the easy part of the problem.
* On facilities **not directly connected** to the POI the model does better (hit@5 44.9 % vs 40.8 %,
  recall@10 26.4 % vs 19.2 %), its probabilities carry twice the Brier skill, and its expected constraint
  count tracks the real one (correlation 0.41 vs 0.21).
* **Oracle ablation**: handing the model the hidden case's exact impedances lifts hit@5 only 52 % → 54 %.
  The missing private data is facility **headroom** (ratings, planning dispatch, contingency definitions),
  not topology.
* **The value of public evidence depends on how fresh it is and how long headroom persists.** With
  everything public up to the eve of the study (10–26 months after the queue date; 698 test projects) the
  learned model reaches hit@5 60.4 % / hit@10 69.9 % vs 51.4 % / 58.6 % for the geography baseline. In a
  second simulated world where baseline upgrades run every 4 years instead of yearly (so facility headroom
  persists), the queue-date model reaches 55.2 % / 66.7 % vs 50.0 % / 59.2 % (`REPORT.md` §5.7b, §5.10).
* Ground-truth extraction from the rendered PDFs: 99.9 % facility precision and recall across three report
  layouts with realistic naming noise.

## Layout

```
gridconstraint/
  data/loaders.py, sources.py        real public inputs; real-data fetchers (documented, blocked here)
  sim/network.py                     DC power flow, PTDF / LODF engine
  sim/world.py, study.py, market.py  hidden ISO: queue, base case evolution, studies, market, fates, upgrades
  sim/naming.py, report_writer.py    facility identity, naming noise, PJM-style PDF rendering
  extract/pdf_parser.py              PDF -> findings (tables, field lists, prose)
  extract/normalize.py               free-text facility names -> canonical ids (fuzzy, abbreviation, kV, circuit aware)
  features/topology.py               public-topology DC model (guessed impedances) -> approximate DFAX
  features/pit.py                    point-in-time data access with vintage assertions; candidate + feature builder
  models/baselines.py                nearest projects, queue density, congestion, geo+size, simple tabular, public DFAX
  models/latent.py                   latent factors from project->constraint outcomes + market co-binding
  models/tabular.py                  main bagged LightGBM ranker with isotonic calibration
  eval/metrics.py, benchmark.py      hit@K / recall@K / precision@K / MRR / ECE, ablations, breakdowns, secondary tasks
  eval/case_studies.py               prospective reconstructions with explanations
  app/predict.py, build_ui.py        prediction service, CLI, static prototype UI (docs/index.html)
scripts/                             00..06 pipeline; run_all.sh
tests/                               vintage-leak invariance test; parser fixtures in PJM report language
data/raw_public/                     the mirrored real inputs (~7 MB)
data/world/  data/public/  data/studies/   simulated hidden truth / public observables / rendered+parsed studies
outputs/tables, outputs/case_studies documented results
```

## Run

```
pip install -r requirements.txt
sh scripts/run_all.sh                       # ~1.5 h; or run the numbered scripts individually
python3 -m gridconstraint.app.predict --sub "Robison Park" --type gen --mw 200 --as-of 2026-01-01
open docs/index.html                        # prototype interface (static, precomputed)
```

## Real-data run status

The follow-up goal (run the frozen pipeline on 100–300 real historical PJM studies with a strict
as-of date) is **blocked in this environment**: pjm.com and every mirror are egress-blocked, and no
GitHub-hosted copy of PJM study reports or dated queue exports exists. What is in place:

* `scripts/real_pjm_run.py` — frozen model (sha256 recorded in `outputs/tables/real_pjm_run_status.json`),
  strict as-of (queue date + 1 day; studies by first-seen date; status from dated snapshots), no training
  of the main model, first benchmark written only from real inputs; `--selftest` proves the scoring path.
* `data/public_real/` — a real PJM public topology built from the HIFLD transmission-line tiles
  (12,498 corridors, 1,481 transformer pairs, 10,675 substations) in the pipeline's schema.
* `gridconstraint/data/sources.py` — fetchers for the queue export, study PDFs and Data Miner feeds.

From a machine with pjm.com access: fill `data/raw_real/pjm/` as described in the runner's docstring,
then `python3 scripts/real_pjm_run.py`.

## Not an interconnection study

Nothing here replaces an ISO feasibility / system impact / facilities study. The prototype ranks
public evidence; it does not model the ISO's planning case, its contingency lists, its dispatch
assumptions or its cost estimates.
