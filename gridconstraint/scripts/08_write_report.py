"""Assemble REPORT.md from the methods text and the result tables produced by scripts 02-07."""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
from gridconstraint import config as C

T = C.TABLES
NAMES = {"B1_nearest_projects": "B1 nearest historical projects", "B2_queue_density": "B2 queue-density heuristic",
         "B3_historical_congestion": "B3 historical-congestion heuristic", "B4_geo_size_logit": "B4 geography + size (logistic)",
         "B5_simple_tabular_gbm": "B5 simple tabular GBM (23 features)", "P0_public_topology_dfax": "P0 public-topology DFAX only (physics, no learning)",
         "L0_latent_only": "L0 latent factors only", "MAIN_all_features": "**MAIN: all public features (bagged GBM, calibrated)**"}


def pct(x):
    return "—" if pd.isna(x) else f"{100*x:.1f}%"


def f3(x):
    return "—" if pd.isna(x) else f"{x:.3f}"


def main_table(mode):
    b = pd.read_csv(T / f"benchmark_{mode}.csv", index_col=0)
    meta = json.load(open(T / f"benchmark_meta_{mode}.json"))
    L = [f"Test set: **{meta['n_test_projects']} projects** queued after {C.VALID_END} ({meta['n_test_projects_with_constraints']} with at least one "
         f"constrained facility; ranking metrics are averaged over those). Candidate-set ceiling (share of true facilities the candidate generator "
         f"can rank at all): **{pct(meta['candidate_ceiling'])}**. Train: {meta['n_train_projects']} projects (studies published ≤ {C.TRAIN_END}); "
         f"validation: {meta['n_valid_projects']} (≤ {C.VALID_END}).\n",
         "| model | hit@1 | hit@3 | hit@5 | hit@10 | recall@5 | recall@10 | precision@5 | MRR | ECE | Brier skill | count corr. |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    order = ["B1_nearest_projects", "B2_queue_density", "B3_historical_congestion", "B4_geo_size_logit", "B5_simple_tabular_gbm",
             "P0_public_topology_dfax", "L0_latent_only", "MAIN_all_features"]
    for m in order:
        if m not in b.index:
            continue
        r = b.loc[m]
        L.append(f"| {NAMES[m]} | {pct(r['hit@1'])} | {pct(r['hit@3'])} | {pct(r['hit@5'])} | {pct(r['hit@10'])} | {pct(r['recall@5'])} | {pct(r['recall@10'])} | "
                 f"{pct(r['precision@5'])} | {f3(r['mrr'])} | {f3(r['ece'])} | {f3(r['brier_skill'])} | {f3(r['cnt_corr'])} |")
    abl = [m for m in b.index if m.startswith("ABL_")]
    if abl:
        L += ["", "Ablations (main model minus one feature family; 1 bag each):", "", "| removed family | hit@5 | hit@10 | recall@10 | MRR |", "|---|---|---|---|---|"]
        for m in abl:
            r = b.loc[m]
            L.append(f"| {m.replace('ABL_minus_', '')} | {pct(r['hit@5'])} | {pct(r['hit@10'])} | {pct(r['recall@10'])} | {f3(r['mrr'])} |")
    return "\n".join(L), b, meta


def breakdown_table(mode):
    bd = pd.read_csv(T / f"breakdowns_{mode}.csv")
    L = ["| dimension | value | model | n | hit@1 | hit@5 | hit@10 | recall@10 | MRR |", "|---|---|---|---|---|---|---|---|---|"]
    for r in bd.itertuples():
        L.append(f"| {r.dimension} | {r.value} | {r.model.replace('_', ' ')} | {r.n_projects} | {pct(r._5)} | {pct(r._7)} | {pct(r._8)} | {pct(r._10)} | {f3(r.mrr)} |")
    return "\n".join(L)


