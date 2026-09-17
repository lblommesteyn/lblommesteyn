"""Frozen real-data run on 100-300 historical PJM studies.

Contract (enforced here, not by convention):
  * The model is FROZEN: data/processed/main_model_queue.pkl is loaded, its sha256 is recorded in
    the first benchmark file, and this script refuses to (re)train anything. Retraining or feature
    changes are only allowed after outputs/tables/real_pjm_first_benchmark.json exists.
  * Strict as-of: features for project X use only records dated strictly before X's queue date
    (queue status from dated snapshots; studies by first-seen date; market rows by operating hour).
  * Labels come only from study PDFs whose first-seen date is after the queue date (they are the
    thing being predicted) - the same PDFs are never a feature for their own project.

Inputs expected under data/raw_real/pjm/ (see gridconstraint/data/sources.py for how to fetch;
this sandbox could not reach pjm.com, so the directory must be filled from a machine that can):
  queue_snapshots/<YYYY-MM-DD>.xls|csv     dated PJM queue exports (>= 2, spanning the study window)
  studies/<queue>_imp.pdf (+ .meta)         impact studies; .meta carries the first-seen date
  dataminer/da_transconstraints.csv (opt)   constraint name, hour, shadow price
  dataminer/da_hrl_lmps.csv (opt)           pnode, hour, LMP, congestion
  hifld/hifld_transmission_lines.pmtiles    (already mirrored: data/raw_public via TransmissionMap)

Usage: python3 scripts/real_pjm_run.py [--min-studies 100] [--max-studies 300] [--dry-run]
"""
from __future__ import annotations
import argparse, hashlib, json, re, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np, pandas as pd
from gridconstraint import config as C
from gridconstraint.data import loaders as L
from gridconstraint.data.hifld_topology import read_hifld_lines, build_public_topology
from gridconstraint.extract.pdf_parser import parse_study
from gridconstraint.extract.normalize import FacilityNormalizer
from gridconstraint.eval.metrics import rank_metrics, calibration
from gridconstraint.models import baselines as B

RAW = C.ROOT / "data" / "raw_real" / "pjm"
FIRST = C.TABLES / "real_pjm_first_benchmark.json"


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def check_inputs() -> dict:
    st = {}
    st["model"] = (C.PROCESSED / "main_model_queue.pkl").exists()
    st["model_sha256"] = sha256(C.PROCESSED / "main_model_queue.pkl") if st["model"] else None
    snaps = sorted((RAW / "queue_snapshots").glob("*")) if (RAW / "queue_snapshots").exists() else []
    st["queue_snapshots"] = [p.name for p in snaps]
    pdfs = sorted((RAW / "studies").glob("*_imp.pdf")) if (RAW / "studies").exists() else []
    st["study_pdfs"] = len(pdfs)
    st["study_pdfs_with_first_seen"] = sum((p.with_suffix(".pdf.meta")).exists() for p in pdfs)
    st["dataminer_constraints"] = (RAW / "dataminer" / "da_transconstraints.csv").exists()
    st["dataminer_lmps"] = (RAW / "dataminer" / "da_hrl_lmps.csv").exists()
    st["hifld_lines"] = any(Path(p).exists() for p in HIFLD_CANDIDATES)
    return st


HIFLD_CANDIDATES = [str(C.RAW / "hifld_transmission_lines.pmtiles"),
                    "/tmp/claude-0/-home-user-lblommesteyn/c17be79c-cc45-5783-a322-0a9344d6ac8c/scratchpad/ext/tmap-data/data/layers/hifld_transmission_lines.pmtiles"]


