"""Parse PJM upgrade snapshots into the canonical long table (one row per upgrade x snapshot_date).

Sources
  legacy construct-status grid (Wayback captures 2010-2019, baseline tab): rows of 11 fields
    [id, required_date, to_projected_date, [location, task, equipment, description, kv, rating, last_updated],
     to, [study_year, baseline_report, report_file, driver, initial_teac, last_teac], "code:Status", state, pct_complete,
     cost_musd, [county, region]]
  legacy cost-allocation view (Wayback captures 2013-2019, all baseline upgrades): 6 or 7 fields
    [id, description, to, (status), "$cost", [alloc %...], required_date]
  live Project Status & Cost Allocation export (xlsx, 2025+): 31 columns incl. Actual In Service Date.
"""
from __future__ import annotations
import gzip, json, re
from pathlib import Path
import numpy as np
import pandas as pd
from .config import RAW, SNAP_COLS

SNAP_DIR = RAW / "pjm_snapshots"
STATUS_CODES = {"IS": "In Service", "UC": "Under Construction", "EP": "Engineering & Procurement", "PL": "Planning", "W": "Withdrawn",
                "UC-ISP": "Partially In Service - Under Construction", "ON-HOLD": "On Hold", "ACTIVE": "Active", "CANCELLED": "Cancelled",
                "C": "Cancelled", "OH": "On Hold", "AC": "Active"}


def parse_date(s):
    """PJM wrote dates as 05/31/2015, 5.31.2015 or 2015-05-31; anything else -> NaT."""
    if s is None or (isinstance(s, float) and np.isnan(s)):
        return pd.NaT
    s = str(s).strip()
    if not s or s.lower() in ("nan", "none", "tbd", "n/a"):
        return pd.NaT
    s = s.replace(".", "/")
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y", "%Y-%m-%d %H:%M:%S"):
        try:
            d = pd.to_datetime(s, format=fmt)
            if 1990 <= d.year <= 2100:
                return d
            return pd.NaT
        except Exception:
            continue
    d = pd.to_datetime(s, errors="coerce")
    return d if (pd.notna(d) and 1990 <= d.year <= 2100) else pd.NaT


def parse_cost(s):
    if s is None:
        return np.nan
    t = str(s).replace("$", "").replace(",", "").strip()
    try:
        return float(t)
    except Exception:
        return np.nan


def parse_pct(s):
    v = parse_cost(s)
    if np.isnan(v):
        return v
    if v > 100 and v % 100 == 0:
        v = v / 100.0
    return float(np.clip(v, 0, 100))


def parse_kv(s):
    m = re.search(r"\d+(?:\.\d+)?", str(s or ""))
    return float(m.group(0)) if m else np.nan


def norm_status(s) -> str:
    s = str(s or "").strip()
    if ":" in s:
        code, title = s.split(":", 1)
        s = title.strip() or code.strip()
    return STATUS_CODES.get(s.upper(), s)


def upgrade_type(uid: str) -> str:
    c = str(uid)[:1].lower()
    return {"b": "Baseline", "n": "Network", "s": "Supplemental", "t": "Transmission Owner"}.get(c, "Other")


def legacy_construct_rows(rows, snapshot_date, source) -> pd.DataFrame:
    out = []
    for r in rows:
        if not (isinstance(r, list) and len(r) >= 11):
            continue
        desc = r[3] if isinstance(r[3], list) else [""] * 7
        drv = r[5] if isinstance(r[5], list) else [""] * 6
        loc = r[10] if isinstance(r[10], list) else ["", ""]
        st = norm_status(r[6])
        out.append(dict(upgrade_id=str(r[0]).strip(), snapshot_date=snapshot_date, source=source, to=str(r[4]).strip(),
                        facility=str(desc[0]).strip(), voltage_kv=parse_kv(desc[4] if len(desc) > 4 else ""),
                        upgrade_type=upgrade_type(r[0]), scope=str(desc[3]).strip(), est_cost_musd=parse_cost(r[9]),
                        expected_isd=parse_date(r[2]), status=st, actual_isd=pd.NaT, cancelled=st.lower() in ("cancelled", "withdrawn"),
                        required_date=parse_date(r[1]), pct_complete=parse_pct(r[8]), state=str(r[7]).strip(),
                        task=str(desc[1]).strip(), equipment=str(desc[2]).strip(), rating=str(desc[5]).strip() if len(desc) > 5 else "",
                        last_updated=parse_date(desc[6]) if len(desc) > 6 else pd.NaT, study_year=str(drv[0]).strip(),
                        driver=str(drv[3]).strip() if len(drv) > 3 else "", initial_teac=parse_date(drv[4]) if len(drv) > 4 else pd.NaT,
                        last_teac=parse_date(drv[5]) if len(drv) > 5 else pd.NaT, region=str(loc[1]).strip() if len(loc) > 1 else ""))
    return pd.DataFrame(out)


