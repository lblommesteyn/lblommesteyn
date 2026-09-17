"""Extractors for REAL PJM System Impact Study reports (2016-2020 vintages).

Two layouts appear in the fetched corpus:
  (T) tabular flowgate rows:   "<desc> <from_bus> <to_bus> <ckt> AC <initial%> <final%> <ER|NR|LD> <MVA> <MW contribution> <ref>"
  (P) prose:                   "The X 69 kV line (from bus 232274 to bus 232272 ckt 1) loads from 105.62% to 106.91% (AC power flow)
                                of its emergency rating (174 MVA) for the ... contingency ... This project contributes approximately 2.16 MW"
Findings are keyed by PSS/E bus numbers when present (exact facility identity across reports) and
carry the free-text description (bus names) for mapping to public (HIFLD) substations.
Sections: Generator Deliverability, Multiple Facility Contingency, Contribution to Previously
Identified Overloads, Potential Congestion (energy-only; excluded from labels by default).
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field

SECTIONS = [
    ("generator_deliverability", r"Generat(?:or|ion) Deliverability\s*\n\(Single or N-1[^\n]*\)?\s*\n"),
    ("multiple_facility", r"Multiple Facility Contingency\s*\n\(Double Circuit[^\)]*\)\s*\.?\s*\n"),
    ("prior_overloads", r"Contribution to Previously Identified Overloads\s*\n\([^\)]*\)\s*\n"),
    ("energy_congestion", r"Potential Congestion due to Local Energy Deliverability\s*\n"),
]
SECTION_END = r"\n?(?:\d+(?:\.\d+)?\s+)?(?:Multiple Facility Contingency|Contribution to Previously Identified Overloads|Potential Congestion due to Local Energy|Short Circuit|Steady-State Voltage|Stability and Reactive|Light Load Analysis|System Reinforcements|New System Reinforcements|Summer Peak Load Flow Analysis Reinforcements|Affected Systems|Queue Dependencies|Contingency Descriptions|Winter Peak)"
FOOTER = re.compile(r"©\s*PJM Interconnection \d{4}\. All rights reserved\.?\s*\d*\s*(?:PJMDOCS-#\s*)?[^\n]*\n?")
PROSE = re.compile(
    r"(?:\((?P<owner>[^)]{2,40})\)\s*)?The\s+(?P<desc>.+?)\s*\(from bus\s+(?P<from>\d{4,6})\s+to bus\s+(?P<to>\d{4,6})\s+ckt\s+(?P<ckt>\d{1,2})\)\s*"
    r"loads from\s+(?P<pre>[\d.]+)%\s+to\s+(?P<post>[\d.]+)%\s+\((?:AC|DC) power flow\)\s+of its\s+(?P<rtype>[a-z ]+?)\s+rating\s+\((?P<rating>[\d,]+)\s*MVA\)"
    r"\s+for the\s+(?P<cont>.+?)(?:\.\s+This project contributes approximately\s+(?P<mw>[\d.]+)\s*MW|\.\s)", re.S)
# (T) 2016-18 flowgate rows; pdfplumber wraps the loading columns, so the row is anchored on the bus numbers and
#     the rating/contribution tail, and the loadings are read from the nearest decimals before the anchor.
TABLE_ROW = re.compile(
    r"(?P<from>\d{5,6})\s+(?P<to>\d{5,6})\s+(?P<ckt>\d{1,2})\s+(?:AC|DC)\s+(?P<tail>[\d. ]{0,30}?)\b(?P<rtype>ER|NR|LD|LTE|STE|LDE|EM|NO)\b\s+(?P<rating>\d{2,5}(?:,\d{3})?)\s+(?P<mw>\d+(?:\.\d+)?)")
# (N) 2019+ rows: ID FROM_BUS# FROM_BUS [kV] AREA TO_BUS# TO_BUS [kV] AREA CKT CONT TYPE RATING PRE POST AC|DC MW
TABLE_ROW_N = re.compile(
    r"(?P<id>\d{6,9})\s+(?P<from>\d{5,6})\s+(?P<fname>[0-9A-Z][A-Z0-9_\-]{1,14}(?: [A-Z0-9]{1,8})?)\s+(?:(?P<fkv>\d{2,3})\.?\d?\s+)?(?P<farea>[A-Z&]{2,6})\s+"
    r"(?P<to>\d{5,6})\s+(?P<tname>[0-9A-Z][A-Z0-9_\-]{1,14}(?: [A-Z0-9]{1,8})?)\s+(?:(?P<tkv>\d{2,3})\.?\d?\s+)?(?P<tarea>[A-Z&]{2,6})\s+(?P<ckt>\d{1,2})\s+"
    r"(?P<cont>.{1,60}?)\s+(?P<ctype>single|singl|tower|bus|breaker|stuck|DCTL|LFFB|[a-z]{3,10})\s*e?\s+(?P<rating>\d{2,5}(?:\.\d+)?)\s+(?P<pre>\d{1,3}\.\d{1,2})\s+(?P<post>\d{1,3}\.\d{1,2})\s+(?:AC|DC)\s+(?P<mw>\d+(?:\.\d+)?)", re.S)


@dataclass
class RealFinding:
    section: str
    desc: str
    from_bus: int | None
    to_bus: int | None
    ckt: int | None
    loading_pre: float | None
    loading_post: float | None
    rating_mva: float | None
    rating_type: str
    contrib_mw: float | None
    contingency: str
    kv: float | None
    owner: str = ""


def _num(x):
    try:
        return float(str(x).replace(",", ""))
    except Exception:
        return None


def _kv(s: str):
    m = re.search(r"(\d{2,3}(?:\.\d)?)\s*[- ]?\s*kV", s, re.I)
    return float(m.group(1)) if m else None


def split_sections(text: str) -> dict[str, str]:
    t = FOOTER.sub("\n", text)
    out = {}
    for name, pat in SECTIONS:
        m = re.search(pat, t)
        if not m:
            continue
        rest = t[m.end():]
        e = re.search(SECTION_END, rest)
        out[name] = rest[: e.start()] if e else rest[:6000]
    return out


def parse_section(name: str, sec: str) -> list[RealFinding]:
    out = []
    body = sec.strip()
    if not body or body.split("\n")[0].strip().lower().startswith("none"):
        return out
    flat = re.sub(r"[ \t]*\n[ \t]*", " ", body)
    # (P) prose
    seen = set()
    for m in PROSE.finditer(flat):
        d = m.groupdict()
        desc = re.sub(r"\s+(line|transformer|xfmr)$", "", d["desc"].strip(), flags=re.I)
        key = (d["from"], d["to"], d["ckt"])
        seen.add(key)
        out.append(RealFinding(name, desc, int(d["from"]), int(d["to"]), int(d["ckt"]), _num(d["pre"]), _num(d["post"]), _num(d["rating"]),
                               d["rtype"].strip(), _num(d["mw"]), d["cont"].strip()[:160], _kv(d["desc"]), (d.get("owner") or "").strip()))
    # (N) new-format rows
    for m in TABLE_ROW_N.finditer(flat):
        key = (m.group("from"), m.group("to"), m.group("ckt"))
        if key in seen:
            continue
        seen.add(key)
        kv = _num(m.group("fkv")) if m.group("fkv") else None
        out.append(RealFinding(name, f"{m.group('fname')}-{m.group('tname')}", int(m.group("from")), int(m.group("to")), int(m.group("ckt")), _num(m.group("pre")),
                               _num(m.group("post")), _num(m.group("rating")), "", _num(m.group("mw")), m.group("cont").strip()[:80], kv))
    # (T) old-format rows: description is the text between the previous row (or section start) and this row's bus numbers
    pos = 0
    for m in TABLE_ROW.finditer(flat):
        key = (m.group("from"), m.group("to"), m.group("ckt"))
        pre_txt = flat[pos:m.start()]
        pos = m.end()
        if key in seen:
            continue
        seen.add(key)
        desc = re.sub(r"(?:#\s*)?(?:Type|Name|Area|Facility Description|From|To|C(?:ir|kt)\.?|Ckt|Flow|Initial|Final|Rating|MVA|Contribution|Ref|Appendix|Loading %|Loading|Bus|Power|MW|Flowgate|Affected|Overload|Contingency|Number|Circuit)\b", " ", pre_txt)
        desc = re.sub(r"\s+", " ", desc).strip(" -:.")
        decs = re.findall(r"\b(\d{1,3}\.\d{1,2})\b", pre_txt[-160:] + " " + m.group("tail"))
        pre_l, post_l = (_num(decs[-2]), _num(decs[-1])) if len(decs) >= 2 else (None, None)
        trailing = flat[m.end(): m.end() + 60]
        kv = _kv(desc) or _kv(trailing)
        out.append(RealFinding(name, desc[-160:], int(m.group("from")), int(m.group("to")), int(m.group("ckt")), pre_l, post_l,
                               _num(m.group("rating")), m.group("rtype"), _num(m.group("mw")), "", kv))
    return out


PAIR = re.compile(r"(?<![A-Z0-9])([0-9]{0,2}[A-Z][A-Z0-9_]{2,11}(?: [A-Z]{2,8})?)\s*-\s*([0-9]{0,2}[A-Z][A-Z0-9_]{2,11}(?: [A-Z]{2,8})?)(?![A-Z0-9])")
NOISE = {"LN", "LOADING", "DVP", "AEP", "DAY", "CPLE", "PPL", "PSEG", "BGE", "PEPCO", "DPL", "APS", "ATSI", "COMED", "DEOK", "DOM", "EKPC", "JCPL",
         "METED", "PENELEC", "PECO", "RECO", "DUQ", "AC", "DC", "ER", "NR", "LD", "LTE", "STE", "NONE", "NON", "DCTL", "LFFB", "TOWER", "LINE", "BUS", "CIRCUIT"}


TAP_PAIR = re.compile(r"([A-Z]{1,2}\d?-\d{2,4})(?:\s*TAP)?\s*-\s*([0-9]{0,2}[A-Z][A-Z0-9_]{2,11}(?: [A-Z]{2,8})?)(?![A-Z0-9])")


def name_pair(desc: str) -> tuple[str, str] | None:
    """Extract the (from, to) PSS/E bus-name pair from a (possibly polluted) facility description.
    A queue-tap end ("AB2-100 TAP") is returned as the literal tap token; callers map it to the POI."""
    best = None
    for m in PAIR.finditer(desc.upper()):
        a, b = m.group(1).strip(), m.group(2).strip()
        if a.split()[0] in NOISE or b.split()[0] in NOISE or re.match(r"^[A-Z]{1,2}\d?$", a) or re.match(r"^\d+$", b):
            continue
        if re.match(r"^(?:[A-Z]{1,2}\d?)$", a) or len(re.sub(r"[^A-Z]", "", a)) < 3 or len(re.sub(r"[^A-Z]", "", b)) < 3:
            continue
        cand = (a, b)
        if best is None or len(a) + len(b) > len(best[0]) + len(best[1]):
            best = cand
    if best is None:
        m = TAP_PAIR.search(desc.upper())
        if m and m.group(2).split()[0] not in NOISE:
            best = ("TAP:" + m.group(1), m.group(2).strip())
    return best


def bus_name_dictionary(all_findings: list) -> dict[int, str]:
    """bus number -> bus name, learned from findings whose description is a clean 'A-B kV' pair."""
    d: dict[int, dict[str, int]] = {}
    for f in all_findings:
        if f.from_bus is None:
            continue
        pr = name_pair(f.desc)
        if pr and re.match(r"^\s*(?:\(?[A-Z&]{2,6}\)?\s*-\s*)?[0-9]{0,2}[A-Z][A-Z0-9_ ]{2,14}-[0-9]{0,2}[A-Z][A-Z0-9_ ]{2,14}\s*\d{2,3}", f.desc.upper()):
            d.setdefault(f.from_bus, {}); d[f.from_bus][pr[0]] = d[f.from_bus].get(pr[0], 0) + 1
            d.setdefault(f.to_bus, {}); d[f.to_bus][pr[1]] = d[f.to_bus].get(pr[1], 0) + 1
    return {b: max(v, key=v.get) for b, v in d.items()}


def parse_real_report(text: str) -> tuple[dict, list[RealFinding]]:
    meta = {}
    m = re.search(r"Queue (?:Position|Project|Number|#)\s*[:#]?\s*([A-Z]{1,2}\d?-\d{2,4})", text)
    if m:
        meta["project_id"] = m.group(1)
    head = text[:1500]
    m = re.search(r"([A-Z]{1,2}\d?-\d{2,4})\s*\n([^\n]{3,80})\n\s*([\d.]+)\s*MW Capacit(?:y|ies)\s*/\s*([\d.]+)\s*MW Energy", head)
    if m:
        meta["poi_str"] = m.group(2).strip(); meta["mw_capacity"] = _num(m.group(3)); meta["mw_energy"] = _num(m.group(4))
    m = re.search(r"(?:Total System Network Upgrade Costs?|Total Network Upgrade Costs?)[^$\n]*\$\s?([\d,]+)", text)
    if m:
        meta["network_upgrade_cost_usd"] = _num(m.group(1))
    m = re.search(r"Total\s+(?:Costs?)?[^$\n]{0,40}\$\s?([\d,]+)\s*\n", text)
    if m and "network_upgrade_cost_usd" not in meta:
        meta["total_cost_usd"] = _num(m.group(1))
    findings = []
    for name, sec in split_sections(text).items():
        findings.extend(parse_section(name, sec))
    return meta, findings
