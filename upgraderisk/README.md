# upgraderisk — delay and cost-overrun risk for PJM transmission upgrades, point-in-time

A research prototype that predicts, for a PJM network/baseline/supplemental upgrade as listed on a given day,
the probability of a >12-month slip past PJM's published in-service date, the probability of a >25 % cost increase,
and completion-date / final-cost ranges — using only what was public on that day. Real data only; the only
synthetic table is the toy used by the unit tests. Results and caveats: `REPORT.md`.

## Where the data comes from

PJM only serves the current version of its Project Status & Cost Allocation table. The longitudinal table is rebuilt
from Internet Archive captures of the legacy "Transmission Construction Status" page (2015–2019, rows embedded in
ViewState or inline JSON), the XML data files behind it (2010, 2013, 2016–2017), and the live export of the current
grid (2026-09-17). The fetch runs on GitHub Actions (`.github/workflows/fetch_pjm_upgrade_snapshots.yml`, script
`scripts/fetch_pjm_legacy_snapshots.py`) because this sandbox cannot reach pjm.com or archive.org; results are
committed under `data/raw/pjm_snapshots/` with `manifest.csv`. Discovery of the sources is in `scripts/discover*.py`
and `data/raw/discovery*/`.

## Pipeline

```
pip install -r requirements.txt
python scripts/01_build_dataset.py        # long table + point-in-time examples + go/no-go summary
python -m pytest -q tests                  # unit + vintage/leakage tests (real table when present)
python scripts/02_run_benchmark.py         # chronological holdout, baselines vs models, breakdowns
python scripts/03_train_final.py           # model bundle trained on labels knowable at the cutoff
python scripts/04_case_studies.py          # prospective case studies on the holdout
python scripts/05_build_ui.py              # outputs/ui/index.html
python scripts/06_write_report.py          # REPORT.md
python scripts/predict_cli.py b2837 --as-of 2018-01-25
python scripts/predict_cli.py --as-of 2019-12-15 --custom '{"to":"AEP","voltage_kv":138,"est_cost_musd":12,"expected_isd":"2021-06-01","equipment":"Transmission Line","task":"Rebuild","status":"Engineering & Procurement"}'
```

Published page (holdout browser): https://claude.ai/artifact/S6TrxGcBmkz11WUbTUPxgJ

## Layout

* `upgraderisk/pjm_snapshots.py` — parsers for the legacy grids, XML files and live export into the canonical long table.
* `upgraderisk/pit.py` — point-in-time references, history features, outcome labels with label-known dates, `known_by(cutoff)`.
* `upgraderisk/features.py` — feature matrix and point-in-time group rates.
* `upgraderisk/baselines.py`, `models.py`, `metrics.py` — baselines, LightGBM (calibrated) + quantile + discrete-time survival, metrics.
* `upgraderisk/predict.py` — score one upgrade at an as-of date (drivers, analogs) or a hypothetical one.
* `outputs/tables/` — benchmark.json, benchmark_main.md, reliability tables, predictions; `outputs/cases/` — case studies.

Statistical estimate from public tables; not an engineering or schedule assessment.
