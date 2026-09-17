"""Post-process the exported world: clean substation names (strip voltage tokens etc.) and
re-render every public field that carries a facility/substation name. Idempotent."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np, pandas as pd
from gridconstraint import config as C
from gridconstraint.sim.naming import _clean, noisy_facility_name

W, P = C.WORLD, C.PUBLIC
subs = pd.read_csv(W / "substations.csv")
used = set(); names = []
for i, n in enumerate(subs.name.fillna("")):
    c = _clean(n) or f"Sub {int(subs.sub_id[i])}"
    base = c; k = 2
    while c.lower() in used:
        c = f"{base} {k}"; k += 1
    used.add(c.lower()); names.append(c)
n_changed = int((pd.Series(names) != subs.name.fillna("")).sum())
subs["name"] = names
subs.to_csv(W / "substations.csv", index=False)
pub = subs[~subs.external.astype(bool)][["sub_id", "name", "lat", "lon", "state", "zone_id", "max_kv", "min_kv"]]
pub.to_csv(P / "substations.csv", index=False)
nm = dict(zip(subs.sub_id.astype(int), subs.name))
q = pd.read_csv(P / "queue.csv")
q["poi_name"] = [f"{nm[int(s)]} {int(k)} kV" for s, k in zip(q.poi_sub_id, q.poi_kv)]
q.to_csv(P / "queue.csv", index=False)
fac = pd.read_csv(W / "branches.csv"); circ = dict(zip(fac.branch, fac.circuit))
facall = pd.read_csv(W / "facilities_all.csv"); ncirc = dict(zip(facall.fid, facall.n_circuits))
mc = pd.read_csv(W / "market_constraints_truth.csv")
if len(mc):
    rng = np.random.default_rng(7); cache = {}
    for b in mc.branch.unique():
        fid = fac.fid.values[b]
        cache[b] = noisy_facility_name(fid, nm, rng, circuit=circ[b] if ncirc.get(fid, 1) > 1 else None, style=dict(kv_fmt="{kv} KV", case="upper", sep=" - "))
    mc["constraint_name"] = mc.branch.map(cache)
    mc.to_csv(W / "market_constraints_truth.csv", index=False)
    mc[["datetime", "constraint_name", "shadow_price", "flow_mw"]].to_csv(P / "market_constraints.csv", index=False)
ot = pd.read_csv(W / "outages_truth.csv")
if len(ot):
    rng = np.random.default_rng(11)
    ot["facility_name"] = [noisy_facility_name(f, nm, rng, circuit=circ[b], style=dict(kv_fmt="{kv} kV", case="title", sep=" - ")) for f, b in zip(ot.fid, ot.branch)]
    ot.to_csv(W / "outages_truth.csv", index=False)
    ot[["facility_name", "start", "end", "reason"]].to_csv(P / "outages.csv", index=False)
ul = pd.read_csv(W / "upgrades.csv")
bl = ul[ul.project_id == "BASELINE"].copy()
if len(bl):
    rng = np.random.default_rng(13)
    bl["facility_name"] = [noisy_facility_name(f, nm, rng, circuit=circ[b], style=dict(kv_fmt="{kv} kV", case="title", sep=" - ")) for f, b in zip(bl.fid, bl.branch)]
    bl[["date", "facility_name"]].assign(upgrade="baseline reliability upgrade").to_csv(P / "baseline_upgrades.csv", index=False)
print("names finalized:", len(subs), "substations;", n_changed, "changed")
