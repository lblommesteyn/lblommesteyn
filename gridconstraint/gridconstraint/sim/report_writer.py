"""Render PJM-style interconnection study reports (PDF) from the hidden study truth.

Three layouts emulate the drift in real report templates:
  A "table"   (2016+): results in ruled tables (Facility | Contingency | Loading | Rating | DFAX)
  B "prose"   (early): sentence form "X is overloaded to 104.2% of its 350 MVA rating for the loss of Y"
  C "fields"  (any):   one field per line "Facility: ... / Contingency: ... / Loading: ..."
Facility names are rendered with a per-report style plus per-mention noise (abbreviations,
typos, circuit suffixes, order swaps), mirroring how transmission owners actually write them.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from .. import config as C
from .naming import noisy_facility_name

FUEL_WORDS = {"solar": "solar photovoltaic", "wind": "wind", "gas": "natural gas combined cycle", "other": "generating",
              "hybrid": "solar plus storage", "storage": "battery energy storage", "load": "large load (data center)"}


def _money(x: float) -> str:
    return "${:,.0f}".format(round(x, -3))


def _cont_text(row, names, rng, style, n_circ):
    if row.cont_branch < 0 or not isinstance(row.cont_fid, str) or row.cont_fid == "":
        return rng.choice(["System intact (N-0)", "Base case", "N-0", "No contingency"])
    circ = int(row.cont_circuit) if n_circ.get(row.cont_fid, 1) > 1 else None
    return noisy_facility_name(row.cont_fid, names, rng, circuit=circ, style=style)


def render_all(seed: int = C.SEED + 1, limit: int | None = None) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    W, P, S = C.WORLD, C.PUBLIC, C.STUDIES
    (S / "pdf").mkdir(exist_ok=True, parents=True)
    q = pd.read_csv(P / "queue.csv").set_index("project_id")
    rows = pd.read_csv(W / "study_rows.csv")
    summ = pd.read_csv(W / "study_summary.csv", parse_dates=["study_date"])
    subs = pd.read_csv(W / "substations.csv")
    names = dict(zip(subs.sub_id.astype(int), subs.name))
    facall = pd.read_csv(W / "facilities_all.csv")
    n_circ = dict(zip(facall.fid, facall.n_circuits))
    grouped = {k: g for k, g in rows.groupby("project_id")}
    styles = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=styles["Normal"], fontSize=9.5, leading=12)
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=8.5, leading=10.5)
    index = []
    for i, s in enumerate(summ.itertuples()):
        if limit and i >= limit:
            break
        pid = s.project_id; pr = q.loc[pid]
        year = s.study_date.year
        template = rng.choice(["A", "B", "C"], p=[0.15, 0.55, 0.30] if year < 2016 else [0.55, 0.15, 0.30])
        rstyle = dict(kv_fmt=rng.choice(["{kv} kV", "{kv}kV", "{kv} KV", "{kv}.0 kV"]), case=rng.choice(["title", "upper", "as_is"]),
                      sep=rng.choice([" - ", "-", " – ", " to ", " / "]))
        g = grouped.get(pid, rows.iloc[0:0])
        pub_date = s.study_date + pd.Timedelta(days=int(rng.integers(0, 20)))
        path = S / "pdf" / f"{pid.lower().replace('-', '')}_imp.pdf"
        doc = SimpleDocTemplate(str(path), pagesize=letter, leftMargin=54, rightMargin=54, topMargin=54, bottomMargin=54)
        el = []
        kind = "Generation" if pr.project_type != "load" else "Load"
        title = rng.choice([f"{kind} Interconnection System Impact Study Report", f"{kind} Interconnection Combined Feasibility / System Impact Study Report",
                            f"Revised {kind} Interconnection System Impact Study Report", f"{kind} Interconnection Request System Impact Study Report"])
        el.append(Paragraph(title, styles["Title"]))
        el.append(Paragraph(f"For Queue Project {pid}", styles["Heading2"]))
        el.append(Paragraph(f"{pr.poi_name} <br/> {pub_date:%B %d, %Y}", body))
        el.append(Spacer(1, 12))
        el.append(Paragraph("1. Introduction", styles["Heading3"]))
        mw_txt = f"{pr.mw:.1f} MW"
        el.append(Paragraph(
            f"This System Impact Study report documents the results of the analyses performed for interconnection request {pid}. "
            f"The Interconnection Customer proposes a {mw_txt} {FUEL_WORDS.get(pr.fuel, 'generating')} facility interconnecting at the "
            f"{pr.poi_name.replace(' kV', ' kV substation')} in the {pr.state} area. The request was received on {pd.Timestamp(pr.queue_date):%B %d, %Y}. "
            f"The study evaluated system intact and single contingency conditions using the regional planning case, including "
            f"{int(s.n_queue_ahead)} higher-queued active requests and their assigned network upgrades.", body))
        el.append(Spacer(1, 8))
        el.append(Paragraph("2. Summary of Results", styles["Heading3"]))
        if len(g) == 0:
            el.append(Paragraph(rng.choice([
                "No thermal overloads attributable to this project were identified. No network upgrades are required.",
                "The study did not identify any facilities overloaded as a result of the project. Network upgrade cost: $0.",
                "This project does not cause any thermal violations under system intact or single contingency conditions."]), body))
            el.append(Paragraph(f"Estimated network upgrade cost: {_money(0)}", body))
        else:
            el.append(Paragraph(
                f"The project was found to contribute (DFAX of 5% or greater) to {len(g)} overloaded facilit{'y' if len(g)==1 else 'ies'}. "
                f"The total estimated cost of the network upgrades allocated to this project is {_money(s.cost_alloc_total)}.", body))
        el.append(Spacer(1, 8))
        el.append(Paragraph("3. Network Impacts", styles["Heading3"]))
        el.append(Paragraph("3.1 Generator Deliverability and Single Contingency Analysis" if kind == "Generation" else "3.1 Load Deliverability Analysis", styles["Heading4"]))
        mentions = []
        if len(g):
            if template == "A":
                data = [["Monitored Facility", "Contingency", "Loading (%)", "Rating (MVA)", "DFAX (%)"]]
                for r in g.itertuples():
                    circ = int(r.circuit) if n_circ.get(r.fid, 1) > 1 else None
                    fn = noisy_facility_name(r.fid, names, rng, circuit=circ, style=rstyle)
                    cn = _cont_text(r, names, rng, rstyle, n_circ)
                    mentions.append((fn, r.fid))
                    data.append([Paragraph(fn, small), Paragraph(cn, small), f"{r.loading_post:.1f}", f"{r.rating_mva:,.0f}", f"{r.dfax:.1f}"])
                t = Table(data, colWidths=[170, 170, 55, 60, 50], repeatRows=1)
                t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.black), ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                                       ("FONTSIZE", (0, 0), (-1, -1), 8), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
                el.append(t)
            elif template == "B":
                for r in g.itertuples():
                    circ = int(r.circuit) if n_circ.get(r.fid, 1) > 1 else None
                    fn = noisy_facility_name(r.fid, names, rng, circuit=circ, style=rstyle)
                    cn = _cont_text(r, names, rng, rstyle, n_circ)
                    mentions.append((fn, r.fid))
                    if r.cont_branch < 0:
                        txt = rng.choice([f"The {fn} is overloaded to {r.loading_post:.1f}% of its {r.rating_mva:,.0f} MVA rating under system intact conditions. The project's distribution factor on this facility is {r.dfax:.1f}%.",
                                          f"{fn} loads to {r.loading_post:.1f}% of its {r.rating_mva:,.0f} MVA normal rating with all facilities in service (DFAX {r.dfax:.1f}%)."])
                    else:
                        txt = rng.choice([f"The {fn} is overloaded to {r.loading_post:.1f}% of its {r.rating_mva:,.0f} MVA emergency rating for the loss of the {cn}. The project contributes {r.dfax:.1f}% DFAX ({r.contrib_mw:.1f} MW) to this overload.",
                                          f"For the loss of {cn}, the {fn} loads to {r.loading_post:.1f}% of its {r.rating_mva:,.0f} MVA rating. Project DFAX: {r.dfax:.1f}%.",
                                          f"{fn}: {r.loading_post:.1f}% loading ({r.rating_mva:,.0f} MVA) following the outage of the {cn}; DFAX = {r.dfax:.1f}%."])
                    el.append(Paragraph(txt, body)); el.append(Spacer(1, 4))
            else:
                for j, r in enumerate(g.itertuples(), 1):
                    circ = int(r.circuit) if n_circ.get(r.fid, 1) > 1 else None
                    fn = noisy_facility_name(r.fid, names, rng, circuit=circ, style=rstyle)
                    cn = _cont_text(r, names, rng, rstyle, n_circ)
                    mentions.append((fn, r.fid))
                    el.append(Paragraph(f"{j}. Facility: {fn}<br/>&nbsp;&nbsp;&nbsp;Contingency: {cn}<br/>&nbsp;&nbsp;&nbsp;Loading: {r.loading_post:.1f}% (Rating: {r.rating_mva:,.0f} MVA)"
                                        f"<br/>&nbsp;&nbsp;&nbsp;DFAX: {r.dfax:.1f}%<br/>&nbsp;&nbsp;&nbsp;Pre-project loading: {r.loading_pre:.1f}%", body))
                    el.append(Spacer(1, 4))
        else:
            el.append(Paragraph("No overloads identified.", body))
        el.append(Paragraph("3.2 Multiple Facility Contingency Analysis", styles["Heading4"]))
        el.append(Paragraph("No additional overloads were identified for multiple facility contingencies.", body))
        el.append(Paragraph("3.3 Short Circuit and Stability", styles["Heading4"]))
        el.append(Paragraph("Short circuit and stability analyses identified no additional network upgrades.", body))
        el.append(Spacer(1, 8))
        el.append(Paragraph("4. Required Network Upgrades and Cost Estimates", styles["Heading3"]))
        if len(g):
            data = [["Facility", "Required Upgrade", "Cost Estimate", "Allocation to Project"]]
            for (fn, fid), r in zip(mentions, g.itertuples()):
                # upgrade text re-renders the facility with fresh noise (as real reports do)
                circ = int(r.circuit) if n_circ.get(r.fid, 1) > 1 else None
                fn2 = noisy_facility_name(r.fid, names, rng, circuit=circ, style=rstyle) if rng.random() < 0.5 else fn
                up = {"reconductor": "Reconductor line", "rebuild": "Rebuild line with higher-capacity conductor",
                      "replace transformer": "Replace transformer with higher-rated unit", "upgrade bus/terminal equipment": "Upgrade terminal equipment / bus work"}[r.upgrade]
                data.append([Paragraph(fn2, small), Paragraph(up, small), _money(r.cost_total), f"{100*r.cost_share:.0f}% ({_money(r.cost_alloc)})"])
            data.append(["", "Total allocated to project", "", _money(s.cost_alloc_total)])
            t = Table(data, colWidths=[165, 150, 85, 105], repeatRows=1)
            t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.black), ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                                   ("FONTSIZE", (0, 0), (-1, -1), 8), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
            el.append(t)
        else:
            el.append(Paragraph("None. Total network upgrade cost allocated to this project: $0.", body))
        el.append(Spacer(1, 12))
        el.append(Paragraph("This report is a simulated study produced by the gridconstraint research prototype on a public synthetic-but-realistic "
                            "PJM-footprint case; it is not a PJM document.", small))
        doc.build(el)
        index.append(dict(project_id=pid, study_type="system_impact", publication_date=pub_date.date(), template=template,
                          pdf_path=str(path.relative_to(C.ROOT))))
    idx = pd.DataFrame(index)
    idx.to_csv(P / "study_index.csv", index=False)
    return idx


if __name__ == "__main__":
    import sys
    lim = int(sys.argv[1]) if len(sys.argv) > 1 else None
    idx = render_all(limit=lim)
    print(idx.template.value_counts().to_dict(), len(idx))
