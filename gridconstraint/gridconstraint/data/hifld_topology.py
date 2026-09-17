"""Build a real public PJM topology from the HIFLD transmission-line tiles (public domain).

Input: the TransmissionMap mirror of HIFLD lines as PMTiles (gzip-compressed Mapbox vector
tiles) with fields ID, OWNER, STATUS, SUB_1, SUB_2, TYPE, VOLTAGE, VOLT_CLASS, plus the HIFLD
substation layer (name, kV, coordinates). Output: substations.csv / facilities.csv in the same
schema the frozen pipeline uses (L:<subA>:<subB>:<kV> corridors), restricted to the PJM states.
This is the real-data counterpart of the simulated world's public layer.
"""
from __future__ import annotations
import gzip
import math
import re
import numpy as np
import pandas as pd
from pmtiles.reader import Reader, MmapSource
import mapbox_vector_tile
from scipy.spatial import cKDTree
from ..sim.naming import to_xy_km

PJM_STATES = {"Pennsylvania", "New Jersey", "Maryland", "Delaware", "Virginia", "West Virginia", "Ohio", "Kentucky", "Indiana", "Illinois",
              "Michigan", "North Carolina", "Tennessee", "District of Columbia"}
PJM_BBOX = (-90.5, 34.5, -73.5, 43.5)   # lon_min, lat_min, lon_max, lat_max (generous)


def _tiles_for_bbox(z, bbox):
    def t(lon, lat):
        n = 2 ** z
        x = int((lon + 180) / 360 * n)
        y = int((1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n)
        return x, y
    x0, y1 = t(bbox[0], bbox[1]); x1, y0 = t(bbox[2], bbox[3])
    return [(z, x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]


def _decode(data):
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    return mapbox_vector_tile.decode(data)


def _tile_to_lonlat(z, x, y, px, py, extent):
    n = 2 ** z
    lon = (x + px / extent) / n * 360 - 180
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * (y + (extent - py) / extent) / n)))
    return lon, math.degrees(lat_rad)


def read_hifld_lines(pmtiles_path: str, bbox=PJM_BBOX, zoom: int | None = None) -> pd.DataFrame:
    with open(pmtiles_path, "rb") as fh:
        r = Reader(MmapSource(fh))
        h = r.header()
        z = zoom or h["max_zoom"]
        rows = {}
        for (zz, x, y) in _tiles_for_bbox(z, bbox):
            data = r.get(zz, x, y)
            if not data:
                continue
            dec = _decode(data)
            for lname, layer in dec.items():
                extent = layer.get("extent", 4096)
                for f in layer["features"]:
                    p = f["properties"]; g = f["geometry"]
                    coords = g["coordinates"]
                    if g["type"] == "LineString":
                        parts = [coords]
                    elif g["type"] == "MultiLineString":
                        parts = coords
                    else:
                        continue
                    pts = [pt for part in parts for pt in part]
                    if not pts:
                        continue
                    lonlat = [_tile_to_lonlat(zz, x, y, px, py, extent) for px, py in (pts[0], pts[-1])]
                    key = str(p.get("ID"))
                    rec = rows.setdefault(key, dict(id=key, owner=p.get("OWNER"), status=p.get("STATUS"), sub_1=p.get("SUB_1"), sub_2=p.get("SUB_2"),
                                                    type=p.get("TYPE"), voltage=p.get("VOLTAGE"), volt_class=p.get("VOLT_CLASS"), pts=[]))
                    rec["pts"].extend(lonlat)
        out = []
        for rec in rows.values():
            pts = np.array(rec["pts"])
            # endpoints: the two most distant sampled points (tiles split lines into pieces)
            if len(pts) >= 2:
                d = np.hypot(*(pts[:, None, :] - pts[None, :, :]).transpose(2, 0, 1))
                i, j = np.unravel_index(np.argmax(d), d.shape)
                a, b = pts[i], pts[j]
            else:
                a = b = pts[0]
            out.append(dict(id=rec["id"], owner=rec["owner"], status=rec["status"], sub_1=rec["sub_1"], sub_2=rec["sub_2"], type=rec["type"],
                            voltage=pd.to_numeric(rec["voltage"], errors="coerce"), volt_class=rec["volt_class"], lon_a=a[0], lat_a=a[1], lon_b=b[0], lat_b=b[1]))
    return pd.DataFrame(out)


