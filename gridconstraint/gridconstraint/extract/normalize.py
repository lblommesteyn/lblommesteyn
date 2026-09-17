"""Facility identity resolution: map free-text facility mentions to canonical ids.

Canonical ids (see sim/naming.py):  L:<subA>:<subB>:<kV> | X:<sub>:<kVhi>:<kVlo> | B:<sub>:<kV>
Public inputs only: the substation list (names, voltages, coordinates) and the public
facility list. The normaliser handles case, abbreviations, punctuation, order swaps,
circuit / unit suffixes, "Substation" tokens, "kV" spelling variants, and small typos via
fuzzy matching. It never sees the hidden branch table.
"""
from __future__ import annotations
import re
import numpy as np
import pandas as pd
from rapidfuzz import fuzz, process

ABBR = {"street": "st", "north": "n", "south": "s", "east": "e", "west": "w", "junction": "jct", "mountain": "mtn", "creek": "crk",
        "river": "riv", "center": "ctr", "heights": "hts", "station": "sta", "point": "pt", "fort": "ft", "saint": "st", "road": "rd",
        "valley": "vly", "mount": "mt", "avenue": "ave", "lake": "lk", "park": "pk", "hill": "hl"}
XFMR_WORDS = r"(?:transformer bank|autotransformer|transformer|xfmr|auto|bank|tx)"
CIRCUIT_RE = re.compile(r"\b(?:circuit|ckt|cir\.?|line|l|bank|unit|t)\s*#?\s*(\d{1,2})\b|#\s*(\d{1,2})\b", re.I)
KV_RE = re.compile(r"\b(\d{2,3})(?:\.0)?\s*-?\s*(?:kv|k v)\b", re.I)
KV_PAIR_RE = re.compile(r"\b(\d{2,3})(?:\.0)?\s*(?:kv)?\s*[/-]\s*(\d{1,3})(?:\.0)?\s*kv", re.I)
XFMR_STRONG = r"(?:transformer bank|autotransformer|transformer|xfmr)"
SEP_RE = re.compile(r"\s+-\s+|\s+–\s+|\s+—\s+|\s+to\s+|\s+/\s+|--|(?<=[A-Za-z0-9.])-(?=[A-Za-z])|–")


def norm_key(name: str) -> str:
    s = str(name).lower()
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"\b(substation|sub|switching station|switchyard|station)\b", " ", s)
    s = re.sub(r"\b\d+\s*kv\b", " ", s)          # voltage residue inside names ("burnett 11514 kv")
    toks = [ABBR.get(t, t) for t in s.split()]
    return " ".join(toks)


