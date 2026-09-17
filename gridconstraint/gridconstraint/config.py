from __future__ import annotations
import os
from pathlib import Path

ROOT = Path(os.environ.get("GC_ROOT", Path(__file__).resolve().parents[1]))
DATA = ROOT / "data"
RAW = DATA / "raw_public"          # real public inputs mirrored from GitHub (see data/sources.py)
WORLD = DATA / "world"             # hidden "ISO planning case" world state + ground truth (never read by models)
PUBLIC = DATA / "public"           # what a market participant could observe (point-in-time)
STUDIES = DATA / "studies"         # rendered study reports (PDF) + parsed labels
PROCESSED = DATA / "processed"     # feature tables etc.
OUTPUTS = ROOT / "outputs"
TABLES = OUTPUTS / "tables"
FIGURES = OUTPUTS / "figures"
CASES = OUTPUTS / "case_studies"

for _p in (WORLD, PUBLIC, STUDIES, PROCESSED, TABLES, FIGURES, CASES):
    _p.mkdir(parents=True, exist_ok=True)

SEED = 20260917

# --- Simulated ISO ("hidden planning case") settings -------------------------------
SIM_START_YEAR = 2011
SIM_END_YEAR = 2025
MONITORED_MIN_KV = 100.0      # PJM monitors >= 100 kV facilities in GI studies
CONTINGENCY_MIN_KV = 100.0
DFAX_THRESHOLD = 0.05         # PJM: project must have >= 5% distribution factor on the overloaded facility
LOADING_THRESHOLD = 1.00      # overload when post-contingency loading > 100% of rating
STUDY_LAG_MONTHS = (10, 26)   # queue date -> study publication lag (uniform, months)
PENALTY_PRICE = 2000.0        # $/MWh transmission constraint penalty in the market model (PJM uses $2000)

# --- Modelling settings ------------------------------------------------------------
CANDIDATE_RADIUS_KM = 90.0
CANDIDATE_MAX_HOPS = 6
CANDIDATE_CAP = 800
CANDIDATE_MIN_APX_DFAX = 0.015   # public-topology N-1 distribution factor rule for far-field candidates
TRAIN_END = "2020-12-31"      # studies published up to here -> train
VALID_END = "2022-06-30"      # -> validation (calibration + early stopping)
# everything after VALID_END -> test
