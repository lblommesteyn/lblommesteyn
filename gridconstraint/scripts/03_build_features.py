"""Build the point-in-time candidate/feature table for every studied project.
mode=queue    : as_of = queue date + 1 day (strict prospective setting)
mode=prestudy : as_of = study publication date - 1 day (everything public before the study)
Parallel over projects (fork; PublicData is read-only)."""
import sys, time
from pathlib import Path
from multiprocessing import get_context
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np, pandas as pd
from gridconstraint import config as C
from gridconstraint.features.pit import PublicData, FeatureBuilder

_PUB = None; _MODE = "queue"; _LABELS = None; _STUDIED = None


def _work(idx_list):
    fb = FeatureBuilder(_PUB)
    parts, cover = [], []
    for i in idx_list:
        r = _STUDIED.iloc[i]
        as_of = (r.queue_date + pd.Timedelta(days=1)) if _MODE == "queue" else (r.publication_date - pd.Timedelta(days=1))
        lab = _LABELS.get(r.project_id, {})
        proj = _PUB.q_by_pid.loc[r.project_id].copy(); proj["project_id"] = r.project_id
        df = fb.build(proj, as_of, lab)
        df["project_id"] = r.project_id
        parts.append(df)
        cover.append(dict(project_id=r.project_id, n_cand=len(df), n_label=len(lab), n_label_in_cand=int(df.y.sum()) if len(lab) else 0))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(), cover


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "queue"
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    pub = PublicData()
    labels = pub.findings.groupby("project_id").apply(lambda g: dict(zip(g.fid, g.loading_pct)), include_groups=False).to_dict()
    studied = pub.study_index.merge(pub.queue, on="project_id")
    _PUB, _MODE, _LABELS, _STUDIED = pub, mode, labels, studied
    chunks = [list(range(i, len(studied), workers)) for i in range(workers)]
    t = time.time()
    with get_context("fork").Pool(workers) as pool:
        results = pool.map(_work, chunks)
    X = pd.concat([r[0] for r in results], ignore_index=True)
    cover = [c for r in results for c in r[1]]
    X.to_parquet(C.PROCESSED / f"features_{mode}.parquet", index=False)
    cv = pd.DataFrame(cover); cv.to_csv(C.PROCESSED / f"candidate_coverage_{mode}.csv", index=False)
    tot = cv.n_label.sum()
    print(f"rows {len(X)} projects {cv.project_id.nunique()} label coverage (candidate recall ceiling) {cv.n_label_in_cand.sum()/max(1,tot):.3f} "
          f"mean candidates {cv.n_cand.mean():.1f} time {time.time()-t:.0f}s")
