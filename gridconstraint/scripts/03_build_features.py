"""Build the point-in-time candidate/feature table for every studied project.
as_of = queue date + 1 day (what was public when the project entered the queue)."""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np, pandas as pd
from gridconstraint import config as C
from gridconstraint.features.pit import PublicData, FeatureBuilder

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "queue"      # queue | prestudy
    pub = PublicData()
    fb = FeatureBuilder(pub)
    labels = pub.findings.groupby("project_id").apply(lambda g: dict(zip(g.fid, g.loading_pct)), include_groups=False)
    studied = pub.study_index.merge(pub.queue, on="project_id")
    t = time.time(); parts = []; cover = []
    for i, r in enumerate(studied.itertuples()):
        as_of = (r.queue_date + pd.Timedelta(days=1)) if mode == "queue" else (r.publication_date - pd.Timedelta(days=1))
        lab = labels.get(r.project_id, {})
        df = fb.build(pub.q_by_pid.loc[r.project_id].rename(r.project_id).to_frame().T.assign(project_id=r.project_id).iloc[0], as_of, lab)
        df["project_id"] = r.project_id
        parts.append(df)
        cover.append(dict(project_id=r.project_id, n_cand=len(df), n_label=len(lab), n_label_in_cand=int(df.y.sum()) if len(lab) else 0))
        if i % 200 == 0:
            print(f"{i}/{len(studied)} {time.time()-t:.0f}s", flush=True)
    X = pd.concat(parts, ignore_index=True)
    X.to_parquet(C.PROCESSED / f"features_{mode}.parquet", index=False)
    cv = pd.DataFrame(cover); cv.to_csv(C.PROCESSED / f"candidate_coverage_{mode}.csv", index=False)
    tot = cv.n_label.sum(); print("rows", len(X), "projects", cv.project_id.nunique(), "label coverage (candidate recall ceiling)",
                                  round(cv.n_label_in_cand.sum() / max(1, tot), 3), "mean candidates", round(cv.n_cand.mean(), 1))