def legacy_costalloc_rows(rows, snapshot_date, source) -> pd.DataFrame:
    out = []
    for r in rows:
        if not (isinstance(r, list) and len(r) in (6, 7)):
            continue
        has_status = len(r) == 7
        st = norm_status(r[3]) if has_status else ""
        cost = r[4] if has_status else r[3]
        req = r[6] if has_status else r[5]
        out.append(dict(upgrade_id=str(r[0]).strip(), snapshot_date=snapshot_date, source=source, to=str(r[2]).strip(), facility="",
                        voltage_kv=parse_kv(re.search(r"(\d+)\s*kV", str(r[1])).group(1) if re.search(r"(\d+)\s*kV", str(r[1])) else ""),
                        upgrade_type=upgrade_type(r[0]), scope=str(r[1]).strip(), est_cost_musd=parse_cost(cost), expected_isd=pd.NaT,
                        status=st, actual_isd=pd.NaT, cancelled=st.lower() in ("cancelled", "withdrawn"), required_date=parse_date(req)))
    return pd.DataFrame(out)


def live_export_rows(path: Path, snapshot_date) -> pd.DataFrame:
    d = pd.read_excel(path, sheet_name="Data")
    col = {c.strip().lower(): c for c in d.columns}
    g = lambda name: d[col[name.lower()]] if name.lower() in col else pd.Series([None] * len(d))
    st = g("Status").map(norm_status)
    out = pd.DataFrame(dict(
        upgrade_id=g("Upgrade Id").astype(str).str.strip(), snapshot_date=pd.Timestamp(snapshot_date), source=f"live_export:{path.name}",
        to=g("Transmission Owner").astype(str).str.strip(), facility=g("Location").fillna("").astype(str).str.strip(),
        voltage_kv=g("Voltage").map(parse_kv), upgrade_type=g("Project Type").fillna("").astype(str).str.strip(),
        scope=g("Description").fillna("").astype(str).str.strip(), est_cost_musd=pd.to_numeric(g("Cost Estimate"), errors="coerce"),
        expected_isd=g("Projected In Service Date").map(parse_date), status=st, actual_isd=g("Actual In Service Date").map(parse_date),
        cancelled=st.str.lower().isin(["cancelled", "withdrawn"]), required_date=g("Required Date").map(parse_date),
        pct_complete=g("Percent Complete").map(parse_pct), state=g("State").fillna("").astype(str),
        task=g("Task").fillna("").astype(str), equipment=g("Equipment").fillna("").astype(str), driver=g("Driver").fillna("").astype(str),
        initial_teac=g("Initial TEAC Date").map(parse_date), last_teac=g("Latest TEAC Date").map(parse_date),
        teac_cost_musd=pd.to_numeric(g("TEAC Cost"), errors="coerce"), board_approval=g("PJM Board Approval Date").map(parse_date),
        revised_isd=g("Revised In-Service Date").map(parse_date), isa_isd=g("ISA In-Service Date").map(parse_date),
        last_updated=g("Last Updated").map(parse_date), region=g("Region").fillna("").astype(str), immediate_need=g("Immediate Need").fillna("").astype(str)))
    return out


def load_legacy_file(fn: Path) -> pd.DataFrame:
    with gzip.open(fn, "rt") as f:
        payload = json.load(f)
    ts = pd.Timestamp(payload["timestamp"][:8])
    parts = []
    for t in payload.get("tables", []):
        if not t:
            continue
        width = len(t[0])
        if payload["label"].endswith("construct_status") and width >= 11:
            parts.append(legacy_construct_rows(t, ts, f"wayback:{payload['label']}:{payload['timestamp']}"))
        elif payload["label"] == "cost_allocation_view" and width in (6, 7):
            parts.append(legacy_costalloc_rows(t, ts, f"wayback:{payload['label']}:{payload['timestamp']}"))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def build_long(snap_dir: Path = SNAP_DIR) -> pd.DataFrame:
    parts = []
    for fn in sorted((snap_dir / "legacy").glob("*.json.gz")):
        d = load_legacy_file(fn)
        if len(d):
            parts.append(d)
    for fn in sorted((snap_dir / "live").glob("export_*.xlsx")):
        m = re.search(r"(\d{4}-\d{2}-\d{2})", fn.name)
        parts.append(live_export_rows(fn, m.group(1)))
    long = pd.concat(parts, ignore_index=True)
    long["snapshot_date"] = pd.to_datetime(long["snapshot_date"])
    # one row per (upgrade, snapshot_date, source family); keep the richer construct-status row when both exist on a day
    long["src_family"] = long["source"].str.split(":").str[0] + ":" + long["source"].str.split(":").str[1]
    long = long.sort_values(["upgrade_id", "snapshot_date", "src_family"]).reset_index(drop=True)
    for c in SNAP_COLS:
        if c not in long:
            long[c] = np.nan
    return long
