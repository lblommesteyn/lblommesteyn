"""Parse interconnection study PDFs into structured findings.

Designed around the language actually used in PJM System Impact Study reports
("... is overloaded to 104.2% of its 350 MVA rating for the loss of ...", ruled tables with
Facility / Contingency / Loading / Rating / DFAX columns, and "Facility: ... Contingency: ..."
field lists). It works on the simulated reports shipped here and is written to degrade
gracefully on real reports: every extractor is independent and results are unioned.

Output schema (one row per finding):
  facility_str, contingency_str, loading_pct, rating_mva, dfax_pct, pre_loading_pct, source
plus a `meta` dict (project id, POI string, MW, dates, total cost) and `upgrades` rows
(facility_str, upgrade_str, cost_total_usd, alloc_pct, cost_alloc_usd).
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
import pdfplumber

MONEY = r"\$\s?([\d,]+(?:\.\d+)?)"


@dataclass
class ParsedStudy:
    meta: dict = field(default_factory=dict)
    findings: list = field(default_factory=list)
    upgrades: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


def _num(s):
    try:
        return float(str(s).replace(",", "").replace("$", "").strip())
    except Exception:
        return None


def extract_text_and_tables(pdf_path: str):
    texts, tables = [], []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            texts.append(page.extract_text() or "")
            try:
                for t in page.extract_tables():
                    if t and len(t) > 1:
                        tables.append(t)
            except Exception:
                pass
    return "\n".join(texts), tables


def _clean(s):
    if s is None:
        return ""
    return re.sub(r"\s+", " ", str(s)).strip()


# ---------------------------------------------------------------------- meta
def parse_meta(text: str) -> dict:
    m = {}
    r = re.search(r"Queue (?:Project|Number|No\.?)\s*[:#]?\s*([A-Z]{1,3}\d?-?\d{1,4}(?:-\d{1,4})?)", text)
    if r: m["project_id"] = r.group(1)
    r = re.search(r"proposes a ([\d,.]+)\s*MW (.+?) facility", text)
    if r: m["mw"] = _num(r.group(1)); m["fuel_text"] = _clean(r.group(2))
    r = re.search(r"interconnect(?:ing|ion)? at the (.+?) substation", text)
    if r: m["poi_str"] = _clean(r.group(1))
    r = re.search(r"request was received on ([A-Z][a-z]+ \d{1,2}, \d{4})", text)
    if r: m["queue_date_str"] = r.group(1)
    dates = re.findall(r"\b([A-Z][a-z]+ \d{1,2}, \d{4})\b", text[:600])
    if dates: m["publication_date_str"] = dates[0]
    r = re.search(r"including (\d+) higher-queued", text)
    if r: m["n_queue_ahead"] = int(r.group(1))
    r = re.search(r"contribute \(DFAX of 5% or greater\) to (\d+) overloaded", text)
    if r: m["n_facilities_stated"] = int(r.group(1))
    r = re.search(r"(?:total estimated cost of the network upgrades allocated to this project is|Total allocated to project|Estimated network upgrade cost:|Total network upgrade cost allocated to this project:)\s*" + MONEY, text)
    if r: m["total_cost_usd"] = _num(r.group(1))
    if re.search(r"No (?:thermal )?overloads (?:attributable|identified)|did not identify any facilities overloaded|does not cause any thermal violations", text):
        m["no_overloads_stated"] = True
    return m


# ---------------------------------------------------------------------- findings
# A facility/contingency name may contain a period only when it is not a sentence end:
# "230.0 kV", "P.S", "Indl.Pk", "A.A.A.", "Cir. 2" are allowed; ". The" / ". For" are not.
_ABBRS = ["St", "Mt", "Ft", "Jct", "Cir", "No", "Co", "Inc", "Llc", "Dr", "Rd", "Ave", "Sta", "Pt", "Blvd", "Hwy"]
_ABBR_FORMS = sorted({a for x in _ABBRS for a in (x, x.upper(), x.lower())})
# a period that belongs to an abbreviation ("St. Clair", "LEA CO.", "W.E. Williams", "Cir. 2")
ABBR_DOT = r"(?:" + "|".join(f"(?<=\\b{a})" for a in _ABBR_FORMS) + r"|(?<=\b[A-Z]))\."
NAME = r"(?:[^.]|\.(?=\S)|\.(?=\s\d)|" + ABBR_DOT + r")+?"
# a sentence-ending period: not an abbreviation's period (a lone "L." may end a sentence: "... 230 kV L.")
SENT_DOT = "".join(f"(?<!\\b{a})" for a in _ABBR_FORMS) + r"(?<!\b[A-KM-Z])\.(?=\s|$)"
SENTENCE_PATTERNS = [
    # "The X is overloaded to 104.2% of its 350 MVA emergency rating for the loss of the Y. The project contributes 6.4% DFAX"
    (re.compile(r"(?:The |the )?(?P<fac>" + NAME + r") is overloaded to (?P<load>[\d.]+)% of its (?P<rating>[\d,]+) MVA (?:emergency |normal )?rating"
                r"(?: for the loss of (?:the )?(?P<cont>" + NAME + r")| under system intact conditions)" + SENT_DOT +
                r"(?:\s*The project(?:'s)? (?:contributes |distribution factor on this facility is )(?P<dfax>[\d.]+)%)?"), "prose_overloaded"),
    # "X loads to 101.4% of its 264 MVA normal rating with all facilities in service (DFAX 6.4%)."
    (re.compile(r"(?P<fac>" + NAME + r") loads to (?P<load>[\d.]+)% of its (?P<rating>[\d,]+) MVA (?:normal )?rating with all facilities in service \(DFAX (?P<dfax>[\d.]+)%\)"), "prose_intact"),
    # "For the loss of Y, the X loads to 101.4% of its 264 MVA rating. Project DFAX: 6.4%."
    (re.compile(r"For the loss of (?P<cont>" + NAME + r"), the (?P<fac>" + NAME + r") loads to (?P<load>[\d.]+)% of its (?P<rating>[\d,]+) MVA rating\.(?:\s*Project DFAX: (?P<dfax>[\d.]+)%)?"), "prose_loss"),
    # "X: 101.4% loading (264 MVA) following the outage of the Y; DFAX = 6.4%."
    (re.compile(r"(?P<fac>(?:[^.:]|\.(?=\S)|\.(?=\s\d)|" + ABBR_DOT + r")+?): (?P<load>[\d.]+)% loading \((?P<rating>[\d,]+) MVA\) following the outage of (?:the )?(?P<cont>" + NAME + r"); DFAX = (?P<dfax>[\d.]+)%"), "prose_colon"),
]
FIELD_RE = re.compile(r"Facility:\s*(?P<fac>.+?)\s*(?:\n|$)\s*Contingency:\s*(?P<cont>.+?)\s*(?:\n|$)\s*Loading:\s*(?P<load>[\d.]+)%\s*\(Rating:\s*(?P<rating>[\d,]+)\s*MVA\)\s*(?:\n|$)\s*DFAX:\s*(?P<dfax>[\d.]+)%(?:\s*(?:\n|$)\s*Pre-project loading:\s*(?P<pre>[\d.]+)%)?", re.S)


def _section(text: str, start_pat: str, end_pat: str) -> str:
    s = re.search(start_pat, text)
    if not s:
        return text
    e = re.search(end_pat, text[s.end():])
    return text[s.end(): s.end() + e.start()] if e else text[s.end():]


def parse_findings_from_text(text: str) -> list[dict]:
    out = []
    sec = _section(text, r"3\.1[^\n]*\n", r"\n3\.2")
    # field-list template
    for m in FIELD_RE.finditer(sec):
        out.append(dict(facility_str=_clean(m.group("fac")), contingency_str=_clean(m.group("cont")), loading_pct=_num(m.group("load")),
                        rating_mva=_num(m.group("rating")), dfax_pct=_num(m.group("dfax")), pre_loading_pct=_num(m.group("pre")), source="fields"))
    if out:
        return out
    # prose templates: join wrapped lines
    flat = re.sub(r"\s*\n\s*", " ", sec)
    for pat, name in SENTENCE_PATTERNS:
        for m in pat.finditer(flat):
            d = m.groupdict()
            fac = _clean(d.get("fac"))
            fac = re.sub(r"^(?:The|the)\s+", "", fac)
            cont = _clean(d.get("cont")) if d.get("cont") else "N-0"
            out.append(dict(facility_str=fac, contingency_str=cont, loading_pct=_num(d.get("load")), rating_mva=_num(d.get("rating")),
                            dfax_pct=_num(d.get("dfax")), pre_loading_pct=None, source=name))
    return out


def parse_findings_from_tables(tables) -> list[dict]:
    out = []
    for t in tables:
        hdr = [_clean(c).lower() for c in t[0]]
        if any("facility" in h for h in hdr) and any("loading" in h for h in hdr):
            ci = {k: next((i for i, h in enumerate(hdr) if k in h), None) for k in ("facility", "contingency", "loading", "rating", "dfax")}
            for row in t[1:]:
                if ci["facility"] is None or not row[ci["facility"]]:
                    continue
                out.append(dict(facility_str=_clean(row[ci["facility"]]), contingency_str=_clean(row[ci["contingency"]]) if ci["contingency"] is not None else "",
                                loading_pct=_num(row[ci["loading"]]) if ci["loading"] is not None else None,
                                rating_mva=_num(row[ci["rating"]]) if ci["rating"] is not None else None,
                                dfax_pct=_num(row[ci["dfax"]]) if ci["dfax"] is not None else None, pre_loading_pct=None, source="table"))
    return out


def parse_upgrades(text: str, tables) -> list[dict]:
    out = []
    for t in tables:
        hdr = [_clean(c).lower() for c in t[0]]
        if any("upgrade" in h for h in hdr) and any("cost" in h for h in hdr):
            fi = next((i for i, h in enumerate(hdr) if "facility" in h), 0)
            ui = next((i for i, h in enumerate(hdr) if "upgrade" in h), 1)
            ci = next((i for i, h in enumerate(hdr) if "cost" in h), 2)
            ai = next((i for i, h in enumerate(hdr) if "alloc" in h), None)
            for row in t[1:]:
                fac = _clean(row[fi]) if fi < len(row) else ""
                if not fac or fac.lower().startswith("total"):
                    continue
                alloc_pct, alloc_usd = None, None
                if ai is not None and ai < len(row) and row[ai]:
                    a = re.search(r"([\d.]+)%\s*\(" + MONEY + r"\)", _clean(row[ai]))
                    if a:
                        alloc_pct, alloc_usd = _num(a.group(1)), _num(a.group(2))
                out.append(dict(facility_str=fac, upgrade_str=_clean(row[ui]) if ui < len(row) else "",
                                cost_total_usd=_num(row[ci]) if ci < len(row) else None, alloc_pct=alloc_pct, cost_alloc_usd=alloc_usd))
    if out:
        return out
    # fallback: lines in section 4 with a dollar amount
    sec = _section(text, r"4\. Required Network Upgrades[^\n]*\n", r"\nThis report")
    for line in sec.splitlines():
        if "$" in line and not line.lower().startswith("total"):
            m = re.search(r"^(.*?)\s{1,}(Reconductor.*?|Rebuild.*?|Replace.*?|Upgrade.*?)\s+" + MONEY + r"\s+([\d.]+)%\s*\(" + MONEY + r"\)", line)
            if m:
                out.append(dict(facility_str=_clean(m.group(1)), upgrade_str=_clean(m.group(2)), cost_total_usd=_num(m.group(3)),
                                alloc_pct=_num(m.group(4)), cost_alloc_usd=_num(m.group(5))))
    return out


def parse_study(pdf_path: str) -> ParsedStudy:
    text, tables = extract_text_and_tables(pdf_path)
    ps = ParsedStudy()
    ps.meta = parse_meta(text)
    ps.findings = parse_findings_from_tables(tables) or parse_findings_from_text(text)
    ps.upgrades = parse_upgrades(text, tables)
    # cross-checks
    n_stated = ps.meta.get("n_facilities_stated")
    if n_stated is not None and n_stated != len(ps.findings):
        ps.warnings.append(f"stated {n_stated} facilities, parsed {len(ps.findings)}")
    if ps.meta.get("no_overloads_stated") and ps.findings:
        ps.warnings.append("report states no overloads but findings parsed")
    return ps