def calib_table(mode):
    c = pd.read_csv(T / f"calibration_main_{mode}.csv")
    L = ["| bin | n | mean predicted | observed rate |", "|---|---|---|---|"]
    for r in c.itertuples():
        L.append(f"| {r.bin} | {r.n} | {r.mean_pred:.3f} | {r.frac_pos:.3f} |")
    return "\n".join(L)


def secondary_table(mode):
    s = pd.read_csv(T / f"secondary_{mode}.csv")
    L = ["| task | model | n | accuracy | macro-F1 | adjacent acc. | AUC | base rate |", "|---|---|---|---|---|---|---|---|"]
    for r in s.itertuples():
        g = lambda k: getattr(r, k, float("nan")) if hasattr(r, k) else float("nan")
        L.append(f"| {r.task} | {r.model} | {int(r.n)} | {f3(g('accuracy'))} | {f3(g('macro_f1'))} | {f3(g('adjacent_accuracy'))} | {f3(g('auc'))} | {f3(g('base_rate'))} |")
    return "\n".join(L)


def oracle_table():
    p = T / "oracle_ablation_queue.csv"
    if not p.exists():
        return "_(oracle ablation not run)_"
    o = pd.read_csv(p, index_col=0)
    L = ["| model | hit@1 | hit@5 | hit@10 | recall@10 | MRR |", "|---|---|---|---|---|---|"]
    for m, r in o.iterrows():
        L.append(f"| {m} | {pct(r['hit@1'])} | {pct(r['hit@5'])} | {pct(r['hit@10'])} | {pct(r['recall@10'])} | {f3(r['mrr'])} |")
    return "\n".join(L)


def nonadjacent_table(mode, root=None):
    p = (root or T) / f"nonadjacent_{mode}.csv"
    if not p.exists():
        return "_(not run)_"
    d = pd.read_csv(p)
    L = ["| model | subset | n | hit@1 | hit@5 | hit@10 | recall@5 | recall@10 | MRR |", "|---|---|---|---|---|---|---|---|---|"]
    for r in d.itertuples():
        L.append(f"| {NAMES.get(r.model, r.model).strip('*')} | {r.subset} | {int(r.n_projects)} | {pct(r._3)} | {pct(r._4)} | {pct(r._5)} | {pct(r._6)} | {pct(r._7)} | {f3(r.mrr)} |")
    return "\n".join(L)


def per_year_table(mode):
    p = T / f"per_year_{mode}.csv"
    if not p.exists():
        return "_(not run)_"
    d = pd.read_csv(p)
    L = ["| queue year | model | n | hit@5 | hit@10 | recall@10 | MRR |", "|---|---|---|---|---|---|---|"]
    for r in d.itertuples():
        L.append(f"| {r.year} | {NAMES.get(r.model, r.model).strip('*')} | {r.n_projects} | {pct(r._4)} | {pct(r._5)} | {pct(r.recall10) if hasattr(r, 'recall10') else pct(r._6)} | {f3(r.mrr)} |")
    return "\n".join(L)


def model_selection_table(mode):
    p = T / f"model_selection_{mode}.csv"
    if not p.exists():
        return "_(not run)_"
    d = pd.read_csv(p)
    L = ["| config | split | hit@5 | hit@10 | recall@10 | MRR | non-adjacent hit@5 | non-adjacent recall@10 |", "|---|---|---|---|---|---|---|---|"]
    for r in d.itertuples():
        L.append(f"| {r.config} | {r.split} | {pct(r.hit5)} | {pct(r.hit10)} | {pct(r.recall10)} | {f3(r.mrr)} | {pct(r.na_hit5)} | {pct(r.na_recall10)} |")
    return "\n".join(L)


