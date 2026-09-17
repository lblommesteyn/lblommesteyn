"""Fetch every Wayback capture of PJM's legacy server-rendered construction-status pages (2009-2019),
decode the ASP.NET ViewState that carries the grid rows, and store the rows as gzipped JSON per capture.
Also stores today's live export of the current Project Status & Cost Allocation grid.
Runs on a GitHub Actions runner (needs internet). Output: upgraderisk/data/raw/pjm_snapshots/.
"""
from __future__ import annotations
import csv, gzip, hashlib, json, os, re, time, traceback
from pathlib import Path
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from viewstate import ViewState

ROOT = Path(__file__).resolve().parents[1] / "data" / "raw" / "pjm_snapshots"
LEG = ROOT / "legacy"; LEG.mkdir(parents=True, exist_ok=True)
LIVE = ROOT / "live"; LIVE.mkdir(parents=True, exist_ok=True)
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
MAX_MINUTES = float(os.environ.get("MAX_MINUTES", "75"))
T0 = time.time()
log = []


def note(**kw):
    kw["t"] = round(time.time() - T0); log.append(kw); print(json.dumps(kw, default=str)[:400], flush=True)


def session():
    s = requests.Session()
    s.headers["User-Agent"] = UA
    s.mount("https://", HTTPAdapter(max_retries=Retry(total=5, backoff_factor=4, status_forcelist=[429, 500, 502, 503, 504])))
    return s


S = session()

PAGES = {
    "construct_status": ["pjm.com/planning/rtep-upgrades-status/construct-status.aspx", "www.pjm.com/planning/rtep-upgrades-status/construct-status"],
    "cost_allocation_view": ["pjm.com/planning/rtep-upgrades-status/cost-allocation-view.aspx"],
    "rtep_upgrades_status": ["pjm.com/planning/rtep-upgrades-status.aspx"],
    "queues_status": ["pjm.com/planning/rtep-upgrades-status/queues-status.aspx"],
}


def cdx(url):
    params = dict(url=url, output="json", fl="original,timestamp,mimetype,length,statuscode,digest", limit=20000, matchType="prefix")
    for attempt in range(4):
        try:
            r = S.get("https://web.archive.org/cdx/search/cdx", params=params, timeout=180)
            if r.status_code == 200 and r.text.strip():
                return r.json()[1:]
            note(cdx=url, status=r.status_code)
        except Exception as e:
            note(cdx=url, error=str(e)[:160])
        time.sleep(20 * (attempt + 1))
    return []


DEC = json.JSONDecoder(strict=False)   # the inline JSON contains raw tabs/newlines inside strings


def json_tables_in_text(text: str, min_rows: int = 20):
    out = {}
    for m in re.finditer(r'\[\["', text):
        try:
            val, _ = DEC.raw_decode(text, m.start())
        except Exception:
            continue
        if isinstance(val, list) and len(val) >= min_rows and isinstance(val[0], list):
            out.setdefault((str(val[0][0])[:20], len(val), len(val[0])), val)
    return list(out.values())


def extract_tables(html: str):
    """Grid rows embedded in the page: inline in <div id="jsonDataSourceContainer"> (2017+ and the
    cost-allocation view) or inside the ASP.NET ViewState (older captures)."""
    found = json_tables_in_text(html)
    if "&quot;" in html:
        found += json_tables_in_text(html.replace("&quot;", '"'))
    m = re.search(r'__VIEWSTATE" value="([^"]+)"', html)
    if m and m.group(1).startswith("/wE"):
        try:
            dec = ViewState(m.group(1)).decode()
            stack = [dec]
            while stack:
                x = stack.pop()
                if isinstance(x, str):
                    if '[["' in x:
                        found += json_tables_in_text(x)
                elif isinstance(x, (list, tuple)):
                    stack.extend(x)
                elif isinstance(x, dict):
                    stack.extend(x.values())
        except Exception as e:
            note(viewstate_error=str(e)[:160])
    uniq = {}
    for t in found:
        uniq.setdefault((str(t[0][0])[:20], len(t), len(t[0])), t)
    return list(uniq.values())


def page_meta(html: str):
    tab = re.search(r'hdnActiveTab"[^>]*value="([^"]*)"', html)
    xml = re.search(r'hdnXmlFileName"[^>]*>([^<]*)<', html)
    radio = re.search(r"rbRTEPRadioList[^\n]{0,200}filter\('\[value=\"(\d)\"\]'\)", html)
    heads = re.findall(r'"title":\s*"([^"]+)"', html)
    return dict(active_tab=tab.group(1) if tab else None, xml=xml.group(1).strip() if xml else None, radio=radio.group(1) if radio else None, columns=heads[:20])


manifest_path = ROOT / "manifest.csv"
done = set()
if manifest_path.exists():
    with open(manifest_path) as f:
        for row in csv.DictReader(f):
            if row["status"] == "ok" and row["n_tables"] not in ("", "0"):
                done.add((row["label"], row["timestamp"]))
keep = []
if manifest_path.exists():
    with open(manifest_path) as f:
        keep = [row for row in csv.DictReader(f) if (row["label"], row["timestamp"]) in done]
mf = open(manifest_path, "w", newline="")
mw = csv.writer(mf)
if True:
    mw.writerow(["label", "timestamp", "original", "status", "bytes", "n_tables", "rows_per_table", "active_tab", "xml", "columns", "file", "sha256"])
for row in keep:
    mw.writerow([row[k] for k in ["label", "timestamp", "original", "status", "bytes", "n_tables", "rows_per_table", "active_tab", "xml", "columns", "file", "sha256"]])

