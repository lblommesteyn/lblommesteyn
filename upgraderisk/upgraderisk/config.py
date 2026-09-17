from __future__ import annotations
import os
from pathlib import Path

ROOT = Path(os.environ.get("UR_ROOT", Path(__file__).resolve().parents[1]))
DATA = ROOT / "data"
RAW = DATA / "raw"
PROCESSED = DATA / "processed"
OUTPUTS = ROOT / "outputs"
TABLES = OUTPUTS / "tables"
FIGURES = OUTPUTS / "figures"
CASES = OUTPUTS / "cases"
for p in (PROCESSED, TABLES, FIGURES, CASES):
    p.mkdir(parents=True, exist_ok=True)

SEED = 20260917
DELAY_MONTHS = 12          # P(delay > 12 months)
OVERRUN_FRAC = 0.25        # P(cost increase > 25 %)
MIN_RESOLVED_FOR_MODELING = 200

# canonical long-table columns (one row per upgrade x observation date)
SNAP_COLS = ["upgrade_id", "snapshot_date", "source", "to", "facility", "voltage_kv", "upgrade_type", "scope",
             "est_cost_musd", "expected_isd", "status", "actual_isd", "cancelled"]
