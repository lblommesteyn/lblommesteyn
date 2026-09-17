"""Substation naming and facility identity for the simulated world.

The hidden case has no substation names, so each nodal substation gets a name from the
HIFLD substation layer (nearest named HIFLD substation within 5 km if unique; otherwise
a real HIFLD name from the same state, re-used as a synthetic name). Names are only
cosmetic for the physics, but they matter for the study-parsing / facility-normalisation
problem, which is a real part of the pipeline.

Canonical facility ids live on the *public* side of the world:
  L:<subA>:<subB>:<kV>       a line corridor (parallel circuits collapsed)
  X:<sub>:<kVhi>:<kVlo>      a transformer bank at a substation (units collapsed)
Study reports mention circuits / units with inconsistent naming; the normaliser maps
those strings back to canonical ids.
"""
from __future__ import annotations
import re
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

ABBREV = {
    "street": "st", "north": "n", "south": "s", "east": "e", "west": "w", "junction": "jct",
    "mountain": "mtn", "creek": "crk", "river": "riv", "center": "ctr", "heights": "hts",
    "station": "sta", "point": "pt", "fort": "ft", "saint": "st", "road": "rd", "valley": "vly",
}


def to_xy_km(lat, lon, lat0=40.0):
    return np.c_[np.asarray(lon) * np.cos(np.deg2rad(lat0)) * 111.0, np.asarray(lat) * 111.0]


def assign_substation_names(subs: pd.DataFrame, hifld: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """subs: sub_id, lat, lon, state. Returns subs with `name`, `name_source`."""
    named = hifld[hifld.name.str.len() > 1].reset_index(drop=True)
    tree = cKDTree(to_xy_km(named.lat.values, named.lon.values))
    d, i = tree.query(to_xy_km(subs.lat.values, subs.lon.values))
    names = [""] * len(subs); src = [""] * len(subs)
    used: set[str] = set()
    order = np.argsort(d)  # closest matches claim names first
    for j in order:
        if d[j] <= 5.0:
            nm = _clean(named.name.values[i[j]])
            if nm and nm.lower() not in used:
                names[j] = nm; src[j] = "hifld_nearest"; used.add(nm.lower())
    # pool of real names per state for the rest
    pool_all = [_clean(n) for n in named.name.values]
    pool_all = [n for n in pool_all if n and n.lower() not in used]
    rng.shuffle(pool_all)
    pool_iter = iter(pool_all)
    for j in range(len(subs)):
        if names[j]:
            continue
        while True:
            nm = next(pool_iter, None)
            if nm is None:
                nm = f"Sub {int(subs.sub_id.values[j])}"
                break
            if nm.lower() not in used:
                break
        names[j] = nm; src[j] = "hifld_pool" if not nm.startswith("Sub ") else "synthetic"; used.add(nm.lower())
    out = subs.copy(); out["name"] = names; out["name_source"] = src
    return out


def _clean(s: str) -> str:
    s = re.sub(r"\s+", " ", str(s)).strip()
    s = re.sub(r"\b(substation|sub|switching station|switchyard)\b\.?", "", s, flags=re.I).strip(" -,")
    s = re.sub(r"\b\d{2,3}(?:\.\d)?\s*-?\s*kv\b\.?", "", s, flags=re.I)      # voltage tokens inside names ("Hosensack 500 Kv")
    s = re.sub(r"[^A-Za-z0-9 .'&-]", "", s)
    s = re.sub(r"\s+", " ", s).strip(" -,.")
    if len(s) < 3:
        return ""
    return s.title()


# ---- canonical facility ids --------------------------------------------------------
def line_fid(sub_a: int, sub_b: int, kv: float) -> str:
    a, b = sorted((int(sub_a), int(sub_b)))
    return f"L:{a}:{b}:{int(round(kv))}"


def xfmr_fid(sub: int, kv_hi: float, kv_lo: float) -> str:
    return f"X:{int(sub)}:{int(round(kv_hi))}:{int(round(kv_lo))}"


def canonical_display(fid: str, sub_names: dict[int, str]) -> str:
    p = fid.split(":")
    if p[0] == "L":
        return f"{sub_names[int(p[1])]} - {sub_names[int(p[2])]} {p[3]} kV"
    return f"{sub_names[int(p[1])]} {p[2]}/{p[3]} kV Transformer"


# ---- noisy name rendering (what study PDFs actually look like) ---------------------
def _abbrev(name: str, rng) -> str:
    words = name.split()
    out = []
    for w in words:
        lw = w.lower()
        if lw in ABBREV and rng.random() < 0.6:
            out.append(ABBREV[lw].capitalize() if w[0].isupper() else ABBREV[lw])
        else:
            out.append(w)
    return " ".join(out)


def _typo(name: str, rng) -> str:
    if len(name) < 6 or rng.random() > 0.05:
        return name
    i = rng.integers(1, len(name) - 1)
    return name[:i] + name[i + 1:]


def noisy_facility_name(fid: str, sub_names: dict[int, str], rng: np.random.Generator, circuit: int | None = None,
                        style: dict | None = None) -> str:
    """Render a facility id the way a transmission owner might write it in a report."""
    style = style or {}
    p = fid.split(":")
    kv_fmt = style.get("kv_fmt", rng.choice(["{kv} kV", "{kv}kV", "{kv} KV", "{kv}.0 kV", "{kv} kv"]))
    case = style.get("case", rng.choice(["title", "upper", "as_is"]))
    sep = style.get("sep", rng.choice([" - ", "-", " – ", " to ", " – ", " / "]))

    def nm(sid):
        s = sub_names[int(sid)]
        s = _abbrev(s, rng)
        s = _typo(s, rng)
        if rng.random() < 0.08:
            s = s + " Substation"
        if case == "upper":
            s = s.upper()
        elif case == "title":
            s = s.title()
        return s

    if p[0] == "L":
        a, b = (p[1], p[2]) if rng.random() < 0.7 else (p[2], p[1])
        kv = kv_fmt.format(kv=p[3])
        s = f"{nm(a)}{sep}{nm(b)} {kv}"
        if circuit is not None and rng.random() < 0.7:
            s += rng.choice([f" Circuit {circuit}", f" Ckt {circuit}", f" #{circuit}", f" Line {circuit}", f" Cir. {circuit}"])
        elif rng.random() < 0.3:
            s += rng.choice([" line", " Line", " L"])
        return s
    else:
        kv = rng.choice([f"{p[2]}/{p[3]} kV", f"{p[2]}-{p[3]} kV", f"{p[2]}/{p[3]}kV", f"{p[2]} kV/{p[3]} kV"])
        word = rng.choice(["Transformer", "XFMR", "Autotransformer", "Auto", "Transformer Bank", "TX"])
        s = f"{nm(p[1])} {kv} {word}"
        if circuit is not None and rng.random() < 0.7:
            s += rng.choice([f" #{circuit}", f" Bank {circuit}", f" T{circuit}", f" Unit {circuit}"])
        return s
