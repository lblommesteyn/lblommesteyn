"""Discovery round 3 (GitHub Actions runner, headless Chromium via Playwright).
Round 2 found PJM's live "Project Status & Cost Allocation" grid (/planning/m/project-construction) and its
Excel export (POST /m/ProjectConst/ProjectConstructionUpgrades with a jsonModel built by PjmGrid.js), plus a
services.pjm.com ProjectConstruction/ExportToXls route that returned only 9 rows for an empty body.
This round drives the real page to capture the request model and the full export, pulls per-upgrade detail
panels, saves the grid JS, and samples Wayback captures of the legacy server-rendered construction-status
pages (2009-2018) to see whether historical snapshots can be reconstructed from them.
Writes under upgraderisk/data/raw/discovery3/.
"""
from __future__ import annotations
import json, re, time, traceback
from pathlib import Path
import requests

OUT = Path(__file__).resolve().parents[1] / "data" / "raw" / "discovery3"
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "wayback").mkdir(exist_ok=True)
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
KEY = {"api-subscription-key": "E29477D0-70E0-4825-89B0-43F460BF9AB4", "Host": "services.pjm.com",
       "Origin": "https://www.pjm.com", "Referer": "https://www.pjm.com/"}
PAGE = "https://www.pjm.com/planning/m/project-construction"
log = []


def note(**kw):
    kw["t"] = time.strftime("%H:%M:%S"); log.append(kw); print(json.dumps(kw, default=str)[:500], flush=True)


