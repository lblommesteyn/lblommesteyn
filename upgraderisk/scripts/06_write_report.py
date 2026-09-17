"""Assemble REPORT.md from the produced tables (dataset summary, benchmark, cases, snapshot manifest)."""
from __future__ import annotations
import json, sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from upgraderisk.config import ROOT, PROCESSED, TABLES, CASES, RAW

S = json.load(open(PROCESSED / "dataset_summary.json"))
B = json.load(open(TABLES / "benchmark.json"))
man = pd.read_csv(RAW / "pjm_snapshots" / "manifest.csv")
ex = pd.read_parquet(PROCESSED / "examples.parquet")
main_md = (TABLES / "benchmark_main.md").read_text()
cases_md = (CASES / "case_studies.md").read_text() if (CASES / "case_studies.md").exists() else ""
R = B["results"]; g = R["gbm"]; base = R["base_rate"]
best_base = max((k for k in R if k not in ("gbm", "dt_survival")), key=lambda k: R[k]["all"]["delay"].get("auroc", 0))
bb = R[best_base]["all"]


def f3(x):
    return "n/a" if x is None else f"{x:.3f}"


done = ex[ex.resolved_done == 1]
stale = float(((pd.to_datetime(done.actual_isd) <= done.obs_date)).mean())
by_type = ex.groupby("upgrade_type").agg(rows=("upgrade_id", "size"), upgrades=("upgrade_id", "nunique"), delay=("delay_12m", "mean"), over=("cost_overrun_25", "mean")).round(3)
leg = man[(man.status == "ok") & (man.n_tables > 0)].groupby("label").agg(n=("timestamp", "size"), first=("timestamp", "min"), last=("timestamp", "max"))
xml = sorted((RAW / "pjm_snapshots" / "legacy_xml").glob("*.xml.gz"))


def bd(key, metric="delay"):
    rows = []
    for gname, r in g["breakdowns"][key].items():
        rows.append(dict(group=gname, n=r["n"], rate=r[metric].get("rate"), auroc=r[metric].get("auroc"), brier=r[metric].get("brier"), mae_p50=r["months_late"].get("mae_p50")))
    d = pd.DataFrame(rows).sort_values("n", ascending=False)
    return d.round(3).to_markdown(index=False)


