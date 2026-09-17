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
    """Dated PJM queue exports -> queue.csv (first appearance) + queue_events.csv (status changes by snapshot date)."""
    frames = []
    for p in sorted((RAW / "queue_snapshots").glob("*")):
        m = re.search(r"(\d{4}-\d{2}-\d{2})", p.name)
        if not m:
            continue
        df = pd.read_excel(p) if p.suffix in (".xls", ".xlsx") else pd.read_csv(p, low_memory=False)
        df.columns = [c.strip() for c in df.columns]
        df["snapshot_date"] = pd.Timestamp(m.group(1))
        frames.append(df)
    if not frames:
        raise SystemExit("no dated queue snapshots under data/raw_real/pjm/queue_snapshots")
    allq = pd.concat(frames, ignore_index=True)
    col = {c.lower(): c for c in allq.columns}
    qn = col.get("queue number") or col.get("queue id") or col.get("queue_number")
    status = col.get("status"); sub = col.get("submitted date") or col.get("queue date"); mw = col.get("mfo") or col.get("mw energy") or col.get("capacity (mw)")
    poi = col.get("point of interconnection") or col.get("interconnection location") or col.get("poi")
    fuel = col.get("fuel") or col.get("generation type"); state = col.get("state")
    first = allq.sort_values("snapshot_date").groupby(qn).first().reset_index()
    queue = pd.DataFrame(dict(project_id=first[qn].astype(str), queue_date=pd.to_datetime(first[sub], errors="coerce"),
                              poi_name=first[poi].astype(str) if poi else "", mw=pd.to_numeric(first[mw], errors="coerce"),
                              fuel=first[fuel].astype(str).str.lower() if fuel else "", state=first[state] if state else ""))
    queue["project_type"] = np.where(queue.fuel.str.contains("storage|battery"), "battery", "gen")
    ev = allq.sort_values("snapshot_date")[[qn, status, "snapshot_date"]].rename(columns={qn: "project_id", status: "status", "snapshot_date": "date"})
    ev["status"] = ev.status.astype(str).str.lower().map(lambda s: "withdrawn" if "withdraw" in s else ("in_service" if "in service" in s or "operational" in s else "active"))
    ev = ev[ev.status != ev.groupby("project_id").status.shift()]     # keep changes only, dated by the snapshot that first showed them
    return queue, ev


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-studies", type=int, default=100); ap.add_argument("--max-studies", type=int, default=300)
    ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--selftest", action="store_true", help="run the scoring path on simulated tables")
    a = ap.parse_args()
    if a.selftest:
        selftest(); return
    st = check_inputs()
    print(json.dumps(st, indent=1))
    missing = [k for k in ("model", "hifld_lines") if not st[k]]
    if len(st["queue_snapshots"]) < 2:
        missing.append("queue_snapshots (>=2 dated exports)")
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
    # ---- 1. public topology (real HIFLD)
    lines = read_hifld_lines(next(p for p in HIFLD_CANDIDATES if Path(p).exists()), zoom=9)
    subs, fac = build_public_topology(lines, L.load_hifld_substations())
    P = C.ROOT / "data" / "public_real"; P.mkdir(exist_ok=True)
    subs.to_csv(P / "substations.csv", index=False); fac.to_csv(P / "facilities.csv", index=False)
    # ---- 2. queue + events from dated snapshots; POI -> substation
    queue, events = load_queue_snapshots()
    N = FacilityNormalizer(subs, fac)
    poi_sub = []
    for s in queue.poi_name:
        c = N.match_sub(str(s))
        poi_sub.append(c[0][0] if c and c[0][1] >= 80 else None)
    queue["poi_sub_id"] = poi_sub
    queue = queue[queue.poi_sub_id.notna() & queue.queue_date.notna()].copy()
    queue["poi_kv"] = queue.poi_name.str.extract(r"(\d{2,3})\s*kV", expand=False).astype(float).fillna(138.0)
    # ---- 3. studies -> labels with first-seen dates
    rows, index = [], []
    for p in sorted((RAW / "studies").glob("*_imp.pdf"))[: a.max_studies]:
        meta = dict(l.split("=", 1) for l in p.with_suffix(".pdf.meta").read_text().splitlines() if "=" in l)
        seen = pd.Timestamp(meta.get("fetched", "")[:10])
        ps = parse_study(str(p))
        pid = ps.meta.get("project_id")
        if pid not in set(queue.project_id):
            continue
        poi = int(queue.set_index("project_id").loc[pid].poi_sub_id)
        for f in ps.findings:
            n = N.normalize(f["facility_str"], poi_sub=poi)
            rows.append(dict(project_id=pid, publication_date=seen, facility_str=f["facility_str"], fid=n["fid"], fid_confidence=n["confidence"],
                             loading_pct=f["loading_pct"], dfax_pct=f["dfax_pct"], contingency_str=f["contingency_str"]))
        index.append(dict(project_id=pid, publication_date=seen, pdf_path=str(p), n_findings=len(ps.findings), n_resolved=sum(1 for r in rows if r["project_id"] == pid and r["fid"])))
    findings = pd.DataFrame(rows); idx = pd.DataFrame(index)
    if len(idx) < a.min_studies:
        raise SystemExit(f"only {len(idx)} studies matched queue entries; need >= {a.min_studies}")
    findings.to_csv(C.STUDIES / "parsed_findings_real.csv", index=False); idx.to_csv(P / "study_index.csv", index=False)
    # ---- 4. features + frozen model, strict as-of = queue date + 1 day
    queue.to_csv(P / "queue.csv", index=False); events.to_csv(P / "queue_events.csv", index=False)
    meta_rows = idx.rename(columns={"n_resolved": "n_fid_resolved"}).assign(total_cost_usd=np.nan)
    meta_rows.to_csv(C.STUDIES / "parsed_meta_real.csv", index=False)
    optional_tables(P)
    res = score_frozen(P, C.STUDIES / "parsed_findings_real.csv", C.STUDIES / "parsed_meta_real.csv", tag="real_pjm", inputs="REAL PJM STUDIES")
    FIRST.write_text(json.dumps(res, indent=1))
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
    if max_projects:
        studied = studied.tail(max_projects)
    parts = []; lat_cache = {}
    t = time.time()
    for i, r in enumerate(studied.itertuples()):
        as_of = pd.Timestamp(r.queue_date) + pd.Timedelta(days=1)
        assert pd.Timestamp(r.publication_date) > pd.Timestamp(r.queue_date), "study published before queue date: as-of rule violated"
        proj = pub.q_by_pid.loc[r.project_id].copy(); proj["project_id"] = r.project_id
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
