"""Prospective case studies on the holdout: real upgrades at real historical dates. Model outputs come from the
rolling-origin benchmark (a model refitted before that month on outcomes knowable then); analogs are past upgrades
whose outcome was already known at the as-of date. Output: outputs/cases/case_studies.md and cases.json"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from upgraderisk.predict import Predictor
from upgraderisk import features
from upgraderisk.config import PROCESSED, CASES, TABLES


def pick(te: pd.DataFrame, n: int, seed: int = 0) -> pd.DataFrame:
    te = te[te["expected_isd"].notna()].sort_values("obs_date").drop_duplicates("upgrade_id", keep="first")
    parts = []
    big = te[te["est_cost_musd"] >= 50].sort_values("est_cost_musd", ascending=False).head(max(2, n // 4)); parts.append(big)
    used = lambda: pd.concat(parts).index
    late = te[(te["delay_12m"] == 1) & ~te.index.isin(used())]; parts.append(late.sample(min(len(late), n // 4), random_state=seed))
    ontime = te[(te["delay_12m"] == 0) & ~te.index.isin(used())]; parts.append(ontime.sample(min(len(ontime), n // 4), random_state=seed))
    canc = te[(te["resolved_cancel"] == 1) & ~te.index.isin(used())]; parts.append(canc.sample(min(len(canc), max(1, n // 6)), random_state=seed))
    over = te[(te["cost_overrun_25"] == 1) & ~te.index.isin(used())]; parts.append(over.sample(min(len(over), max(1, n - len(used()))), random_state=seed))
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


def add_months(d, m):
    return None if pd.isna(d) else str((pd.Timestamp(d) + pd.Timedelta(days=float(m) * 30.4375)).date())


def main(n: int):
    CASES.mkdir(parents=True, exist_ok=True)
    pt = pd.read_parquet(TABLES / "predictions_test.parquet")
    pr = Predictor.load()
    sel = pick(pt, n)
    cases, md = [], ["# Prospective case studies (rolling-origin holdout)\n",
                     "Each case is a real PJM upgrade at a real archived observation date. The model outputs are those of the benchmark model refitted before that month on "
                     "outcomes knowable then; it saw nothing published after the as-of date. Analogs are earlier upgrades whose outcome was already known on that date. "
                     "What happened is taken from PJM's current table (2026).\n"]
    for _, row in sel.iterrows():
        t = pd.Timestamp(row["obs_date"])
        f = features.base_features(pd.DataFrame([row]))
        ana = pr.analogs(f, 4).to_dict(orient="records")
        for a in ana:
            for kk in ("obs_date", "expected_isd", "actual_isd"):
                a[kk] = None if pd.isna(a[kk]) else str(pd.Timestamp(a[kk]).date())
        drivers = json.loads(row["gbm_drivers"]) if isinstance(row.get("gbm_drivers"), str) else []
        p = dict(p_delay=float(row["blend_p_delay"]), p_delay_survival=float(row["dt_survival_p_delay"]), p_delay_gbm=float(row["gbm_p_delay"]), p_over=float(row["gbm_p_over"]),
                 p_cancel=(None if pd.isna(row["gbm_p_cancel"]) else float(row["gbm_p_cancel"])),
                 cod_p10=add_months(row["expected_isd"], row["dt_survival_late_p10"]), cod_p50=add_months(row["expected_isd"], row["dt_survival_late_p50"]), cod_p90=add_months(row["expected_isd"], row["dt_survival_late_p90"]),
                 cost_p10=float(row["est_cost_musd"] * (1 + row["gbm_over_p10"])), cost_p50=float(row["est_cost_musd"] * (1 + row["gbm_over_p50"])), cost_p90=float(row["est_cost_musd"] * (1 + row["gbm_over_p90"])))
        hit = (p["p_delay"] >= 0.5) == (row["delay_12m"] == 1) if pd.notna(row["delay_12m"]) else None
        cases.append(dict(upgrade_id=row["upgrade_id"], as_of=str(t.date()), inputs=dict(to=row["to"], voltage_kv=row["voltage_kv"], equipment=row["equipment"], status=row["status"], est_cost_musd=row["est_cost_musd"],
                          expected_isd=str(pd.Timestamp(row["expected_isd"]).date()), age_months=row["age_months"], slip_so_far_months=row["slip_so_far_months"], n_isd_revisions=int(row["n_isd_revisions"]), scope=row["scope"][:200]),
                          prediction=p, drivers=drivers, analogs=ana,
                          actual=dict(text=actual_text(row), delay_12m=(None if pd.isna(row["delay_12m"]) else int(row["delay_12m"])), months_late=(None if pd.isna(row["months_late"]) else float(row["months_late"])),
                                      cost_overrun_25=(None if pd.isna(row["cost_overrun_25"]) else int(row["cost_overrun_25"])), pct_overrun=(None if pd.isna(row["pct_overrun"]) else float(row["pct_overrun"])), cancelled=int(row["resolved_cancel"])),
                          delay_call_correct=hit))
        slip = f", slipped {row['slip_so_far_months']:.0f} months so far" if pd.notna(row["slip_so_far_months"]) else ""
        md += [f"## {row['upgrade_id']} — {row['to']}, {row['voltage_kv']} kV {row['equipment']} (as of {t.date()})", f"*{str(row['scope'])[:220]}*", "",
               f"- **At {t.date()} PJM's table said:** in service {pd.Timestamp(row['expected_isd']).date()}, cost ${row['est_cost_musd']:.2f}M, status {row['status']}, listed for {row['age_months']:.0f} months, date revised {int(row['n_isd_revisions'])} time(s){slip}.",
               f"- **Model would have said:** P(slip > 12 months) **{p['p_delay']:.0%}** (survival {p['p_delay_survival']:.0%}, classifier {p['p_delay_gbm']:.0%}); completion P50 **{p['cod_p50']}**, P90 {p['cod_p90']} (survival model); "
               f"P(cost increase > 25 %) **{p['p_over']:.0%}**; cost P50 ${p['cost_p50']:.2f}M (P10–P90 ${p['cost_p10']:.2f}M–${p['cost_p90']:.2f}M)" + (f"; P(cancelled) {p['p_cancel']:.0%}" if p["p_cancel"] is not None else "") + ".",
               f"- **Drivers:** " + ", ".join(f"{d['f']}={str(d['v'])[:20]} ({d['c']:+.2f})" for d in drivers[:4]),
               f"- **Analogs known then:** " + ("; ".join(f"{a['upgrade_id']} ({a['to']}, {'cancelled' if a['resolved_cancel'] else ('late ' + format(a['months_late'], '+.0f') + ' mo' if a['months_late'] is not None and a['months_late'] == a['months_late'] else 'done')})" for a in ana) if ana else "none"),
               f"- **What happened:** {actual_text(row)}.", ""]
    json.dump(cases, open(CASES / "cases.json", "w"), indent=1, default=str)
    calls = [c["delay_call_correct"] for c in cases if c["delay_call_correct"] is not None]
    md.append(f"\nSlip calls at the 50 % threshold correct in {sum(calls)}/{len(calls)} labelled cases (the benchmark tables are the evaluation; these are illustrations).\n")
    (CASES / "case_studies.md").write_text("\n".join(md))
    print(f"{len(cases)} cases written; delay calls correct {sum(calls)}/{len(calls)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--n", type=int, default=12)
    a = ap.parse_args(); main(a.n)