md = f"""# Predicting transmission network-upgrade delay and cost-overrun risk from public PJM data

*Research prototype. Every number below comes from real PJM publications (archived snapshots of PJM's own project
status tables); nothing is simulated. It is a statistical estimate from public tables, not an engineering or schedule
assessment, and it does not replace PJM's or a transmission owner's process.*

## 1. Question

Given a network upgrade at time *t*, using only information public at *t*: what is the probability the upgrade slips
more than 12 months past the in-service date PJM was publishing at *t*; what is the probability its cost estimate
ends up more than 25 % above the estimate published at *t*; and what completion-date and final-cost ranges are
consistent with the public record.

## 2. Data (all public, PJM)

PJM's "Transmission Construction Status" / "Project Status & Cost Allocation" table is republished continuously,
and only the current version is served. The longitudinal table **upgrade × observation_date** was reconstructed from:

| Source | Snapshots | Dates | What it carries |
|---|---|---|---|
| Wayback captures of the legacy `construct-status.aspx` page (baseline tab; rows embedded in ASP.NET ViewState or an inline JSON block) | {int(leg.loc['construct_status','n'])} | {str(leg.loc['construct_status','first'])[:8]} – {str(leg.loc['construct_status','last'])[:8]} | upgrade ID, TO projected in-service date, PJM required date, status (EP / UC / On Hold …), % complete, cost estimate ($M), owner, voltage, equipment, task, driver, initial/latest TEAC date, last-updated |
| Wayback captures of the legacy `cost-allocation-view.aspx` page (all baseline upgrades, in-service ones included) | {int(leg.loc['cost_allocation_view','n'])} | {str(leg.loc['cost_allocation_view','first'])[:8]} – {str(leg.loc['cost_allocation_view','last'])[:8]} | cost estimate, cost-allocation shares, required date, cancelled flag (used for cost history only; never as a status reference) |
| Wayback captures of the XML data files behind the legacy page (`TOUP_planned_baseline / network / TO.xml`) | {len(xml)} | 2010, 2013, 2016 – 2017 | same fields as the page for the baseline, network and supplemental tabs |
| Live export of PJM's current Project Status & Cost Allocation grid (`/planning/m/project-construction`) | 1 | 2026-09-17 | {S['n_upgrades']:,} upgrades with status, actual in-service date, current cost, TEAC cost, board-approval and TEAC dates |

The fetch runs on a GitHub Actions runner (this sandbox cannot reach pjm.com or archive.org); the decoded rows are
committed under `data/raw/pjm_snapshots/` with a manifest (URL, capture timestamp, sha256). Captures from
2010–2014 were ActiveX pages whose data lived in XML files, of which Wayback holds a few; 2019 cost-allocation captures
are truncated by the archive and were dropped.

Long table: **{S['n_snapshot_rows']:,} rows, {S['n_upgrades']:,} distinct upgrade IDs.** Observation dates are the
{len(S['snapshot_dates']['legacy_construct_status'])} construction-status snapshot dates ({S['snapshot_dates']['legacy_construct_status'][0]} … {S['snapshot_dates']['legacy_construct_status'][-1]}).

### Point-in-time rules (enforced in code and tests)

* The reference row for an upgrade at *t* is the latest **status-bearing** snapshot published within the 45 days
  before *t*. An upgrade absent from recent status snapshots has left the active list and gets no example (the
  cost-allocation view's bare "Active" flag is never treated as a status).
* Features use only rows with `snapshot_date <= t`. `tests/test_vintage.py` rebuilds the features from a table truncated
  at *t* and asserts equality; it also asserts every completion-known date lies after the observation.
* Labels use rows published after *t* plus PJM's current record: in-service date, final cost, cancellation.
* A model "trained at cutoff *c*" only sees labels that were **knowable by *c*** (`pit.known_by`): a 12-month slip
  label is decidable once the 12-month window has closed or the project was seen finished after it; a cost label
  once the project finished or its estimate first exceeded the +25 % line; the survival target is censored at *c*.
  Without this, a model recognises an upgrade seen in training and recalls its eventual fate.
* Examples whose 12-month window had already closed at *t* carry no slip label (the outcome was not a forecast).
* Owner / voltage / equipment historical rates used as features are computed from earlier examples whose labels were
  known at *t*, shrunk toward the global known rate.

### Outcome definitions

* `delay_12m`: in-service date (PJM's record) more than 12 months after the projected date published at *t*; also 1
  when the project was still unbuilt 12 months after that date. Cancelled projects: no slip label.
* `cost_overrun_25`: final cost (or, if unfinished, latest estimate) more than 25 % above the estimate at *t*. Cancelled
  projects and projects whose final cost field is zero: no cost label.
* `months_late`, `pct_overrun`: continuous versions for completed projects.
* `cancelled`: 1 if cancelled/withdrawn, 0 if completed, missing while unresolved.
* Survival target: months from *t* to in-service, censored at the last observation.
* Censoring: {S['censored_examples']:,} of {S['n_examples']:,} examples ({S['censored_examples']/S['n_examples']:.0%}) are unresolved in
  PJM's current table; {stale:.0%} of completed examples have a recorded in-service date at or before the
  observation date (PJM's table lagged the energisation, or the date refers to a first partial energisation) — they are
  kept, labelled from the recorded date.

### Dataset

* {S['n_examples']:,} examples ({S['n_example_upgrades']:,} upgrades); {S['unique_upgrades_resolved']:,} upgrades resolved (in service or cancelled) — the go/no-go threshold was 200.
* Slip label available for {S['delay_label_available']:,} examples, base rate {S['delay_rate']:.1%}; cost label for {S['overrun_label_available']:,}, base rate {S['overrun_rate']:.1%}.
* Months late (completed, relative to the date published at *t*): P10 {S['months_late_quantiles']['0.1']:.0f}, P50 {S['months_late_quantiles']['0.5']:.0f}, P90 {S['months_late_quantiles']['0.9']:.0f} months.

By project type (the 2018–2019 snapshots cover the baseline tab only, so the holdout is baseline upgrades):

{by_type.to_markdown()}

## 3. Models

Baselines: always-on-time (PJM's own date and cost), base rate, project-age × slip-so-far heuristic, point-in-time
owner / voltage-class / equipment rates, logistic regression on (voltage, cost, horizon), logistic regression on all
numeric features. Models: bagged LightGBM classifiers with isotonic calibration on the later quarter of the training
window (slip, cost, cancellation), LightGBM quantile regressors (P10/P50/P90 months late and % cost change), and a
discrete-time (monthly) hazard model for time-to-in-service (P(not in service by PJM's date + 12 months), median).

## 4. Benchmark (chronological holdout)

Train: observations up to **{B['cutoff']}** ({B['n_train']:,} examples, {B['train_upgrades']:,} upgrades), labels only where knowable by
the cutoff. Test: observations after the cutoff ({B['n_test']:,} examples, {B['test_upgrades']:,} upgrades, {B['n_test_new']:,} examples of
upgrades never observed before the cutoff), labels from the full record.

{main_md}

Headline: **slip > 12 months AUROC {f3(g['all']['delay'].get('auroc'))} / Brier {f3(g['all']['delay'].get('brier'))}** (base rate Brier {f3(base['all']['delay'].get('brier'))}, best
baseline `{best_base}` AUROC {f3(bb['delay'].get('auroc'))}); **cost +25 % AUROC {f3(g['all']['overrun'].get('auroc'))} / Brier {f3(g['all']['overrun'].get('brier'))}** (base rate
{f3(base['all']['overrun'].get('brier'))}, best baseline {f3(bb['overrun'].get('auroc'))}); completion-month MAE {g['all'].get('cod_mae_months_model', float('nan')):.1f} months for the model P50 vs
{g['all'].get('cod_mae_months_iso', float('nan')):.1f} for PJM's published date; P50 coverage {g['all']['months_late'].get('cov_p50', float('nan')):.2f}, P90 coverage {g['all']['months_late'].get('cov_p90', float('nan')):.2f}.
Cancellation AUROC: {f3((g['all'].get('cancel') or {}).get('auroc'))}.

**Upgrades unseen before the cutoff**: slip AUROC {f3(g['new_upgrades']['delay'].get('auroc'))}, cost AUROC {f3(g['new_upgrades']['overrun'].get('auroc'))}
(n = {g['new_upgrades']['delay'].get('n')}). Most of the skill comes from an upgrade's own public history (how long it has been
listed, how often its date moved, its owner's track record); for a brand-new upgrade the model is only modestly better
than the baselines.

### Breakdowns (GBM, slip label)

By transmission owner:

{bd('to')}

By voltage class:

{bd('voltage_class')}

By cost estimate:

{bd('cost_bucket')}

By horizon to the published in-service date:

{bd('horizon_bucket')}

By status at observation:

{bd('status')}

Cost label by owner:

{bd('to', 'overrun')}

### Feature importance (gain, slip model)

{pd.Series(B['feature_importance']['delay_12m']).sort_values(ascending=False).head(15).round(0).to_markdown()}

## 5. Case studies

{cases_md.split(chr(10), 1)[1] if cases_md else '(run scripts/04_case_studies.py)'}

## 6. Prototype

* CLI: `python scripts/predict_cli.py <upgrade id> --as-of YYYY-MM-DD` or `--custom '{{...}}'` — prints PJM's date and
  cost, model P50/P90 completion, P(slip), cost range, P(cost +25 %), P(cancelled), risk drivers and resolved analogs.
* Page: `outputs/ui/index.html` (built by `scripts/05_build_ui.py`) — every holdout example, searchable, with the same
  fields and a "reveal what happened" control.

## 7. Limits and what would change the picture

* Coverage is baseline upgrades in the holdout and 2015–2019 observation dates; network and supplemental upgrades are
  in training only through the 2016–2017 XML files. Snapshot density is uneven (monthly in 2016–2017, quarterly later).
* Between the last archived snapshot (2019-12) and the live export (2026-09) there is no intermediate public snapshot,
  so cost paths after 2019 are unobserved (labels still resolve via the 2026 record).
* PJM's in-service dates lag or refer to partial energisations for some multi-part upgrades; owner-level results for
  small owners are noisy.
* Labels are relative to PJM's published date at *t*, which is itself revised; the "slip" is measured against what the
  public could see then, which is the deployment-relevant quantity.
* Private data that would help most: TO construction schedules and milestone reports, permitting dockets, procurement
  lead times, and the RTEP cost/scope change memos in structured form.
"""
(ROOT / "REPORT.md").write_text(md)
print("REPORT.md written", len(md))
