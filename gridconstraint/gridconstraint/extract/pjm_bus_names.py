"""Map PSS/E-style bus names in PJM reports ("8CHCKAHM-8ELMONT", "3BTLEBRO-3ROCKYMT115T",
"PINEY_69-M HERMON", "AB2-100 TAP-6CLUBHSE") to public (HIFLD) substations.

Bus names are truncated, vowel-dropped, prefixed with voltage-level digits (Dominion: 8=500 kV,
6=230 kV, 3=115 kV; others use kV suffixes like "115T"), and sometimes carry queue-number taps.
Matching: strip prefixes/suffixes, then score candidates by (a) fuzzy ratio on lower-case tokens,
(b) ratio on consonant skeletons (vowels removed), (c) prefix match of the skeleton; restricted
to substations within `radius_km` of an anchor (the project's POI) so short tokens stay
unambiguous. Returns (sub_id, score) or None.
"""
from __future__ import annotations
import re
import numpy as np
import pandas as pd
from rapidfuzz import fuzz
from ..sim.naming import to_xy_km

PREFIX = re.compile(r"^(?:[0-9]{1,2})(?=[A-Z])")           # voltage-level digit prefix
SUFFIX = re.compile(r"(?:_?\d{2,3}[A-Z]?|\d{2,3}|_[A-Z]{1,2}|\s*TAP|\s*TP|\s*T\d?|\s+[A-Z])$")
QUEUE_TAP = re.compile(r"^[A-Z]{1,2}\d?-\d{2,4}\s*(?:TAP)?\s*$")


def skeleton(s: str) -> str:
    s = re.sub(r"[^A-Z]", "", s.upper())
    return re.sub(r"(?<!^)[AEIOUY]", "", s)


def clean_token(tok: str) -> str:
    t = tok.strip().upper()
    t = PREFIX.sub("", t)
    t = SUFFIX.sub("", t)
    t = re.sub(r"[_\.]", " ", t).strip()
    t = SUFFIX.sub("", t).strip()          # second pass: "WALR209" -> "WALR", "MIDLTNTP" -> "MIDLTN"
    return t


def split_desc(desc: str) -> list[str]:
    """'DVP - 8CHCKAHM-8ELMONT 500 kV line' -> ['8CHCKAHM', '8ELMONT']; owner prefixes and kV dropped."""
    d = re.sub(r"\b\d{2,3}(?:\.\d)?\s*kV\b.*$", "", desc, flags=re.I)
    d = re.sub(r"^\s*(?:[A-Z&]{2,6}(?:\s*-\s*[A-Z&]{2,6})?)\s*-\s*(?=\S)", "", d)   # leading "DVP - " / "DP&L - DP&L" owner tags
    d = re.sub(r"\((?:from bus|ITO|TO)[^)]*\)", " ", d)
    parts = [p for p in re.split(r"\s*-\s*|\s+to\s+", d) if p.strip()]
    parts = [p for p in parts if not QUEUE_TAP.match(p.strip().upper())]
    return [p.strip() for p in parts][:2]


class BusNameMatcher:
    def __init__(self, subs: pd.DataFrame):
        self.subs = subs.reset_index(drop=True)
        self.names = self.subs.name.fillna("").astype(str).str.upper().values
        self.skel = np.array([skeleton(n) for n in self.names])
        self.xy = to_xy_km(self.subs.lat.values, self.subs.lon.values)
        self.sub_id = self.subs.sub_id.values.astype(int)
        self.pos = {int(s): i for i, s in enumerate(self.sub_id)}

    def match(self, token: str, anchor_sub: int | None = None, radius_km: float = 250.0, min_score: float = 84.0):
        t = clean_token(token)
        if len(t) < 3:
            return None
        ts = skeleton(t)
        idx = np.arange(len(self.names))
        dist = np.zeros(len(self.names))
        if anchor_sub is not None and int(anchor_sub) in self.pos:
            dist = np.hypot(*(self.xy - self.xy[self.pos[int(anchor_sub)]]).T)
            idx = idx[dist <= radius_km]
        best = None
        for i in idx:
            n = self.names[i]
            if not n or n.startswith("HIFLD "):
                continue
            s1 = fuzz.ratio(t, n)
            sk = self.skel[i]
            s2 = fuzz.ratio(ts, sk) if ts and sk else 0
            s3 = 92.0 if (len(ts) >= 5 and sk.startswith(ts)) else (88.0 if len(ts) >= 4 and sk.startswith(ts) else (86.0 if len(ts) == 3 and len(t) >= 5 and sk.startswith(ts) else 0))
            s4 = fuzz.partial_ratio(t, n) - 12 if len(t) >= 6 else 0
            # truncated multi-word names: "BTLEBRO" ~ "BATTLEBORO", "NO ANNA" ~ "NORTH ANNA": compare against the name's word-initial skeleton
            s5 = fuzz.ratio(ts, skeleton(n.replace("NORTH ", "NO ").replace("SOUTH ", "SO ").replace("EAST ", "E ").replace("WEST ", "W "))) if ts else 0
            score = max(s1, s2, s3, s4, s5) - min(3.0, dist[i] / 100.0)     # near-ties resolve to the substation closer to the POI
            if best is None or score > best[1]:
                best = (int(self.sub_id[i]), float(score), n)
        if best and best[1] >= min_score:
            return best
        return None
