"""Build the simulated ISO world (hidden planning case + public observables). ~40 min on 4 cores."""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gridconstraint import config as C
from gridconstraint.sim.world import World

if __name__ == "__main__":
    t = time.time()
    w = World(seed=C.SEED, start_year=C.SIM_START_YEAR, end_year=C.SIM_END_YEAR, arrival_scale=1.0,
              market_hours_per_year=12, n_workers=4)
    w.build_queue()
    w.run()
    w.export()
    print(f"done in {(time.time()-t)/60:.1f} min; projects={len(w.projects)} studies={len(w.studies)}")
