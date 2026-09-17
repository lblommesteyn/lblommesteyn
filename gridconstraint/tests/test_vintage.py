"""Vintage-leak guard: features computed with full tables must equal features computed from
tables physically truncated at as_of. Also checks the PIT accessors reject future rows."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np, pandas as pd
from gridconstraint.features.pit import PublicData, FeatureBuilder, PITView


def test_vintage_invariance(n_projects: int = 12):
    pub = PublicData(verbose=False)
    studied = pub.study_index.merge(pub.queue, on="project_id").sample(n_projects, random_state=0)
    for r in studied.itertuples():
        as_of = r.queue_date + pd.Timedelta(days=1)
        proj = pub.q_by_pid.loc[r.project_id].copy(); proj["project_id"] = r.project_id
        full = FeatureBuilder(pub).build(proj, as_of)
        cut = FeatureBuilder(pub.truncated(as_of)).build(proj, as_of)
        num = full.select_dtypes(include=[np.number]).columns
        assert list(full.fid) == list(cut.fid), "candidate sets differ"
        diff = (full[num].fillna(-1) - cut[num].fillna(-1)).abs().max()
        assert float(diff.max()) < 1e-9, f"feature values depend on future rows: {diff[diff > 1e-9]}"


def test_guard_rejects_future():
    pub = PublicData(verbose=False)
    v = PITView(pub, pd.Timestamp("2015-06-01"))
    assert (v.findings().publication_date < pd.Timestamp("2015-06-01")).all()
    assert (v.constraints().datetime < pd.Timestamp("2015-06-01")).all()
    assert (v.queue().queue_date < pd.Timestamp("2015-06-01")).all()


if __name__ == "__main__":
    test_vintage_invariance(); test_guard_rejects_future(); print("vintage tests passed")
