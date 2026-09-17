"""Build the static prototype interface (docs/index.html): precomputed predictions for a grid of
substations x project types x sizes, rendered by a small vanilla-JS page. The page states
plainly that it is a research prototype on a simulated ISO over public topology."""
from __future__ import annotations
import json
import sys
import time
import numpy as np
import pandas as pd
from .. import config as C
from .predict import Predictor

SIZES = {"gen": [100, 400], "battery": [100, 300], "load": [150, 600]}
AS_OF = pd.Timestamp("2026-01-01")


def select_substations(pub, n_active: int = 120, n_random: int = 30, seed: int = 3) -> list[int]:
    q = pub.queue
    act = q.groupby("poi_sub_id").mw.sum().sort_values(ascending=False)
    chosen = list(act.index[:n_active].astype(int))
    rng = np.random.default_rng(seed)
    rest = pub.subs[(pub.subs.max_kv >= 230) & (~pub.subs.sub_id.isin(chosen))]
    chosen += list(rng.choice(rest.sub_id.values, size=min(n_random, len(rest)), replace=False).astype(int))
    return chosen


def _record(r, fidx):
    return dict(
        kv=int(r["project"]["poi_kv"]), seen=int(r["project"]["seen_poi"]), nc=r["project"]["n_candidates"],
        d=[round(r["difficulty"]["expected_constraints"], 2), round(r["difficulty"]["p_no_constraint"], 3), r["difficulty"]["label"], round(r["difficulty"]["mean_bag_sd_top10"], 3)],
        c=[round(v, 3) for v in r["cost_bucket_probs"].values()] if r["cost_bucket_probs"] else None,
        r=[[fidx(x["fid"], x["display"], x["fac_kv"]), round(float(x["p"]), 3), round(float(x["sd"]), 3), round(float(x["dist_km"]), 1), x["evidence"][:3]] for x in r["ranked"]],
        a=[[a["project_id"], a["distance_km"], a["mw"], a["project_type"], a["fuel"], a["poi"], a["published"], a["n_facilities"],
            round(a["cost_usd"] / 1e6, 1) if a["cost_usd"] is not None else None, a["facilities"][:3]] for a in r["analogs"]])


def build_shard(shard: int, n_shards: int, limit: int | None = None):
    """Compute predictions for every n_shards-th substation; write docs/ui_shard_<k>.json.
    Shards are independent OS processes (multiprocessing pools deadlock with LightGBM/OpenMP after fork)."""
    P = Predictor()
    for m in P.model.models:
        m.set_params(n_jobs=1)
    subs = select_substations(P.pub)
    if limit:
        subs = subs[:limit]
    subs = subs[shard::n_shards]
    fac_list: list[dict] = []; fac_names: dict[str, int] = {}

    def fidx(fid, display, kv):
        if fid not in fac_names:
            fac_names[fid] = len(fac_list); fac_list.append(dict(id=fid, n=display, kv=int(kv)))
        return fac_names[fid]

    records = {}; t = time.time()
    for i, s in enumerate(subs):
        for ptype, sizes in SIZES.items():
            for mw in sizes:
                try:
                    r = P.predict(int(s), ptype, mw, AS_OF, top_k=10, n_analogs=4)
                except Exception as e:  # noqa
                    print("skip", s, ptype, mw, e, flush=True); continue
                records[f"{s}|{ptype}|{mw}"] = _record(r, fidx)
        if i % 5 == 0:
            print(f"shard {shard}: {i}/{len(subs)} substations, {time.time()-t:.0f}s", flush=True)
    (C.ROOT / "docs" / f"ui_shard_{shard}.json").write_text(json.dumps(dict(facilities=fac_list, records=records), separators=(",", ":")))
    print(f"shard {shard} done: {len(records)} records", flush=True)


def build(limit: int | None = None, n_shards: int = 3):
    """Merge shard files into docs/index.html (run after all shards finished)."""
    P = Predictor()
    pub = P.pub
    subs = select_substations(pub)
    if limit:
        subs = subs[:limit]
    fac_list: list[dict] = []; fac_names: dict[str, int] = {}
    records = {}
    for k in range(n_shards):
        d = json.loads((C.ROOT / "docs" / f"ui_shard_{k}.json").read_text())
        remap = {}
        for j, f in enumerate(d["facilities"]):
            if f["id"] not in fac_names:
                fac_names[f["id"]] = len(fac_list); fac_list.append(f)
            remap[j] = fac_names[f["id"]]
        for key, rec in d["records"].items():
            rec["r"] = [[remap[x[0]]] + x[1:] for x in rec["r"]]
            records[key] = rec
    subs = [s for s in subs if any(k.startswith(f"{s}|") for k in records)]
    cost_labels = list(next(iter(v for v in records.values() if v["c"]))["c"]) and P.cost_model["labels"] if P.cost_model else []
    sub_meta = pub.subs.set_index("sub_id").loc[subs][["name", "state", "max_kv", "lat", "lon"]]
    sub_meta["n_queue"] = pub.queue.groupby("poi_sub_id").size().reindex(subs).fillna(0).astype(int).values
    sub_meta["n_studied"] = pub.study_index.merge(pub.queue, on="project_id").groupby("poi_sub_id").size().reindex(subs).fillna(0).astype(int).values
    bench = pd.read_csv(C.TABLES / "benchmark_queue.csv", index_col=0)
    meta = json.load(open(C.TABLES / "benchmark_meta_queue.json"))
    headline = dict(hit5=round(float(bench.loc["MAIN_all_features", "hit@5"]), 3), hit10=round(float(bench.loc["MAIN_all_features", "hit@10"]), 3),
                    recall10=round(float(bench.loc["MAIN_all_features", "recall@10"]), 3), mrr=round(float(bench.loc["MAIN_all_features", "mrr"]), 3),
                    ece=round(float(bench.loc["MAIN_all_features", "ece"]), 3),
                    best_base=meta["best_baseline"], best_base_hit5=round(float(bench.loc[meta["best_baseline"], "hit@5"]), 3),
                    n_test=meta["n_test_projects"], ceiling=round(meta["candidate_ceiling"], 3), train_end=C.TRAIN_END, valid_end=C.VALID_END)
    data = dict(as_of=str(AS_OF.date()), sizes=SIZES, cost_labels=cost_labels, facilities=fac_list, records=records, headline=headline,
                subs=[dict(id=int(s), name=str(m.name), state=str(m.state), kv=int(m.max_kv), nq=int(m.n_queue), ns=int(m.n_studied)) for s, m in sub_meta.iterrows()])
    (C.ROOT / "docs" / "ui_data.json").write_text(json.dumps(data, separators=(",", ":")))
    html = (C.ROOT / "gridconstraint" / "app" / "ui_template.html").read_text()
    page = html.replace("/*__DATA__*/null", json.dumps(data, separators=(",", ":")))
    (C.ROOT / "docs" / "index.html").write_text(page)
    print("wrote docs/index.html", f"{len(page)/1e6:.1f} MB", "records", len(records))


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "shard":
        build_shard(int(sys.argv[2]), int(sys.argv[3]), limit=int(sys.argv[4]) if len(sys.argv) > 4 else None)
    elif len(sys.argv) > 1 and sys.argv[1] == "merge":
        build(n_shards=int(sys.argv[2]) if len(sys.argv) > 2 else 3)
    else:
        build()