# ---------------------------------------------------------------- 1. enumerate captures
plan = []
for label, urls in PAGES.items():
    rows = []
    for u in urls:
        rows += cdx(u)
        time.sleep(2)
    ok = [r for r in rows if r[4] == "200" and int(r[3] or 0) > 60000]
    # one capture per day (largest), dedupe identical digests
    byday, seen_digest = {}, set()
    for r in sorted(ok, key=lambda r: (r[1][:8], -int(r[3]))):
        if r[5] in seen_digest:
            continue
        seen_digest.add(r[5])
        byday.setdefault(r[1][:8], r)
    note(label=label, captures=len(rows), ok=len(ok), distinct_days=len(byday))
    for day, r in sorted(byday.items()):
        plan.append((label, r))
json.dump(plan, open(ROOT / "capture_plan.json", "w"))

# ---------------------------------------------------------------- 2. fetch + decode
order = ["construct_status", "cost_allocation_view", "rtep_upgrades_status", "queues_status"]
plan.sort(key=lambda p: (order.index(p[0]), p[1][1]))
for label, r in plan:
    if (time.time() - T0) / 60 > MAX_MINUTES:
        note(stop="time budget reached"); break
    original, ts = r[0], r[1]
    if (label, ts) in done:
        continue
    u = f"https://web.archive.org/web/{ts}id_/{original}"
    html = None
    for attempt in range(3):
        try:
            resp = S.get(u, timeout=240)
            if resp.status_code == 200 and len(resp.content) > 30000:
                html = resp.text; break
            note(fetch=u, status=resp.status_code, size=len(resp.content))
        except Exception as e:
            note(fetch=u, error=str(e)[:160])
        time.sleep(15 * (attempt + 1))
    if html is None:
        mw.writerow([label, ts, original, "failed", 0, 0, "", "", "", "", "", ""]); mf.flush()
        continue
    tables = extract_tables(html)
    meta = page_meta(html)
    if not tables:  # keep the raw page so the format can be inspected offline
        RAWD = ROOT / "legacy_raw"; RAWD.mkdir(exist_ok=True)
        with gzip.open(RAWD / f"{label}_{ts}.html.gz", "wt") as f:
            f.write(html)
    fn = LEG / f"{label}_{ts}.json.gz"
    payload = dict(label=label, timestamp=ts, original=original, meta=meta, tables=tables)
    raw = json.dumps(payload).encode()
    with gzip.open(fn, "wb") as f:
        f.write(raw)
    mw.writerow([label, ts, original, "ok", len(html), len(tables), "|".join(str(len(t)) for t in tables), meta["active_tab"], meta["xml"], "|".join(meta["columns"]), fn.name, hashlib.sha256(raw).hexdigest()[:16]])
    mf.flush()
    note(saved=fn.name, tables=[len(t) for t in tables], tab=meta["active_tab"], xml=meta["xml"])
    time.sleep(2.5)
mf.close()

# ---------------------------------------------------------------- 2b. the XML data files the legacy pages loaded (all tabs, if archived)
XMLD = ROOT / "legacy_xml"; XMLD.mkdir(exist_ok=True)
xml_rows = cdx("pjm.com/pub/account/gen-queues/")
json.dump(xml_rows, open(ROOT / "cdx_gen_queues.json", "w"))
want = [r for r in xml_rows if r[4] == "200" and re.search(r"(TOUP|CostAllocation|planned|construct)", r[0], re.I) and int(r[3] or 0) > 5000]
note(gen_queues_captures=len(xml_rows), wanted=len(want), names=sorted(set(r[0].rsplit("/", 1)[-1] for r in want))[:40])
seen = set()
for r in sorted(want, key=lambda r: r[1]):
    if (time.time() - T0) / 60 > MAX_MINUTES:
        note(stop="time budget reached (xml)"); break
    key = (r[0].rsplit("/", 1)[-1].lower(), r[1][:8])
    if key in seen or r[5] in seen:
        continue
    seen.add(key); seen.add(r[5])
    fn = XMLD / f"{key[0].replace('.xml', '')}_{r[1]}.xml.gz"
    if fn.exists():
        continue
    try:
        resp = S.get(f"https://web.archive.org/web/{r[1]}id_/{r[0]}", timeout=240)
        if resp.status_code == 200 and len(resp.content) > 2000:
            with gzip.open(fn, "wb") as f:
                f.write(resp.content)
            note(xml=fn.name, size=len(resp.content))
        else:
            note(xml=r[0], ts=r[1], status=resp.status_code)
    except Exception as e:
        note(xml=r[0], ts=r[1], error=str(e)[:160])
    time.sleep(2.5)

# ---------------------------------------------------------------- 3. today's live export (same request the page makes)
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(); ctx = b.new_context(accept_downloads=True, user_agent=UA); page = ctx.new_page()
        page.goto("https://www.pjm.com/planning/m/project-construction", wait_until="networkidle", timeout=180000)
        page.wait_for_timeout(3000)
        txt = page.inner_text("body"); m = re.search(r"Showing results[^\n]*", txt)
        with page.expect_download(timeout=300000) as dl:
            page.click("#cost_alloc_exportXL")
        today = time.strftime("%Y-%m-%d")
        dest = LIVE / f"export_{today}.xlsx"; dl.value.save_as(str(dest))
        note(live_export=dest.name, size=dest.stat().st_size, showing=m.group(0) if m else None)
        b.close()
except Exception as e:
    note(live_export_error=str(e)[:300], tb=traceback.format_exc()[-800:])
json.dump(log, open(ROOT / "fetch_log.json", "w"), indent=1, default=str)
