"""Render study PDFs from the hidden truth, parse them back with the public-side parser and
normaliser, and score extraction quality against the truth (the automated stand-in for
manual inspection; a small random sample is also dumped for eyeballing)."""
import sys, random
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
from gridconstraint import config as C
from gridconstraint.sim.report_writer import render_all
from gridconstraint.extract.pdf_parser import parse_study, extract_text_and_tables
from gridconstraint.extract.normalize import FacilityNormalizer

if __name__ == "__main__":
    if "--no-render" in sys.argv:
        idx = pd.read_csv(C.PUBLIC / "study_index.csv")
    else:
        idx = render_all()
        print("rendered", len(idx), idx.template.value_counts().to_dict())
    subs = pd.read_csv(C.PUBLIC / "substations.csv"); fac = pd.read_csv(C.PUBLIC / "facilities.csv")
    N = FacilityNormalizer(subs, fac)
    q = pd.read_csv(C.PUBLIC / "queue.csv").set_index("project_id")
    truth = pd.read_csv(C.WORLD / "study_rows.csv")
    tsum = pd.read_csv(C.WORLD / "study_summary.csv")
    rows, meta_rows, qual = [], [], []
    for r in idx.itertuples():
        ps = parse_study(str(C.ROOT / r.pdf_path))
        poi = int(q.loc[r.project_id].poi_sub_id)
        got = {}
        for f in ps.findings:
            n = N.normalize(f["facility_str"], poi_sub=poi)
            c = N.normalize(f["contingency_str"], poi_sub=poi) if f.get("contingency_str") and f["contingency_str"] not in ("N-0",) else dict(fid=None)
            rows.append(dict(project_id=r.project_id, publication_date=r.publication_date, facility_str=f["facility_str"], fid=n["fid"],
                             fid_confidence=n["confidence"], in_public_layer=n["in_public_layer"], contingency_str=f["contingency_str"],
                             cont_fid=c["fid"], loading_pct=f["loading_pct"], rating_mva=f["rating_mva"], dfax_pct=f["dfax_pct"],
                             pre_loading_pct=f["pre_loading_pct"], source=f["source"]))
            if n["fid"]:
                got[n["fid"]] = max(got.get(n["fid"], 0), f["loading_pct"] or 0)
        # upgrades -> cost per fid
        up = {}
        for u in ps.upgrades:
            n = N.normalize(u["facility_str"], poi_sub=poi)
            if n["fid"]:
                up[n["fid"]] = u
        for rr in rows:
            if rr["project_id"] == r.project_id and rr["fid"] in up:
                rr["upgrade_str"] = up[rr["fid"]]["upgrade_str"]; rr["cost_total_usd"] = up[rr["fid"]]["cost_total_usd"]
                rr["cost_alloc_usd"] = up[rr["fid"]]["cost_alloc_usd"]
        m = ps.meta
        meta_rows.append(dict(project_id=r.project_id, publication_date=r.publication_date, parsed_project_id=m.get("project_id"),
                              mw=m.get("mw"), poi_str=m.get("poi_str"), n_facilities_stated=m.get("n_facilities_stated"),
                              n_findings_parsed=len(ps.findings), n_fid_resolved=len(got), total_cost_usd=m.get("total_cost_usd"),
                              n_queue_ahead=m.get("n_queue_ahead"), warnings="; ".join(ps.warnings), template=r.template))
        tr = truth[truth.project_id == r.project_id]
        tr_fids = set(tr.fid)
        tsr = tsum[tsum.project_id == r.project_id].iloc[0]
        qual.append(dict(project_id=r.project_id, template=r.template, n_truth=len(tr_fids), n_parsed=len(ps.findings), n_resolved=len(got),
                         tp=len(set(got) & tr_fids), fp=len(set(got) - tr_fids), fn=len(tr_fids - set(got)),
                         cost_ok=(m.get("total_cost_usd") is not None and abs(m["total_cost_usd"] - tsr.cost_alloc_total) < 2000),
                         loading_abs_err=(sum(abs(got[f] - tr[tr.fid == f].loading_post.max()) for f in got if f in tr_fids) / max(1, len(set(got) & tr_fids)))))
    pf = pd.DataFrame(rows); pf.to_csv(C.STUDIES / "parsed_findings.csv", index=False)
    pm = pd.DataFrame(meta_rows); pm.to_csv(C.STUDIES / "parsed_meta.csv", index=False)
    qd = pd.DataFrame(qual); qd.to_csv(C.TABLES / "parse_quality_per_study.csv", index=False)
    summary = dict(n_studies=len(qd), findings_truth=int(qd.n_truth.sum()), findings_parsed=int(qd.n_parsed.sum()),
                   extraction_recall=float(qd.n_parsed.sum() / max(1, qd.n_truth.sum())),
                   fid_precision=float(qd.tp.sum() / max(1, qd.tp.sum() + qd.fp.sum())), fid_recall=float(qd.tp.sum() / max(1, qd.tp.sum() + qd.fn.sum())),
                   studies_exact=float((qd.fp.eq(0) & qd.fn.eq(0)).mean()), cost_total_match=float(qd.cost_ok.mean()),
                   loading_mae=float(qd.loading_abs_err.mean()), project_id_match=float((pm.parsed_project_id == pm.project_id).mean()))
    by_t = qd.groupby("template").apply(lambda g: pd.Series(dict(n=len(g), fid_precision=g.tp.sum() / max(1, g.tp.sum() + g.fp.sum()),
                                                                 fid_recall=g.tp.sum() / max(1, g.tp.sum() + g.fn.sum()))), include_groups=False)
    pd.DataFrame([summary]).to_csv(C.TABLES / "parse_quality_summary.csv", index=False)
    by_t.to_csv(C.TABLES / "parse_quality_by_template.csv")
    print(summary); print(by_t)
    # inspection sample for manual review
    random.seed(3)
    sample = random.sample(list(idx.itertuples()), min(5, len(idx)))
    with open(C.CASES / "parse_inspection_sample.md", "w") as fh:
        fh.write("# Parser inspection sample (5 random studies)\n\nFor each: raw PDF text (section 3.1), parsed+normalised facilities, hidden truth.\n\n")
        for r in sample:
            text, _ = extract_text_and_tables(str(C.ROOT / r.pdf_path))
            sec = text.split("3.1")[1].split("3.2")[0] if "3.1" in text else text[:1500]
            fh.write(f"## {r.project_id} (template {r.template})\n\n```\n{sec.strip()[:2500]}\n```\n\n")
            g = pf[pf.project_id == r.project_id]
            fh.write("Parsed -> normalised:\n\n| facility string | fid | conf | loading |\n|---|---|---|---|\n")
            for x in g.itertuples():
                fh.write(f"| {x.facility_str} | {x.fid} | {x.fid_confidence:.2f} | {x.loading_pct} |\n")
            tr = truth[truth.project_id == r.project_id]
            fh.write("\nTruth fids: " + ", ".join(f"{a} ({b}%)" for a, b in zip(tr.fid, tr.loading_post)) + "\n\n")
    print("wrote inspection sample")