class FacilityNormalizer:
    def __init__(self, substations: pd.DataFrame, facilities: pd.DataFrame | None = None):
        self.subs = substations.reset_index(drop=True)
        self.subs["key"] = self.subs.name.map(norm_key)
        self.keys = self.subs.key.tolist()
        self.key_to_rows: dict[str, list[int]] = {}
        for i, k in enumerate(self.keys):
            self.key_to_rows.setdefault(k, []).append(i)
        self.uniq_keys = list(self.key_to_rows)
        self.public_fids = set(facilities.fid) if facilities is not None else set()
        self.xy = np.c_[self.subs.lon.values * 85.0, self.subs.lat.values * 111.0]
        self.sub_pos = {int(s): i for i, s in enumerate(self.subs.sub_id.values)}

    # ---- parsing ---------------------------------------------------------------------
    def parse(self, s: str) -> dict:
        """Split a facility mention into (kind, name parts, kV list, circuit). Name parts are the
        atomic tokens between any separator; grouping into two substation names is decided by
        matching (see normalize), because substation names themselves may contain hyphens."""
        raw = str(s)
        t = raw.strip()
        kind, kv = None, []
        m = KV_PAIR_RE.search(t)
        if m:
            kind = "X"; kv = [int(m.group(1)), int(m.group(2))]
            head, tail = t[:m.start()], t[m.end():]
        else:
            kvs = list(KV_RE.finditer(t))
            if kvs:
                kv = [int(k.group(1)) for k in kvs]
                head, tail = t[:kvs[0].start()], t[kvs[-1].end():]
            else:
                head, tail = t, ""
        circuit = None
        mc = CIRCUIT_RE.search(tail)
        if mc:
            circuit = int(mc.group(1) or mc.group(2))
        strong = bool(re.search(r"\b" + XFMR_STRONG + r"\b", raw, re.I))
        weak = bool(re.search(r"\b(?:auto|bank|tx)\b", tail + " " + head[-12:], re.I))
        head = re.sub(r"\b" + XFMR_STRONG + r"\b", " ", head, flags=re.I)
        head = re.sub(r"\b(?:auto|bank|tx)\b\s*$", " ", head.strip(), flags=re.I) if (strong or kind == "X") else head
        is_bus = bool(re.search(r"\bbus\b", raw, re.I)) and kind is None
        parts = [p.strip(" .,-–/") for p in SEP_RE.split(head) if p and p.strip(" .,-–/")]
        parts = [re.sub(r"\s+", " ", p) for p in parts]
        if kind is None:
            if strong or (weak and len(parts) == 1):
                kind = "X"
            elif is_bus:
                kind = "B"
            else:
                kind = "L" if len(parts) >= 2 else "X?"
        return dict(kind=kind, names=parts, kv=kv, circuit=circuit, raw=raw)

    # ---- matching --------------------------------------------------------------------
    def match_sub(self, name: str, kv_hint: float | None = None, near_xy=None, topn: int = 5) -> list[tuple[int, float]]:
        key = norm_key(name)
        if not key:
            return []
        c1 = process.extract(key, self.uniq_keys, scorer=fuzz.ratio, limit=topn * 3)
        c2 = process.extract(key, self.uniq_keys, scorer=fuzz.token_set_ratio, limit=topn * 3)
        cand_keys = {k for k, _, _ in c1} | {k for k, _, _ in c2}
        out = []
        for k in cand_keys:
            r = fuzz.ratio(key, k); ts = fuzz.token_set_ratio(key, k)
            # token-set is lenient for short candidates ("an" in "kirkland park"): penalise length mismatch
            ln = min(len(key), len(k)) / max(len(key), len(k), 1)
            score = max(r, ts - 30.0 * (1.0 - ln))
            for i in self.key_to_rows[k]:
                s = score
                if kv_hint is not None:
                    mx, mn = self.subs.max_kv.values[i], self.subs.min_kv.values[i]
                    if not (mn - 1 <= kv_hint <= mx + 1):
                        s -= 8
                if near_xy is not None:   # tie-breaker only (facilities in a study can be far from the POI)
                    d = float(np.hypot(*(self.xy[i] - near_xy)))
                    s -= min(4.0, d / 150.0)
                out.append((int(self.subs.sub_id.values[i]), float(s)))
        out.sort(key=lambda x: -x[1])
        return out[:topn]

    def normalize(self, facility_str: str, poi_sub: int | None = None, min_score: float = 72.0) -> dict:
        p = self.parse(facility_str)
        near = self.xy[self.sub_pos[int(poi_sub)]] if poi_sub is not None and int(poi_sub) in self.sub_pos else None
        res = dict(raw=facility_str, kind=p["kind"], kv=p["kv"], circuit=p["circuit"], fid=None, confidence=0.0, in_public_layer=False)
        if p["kind"] == "X" or (p["kind"] == "X?" and len(p["kv"]) >= 2):
            if len(p["kv"]) < 2 or not p["names"]:
                return res
            hi, lo = max(p["kv"][:2]), min(p["kv"][:2])
            c = self.match_sub(" ".join(p["names"]), kv_hint=hi, near_xy=near)
            if not c or c[0][1] < min_score:
                return res
            for sid, sc in c:
                fid = f"X:{sid}:{hi}:{lo}"
                if fid in self.public_fids:
                    res.update(fid=fid, confidence=min(1.0, sc / 100), in_public_layer=True, kind="X"); return res
            sid, sc = c[0]
            res.update(fid=f"X:{sid}:{hi}:{lo}", confidence=min(1.0, sc / 100) * 0.8, kind="X"); return res
        if p["kind"] == "B":
            kv = p["kv"][0] if p["kv"] else None
            c = self.match_sub(" ".join(p["names"]), kv_hint=kv, near_xy=near)
            if c and c[0][1] >= min_score and kv:
                res.update(fid=f"B:{c[0][0]}:{kv}", confidence=min(1.0, c[0][1] / 100), kind="B", in_public_layer=f"B:{c[0][0]}:{kv}" in self.public_fids)
            return res
        if len(p["names"]) < 2:
            return res
        kv = p["kv"][0] if p["kv"] else None
        if kv is None:
            return res
        best = None
        parts = p["names"]
        for split in range(1, len(parts)):
            na, nb = " ".join(parts[:split]), " ".join(parts[split:])
            ca = self.match_sub(na, kv_hint=kv, near_xy=near)
            cb = self.match_sub(nb, kv_hint=kv, near_xy=near)
            if not ca or not cb or ca[0][1] < min_score or cb[0][1] < min_score:
                continue
            for sa, sca in ca:
                for sb, scb in cb:
                    if sa == sb:
                        continue
                    a, b = sorted((sa, sb))
                    fid = f"L:{a}:{b}:{kv}"
                    score = (sca + scb) / 2 + (10 if fid in self.public_fids else 0)
                    if best is None or score > best[1]:
                        best = (fid, score)
        if best:
            res.update(fid=best[0], confidence=min(1.0, best[1] / 100), kind="L", in_public_layer=best[0] in self.public_fids)
        return res
