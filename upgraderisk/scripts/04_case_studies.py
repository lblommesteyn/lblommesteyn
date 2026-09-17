"""Prospective case studies on the chronological holdout: for real upgrades at real historical dates, what PJM's
table said, what the model (trained only on outcomes knowable at the cutoff) would have predicted, and what happened.
Output: outputs/cases/case_studies.md and cases.json"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from upgraderisk.predict import Predictor
from upgraderisk.config import PROCESSED, CASES, TABLES


def pick(ex: pd.DataFrame, cutoff: str, n: int, seed: int = 0) -> pd.DataFrame:
    te = ex[(ex["obs_date"] > cutoff) & ex["expected_isd"].notna()].copy()
    te = te.sort_values("obs_date").drop_duplicates("upgrade_id", keep="first")   # first post-cutoff sighting of each upgrade
    rng = np.random.default_rng(seed)
    parts = []
    big = te[te["est_cost_musd"] >= 50].sort_values("est_cost_musd", ascending=False).head(max(2, n // 4)); parts.append(big)
    late = te[(te["delay_12m"] == 1) & ~te.index.isin(big.index)]; parts.append(late.sample(min(len(late), n // 4), random_state=seed))
    ontime = te[(te["delay_12m"] == 0) & ~te.index.isin(pd.concat(parts).index)]; parts.append(ontime.sample(min(len(ontime), n // 4), random_state=seed))
    canc = te[(te["resolved_cancel"] == 1) & ~te.index.isin(pd.concat(parts).index)]; parts.append(canc.sample(min(len(canc), max(1, n // 6)), random_state=seed))
    over = te[(te["cost_overrun_25"] == 1) & ~te.index.isin(pd.concat(parts).index)]; parts.append(over.sample(min(len(over), max(1, n - len(pd.concat(parts)))), random_state=seed))
    return pd.concat(parts).head(n)


def actual_text(row) -> str:
    if row["resolved_cancel"] == 1:
        return "cancelled / withdrawn"
    if row["resolved_done"] == 1:
        t = f"in service {pd.Timestamp(row['actual_isd']).date()}"
        if pd.notna(row["months_late"]):
            t += f" ({row['months_late']:+.0f} months vs the date published then)"
        if pd.notna(row["final_cost_musd"]):
            t += f", final cost ${row['final_cost_musd']:.2f}M" + (f" ({row['pct_overrun']:+.0%})" if pd.notna(row["pct_overrun"]) else "")
        return t
    return f"not yet in service as of the last observation ({pd.Timestamp(row['last_obs']).date()})"


def main(n: int, cutoff: str):
    CASES.mkdir(parents=True, exist_ok=True)
    ex = pd.read_parquet(PROCESSED / "examples.parquet")
    pr = Predictor.load()
    sel = pick(ex, cutoff, n)
    cases, md = [], [f"# Prospective case studies (holdout, observations after {cutoff})\n",
                     "Each case is a real PJM upgrade at a real historical observation date. The model is the bundle trained on outcomes knowable at the cutoff; "
                     "it saw nothing published after the as-of date. Outcomes are taken from PJM's current table (2026).\n"]
    for _, row in sel.iterrows():
        try:
            r = pr.explain(row["upgrade_id"], str(row["obs_date"].date()))
        except Exception as e:
            print("skip", row["upgrade_id"], e); continue
        p = r["prediction"]
        hit_delay = (p["p_delay_12m"] >= 0.5) == (row["delay_12m"] == 1) if pd.notna(row["delay_12m"]) else None
        c = dict(upgrade_id=row["upgrade_id"], as_of=r["as_of"], inputs=r["inputs"], prediction=p, drivers=r["drivers"]["delay_12m"][:5], analogs=r["analogs"][:4],
                 actual=dict(text=actual_text(row), delay_12m=(None if pd.isna(row["delay_12m"]) else int(row["delay_12m"])), months_late=(None if pd.isna(row["months_late"]) else float(row["months_late"])),
                             cost_overrun_25=(None if pd.isna(row["cost_overrun_25"]) else int(row["cost_overrun_25"])), pct_overrun=(None if pd.isna(row["pct_overrun"]) else float(row["pct_overrun"])),
                             cancelled=int(row["resolved_cancel"])), delay_call_correct=hit_delay)
        cases.append(c)
        i = r["inputs"]
        md += [f"## {row['upgrade_id']} — {i['to']}, {i['voltage_kv']} kV {i['equipment']} (as of {r['as_of']})",
               f"*{i['scope'][:220]}*", "",
               f"- **At {r['as_of']} PJM's table said:** in service {p['iso_expected_isd']}, cost ${p['iso_cost_musd']:.2f}M, status {i['status']}, listed for {i['age_months']:.0f} months, "
               f"date revised {i['n_isd_revisions']} time(s), slipped {i['slip_so_far_months']:.0f} months so far." if i['slip_so_far_months'] is not None else
               f"- **At {r['as_of']} PJM's table said:** in service {p['iso_expected_isd']}, cost ${p['iso_cost_musd']:.2f}M, status {i['status']}, listed for {i['age_months']:.0f} months.",
               f"- **Model would have said:** P(delay > 12 months) **{p['p_delay_12m']:.0%}**; completion P50 **{p['model_cod_p50']}**, P90 {p['model_cod_p90']}; "
               f"P(cost increase > 25%) **{p['p_cost_overrun_25']:.0%}**; cost P50 ${p['model_cost_p50']:.2f}M (P10–P90 ${p['model_cost_p10']:.2f}M–${p['model_cost_p90']:.2f}M)"
               + (f"; P(cancelled) {p['p_cancelled']:.0%}" if p.get("p_cancelled") is not None else "") + ".",
               f"- **Drivers:** " + ", ".join(f"{d['feature']}={str(d['value'])[:20]} ({d['contribution_logodds']:+.2f})" for d in r["drivers"]["delay_12m"][:4]),
               f"- **What happened:** {actual_text(row)}.", ""]
    json.dump(cases, open(CASES / "cases.json", "w"), indent=1, default=str)
    calls = [c["delay_call_correct"] for c in cases if c["delay_call_correct"] is not None]
    md.append(f"\nDelay calls at the 50% threshold correct in {sum(calls)}/{len(calls)} labelled cases (the benchmark tables are the proper evaluation; these are illustrations).\n")
    (CASES / "case_studies.md").write_text("\n".join(md))
    print(f"{len(cases)} cases written; delay calls correct {sum(calls)}/{len(calls)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--n", type=int, default=12); ap.add_argument("--cutoff", default="2017-12-31")
    a = ap.parse_args(); main(a.n, a.cutoff)