def build_public_topology(lines: pd.DataFrame, subs: pd.DataFrame, max_snap_km: float = 3.0):
    """Snap line endpoints to HIFLD substations (by name when it matches within 15 km, else nearest
    within max_snap_km) and emit substations.csv / facilities.csv in the pipeline schema."""
    subs = subs.copy()
    subs["name"] = subs["name"].fillna("").astype(str).str.strip()
    subs = subs[(subs.lon.between(PJM_BBOX[0], PJM_BBOX[2])) & (subs.lat.between(PJM_BBOX[1], PJM_BBOX[3]))].reset_index(drop=True)
    xy = to_xy_km(subs.lat.values, subs.lon.values); tree = cKDTree(xy)
    name_idx = {}
    for i, n in enumerate(subs.name.str.upper()):
        if n:
            name_idx.setdefault(n, []).append(i)

    def snap(lon, lat, name):
        p = to_xy_km([lat], [lon])[0]
        if isinstance(name, str) and name.strip().upper() in name_idx:
            cands = name_idx[name.strip().upper()]
            d = [float(np.hypot(*(xy[c] - p))) for c in cands]
            j = int(np.argmin(d))
            if d[j] <= 15.0:
                return int(subs.hifld_id.values[cands[j]])
        d, i = tree.query(p)
        return int(subs.hifld_id.values[i]) if d <= max_snap_km else None

    recs = []
    end_labels: dict[int, list[str]] = {}
    for r in lines.itertuples():
        if not (r.voltage and r.voltage > 0):
            continue
        a = snap(r.lon_a, r.lat_a, r.sub_1); b = snap(r.lon_b, r.lat_b, r.sub_2)
        if a is None or b is None or a == b:
            continue
        for sid, lab in ((a, r.sub_1), (b, r.sub_2)):
            if isinstance(lab, str) and lab.strip() and not re.match(r"^(TAP|UNKNOWN|NOT AVAILABLE)\s*\d*$", lab.strip().upper()):
                end_labels.setdefault(sid, []).append(lab.strip().title())
        sa, sb = sorted((a, b))
        kv = int(round(r.voltage))
        recs.append(dict(fid=f"L:{sa}:{sb}:{kv}", kind="L", sub_a=sa, sub_b=sb, kv=kv, line_id=r.id, owner=r.owner, status=r.status))
    fac = pd.DataFrame(recs)
    if len(fac) == 0:
        return subs, fac
    fac["length_km"] = [float(np.hypot(*(xy[subs.index[subs.hifld_id == a][0]] - xy[subs.index[subs.hifld_id == b][0]])) * 1.2) for a, b in zip(fac.sub_a, fac.sub_b)]
    corridors = fac.groupby("fid").agg(kind=("kind", "first"), sub_a=("sub_a", "first"), sub_b=("sub_b", "first"), kv=("kv", "first"),
                                       length_km=("length_km", "mean"), n_circuits=("line_id", "nunique")).reset_index()
    used = set(corridors.sub_a) | set(corridors.sub_b)
    out_subs = subs[subs.hifld_id.isin(used)].copy()
    out_subs["sub_id"] = out_subs.hifld_id.astype(int)
    # HIFLD's substation layer is sparsely named; the line records carry endpoint names, so an unnamed
    # substation takes the most frequent endpoint label of the lines snapped to it.
    from collections import Counter
    out_subs["name"] = [n if n else (Counter(end_labels[int(i)]).most_common(1)[0][0] if int(i) in end_labels else f"HIFLD {i}")
                        for n, i in zip(out_subs.name, out_subs.hifld_id)]
    # transformers: a substation with several voltage levels gets an X facility per adjacent pair (HIFLD has no transformer records)
    lv = pd.concat([corridors[["sub_a", "kv"]].rename(columns={"sub_a": "sub"}), corridors[["sub_b", "kv"]].rename(columns={"sub_b": "sub"})])
    xf = []
    for s, g in lv.groupby("sub"):
        kvs = sorted(set(g.kv))
        for lo, hi in zip(kvs[:-1], kvs[1:]):
            xf.append(dict(fid=f"X:{s}:{hi}:{lo}", kind="X", sub_a=s, sub_b=np.nan, kv=hi, length_km=0.0, n_circuits=1))
    facilities = pd.concat([corridors, pd.DataFrame(xf)], ignore_index=True)
    kvagg = lv.groupby("sub").kv.agg(line_max_kv="max", line_min_kv="min").reset_index().rename(columns={"sub": "hifld_id"})
    out_subs = out_subs.merge(kvagg, on="hifld_id", how="left")
    out_subs["max_kv"] = np.nanmax(np.c_[pd.to_numeric(out_subs.get("max_kv"), errors="coerce").fillna(0).values, out_subs.line_max_kv.values], axis=1)
    out_subs["min_kv"] = out_subs.line_min_kv.values
    out_subs["state"] = ""; out_subs["zone_id"] = 0
    return out_subs[["sub_id", "name", "lat", "lon", "state", "zone_id", "max_kv", "min_kv"]].reset_index(drop=True), facilities