def slug(u: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", u.lower()).strip("_")[:120]


# ---------------------------------------------------------------- 0. grid JS (for the request model)
for u in ["https://www.pjm.com/Scripts/MVC/Custom/PJM.Website.Foundation.PjmGrid.js", "https://www.pjm.com/Scripts/MVC/custom/master.js"]:
    try:
        r = requests.get(u, headers={"User-Agent": UA}, timeout=60)
        note(js=u, status=r.status_code, size=len(r.content))
        if r.status_code == 200:
            (OUT / ("js_" + slug(u) + ".js")).write_text(r.text[:2_000_000])
    except Exception as e:
        note(js=u, error=str(e)[:200])

# ---------------------------------------------------------------- 1. drive the live page
captured_requests, captured_responses = [], []
model_json = None
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(accept_downloads=True, user_agent=UA)
        page = ctx.new_page()
        n_resp = [0]

        def on_request(req):
            if "/m/ProjectConst/" in req.url or "PJMPlanningApi" in req.url:
                captured_requests.append(dict(url=req.url, method=req.method, post=req.post_data, headers=dict(req.headers)))

        def on_response(resp):
            if "/m/ProjectConst/" in resp.url or "PJMPlanningApi" in resp.url:
                try:
                    body = resp.body()
                except Exception:
                    body = b""
                n_resp[0] += 1
                fn = f"resp_{n_resp[0]:02d}_{slug(resp.url.split('?')[0][-60:])}.bin"
                if body:
                    (OUT / fn).write_bytes(body[:20_000_000])
                captured_responses.append(dict(url=resp.url, status=resp.status, ctype=resp.headers.get("content-type", ""), size=len(body), file=fn))

        page.on("request", on_request)
        page.on("response", on_response)
        page.goto(PAGE, wait_until="networkidle", timeout=180000)
        page.wait_for_timeout(4000)
        (OUT / "rendered_page.html").write_text(page.content()[:3_000_000])
        body_txt = page.inner_text("body")
        m = re.search(r"Showing results[^\n]*\n?[^\n]*", body_txt)
        note(page="loaded", showing=(m.group(0) if m else None)[:200] if m else None)
        (OUT / "page_text.txt").write_text(body_txt[:200000])
        # the request model exactly as the page builds it
        model_json = page.evaluate("""() => { try {
            const g = 'CostAllocation';
            const f = jQuery('#' + g).find("[data-type='filter']");
            const ext = jQuery('#projConstExtFilters').find("[data-type='filter-ext']");
            for (let i = 0; i < ext.length; i++) f.push(ext[i]);
            return JSON.stringify(BuildRefreshRequestModel(g, f, getAPaginatorObj(g)));
          } catch (e) { return 'ERR ' + e.toString(); } }""")
        note(model=str(model_json)[:800])
        (OUT / "request_model.json").write_text(str(model_json))
        # bump page size to 500 and let the grid refresh
        try:
            page.select_option("select[data-type='paginator']", "500")
            page.wait_for_load_state("networkidle", timeout=120000)
            page.wait_for_timeout(3000)
        except Exception as e:
            note(paginator_error=str(e)[:200])
        # export
        try:
            with page.expect_download(timeout=300000) as dl_info:
                page.click("#cost_alloc_exportXL")
            dl = dl_info.value
            dest = OUT / "export_live.xlsx"
            dl.save_as(str(dest))
            note(export="saved", size=dest.stat().st_size)
        except Exception as e:
            note(export_error=str(e)[:300])
        # per-upgrade detail panels
        for uid in ["b2752", "n0381.1", "s2069", "b3123", "b0001", "b2436", "s1234", "n5678"]:
            try:
                page.evaluate(f"OpenUpgradeDetails('{uid}')")
                page.wait_for_timeout(2500)
                (OUT / f"details_{slug(uid)}.html").write_text(page.inner_html("#upgradeDetails")[:400000])
                page.evaluate("CloseUpgradeDetails()")
            except Exception as e:
                note(details=uid, error=str(e)[:200])
        for uid in ["b2752", "b3123"]:
            try:
                page.evaluate(f"OpenCostAllocationDetails('{uid}')")
                page.wait_for_timeout(2500)
                (OUT / f"costalloc_{slug(uid)}.html").write_text(page.inner_html("#costAllocationDetails")[:200000])
            except Exception as e:
                note(costalloc=uid, error=str(e)[:200])
        # replay the export with a modified paginator through the browser's cookie jar
        try:
            base = json.loads(model_json) if model_json and not str(model_json).startswith("ERR") else None
        except Exception:
            base = None
        if base is not None:
            def variants(m):
                yield "as_is", m
                mm = json.loads(json.dumps(m))
                for k in list(mm.keys()):
                    if "agin" in k.lower() and isinstance(mm[k], dict):
                        for kk in mm[k]:
                            if "size" in kk.lower():
                                mm[k][kk] = 100000
                            if "page" in kk.lower() and "size" not in kk.lower():
                                mm[k][kk] = 1
                yield "pagesize_100000", mm
            tok = page.eval_on_selector("input[name='__RequestVerificationToken']", "e => e.value")
            for label, m in variants(base):
                for url in ["https://www.pjm.com/m/ProjectConst/ProjectConstructionUpgrades", "https://www.pjm.com/m/ProjectConst/CostAllocResetGrdBody", "https://www.pjm.com/m/ProjectConst/CostAllocReset"]:
                    try:
                        r = ctx.request.post(url, form={"jsonModel": json.dumps(m), "__RequestVerificationToken": tok},
                                             headers={"X-Requested-With": "XMLHttpRequest", "Referer": PAGE, "RequestVerificationToken": tok})
                        b = r.body()
                        fn = f"replay_{label}_{slug(url[-40:])}.bin"
                        (OUT / fn).write_bytes(b[:40_000_000])
                        note(replay=url, label=label, status=r.status, size=len(b), ctype=r.headers.get("content-type", ""))
                    except Exception as e:
                        note(replay=url, label=label, error=str(e)[:200])
        json.dump(ctx.cookies(), open(OUT / "cookies.json", "w"), indent=1)
        browser.close()
except Exception as e:
    note(playwright_error=str(e)[:400], tb=traceback.format_exc()[-1500:])
json.dump(captured_requests, open(OUT / "captured_requests.json", "w"), indent=1, default=str)
json.dump(captured_responses, open(OUT / "captured_responses.json", "w"), indent=1, default=str)

# ---------------------------------------------------------------- 2. services API variants
probes = {}
bodies = [("empty", None), ("pagesize", {"pageSize": 100000, "currentPage": 1}), ("Paginator", {"Paginator": {"PageSize": 100000, "CurrentPage": 1}}),
          ("model", json.loads(model_json) if model_json and not str(model_json).startswith("ERR") else {"x": 1})]
for label, body in bodies:
    for path in ["ProjectConstruction/ExportToXls", "ProjectConstruction/GetFilteredProjectConstructions", "ProjectConstruction/GetFilteredUpgrades",
                 "ProjectConstruction/GetUpgrades", "ProjectConstruction/Search", "ProjectConstruction/GetAll"]:
        url = f"https://services.pjm.com/PJMPlanningApi/api/{path}"
        try:
            r = requests.post(url, headers={**KEY, "Content-Type": "application/json"}, data=json.dumps(body) if body is not None else "{}", timeout=120)
            probes[f"POST {path} [{label}]"] = dict(status=r.status_code, ctype=r.headers.get("Content-Type", ""), size=len(r.content), head=r.text[:200] if "html" in r.headers.get("Content-Type", "") or "json" in r.headers.get("Content-Type", "") else "")
            if r.status_code == 200 and len(r.content) > 13000:
                (OUT / f"api_{slug(path)}_{label}.bin").write_bytes(r.content[:40_000_000])
                note(api=path, label=label, status=200, size=len(r.content))
        except Exception as e:
            probes[f"POST {path} [{label}]"] = dict(error=str(e)[:120])
for uid in ["b2752", "n0381.1"]:
    for path in [f"ProjectConstruction/UpgradeDetails?upgradeId={uid}", f"ProjectConstruction/GetUpgradeDetails?upgradeId={uid}", f"ProjectConstruction/{uid}"]:
        url = f"https://services.pjm.com/PJMPlanningApi/api/{path}"
        try:
            r = requests.get(url, headers=KEY, timeout=60)
            probes[f"GET {path}"] = dict(status=r.status_code, ctype=r.headers.get("Content-Type", ""), size=len(r.content), head=r.text[:300])
        except Exception as e:
            probes[f"GET {path}"] = dict(error=str(e)[:120])
json.dump(probes, open(OUT / "api_probes.json", "w"), indent=1)

# ---------------------------------------------------------------- 3. legacy server-rendered pages in Wayback
def cdx(label, url, collapse=False, limit=5000):
    params = dict(url=url, output="json", fl="original,timestamp,mimetype,length,statuscode", limit=limit, matchType="prefix")
    if collapse:
        params["collapse"] = collapse
    try:
        r = requests.get("https://web.archive.org/cdx/search/cdx", params=params, headers={"User-Agent": UA}, timeout=180)
        rows = r.json() if r.status_code == 200 and r.text.strip() else []
    except Exception as e:
        note(cdx=label, error=str(e)[:160]); rows = []
    json.dump(rows, open(OUT / f"cdx_{label}.json", "w"))
    note(cdx=label, rows=max(0, len(rows) - 1))
    time.sleep(2)
    return rows[1:] if rows else []


legacy = {}
legacy["construct_status"] = cdx("construct_status", "pjm.com/planning/rtep-upgrades-status/construct-status.aspx")
legacy["rtep_upgrades_status"] = cdx("rtep_upgrades_status", "pjm.com/planning/rtep-upgrades-status.aspx")
legacy["cost_allocation_view"] = cdx("cost_allocation_view", "pjm.com/planning/rtep-upgrades-status/cost-allocation-view.aspx")
legacy["queues_status"] = cdx("queues_status", "pjm.com/planning/rtep-upgrades-status/queues-status.aspx")
legacy["www_construct_status"] = cdx("www_construct_status", "www.pjm.com/planning/rtep-upgrades-status/construct-status")
cdx("project_construction_tcs", "www.pjm.com/planning/project-construction/", collapse="urlkey")
cdx("rtep_upgrades_status_all", "pjm.com/planning/rtep-upgrades-status/", collapse="urlkey", limit=20000)


def wb_fetch(original, ts, tag):
    u = f"https://web.archive.org/web/{ts}id_/{original}"
    try:
        r = requests.get(u, headers={"User-Agent": UA}, timeout=180)
        fn = OUT / "wayback" / f"{tag}_{ts}.html"
        fn.write_bytes(r.content[:4_000_000])
        note(wayback=u, status=r.status_code, size=len(r.content))
        return r
    except Exception as e:
        note(wayback=u, error=str(e)[:160])


for label, rows in legacy.items():
    ok = [r for r in rows if r[4] == "200" and int(r[3] or 0) > 30000]
    if not ok:
        continue
    # spread up to 6 captures over time
    step = max(1, len(ok) // 6)
    for r in ok[::step][:6]:
        wb_fetch(r[0], r[1], label)
        time.sleep(1)
json.dump(log, open(OUT / "log.json", "w"), indent=1, default=str)
