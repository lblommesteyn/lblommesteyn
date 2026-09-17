"""Real-data fetchers for the PJM pipeline (NOT runnable from the build sandbox: pjm.com,
dataminer2.pjm.com, emp.lbl.gov and hifld-geoplatform.opendata.arcgis.com were all blocked
by the egress policy; every request returned a proxy 403). They are written so that the
same downstream code (parser, normaliser, PIT features, models) runs unchanged once the
files are present in data/raw_real/.

Sources and what each one feeds
--------------------------------
1. PJM New Services Queue (XLS/XML export, weekly)            -> public/queue.csv, queue_events.csv
   https://www.pjm.com/planning/service-requests/interconnection-queues  (export: "PlanningQueues.xls")
   Columns used: Queue Number, Project Name, Commercial Name, State, County, Transmission Owner,
   Fuel, MFO (MW), MW Energy, MW Capacity, Submitted Date, Status, Withdrawal Date, In Service Date,
   Point of Interconnection (POI string, e.g. "Keystone 500 kV"), Feasibility/System Impact/Facilities
   study links. Weekly snapshots (or the Wayback Machine) give status *history*; a single current
   export must be treated as vintage-leaky for status features and is used only for labels.
2. Study reports (PDF)                                          -> studies/pdf/, study_index.csv
   https://www.pjm.com/pub/planning/project-queues/{feas_docs,impact_studies,facilities_studies}/<queue>_{fea,imp,fac}.pdf
   Publication date = PDF creation date (or the "Last Modified" header), cross-checked with the
   report's title-page date. extract/pdf_parser.py is written against these reports' phrasing.
3. PJM Data Miner 2 (free API key)                              -> market_lmp.parquet, market_constraints.csv
   feeds: da_hrl_lmps / rt_hrl_lmps (pnode LMP with congestion component), da_transconstraints /
   rt_transn_constraints (constraint name, shadow price), transmission_limits.
   Constraint names are TO-style strings ("KEYSTONE - JUNIATA 500 KV") -> extract/normalize.py.
4. PJM planned/actual transmission outages (eDART public posting / Data Miner "outages")  -> outages.csv
5. HIFLD Electric Substations + Transmission Lines (public domain) -> public/substations.csv, facilities.csv
   Line geometry + voltage; parallel circuits not distinguished; used by features/topology.py
   to build the guessed-impedance DC model.
6. EIA-860 generators + PJM zonal load (Data Miner hrl_load_metered)   -> generators.csv, load_zonal_annual.csv
7. RTEP baseline upgrade lists (TEAC materials) -> baseline_upgrades.csv (optional).

Point-in-time discipline for real data
--------------------------------------
* Queue status must come from dated snapshots; never from the latest export.
* A study is usable as a feature only after its posting date; PJM re-posts revised reports under
  the same URL, so keep the first-seen copy (hash) and its first-seen date.
* LMP / constraint rows are usable after their operating hour; outages after their posting date.
"""
from __future__ import annotations
import hashlib
import os
import time
from pathlib import Path

import requests

RAW_REAL = Path(__file__).resolve().parents[2] / "data" / "raw_real"
PJM_QUEUE_XLS = "https://www.pjm.com/pub/planning/project-queues/PlanningQueues.xls"
PJM_STUDY_URL = "https://www.pjm.com/pub/planning/project-queues/{folder}/{queue}_{suffix}.pdf"
STUDY_FOLDERS = {"feasibility": ("feas_docs", "fea"), "impact": ("impact_studies", "imp"), "facilities": ("facilities_studies", "fac")}
DATAMINER = "https://api.pjm.com/api/v1/{feed}"


def _get(url: str, dest: Path, headers: dict | None = None, retries: int = 3) -> Path | None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    for i in range(retries):
        try:
            r = requests.get(url, headers=headers, timeout=60)
            if r.status_code == 200:
                dest.write_bytes(r.content)
                meta = dest.with_suffix(dest.suffix + ".meta")
                meta.write_text(f"url={url}\nfetched={time.strftime('%Y-%m-%dT%H:%M:%S')}\nsha256={hashlib.sha256(r.content).hexdigest()}\n"
                                f"last_modified={r.headers.get('Last-Modified', '')}\n")
                return dest
            if r.status_code in (403, 404):
                return None
        except requests.RequestException:
            time.sleep(2 ** i)
    return None


def fetch_queue_export(dest: Path = RAW_REAL / "pjm" / "PlanningQueues.xls") -> Path | None:
    return _get(PJM_QUEUE_XLS, dest)


def fetch_study(queue_number: str, kind: str = "impact", dest_dir: Path = RAW_REAL / "pjm" / "studies") -> Path | None:
    """queue_number like 'AE2-281' -> file ae2281_imp.pdf (PJM strips the dash and lower-cases)."""
    folder, suffix = STUDY_FOLDERS[kind]
    q = queue_number.replace("-", "").lower()
    return _get(PJM_STUDY_URL.format(folder=folder, queue=q, suffix=suffix), dest_dir / f"{q}_{suffix}.pdf")


def fetch_dataminer(feed: str, params: dict, dest: Path, api_key: str | None = None) -> Path | None:
    key = api_key or os.environ.get("PJM_API_KEY")
    if not key:
        raise RuntimeError("PJM_API_KEY required (free at apiportal.pjm.com)")
    url = DATAMINER.format(feed=feed) + "?" + "&".join(f"{k}={v}" for k, v in params.items())
    return _get(url, dest, headers={"Ocp-Apim-Subscription-Key": key, "Accept": "text/csv"})


def fetch_all(queue_numbers: list[str]) -> dict:
    """One-shot fetch of everything needed for the real-data run. Returns a status dict."""
    status = {"queue": fetch_queue_export() is not None, "studies": 0, "missing": []}
    for qn in queue_numbers:
        ok = False
        for kind in ("impact", "feasibility", "facilities"):
            if fetch_study(qn, kind) is not None:
                ok = True
        status["studies"] += ok
        if not ok:
            status["missing"].append(qn)
    return status