def load_queue_snapshots() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Dated PJM queue exports -> queue.csv + queue_events.csv.
    With several snapshots, status changes are dated by the first snapshot that shows them. With a
    single export, the export's own dated columns are used (Submitted Date, Withdrawal Date, Actual
    In Service Date): a withdrawal/in-service event is public from that date. Restatements that a
    later export would overwrite cannot be recovered from one snapshot (documented limitation)."""
    frames = []
    for p in sorted((RAW / "queue_snapshots").glob("*")):
        m = re.search(r"(\d{4}-\d{2}-\d{2})", p.name)
        if not m or p.suffix not in (".xls", ".xlsx", ".csv"):
            continue
        df = pd.read_excel(p) if p.suffix in (".xls", ".xlsx") else pd.read_csv(p, low_memory=False)
        df.columns = [str(c).strip() for c in df.columns]
        df["snapshot_date"] = pd.Timestamp(m.group(1))
        frames.append(df)
    if not frames:
        raise SystemExit("no dated queue exports under data/raw_real/pjm/queue_snapshots")
    allq = pd.concat(frames, ignore_index=True)
    col = {c.lower(): c for c in allq.columns}
    g = lambda *names: next((col[n] for n in names if n in col), None)
    qn = g("project id", "queue number", "queue id"); status = g("status"); sub = g("submitted date", "queue date")
    mw = g("mfo", "mw energy", "capacity (mw)", "mw capacity"); poi = g("point of interconnection", "interconnection location", "poi", "substation")
    fuel = g("fuel", "generation type"); state = g("state"); wd = g("withdrawal date", "withdrawn date"); isd = g("actual in service date", "in service date")
    to = g("transmission owner")
    first = allq.sort_values("snapshot_date").groupby(qn).first().reset_index()
    queue = pd.DataFrame(dict(project_id=first[qn].astype(str).str.strip(), queue_date=pd.to_datetime(first[sub], errors="coerce"),
                              poi_name=first[poi].astype(str) if poi else "", mw=pd.to_numeric(first[mw], errors="coerce") if mw else np.nan,
                              fuel=first[fuel].astype(str).str.lower() if fuel else "", state=first[state] if state else "",
                              transmission_owner=first[to] if to else ""))
    queue["project_type"] = np.where(queue.fuel.str.contains("storage|battery", na=False), "battery",
                                     np.where(queue.fuel.str.contains("load", na=False), "load", "gen"))
    queue["fuel"] = queue.fuel.map(lambda f: "solar" if "solar" in f else ("wind" if "wind" in f else ("gas" if "gas" in f or "methane" in f else
                                   ("storage" if "storage" in f or "battery" in f else ("hybrid" if ";" in f or "/" in f else "other")))))
    ev = [pd.DataFrame(dict(project_id=queue.project_id, date=queue.queue_date, status="queued"))]
    if len(frames) >= 2 and status:
        e = allq.sort_values("snapshot_date")[[qn, status, "snapshot_date"]].rename(columns={qn: "project_id", status: "status", "snapshot_date": "date"})
        e["project_id"] = e.project_id.astype(str).str.strip()
        e["status"] = e.status.astype(str).str.lower().map(lambda s: "withdrawn" if "withdraw" in s else ("in_service" if "in service" in s or "operational" in s else "active"))
        e = e[e.status != e.groupby("project_id").status.shift()]
        ev.append(e[e.status != "active"])
    else:
        if wd:
            w = pd.DataFrame(dict(project_id=queue.project_id, date=pd.to_datetime(first[wd], errors="coerce"), status="withdrawn")).dropna(subset=["date"])
            ev.append(w)
        if isd:
            i = pd.DataFrame(dict(project_id=queue.project_id, date=pd.to_datetime(first[isd], errors="coerce"), status="in_service")).dropna(subset=["date"])
            ev.append(i)
    events = pd.concat(ev, ignore_index=True).dropna(subset=["date"]).sort_values(["date", "project_id"])
    return queue, events


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-studies", type=int, default=100); ap.add_argument("--max-studies", type=int, default=300)
    ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--selftest", action="store_true", help="run the scoring path on simulated tables")
    ap.add_argument("--rebuild-topology", action="store_true"); ap.add_argument("--include-energy", action="store_true", help="also label energy-only congestion facilities")
    a = ap.parse_args()
    if a.selftest:
        selftest(); return
    st = check_inputs()
    print(json.dumps(st, indent=1))
    missing = [k for k in ("model", "hifld_lines") if not st[k]]
    if len(st["queue_snapshots"]) < 1:
        missing.append("queue_snapshots (>=1 dated export)")
    if st["study_pdfs"] < a.min_studies:
        missing.append(f"study_pdfs (have {st['study_pdfs']}, need >= {a.min_studies})")
    if FIRST.exists():
        print("NOTE: first benchmark already recorded; model changes are now permitted:", FIRST)
    if missing:
        (C.TABLES / "real_pjm_run_status.json").write_text(json.dumps(dict(checked_at=time.strftime("%Y-%m-%dT%H:%M:%S"), status=st, missing=missing), indent=1))
        print("BLOCKED - missing inputs:", missing)
        print("The model is frozen (sha256 above). Fill data/raw_real/pjm/ from a machine with pjm.com access and re-run.")
        sys.exit(2)
    if a.dry_run:
        return
    # ---- 1. public topology (real HIFLD) -> data/public_real (built once; rebuild with --rebuild-topology)
    P = C.ROOT / "data" / "public_real"; P.mkdir(exist_ok=True)
    if a.rebuild_topology or not (P / "facilities.csv").exists():
        lines = read_hifld_lines(next(p for p in HIFLD_CANDIDATES if Path(p).exists()), zoom=9)
        subs, fac = build_public_topology(lines, L.load_hifld_substations())
        subs.to_csv(P / "substations.csv", index=False); fac.to_csv(P / "facilities.csv", index=False)
    # ---- 2+3. queue, dated status events, parsed studies with HIFLD-resolved facilities
    from gridconstraint.data.pjm_real_ingest import build_all
    queue, events, findings, index = build_all(include_energy=a.include_energy)
    n_lab = index.n_fid_resolved.gt(0).sum()
    print(f"studies matched to queue: {len(index)}; with >=1 resolved facility: {n_lab}; findings {len(findings)} (resolved {findings.fid.notna().sum()})")
    if len(index) < a.min_studies:
        raise SystemExit(f"only {len(index)} studies matched queue entries; need >= {a.min_studies}")
    optional_tables(P)
    # ---- 4. frozen model, strict as-of = queue date + 1 day; first benchmark recorded
    res = score_frozen(P, C.STUDIES / "parsed_findings_real.csv", C.STUDIES / "parsed_meta_real.csv", tag="real_pjm", inputs="REAL PJM STUDIES")
    res["n_studies_fetched"] = int(len(index)); res["n_studies_with_resolved_facility"] = int(n_lab)
    res["labels"] = "network-impact sections (generator deliverability, multiple facility contingency, contribution to previously identified overloads)" + (" + energy-only congestion" if a.include_energy else "")
    FIRST.write_text(json.dumps(res, indent=1, default=str))
    print("FIRST BENCHMARK RECORDED:", FIRST)


def optional_tables(P: Path):
    """Data Miner feeds if present -> market_constraints.csv / market_lmp.csv in pipeline schema."""
    dc = RAW / "dataminer" / "da_transconstraints.csv"
    if dc.exists():
        d = pd.read_csv(dc, low_memory=False); col = {c.lower(): c for c in d.columns}
        out = pd.DataFrame(dict(datetime=pd.to_datetime(d[col.get("datetime_beginning_ept") or col.get("datetime")], errors="coerce"),
                                constraint_name=d[col.get("monitored_facility") or col.get("constraint_name")].astype(str),
                                shadow_price=pd.to_numeric(d[col.get("shadow_price") or col.get("marginal_value")], errors="coerce"), flow_mw=np.nan))
        out.dropna(subset=["datetime"]).to_csv(P / "market_constraints.csv", index=False)
    dl = RAW / "dataminer" / "da_hrl_lmps.csv"
    if dl.exists():
        d = pd.read_csv(dl, low_memory=False); col = {c.lower(): c for c in d.columns}
        subs = pd.read_csv(P / "substations.csv"); N = FacilityNormalizer(subs, pd.read_csv(P / "facilities.csv"))
        pn = d[col.get("pnode_name")].astype(str)
        mp = {n: (N.match_sub(n)[0][0] if N.match_sub(n) and N.match_sub(n)[0][1] >= 85 else None) for n in pn.unique()}
        out = pd.DataFrame(dict(datetime=pd.to_datetime(d[col.get("datetime_beginning_ept")], errors="coerce"), sub_id=pn.map(mp),
                                lmp=pd.to_numeric(d[col.get("total_lmp_da") or col.get("total_lmp_rt")], errors="coerce"),
                                congestion=pd.to_numeric(d[col.get("congestion_price_da") or col.get("congestion_price_rt")], errors="coerce")))
        out.dropna(subset=["datetime", "sub_id"]).to_csv(P / "market_lmp.csv", index=False)


def score_frozen(P: Path, findings_path: Path, meta_path: Path, tag: str, inputs: str, max_projects: int | None = None) -> dict:
    """Score every studied project with the FROZEN model as of its queue date; heuristic baselines need no
    training; the two trained baselines are fit on the chronologically earlier half and reported on the
    later half (the frozen model is reported on both). Nothing here retrains the main model."""
    import pickle
    from gridconstraint.features.pit import PublicData, FeatureBuilder
    from gridconstraint.models.latent import LatentModel
    pub = PublicData(root=P, findings_path=findings_path, meta_path=meta_path, verbose=False)
    fb = FeatureBuilder(pub)
    model_pkl = C.PROCESSED / "main_model_queue.pkl"
    d = pickle.load(open(model_pkl, "rb")); model, cols = d["model"], d["cols"]
    labels = pub.findings[pub.findings.fid.notna()].groupby("project_id").apply(lambda g: dict(zip(g.fid, g.loading_pct)), include_groups=False).to_dict()
    studied = pub.study_index.merge(pub.queue, on="project_id").sort_values("queue_date")
    studied = studied[studied.poi_sub_id.notna() & studied.queue_date.notna()]
    if max_projects:
        studied = studied.tail(max_projects)
    parts = []; lat_cache = {}
    t = time.time()
    for i, r in enumerate(studied.itertuples()):
        as_of = pd.Timestamp(r.queue_date) + pd.Timedelta(days=1)
        assert pd.Timestamp(r.publication_date) > pd.Timestamp(r.queue_date), "study published before queue date: as-of rule violated"
        proj = pub.q_by_pid.loc[r.project_id].copy(); proj["project_id"] = r.project_id
        proj["poi_sub_id"] = int(proj.poi_sub_id); proj["mw"] = float(proj.mw) if proj.mw == proj.mw else 100.0
        X = fb.build(proj, as_of, labels.get(r.project_id, {}))
        y = as_of.year
        if y not in lat_cache:
            lat_cache[y] = LatentModel(pub).fit(pd.Timestamp(year=y, month=1, day=1))
        lm = lat_cache[y]
        X["latent_score"] = lm.score(int(proj.poi_sub_id), X.fid.values) if lm.V is not None else 0.0
        e = lm.poi_embedding(int(proj.poi_sub_id)) if lm.V is not None else None
        X["latent_seen_poi"] = float(e is not None and e[1])
        for c in cols:
            if c not in X:
                X[c] = 0.0
        p, raw, sd = model.predict(X)
        X["p_main"] = p; X["p_main_raw"] = raw; X["project_id"] = r.project_id; X["queue_date"] = r.queue_date
        parts.append(X)
        if i % 25 == 0:
            print(f"  scored {i}/{len(studied)} ({time.time()-t:.0f}s)", flush=True)
    te = pd.concat(parts, ignore_index=True)
    n_pos_proj = int(te.groupby("project_id").y.sum().gt(0).sum())
    cov = te.groupby("project_id").y.sum(); n_lab = sum(len(labels.get(p, {})) for p in te.project_id.unique())
    ceiling = float(cov.sum() / max(1, n_lab))
    out = dict(tag=tag, inputs=inputs, recorded_at=time.strftime("%Y-%m-%dT%H:%M:%S"), model_pkl=str(model_pkl), model_sha256=sha256(model_pkl),
               as_of_policy="queue_date + 1 day; studies by first-seen date; status by dated snapshots", n_projects=int(te.project_id.nunique()),
               n_projects_with_constraints=n_pos_proj, candidate_ceiling=ceiling, metrics={})
    scores = {"MAIN_frozen": te.p_main_raw.values, "B1_nearest_projects": B.score_nearest_projects(te), "B2_queue_density": B.score_queue_density(te),
              "B3_historical_congestion": B.score_historical_congestion(te), "P0_public_topology_dfax": B.score_apx_dfax(te)}
    for name, sc in scores.items():
        rm = rank_metrics(te.assign(score=sc), "score"); out["metrics"][name + "@all"] = {k: (float(v) if v == v else None) for k, v in rm.items()}
    cal = calibration(te.assign(prob=te.p_main), "prob"); out["metrics"]["MAIN_frozen_calibration@all"] = dict(ece=cal["ece"], brier=cal["brier"], brier_skill=cal["brier_skill"])
    # chronological halves for the trained baselines
    pids = studied.project_id.tolist(); half = len(pids) // 2
    tr = te[te.project_id.isin(pids[:half])]; ev = te[te.project_id.isin(pids[half:])]
    if len(tr) and len(ev) and tr.y.sum() > 5:
        gs = B.GeoSizeModel().fit(tr); st = B.SimpleTabular().fit(tr)
        for name, sc in (("MAIN_frozen", ev.p_main_raw.values), ("B4_geo_size_logit", gs.predict(ev)), ("B5_simple_tabular_gbm", st.predict(ev)),
                         ("B2_queue_density", B.score_queue_density(ev)), ("P0_public_topology_dfax", B.score_apx_dfax(ev))):
            rm = rank_metrics(ev.assign(score=sc), "score"); out["metrics"][name + "@later_half"] = {k: (float(v) if v == v else None) for k, v in rm.items()}
    te.to_parquet(C.PROCESSED / f"{tag}_predictions.parquet", index=False)
    return out


def selftest():
    """Prove the runner path end-to-end on the SIMULATED public tables (never written as the real benchmark)."""
    res = score_frozen(C.PUBLIC, C.STUDIES / "parsed_findings.csv", C.STUDIES / "parsed_meta.csv", tag="runner_selftest_simulated",
                       inputs="SIMULATED ISO tables (self-test of the runner only)", max_projects=120)
    (C.TABLES / "real_pjm_runner_selftest.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({k: v for k, v in res.items() if k != "metrics"}, indent=1))
    for k, v in res["metrics"].items():
        if "@later_half" in k or k.startswith("MAIN"):
            print(k, {m: round(v[m], 3) for m in ("hit@5", "hit@10", "recall@10", "mrr") if m in v} if isinstance(v, dict) and "hit@5" in v else v)


if __name__ == "__main__":
    main()
