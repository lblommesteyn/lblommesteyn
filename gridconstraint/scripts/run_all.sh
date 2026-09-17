#!/usr/bin/env sh
# Full reproduction (~1.5 h on 4 cores). Each step is restartable.
set -e
cd "$(dirname "$0")/.."
python3 scripts/01_build_world.py            # simulated ISO world + public observables (~20 min)
python3 scripts/01b_finalize_names.py        # clean substation names, re-render name-bearing public files
python3 scripts/02_render_and_parse_studies.py   # PDFs -> parsed labels + extraction quality
python3 scripts/03_build_features.py queue   # point-in-time features as of queue date
python3 tests/test_vintage.py                # leakage guard
python3 tests/test_parser_fixtures.py
python3 scripts/04_run_benchmark.py queue    # baselines, main model, ablations, breakdowns, secondary tasks
python3 scripts/05_case_studies.py queue     # prospective case studies
python3 scripts/06_build_ui.py               # static prototype interface -> docs/index.html
