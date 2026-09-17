"""Turn the fetched PJM inputs into the pipeline's public tables (data/public_real/).

queue.csv / queue_events.csv  from the dated queue export (Submitted / Withdrawal / Actual In Service)
substations.csv / facilities.csv  from HIFLD (built by hifld_topology.py)
study_index.csv + parsed findings  from the fetched impact studies (publication = Last-Modified header)
POI resolution: the queue 'Name' field is the point of interconnection ("Ontelaunee 230 kV",
"Jacksonville-Renaker 138kV") -> HIFLD substation by fuzzy name (+ kV hint); PDF title block as fallback.
"""
from __future__ import annotations
import glob, json, re
from pathlib import Path
import numpy as np
import pandas as pd
from .. import config as C
from ..extract.normalize import FacilityNormalizer
from ..extract.pjm_real import parse_real_report, name_pair, bus_name_dictionary
from ..extract.pjm_bus_names import BusNameMatcher, split_desc

RAW = C.ROOT / "data" / "raw_real" / "pjm"
P = C.ROOT / "data" / "public_real"

FUEL = [("solar", "solar"), ("storage", "storage"), ("battery", "storage"), ("wind", "wind"), ("gas", "gas"), ("methane", "gas"), ("nuclear", "other"),
        ("hydro", "other"), ("coal", "other"), ("oil", "other"), ("diesel", "other"), ("biomass", "other"), ("load", "load")]


def _fuel(s: str) -> str:
    s = str(s).lower()
    hits = [v for k, v in FUEL if k in s]
    if len(set(hits)) > 1 and "storage" in hits:
        return "hybrid"
    return hits[0] if hits else "other"