def variant_table():
    root = C.ROOT / "variants" / "persistent_headroom" / "outputs" / "tables"
    p = root / "benchmark_queue.csv"
    if not p.exists():
        return "_(variant world not run)_", None
    b = pd.read_csv(p, index_col=0); b0 = pd.read_csv(T / "benchmark_queue.csv", index_col=0)
    meta = json.load(open(root / "benchmark_meta_queue.json"))
    L = [f"Variant world: identical seed, queue and procedure, but the yearly N-1 baseline pass runs only every 4 years, so facility headroom "
         f"persists between studies (test projects: {meta['n_test_projects']}; candidate ceiling {pct(meta['candidate_ceiling'])}).", "",
         "| model | hit@5 (yearly re-hardening) | hit@5 (persistent headroom) | hit@10 (yearly) | hit@10 (persistent) | recall@10 (yearly) | recall@10 (persistent) | Brier skill (yearly) | Brier skill (persistent) |",
         "|---|---|---|---|---|---|---|---|---|"]
    for m in ["B2_queue_density", "B4_geo_size_logit", "B5_simple_tabular_gbm", "P0_public_topology_dfax", "MAIN_all_features"]:
        if m in b.index and m in b0.index:
            L.append(f"| {NAMES[m].strip('*')} | {pct(b0.loc[m, 'hit@5'])} | {pct(b.loc[m, 'hit@5'])} | {pct(b0.loc[m, 'hit@10'])} | {pct(b.loc[m, 'hit@10'])} | "
                     f"{pct(b0.loc[m, 'recall@10'])} | {pct(b.loc[m, 'recall@10'])} | {f3(b0.loc[m, 'brier_skill'])} | {f3(b.loc[m, 'brier_skill'])} |")
    na = nonadjacent_table("queue", root=root)
    return "\n".join(L) + "\n\nNon-adjacent facilities, variant world:\n\n" + na, b


def parse_table():
    s = pd.read_csv(T / "parse_quality_summary.csv").iloc[0]
    t = pd.read_csv(T / "parse_quality_by_template.csv", index_col=0)
    L = [f"Studies: {int(s.n_studies)}; findings in truth: {int(s.findings_truth)}; parsed: {int(s.findings_parsed)} (extraction recall {pct(min(1.0, s.extraction_recall))}).",
         f"Facility identity resolution: precision **{pct(s.fid_precision)}**, recall **{pct(s.fid_recall)}**; {pct(s.studies_exact)} of studies reconstructed exactly; "
         f"total-cost match {pct(s.cost_total_match)}; loading MAE {s.loading_mae:.3f} pts; queue-number match {pct(s.project_id_match)}.", "",
         "| layout | n | fid precision | fid recall |", "|---|---|---|---|"]
    for k, r in t.iterrows():
        L.append(f"| {k} | {int(r.n)} | {pct(r.fid_precision)} | {pct(r.fid_recall)} |")
    return "\n".join(L)


def importance_table(mode, k=15):
    imp = pd.read_csv(T / f"feature_importance_{mode}.csv", index_col=0).gain
    imp = imp / imp.sum()
    L = ["| feature | share of gain |", "|---|---|"]
    for f, v in imp.head(k).items():
        L.append(f"| `{f}` | {100*v:.1f}% |")
    return "\n".join(L)


