"""Prospective-style case studies: reconstruct the as-of-queue-date prediction for chosen
test projects, then reveal the study and explain hits and misses (using hidden-world
diagnostics only in the explanation step, clearly labelled)."""
from __future__ import annotations
import numpy as np
import pandas as pd
from .. import config as C
from ..app.predict import Predictor


def pick_cases(te: pd.DataFrame, n_each: int = 2) -> list[tuple[str, str]]:
    g = te.groupby("project_id")
    summ = pd.DataFrame(dict(n_pos=g.y.sum(), hit1=g.apply(lambda d: d.sort_values("p_main", ascending=False).y.iloc[0], include_groups=False),
                             hit5=g.apply(lambda d: d.sort_values("p_main", ascending=False).y.head(5).sum() > 0, include_groups=False),
                             seen=g.seen_poi.first(), ptype=g.project_type.first(), mw=g.mw.first(), pmax=g.p_main.max()))
    cases = []
    s = summ[(summ.n_pos >= 2) & (summ.hit1 == 1)].sort_values("n_pos", ascending=False)
    cases += [(p, "clear hit (top-1 correct, several facilities)") for p in s.index[:n_each]]
    s = summ[(summ.n_pos >= 1) & (summ.hit5 == 0)].sort_values("pmax", ascending=False)
    cases += [(p, "miss (no true facility in top-5)") for p in s.index[:n_each]]
    s = summ[(summ.n_pos >= 1) & (~summ.seen) & (summ.hit5)].sort_values("n_pos", ascending=False)
    cases += [(p, "unseen POI, hit within top-5") for p in s.index[:1]]
    s = summ[(summ.n_pos >= 1) & (summ.ptype != "gen") & (summ.hit5)]
    cases += [(p, f"non-generator project ({summ.loc[p].ptype})") for p in s.index[:1]]
    s = summ[(summ.n_pos == 0)].sort_values("pmax")
    cases += [(p, "no constraints found by ISO; model expected few") for p in s.index[:1]]
    seen_p = set(); out = []
    for p, why in cases:
        if p not in seen_p:
            out.append((p, why)); seen_p.add(p)
    return out


