"""Command-line prototype.

  python scripts/predict_cli.py b2837 --as-of 2018-01-25
  python scripts/predict_cli.py --custom '{"to":"AEP","voltage_kv":138,"est_cost_musd":12,"expected_isd":"2021-06-01","equipment":"Transmission Line","task":"Rebuild","status":"Engineering & Procurement"}' --as-of 2019-12-15
  python scripts/predict_cli.py b2837 --as-of 2018-01-25 --json
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from upgraderisk.predict import Predictor


def fmt(r: dict) -> str:
    p, i = r["prediction"], r["inputs"]
    L = [f"Upgrade {r['upgrade_id']}  as of {r['as_of']}  (snapshot used: {r.get('snapshot_used')})",
         f"  {i['to']} | {i['voltage_kv']} kV | {i['equipment']} | status {i['status']} | listed {i['age_months']:.0f} months | slipped so far {i['slip_so_far_months'] if i['slip_so_far_months'] is not None else 'n/a'} months | ISD revisions {i['n_isd_revisions']}",
         f"  scope: {i['scope'][:120]}",
         "",
         f"  ISO says:      in service {p['iso_expected_isd']}   cost ${p['iso_cost_musd']:.2f}M" if p["iso_cost_musd"] is not None else f"  ISO says:      in service {p['iso_expected_isd']}   cost n/a",
         f"  Model:         P(delay > 12 months) = {p['p_delay_12m']:.0%}   (survival model: {p['survival_p_delay']:.0%})",
         f"                 completion P50 {p['model_cod_p50']}   P90 {p['model_cod_p90']}   (P10 {p['model_cod_p10']})",
         f"                 P(cost increase > 25%) = {p['p_cost_overrun_25']:.0%}" + (f"   P(cancelled) = {p['p_cancelled']:.0%}" if p.get("p_cancelled") is not None else ""),
         (f"                 cost P50 ${p['model_cost_p50']:.2f}M   P10-P90 ${p['model_cost_p10']:.2f}M - ${p['model_cost_p90']:.2f}M" if p["model_cost_p50"] is not None else "                 cost range n/a"),
         "", "  Risk drivers (log-odds contribution, delay):"]
    for d in r["drivers"]["delay_12m"][:6]:
        L.append(f"     {d['feature']:32s} {str(d['value'])[:28]:28s} {d['contribution_logodds']:+.2f}")
    L.append("  Similar past upgrades (outcomes as known today):")
    for a in r["analogs"][:6]:
        late = a["months_late"]; over = a["pct_overrun"]
        late_s = "n/a" if late is None or late != late else f"{late:+.1f}"
        over_s = "n/a" if over is None or over != over else f"{over:+.0%}"
        canc = "  CANCELLED" if a["resolved_cancel"] else ""
        L.append(f"     {a['upgrade_id']:10s} {str(a['to']):9s} {str(a['voltage_kv']):6s} {str(a['equipment'])[:18]:18s} expected {a['expected_isd']} -> actual {a['actual_isd']}  late {late_s} mo  cost {over_s}{canc}")
    if r.get("warning"):
        L += ["", f"  WARNING: {r['warning']}"]
    L += ["", f"  {r['caveat']}"]
    return "\n".join(L)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("upgrade_id", nargs="?")
    ap.add_argument("--as-of", required=True)
    ap.add_argument("--custom", help="JSON dict of characteristics for a hypothetical upgrade")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    pr = Predictor.load()
    r = pr.explain_custom(json.loads(a.custom), a.as_of) if a.custom else pr.explain(a.upgrade_id, a.as_of)
    print(json.dumps(r, indent=1, default=str) if a.json else fmt(r))