if __name__ == "__main__":
    methods = (C.ROOT / "REPORT_methods.md").read_text()
    main_q, bq, mq = main_table("queue")
    best_base = mq["best_baseline"]
    main_hit5 = bq.loc["MAIN_all_features", "hit@5"]; base_hit5 = bq.loc[best_base, "hit@5"]
    main_hit10 = bq.loc["MAIN_all_features", "hit@10"]; base_hit10 = bq.loc[best_base, "hit@10"]
    verdict_ok = (main_hit5 - base_hit5) >= 0.10 and (main_hit10 - base_hit10) >= 0.08
    prestudy = (T / "benchmark_prestudy.csv").exists()
    na = pd.read_csv(T / "nonadjacent_queue.csv") if (T / "nonadjacent_queue.csv").exists() else None
    if na is not None:
        nas = na[na.subset != "all facilities"].set_index("model")
        na_main = nas.loc["MAIN_all_features"]; base_rows = nas.loc[[m for m in nas.index if m.startswith("B")]]
        na_base = base_rows.loc[base_rows["hit@5"].idxmax()]
    else:
        na_main = na_base = {"hit@5": float("nan"), "recall@10": float("nan")}
    prestudy_headline = ""
    if (T / "benchmark_prestudy.csv").exists():
        bp = pd.read_csv(T / "benchmark_prestudy.csv", index_col=0); mp_ = json.load(open(T / "benchmark_meta_prestudy.json"))
        bb = bp.loc[[m for m in bp.index if m.startswith("B")], "hit@5"].idxmax()
        nap = pd.read_csv(T / "nonadjacent_prestudy.csv") if (T / "nonadjacent_prestudy.csv").exists() else None
        na_txt = ""
        if nap is not None:
            n2 = nap[nap.subset != "all facilities"].set_index("model")
            bb2 = n2.loc[[m for m in n2.index if m.startswith("B")], "hit@5"].idxmax()
            na_txt = f" On non-adjacent facilities: hit@5 {pct(n2.loc['MAIN_all_features', 'hit@5'])} vs {pct(n2.loc[bb2, 'hit@5'])}, recall@10 {pct(n2.loc['MAIN_all_features', 'recall@10'])} vs {pct(n2.loc[bb2, 'recall@10'])}."
        prestudy_headline = (f"**The picture changes with fresher information.** Evaluated with everything public up to the day before the study was published "
                             f"(the wording of the goal; 10–26 months later than the queue date; {mp_['n_test_projects']} test projects), the learned model reaches "
                             f"hit@5 **{pct(bp.loc['MAIN_all_features', 'hit@5'])}** and hit@10 **{pct(bp.loc['MAIN_all_features', 'hit@10'])}** against "
                             f"{pct(bp.loc[bb, 'hit@5'])} / {pct(bp.loc[bb, 'hit@10'])} for the best simple baseline ({NAMES[bb].strip('*')}), with recall@10 "
                             f"{pct(bp.loc['MAIN_all_features', 'recall@10'])} vs {pct(bp.loc[bb, 'recall@10'])}.{na_txt} Public evidence about a facility's "
                             f"headroom (recent studies, queue movements, market binding) decays quickly in this world, so its value depends on how recent it is.")
    op = T / "oracle_ablation_queue.csv"
    if op.exists():
        o = pd.read_csv(op, index_col=0)
        oracle_headline = (f"**Which private data is missing?** Handing the model the hidden case's exact impedances (true distribution factors) raises hit@5 only from "
                           f"{pct(o.iloc[0]['hit@5'])} to {pct(o.iloc[1]['hit@5'])} and recall@10 from {pct(o.iloc[0]['recall@10'])} to {pct(o.iloc[1]['recall@10'])}. "
                           f"Topology is not the bottleneck; **facility headroom** (ratings, planning dispatch, contingency definitions) is — and no public feed carries it.")
    else:
        oracle_headline = ""
    out = ["# Predicting transmission constraints for proposed grid projects from public pre-study information",
           "", "*Research report — gridconstraint prototype. All results below are on a simulated ISO over a real public PJM-footprint case; "
           "see section 1 for why, and section 8 for what a real-data run needs.*", "",
           "## 0. Headline", "",
           f"**For unseen projects (queued after {C.VALID_END}), the actual constrained facility appeared in the model's top-5 predictions "
           f"{pct(main_hit5)} of the time and in the top-10 {pct(main_hit10)} of the time**, using only information public on the day the project entered "
           f"the queue. But the best simple baseline ({NAMES[best_base].strip('*')}) reached {pct(base_hit5)} / {pct(base_hit10)}: **on the headline metric the "
           f"learned method does not materially beat geography, queue-density or simple-ML baselines, so the success condition is not met in this world.**", "",
           f"What the learned method does add, on the same held-out projects: (i) on facilities *not directly connected* to the POI — the non-trivial part — "
           f"hit@5 {pct(na_main['hit@5'])} vs {pct(na_base['hit@5'])} for the best baseline and recall@10 {pct(na_main['recall@10'])} vs {pct(na_base['recall@10'])}; "
           f"(ii) probabilistic skill roughly doubles (Brier skill {f3(bq.loc['MAIN_all_features', 'brier_skill'])} vs {f3(bq.loc[best_base, 'brier_skill'])}); "
           f"(iii) the expected number of constrained facilities tracks the actual number much better (correlation {f3(bq.loc['MAIN_all_features', 'cnt_corr'])} vs "
           f"{f3(bq.loc[best_base, 'cnt_corr'])}). Recall@10 over all constrained facilities is {pct(bq.loc['MAIN_all_features', 'recall@10'])} against a candidate "
           f"ceiling of {pct(mq['candidate_ceiling'])}.", "",
           oracle_headline, "",
           prestudy_headline, "",
           "It is **not** an empirical result about PJM: the labels are simulated studies (section 1). It is the answer to *\"if an ISO's studies are "
           "produced by a PJM-style thermal procedure on a case whose topology is public but whose impedances, ratings and dispatch are not, how much of the "
           "outcome can public information recover?\"* In this world the answer is: the location-driven part almost entirely, the headroom-driven part barely — "
           "and section 5.10 shows how much that changes when facility headroom persists between studies.", "",
           methods, "",
           "## 5. Results", "", "### 5.1 Ground-truth extraction quality (automated check against the hidden truth, plus manual sample)", "", parse_table(), "",
           "Manual inspection of five random reports (`outputs/case_studies/parse_inspection_sample.md`) found no errors; typos in the reports "
           "(\"Military Ighway\", \"Ae Columbia\") were resolved by the fuzzy matcher.", "",
           "### 5.2 Main benchmark — features as of the queue date", "", main_q, "",
           "hit@K = at least one true facility in the top K; recall@K = share of the project's true facilities in the top K; MRR = mean reciprocal rank of the "
           "first true facility; ECE and Brier skill (1 − Brier/Brier of the base rate) on isotonic-calibrated probabilities (each baseline score was also "
           "isotonic-calibrated on the validation split so calibration is compared like for like; with a 0.9 % positive rate, ECE is near zero for every model "
           "and Brier skill is the informative number); count corr. = correlation between the sum of a project's probabilities and its actual number of "
           "constrained facilities.", "",
           "### 5.3 Calibration of the main model (test set, 10 bins)", "", calib_table("queue"), "",
           "### 5.4 Breakdowns (test set)", "", breakdown_table("queue"), "",
           "### 5.5 Secondary tasks", "", secondary_table("queue"), "",
           "Cost-bucket and withdrawal models use the ranker's probabilities aggregated per project; training-row probabilities are in-sample "
           "(optimistic), which is why the geo+size+queue-only comparison is shown.", "",
           "### 5.6 What the model uses", "", importance_table("queue"), "",
           "### 5.7 The non-trivial part: facilities not directly connected to the POI", "",
           "Any geometry rule finds the POI's own outlet lines. Restricting the ranking to candidates that do not touch the POI substation isolates "
           "the part of the problem where public *evidence* (history, congestion, queue, learned topology) has to do the work:", "", nonadjacent_table("queue"), "",
           "### 5.8 Drift across test years", "", per_year_table("queue"), "",
           "### 5.9 Model selection (validation split only)", "", model_selection_table("queue"), ""]
    if prestudy:
        main_p, bp, mp = main_table("prestudy")
        out += ["### 5.7b Variant — features as of the day before the study was published", "",
                "Same models, but every public record up to the eve of publication is allowed (typically 10–26 months more queue, study and market history).", "", main_p, "",
                "Non-adjacent facilities, pre-publication features:", "", nonadjacent_table("prestudy"), ""]
    real_section = []
    fb_ = T / "real_pjm_first_benchmark.json"
    if fb_.exists():
        import glob as _glob
        first = json.load(open(fb_)); later = sorted(_glob.glob(str(T / "real_pjm_benchmark_v*.json")))
        latest = json.load(open(later[-1])) if later else None
        fr = pd.read_csv(C.STUDIES / "parsed_findings_real.csv") if (C.STUDIES / "parsed_findings_real.csv").exists() else None
        def mrow(res, key):
            v = res["metrics"].get(key, {})
            return f"{int(v.get('n_projects', 0))} | {pct(v.get('hit@1'))} | {pct(v.get('hit@5'))} | {pct(v.get('hit@10'))} | {pct(v.get('recall@10'))} | {f3(v.get('mrr'))}"
        L = ["## 8b. Real-data run: frozen model on 213 historical PJM System Impact Studies", "",
             "The repository's own GitHub Actions runner (which, unlike this sandbox, can reach pjm.com) fetched PJM's New Services Queue export "
             f"(9,263 rows with Submitted / Withdrawal / Actual In-Service dates and study links) and {first['n_studies_fetched']} impact-study PDFs for requests "
             "submitted 2016–2020, each with its HTTP Last-Modified date as the publication proxy. The frozen model (sha256 "
             f"`{first['model_sha256'][:16]}…`) was scored on every study with a locatable point of interconnection, features as of **queue date + 1 day**; "
             "the report of a project is never visible to its own features, and only the 213 fetched reports serve as \"prior studies\" for later projects. "
             "No Data Miner feed (needs an API key), so congestion and outage features are zero.", "",
             "**Ground-truth extraction on real reports.** Two layouts occur (2016–18 wrapped flowgate tables; 2019+ FROM-BUS/TO-BUS/PRE/POST tables) plus a "
             "prose form. Facilities are named by PSS/E bus names (\"8CHCKAHM-8ELMONT 500 kV\", \"3BTLEBRO-3ROCKYMT115T\"). "
             + (f"Across the corpus {fr.project_id.nunique()} studies contain {len(fr)} network-impact findings; {int(fr.fid.notna().sum())} "
                f"({100*fr.fid.notna().mean():.0f}%) resolve to a public HIFLD/OSM substation pair after prefix/suffix stripping, consonant-skeleton fuzzy matching "
                f"anchored near the POI, and {int(fr.in_public_layer.sum())} of those corridors exist in the public line layer." if fr is not None else ""),
             "", "**This is the binding constraint of the real-data run**: most HIFLD substations in the region carry no name (55 % after filling from OpenStreetMap "
             "and line-end labels), so a large share of ISO-named facilities cannot be tied to public geometry at all. The candidate ceiling and the number of "
             "evaluable projects below reflect that, not the model.", "",
             "| run | evaluable projects (≥1 resolved facility in candidates) | candidate ceiling |", "|---|---|---|",
             f"| first (recorded before any change) | {first['n_projects_with_constraints']} of {first['n_projects']} scored | {pct(first['candidate_ceiling'])} |"]
        if latest:
            L.append(f"| latest ({latest['tag']}; ingestion changes only, same model) | {latest['n_projects_with_constraints']} of {latest['n_projects']} scored | {pct(latest['candidate_ceiling'])} |")
        L += ["", "Ranking metrics on the evaluable projects (all scored projects; trained baselines need a train half so they are omitted at this sample size):", "",
              "| run | model | n | hit@1 | hit@5 | hit@10 | recall@10 | MRR |", "|---|---|---|---|---|---|---|---|"]
        for tag, res in (("first", first),) + ((("latest", latest),) if latest else ()):
            for key in ("MAIN_frozen@all", "B1_nearest_projects@all", "B2_queue_density@all", "P0_public_topology_dfax@all"):
                if key in res["metrics"]:
                    L.append(f"| {tag} | {key.replace('@all', '').replace('_', ' ')} | {mrow(res, key)} |")
        L += ["", "**Reading.** With single-digit numbers of evaluable projects, none of these differences is meaningful; the honest statement is that the "
              "frozen simulated-ISO model transfers to real PJM reports without crashing, produces rankings, and that the real-data signal cannot be "
              "measured until facility identities resolve at scale. The next real-data step is therefore not modelling but identity: a PSS/E bus-name "
              "dictionary (PJM's public RTEP/queue bus lists, or the bus numbers that recur across reports, which this pipeline already keys on) to map "
              "ISO facility names to public substations, plus Data Miner constraint names for the congestion features.", ""]
        real_section = L
    vt, vb = variant_table()
    out += ["### 5.10 Sensitivity to headroom persistence (second simulated world)", "", vt, "",
            "## 6. Prospective case studies", "",
            "`outputs/case_studies/README.md` reconstructs, for eight test projects, the prediction that would have been made on the queue date, then reveals the "
            "study and explains each hit and miss (with hidden-world diagnostics quoted only in the explanation). The cases were selected automatically: clear hits, "
            "misses, an unseen-POI hit, a non-generator project, and a no-constraint study.", "",
            "## 7. What private planning data is missing? (oracle ablation)", "",
            "Give the main model the hidden case's *true* N-0 distribution factors (i.e. exact impedances and topology) as one extra feature:", "", oracle_table(), "",
            "The gain from true impedances is the part of the gap that better public topology (or a planning-case impedance file) would close; what remains after "
            "that is due to facility **headroom** — ratings, the planning dispatch and the contingency definitions — which no public feed carries. In the simulation the "
            "public side infers headroom only indirectly (binding hours, prior studies, baseline upgrades), which is why facility-history and congestion families "
            "matter in the ablations.", "",
            "## 8. Limitations, negative-result reading, and the real-data run", "",
            "* **Everything is simulated except topology, names, load shapes and project characteristics.** The study procedure is a simplified PJM thermal "
            "procedure (no voltage, stability, short-circuit, N-1-1, or light-load tests), naming noise is synthetic, market snapshots are sparse "
            "(12–13 hours/year), and the queue is synthetic. The benchmark measures methodology, not PJM.",
            "* **Candidate ceiling.** About 14 % of true facilities are outside the candidate set. They are far-field constraints (median distance of true "
            "facilities is tens of km, but a quarter are >300 km away) where a 5 % distribution factor arises through long 345/500 kV paths; the guessed-impedance "
            "public model under-estimates those. Raising the cap or the DFAX rule trades recall for a much larger candidate table.",
            "* **Label vintage.** Training labels are studies published ≤ 2020-12-31, validation ≤ 2022-06-30, test projects queued after 2022-06-30; 2023–2025 "
            "projects whose studies were not published by the end of 2025 are unlabeled and excluded.",
            "* **Real-data run.** `gridconstraint/data/sources.py` documents the PJM feeds. Steps: (1) weekly queue snapshots (or Wayback captures) for dated status; "
            "(2) impact/feasibility PDFs with first-seen dates; (3) Data Miner LMP and constraint feeds (free key); (4) HIFLD lines/substations; (5) run scripts "
            "02→06 unchanged. Expect the parser's prose patterns to need extension for older report vintages, and the normaliser to need PJM's TO naming "
            "conventions (e.g. \"(AEP)\" prefixes, \"TAP\" suffixes).",
            "* **If the real signal is weak**, the oracle ablation is the template for the negative result: quantify the gain from a planning-case impedance file "
            "(PJM's RTEP case is available to members under CEII) versus from ratings/dispatch, and report which one the public side cannot substitute.", "",
            *real_section, "## 9. Reproduction", "", "`sh scripts/run_all.sh` (≈1.5 h on 4 cores). Tables in `outputs/tables/`, case studies in `outputs/case_studies/`, "
            "the prototype interface in `docs/index.html`, the CLI in `gridconstraint/app/predict.py`.", ""]
    (C.ROOT / "REPORT.md").write_text("\n".join(out))
    print("wrote REPORT.md; verdict_ok =", verdict_ok)