def write_cases(mode: str = "queue"):
    te = pd.read_parquet(C.PROCESSED / f"test_predictions_{mode}.parquet")
    P = Predictor(mode=mode)
    pub = P.pub
    truth = pd.read_csv(C.WORLD / "study_rows.csv")
    tsum = pd.read_csv(C.WORLD / "study_summary.csv")
    meta = pub.meta.set_index("project_id")
    fac_all = pd.read_csv(C.WORLD / "facilities_all.csv").set_index("fid")
    idx_lines = ["# Prospective case studies\n", "Each case: (1) what was public on the queue date, (2) the model's ranked prediction made from that "
                 "information only, (3) the ISO study revealed later, (4) why the model was right or wrong (the explanation may quote hidden-world "
                 "diagnostics such as the true distribution factor; those were never available to the model).\n"]
    for pid, why in pick_cases(te):
        q = pub.q_by_pid.loc[pid]; as_of = q.queue_date + pd.Timedelta(days=1)
        r = P.predict(int(q.poi_sub_id), q.project_type, float(q.mw), as_of, fuel=q.fuel, project_id=pid, top_k=10)
        g = te[te.project_id == pid]
        pos = set(g[g.y == 1].fid)
        tr = truth[truth.project_id == pid].sort_values("loading_post", ascending=False)
        ts = tsum[tsum.project_id == pid].iloc[0]
        m = meta.loc[pid]
        L = [f"## {pid} — {why}\n",
             f"**Project**: {q.project_type} ({q.fuel}), {q.mw:.0f} MW at {r['project']['poi_name']} {r['project']['poi_kv']:.0f} kV, queued {q.queue_date.date()}. "
             f"Prediction made as of {as_of.date()}; study published {m.publication_date.date()}.\n",
             f"**Public context at the time**: {'previously studied POI' if r['project']['seen_poi'] else 'no prior study at this POI'}; "
             f"{int(g.queue_n_same_poi.iloc[0])} earlier queue entries at the POI ({g.queue_mw_active_same_poi.iloc[0]:.0f} MW active); "
             f"{g.queue_mw_active_50km.iloc[0]:.0f} MW active queue within 50 km; POI congestion component {g.poi_cong_mean.iloc[0]:+.1f} $/MWh (24-month mean); "
             f"{int(g.analog_n.iloc[0])} analog projects within 80 km.\n",
             f"**Model output**: difficulty **{r['difficulty']['label']}** (expected {r['difficulty']['expected_constraints']:.1f} constrained facilities, "
             f"P(no constraint) = {r['difficulty']['p_no_constraint']:.2f}).\n", "| rank | predicted facility | p | ±sd | evidence | outcome |", "|---|---|---|---|---|---|"]
        for i, x in enumerate(r["ranked"], 1):
            outcome = "**HIT**" if x["fid"] in pos else "-"
            L.append(f"| {i} | {x['display']} | {x['p']:.2f} | {x['sd']:.2f} | {'; '.join(x['evidence'][:3])} | {outcome} |")
        L.append(f"\n**Revealed ISO study** ({m.publication_date.date()}): {int(m.n_fid_resolved)} constrained facilities, total allocated upgrade cost "
                 f"${(m.total_cost_usd or 0)/1e6:.1f}M ({(m.total_cost_usd or 0)/(q.mw*1000):.0f} $/kW).\n")
        if len(tr):
            L += ["| facility (study) | loading % | pre-project % | true DFAX % | contingency | in candidates | model rank | model p |", "|---|---|---|---|---|---|---|---|"]
            ranks = {f: i + 1 for i, f in enumerate(g.sort_values("p_main", ascending=False).fid)}
            pmap = dict(zip(g.fid, g.p_main))
            for x in tr.drop_duplicates("fid").itertuples():
                L.append(f"| {P.display(x.fid)} | {x.loading_post:.1f} | {x.loading_pre:.1f} | {x.dfax:.1f} | {P.display(x.cont_fid) if isinstance(x.cont_fid, str) and x.cont_fid else 'N-0'} | "
                         f"{'yes' if x.fid in ranks else 'no'} | {ranks.get(x.fid, '-')} | {pmap.get(x.fid, float('nan')):.2f} |")
        # explanation
        top10 = [x["fid"] for x in r["ranked"]]
        hits = [f for f in top10 if f in pos]; missed = [f for f in pos if f not in top10]
        expl = []
        if hits:
            expl.append(f"{len(hits)} of {len(pos)} true facilities were in the top-10 (first hit at rank {top10.index(hits[0]) + 1}).")
        for f in missed[:4]:
            row = g[g.fid == f]
            trow = tr[tr.fid == f].iloc[0] if (tr.fid == f).any() else None
            if len(row) == 0:
                dd = pub.topo.fac_dist_km(int(q.poi_sub_id))[0][pub.fac_pos[f]] if f in pub.fac_pos else float("nan")
                expl.append(f"Missed {P.display(f)}: not in the candidate set (distance {dd:.0f} km; true DFAX {trow.dfax if trow is not None else float('nan'):.1f}% — "
                            f"far-field sensitivity the public-topology model estimated below the candidate threshold).")
            else:
                rr = row.iloc[0]
                reasons = []
                if rr.apx_dfax_n1 < 0.05: reasons.append(f"public-topology DFAX only {rr.apx_dfax_n1:.2f} vs true {trow.dfax:.1f}%" if trow is not None else f"public-topology DFAX only {rr.apx_dfax_n1:.2f}")
                if rr.fac_n_named == 0: reasons.append("never named in a prior study")
                if rr.cong_hours_all == 0: reasons.append("never bound in sampled market hours")
                if trow is not None and trow.loading_pre >= 97: reasons.append(f"facility sat at {trow.loading_pre:.0f}% pre-project (hair-trigger headroom invisible publicly)")
                expl.append(f"Missed {P.display(f)} (rank {int((g.p_main > rr.p_main).sum()) + 1}, p={rr.p_main:.2f}): " + "; ".join(reasons) + ".")
        fps = [x for x in r["ranked"][:5] if x["fid"] not in pos]
        for x in fps[:2]:
            fa = fac_all.loc[x["fid"]] if x["fid"] in fac_all.index else None
            expl.append(f"False alarm {x['display']} (p={x['p']:.2f}): evidence was {'; '.join(x['evidence'][:2])}"
                        + (f"; hidden truth: facility was flagged in earlier studies whose upgrades are assumed in service, so it had headroom." if g[g.fid == x['fid']].fac_n_active.iloc[0] > 0 else "."))
        if not pos:
            expl.append("The ISO found no constraints; the model's low expected count and high P(no constraint) agree with that.")
        L.append("\n**Why**: " + " ".join(expl) + "\n")
        (C.CASES / f"case_{pid}.md").write_text("\n".join(L))
        idx_lines.append("\n".join(L))
    (C.CASES / "README.md").write_text("\n".join(idx_lines))
    print("wrote", len(idx_lines) - 2, "case studies")


if __name__ == "__main__":
    write_cases()