def build_queue(subs: pd.DataFrame, fac: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    src = sorted(glob.glob(str(RAW / "queue_snapshots" / "*.csv")))[-1]
    snap_date = pd.Timestamp(re.search(r"(\d{4}-\d{2}-\d{2})", Path(src).name).group(1))
    q = pd.read_csv(src, low_memory=False)
    N = FacilityNormalizer(subs, fac)
    poi_ids, poi_kv, poi_conf = [], [], []
    cache = {}
    for name in q["Name"].fillna("").astype(str):
        if name in cache:
            sid, kv, sc = cache[name]
        else:
            kvm = re.search(r"(\d{2,3}(?:\.\d)?)\s*kV", name, re.I)
            kv = float(kvm.group(1)) if kvm else np.nan
            base = re.sub(r"\s*\d{2,3}(?:\.\d)?\s*kV.*$", "", name, flags=re.I)
            first = re.split(r"\s*[-–/]\s*", base)[0].strip()
            c = N.match_sub(first, kv_hint=kv if kv == kv else None) if len(first) >= 3 else []
            sid, sc = (c[0][0], c[0][1]) if c else (None, 0.0)
            cache[name] = (sid, kv, sc)
        poi_ids.append(sid); poi_kv.append(kv); poi_conf.append(sc)
    queue = pd.DataFrame(dict(project_id=q["Project ID"].astype(str).str.strip(), queue_date=pd.to_datetime(q["Submitted Date"], errors="coerce"),
                              poi_name=q["Name"].fillna("").astype(str), poi_sub_id=poi_ids, poi_kv=poi_kv, poi_match_score=poi_conf,
                              mw=pd.to_numeric(q["MFO"], errors="coerce"), fuel=q["Fuel"].fillna("").map(_fuel), state=q["State"], transmission_owner=q["Transmission Owner"],
                              status_now=q["Status"]))
    queue["project_type"] = np.where(queue.fuel == "storage", "battery", np.where(queue.fuel == "load", "gen", "gen"))
    queue["poi_kv"] = queue.poi_kv.fillna(138.0)
    queue = queue[queue.queue_date.notna()].reset_index(drop=True)
    ev = [pd.DataFrame(dict(project_id=queue.project_id, date=queue.queue_date, status="queued"))]
    for col, st in (("Withdrawal Date", "withdrawn"), ("Actual In Service Date", "in_service")):
        d = pd.to_datetime(q[col], errors="coerce")
        e = pd.DataFrame(dict(project_id=q["Project ID"].astype(str).str.strip(), date=d, status=st)).dropna(subset=["date"])
        ev.append(e[e.project_id.isin(queue.project_id)])
    events = pd.concat(ev, ignore_index=True).sort_values(["date", "project_id"])
    # a status that the export shows today but that is not dated cannot be placed in time: ignored (documented)
    return queue, events


def build_studies(queue: pd.DataFrame, subs: pd.DataFrame, fac: pd.DataFrame, include_energy: bool = False):
    """Parse the fetched reports; resolve facilities to HIFLD corridors near the POI."""
    M = BusNameMatcher(subs)
    N = FacilityNormalizer(subs, fac)
    qmap = queue.set_index("project_id")
    fids_public = set(fac.fid)
    parsed = []
    for f in sorted(glob.glob(str(RAW / "studies" / "*_imp.pdf"))):
        meta_file = Path(f).with_suffix(".pdf.meta")
        meta = dict(l.split("=", 1) for l in meta_file.read_text().splitlines() if "=" in l) if meta_file.exists() else {}
        cache = C.PROCESSED / "real_text" / (Path(f).name + ".json")
        text = json.load(open(cache))["text"] if cache.exists() else None
        if text is None:
            from ..extract.pdf_parser import extract_text_and_tables
            text, _ = extract_text_and_tables(f)
        m, findings = parse_real_report(text)
        pid = m.get("project_id") or Path(f).name.split("_")[0].upper()
        if pid not in qmap.index:
            alt = [p for p in qmap.index if p.replace("-", "").lower() == Path(f).name.split("_")[0].lower()]
            if not alt:
                continue
            pid = alt[0]
        lm = pd.to_datetime(meta.get("last_modified", ""), errors="coerce", utc=True)
        pub = (lm.tz_convert(None) if pd.notna(lm) else pd.Timestamp(meta.get("fetched", "2026-09-17")[:10])).normalize()
        parsed.append(dict(pid=pid, pub=pub, meta=m, findings=findings, path=f))
    allf = [x for p in parsed for x in p["findings"]]
    D = bus_name_dictionary(allf)
    rows, index = [], []
    for p in parsed:
        pid = p["pid"]; qrow = qmap.loc[pid]
        poi = qrow.poi_sub_id
        if pd.isna(poi) and p["meta"].get("poi_str"):
            c = N.match_sub(re.sub(r"\s*\d{2,3}\s*kV.*$", "", p["meta"]["poi_str"], flags=re.I))
            poi = c[0][0] if c and c[0][1] >= 80 else np.nan
        n_res = 0
        for x in p["findings"]:
            if x.section == "energy_congestion" and not include_energy:
                continue
            pr = name_pair(x.desc)
            if pr is None and x.from_bus in D and x.to_bus in D:
                pr = (D[x.from_bus], D[x.to_bus])
            fid = None; ma = mb = None
            if pr and pd.notna(poi):
                ma = (int(poi), 100.0, "POI") if pr[0].startswith("TAP:") else M.match(pr[0], anchor_sub=int(poi))
                mb = (int(poi), 100.0, "POI") if pr[1].startswith("TAP:") else M.match(pr[1], anchor_sub=int(poi))
                if ma and mb and ma[0] != mb[0] and x.kv:
                    a, b = sorted((ma[0], mb[0])); fid = f"L:{a}:{b}:{int(round(x.kv))}"
                    if fid not in fids_public:      # try the corridor at the public layer's voltage class
                        alts = [g for g in fids_public if g.startswith(f"L:{a}:{b}:")]
                        fid = alts[0] if alts else fid
            n_res += fid is not None
            rows.append(dict(project_id=pid, publication_date=p["pub"], section=x.section, facility_str=x.desc, bus_from=x.from_bus, bus_to=x.to_bus,
                             ckt=x.ckt, name_pair=("|".join(pr) if pr else ""), fid=fid, fid_confidence=(min(ma[1], mb[1]) / 100 if (ma and mb) else 0.0),
                             in_public_layer=(fid in fids_public) if fid else False, loading_pct=x.loading_post, pre_loading_pct=x.loading_pre,
                             rating_mva=x.rating_mva, dfax_pct=np.nan, contrib_mw=x.contrib_mw, contingency_str=x.contingency))
        index.append(dict(project_id=pid, publication_date=p["pub"], pdf_path=p["path"], n_findings=len(p["findings"]), n_fid_resolved=n_res,
                          total_cost_usd=p["meta"].get("network_upgrade_cost_usd", p["meta"].get("total_cost_usd", np.nan)),
                          poi_sub_id=poi, poi_from_pdf=p["meta"].get("poi_str", "")))
    return pd.DataFrame(rows), pd.DataFrame(index)


def build_all(include_energy: bool = False):
    subs = pd.read_csv(P / "substations.csv"); fac = pd.read_csv(P / "facilities.csv")
    queue, events = build_queue(subs, fac)
    findings, index = build_studies(queue, subs, fac, include_energy=include_energy)
    # POI back-fill from PDFs into the queue table for studied projects
    fill = index.dropna(subset=["poi_sub_id"]).set_index("project_id").poi_sub_id
    queue.loc[queue.project_id.isin(fill.index) & queue.poi_sub_id.isna(), "poi_sub_id"] = queue.project_id.map(fill)
    queue.to_csv(P / "queue.csv", index=False); events.to_csv(P / "queue_events.csv", index=False)
    index[["project_id", "publication_date", "pdf_path"]].assign(study_type="system_impact").to_csv(P / "study_index.csv", index=False)
    findings.to_csv(C.STUDIES / "parsed_findings_real.csv", index=False)
    meta = index[["project_id", "publication_date", "n_findings", "n_fid_resolved", "total_cost_usd"]].copy()
    meta["xy_idx"] = np.nan
    meta.to_csv(C.STUDIES / "parsed_meta_real.csv", index=False)
    return queue, events, findings, index
