"""Discovery round 2 (GitHub Actions runner). Round 1 showed the PJM "Project Status & Cost Allocation"
page moved to the single-page app at /planning/m/project-construction and that the guessed Planning API
upgrade endpoints do not exist. This round:
  A. fetches the SPA pages and every JS bundle they reference, and greps them for Planning API routes;
  B. probes each discovered route (GET and POST) with the public subscription key;
  C. lists Wayback captures for the construction-status export, the old/new project-construction pages,
     the Planning API host and PJM planning media folders (candidate historical snapshots);
  D. downloads three sample sub-regional "M-3 process needs status" workbooks to inspect their schema;
  E. records the RTEP baseline-reports and TEAC page links.
Everything is written under upgraderisk/data/raw/discovery2/.
"""
from __future__ import annotations
import json, re, time
from pathlib import Path
from urllib.parse import urljoin
import requests

OUT = Path(__file__).resolve().parents[1] / "data" / "raw" / "discovery2"
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "samples").mkdir(exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
KEY = {"api-subscription-key": "E29477D0-70E0-4825-89B0-43F460BF9AB4", "Host": "services.pjm.com",
       "Origin": "https://www.pjm.com", "Referer": "https://www.pjm.com/"}
log = []


def note(**kw):
    kw["t"] = time.strftime("%H:%M:%S"); log.append(kw); print(json.dumps(kw)[:400], flush=True)


def get(url, headers=None, **kw):
    try:
        return requests.get(url, headers=headers or UA, timeout=90, **kw)
    except Exception as e:
        note(url=url, error=str(e)[:160]); return None


def slug(u: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", u.lower()).strip("_")[:120]


# ---------------------------------------------------------------- A. SPA pages + JS bundles
pages = ["https://www.pjm.com/planning/m/project-construction", "https://www.pjm.com/planning/m/cycle-service-request-status",
         "https://www.pjm.com/planning/m/", "https://www.pjm.com/planning/m/project-construction/"]
js_urls: list[str] = []
page_hrefs = {}
for u in pages:
    r = get(u)
    if r is None:
        continue
    note(page=u, status=r.status_code, size=len(r.content), final=r.url)
    if r.status_code != 200:
        continue
    (OUT / (slug(u) + ".html")).write_text(r.text[:600000])
    base = r.url
    m = re.search(r'<base\s+href="([^"]+)"', r.text)
    if m:
        base = urljoin(r.url, m.group(1))
    hrefs = sorted(set(re.findall(r'(?:href|src)="([^"]+)"', r.text)))
    page_hrefs[u] = dict(base=base, hrefs=hrefs)
    for h in hrefs:
        if re.search(r"\.js(\?|$)", h):
            js_urls.append(urljoin(base, h))
json.dump(page_hrefs, open(OUT / "page_hrefs.json", "w"), indent=1)

seen, hits, queue = set(), {}, list(dict.fromkeys(js_urls))
PAT_API = re.compile(r"api/[A-Za-z0-9_/\-\.]{3,90}")
PAT_EXP = re.compile(r"[A-Za-z0-9_/]{2,60}/(?:ExportToXls|ExportToExcel|Export|GetFiltered[A-Za-z]+|Get[A-Za-z]+)")
PAT_GUID = re.compile(r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}")
PAT_HOST = re.compile(r"https?://[a-z0-9\-\.]*pjm\.com[^\"'\s)]*")
while queue and len(seen) < 60:
    ju = queue.pop(0)
    if ju in seen:
        continue
    seen.add(ju)
    r = get(ju)
    if r is None or r.status_code != 200:
        note(js=ju, status=None if r is None else r.status_code); continue
    t = r.text
    apis = sorted(set(PAT_API.findall(t)))
    exps = sorted(set(PAT_EXP.findall(t)))
    guids = sorted(set(PAT_GUID.findall(t)))
    hosts = sorted(set(PAT_HOST.findall(t)))
    ctx = []
    for m in re.finditer(r"api/[A-Za-z0-9_/\-]{3,60}", t):
        if len(ctx) < 300:
            ctx.append(t[max(0, m.start() - 80): m.end() + 80].replace("\n", " "))
    if apis or exps or guids:
        hits[ju] = dict(size=len(t), apis=apis[:400], exports=exps[:200], guids=guids[:20], hosts=hosts[:60], context=ctx)
        note(js=ju, size=len(t), n_api=len(apis), n_exp=len(exps), guids=guids[:3])
        (OUT / ("js_" + slug(ju) + ".js")).write_text(t[:3_000_000])
    # lazy chunks referenced by name inside the bundle
    for name in set(re.findall(r'"([A-Za-z0-9_\-\.]+\.js)"', t)):
        cand = urljoin(ju, name)
        if cand not in seen and "pjm.com" in cand:
            queue.append(cand)
json.dump(hits, open(OUT / "js_api_hits.json", "w"), indent=1)

# ---------------------------------------------------------------- B. probe discovered routes
routes = set()
for h in hits.values():
    for a in h["apis"]:
        routes.add(a)
    for e in h["exports"]:
        routes.add(e)
extra = ["api/Construction/ExportToXls", "api/ProjectConstruction/ExportToXls", "api/Construction/GetFilteredConstructionProjects",
         "api/Upgrade/GetFilteredUpgrades", "api/Upgrades/GetFilteredUpgrades", "api/Project/GetFilteredProjects", "api/Queue/ExportToXls"]
routes.update(extra)
probes = {}
n = 0
for rt in sorted(routes):
    if n >= 120:
        break
    path = rt[4:] if rt.startswith("api/") else rt
    path = path.strip("/")
    if not re.search(r"[A-Za-z]", path) or "." in path.split("/")[-1] and not path.endswith(("Xls", "Excel")):
        continue
    url = f"https://services.pjm.com/PJMPlanningApi/api/{path}"
    for method in ("GET", "POST"):
        n += 1
        try:
            if method == "POST":
                r = requests.post(url, headers={**KEY, "Content-Type": "application/json"}, data="{}", timeout=90)
            else:
                r = requests.get(url, headers=KEY, timeout=90)
            info = dict(status=r.status_code, ctype=r.headers.get("Content-Type", ""), size=len(r.content), head=r.text[:200] if "json" in r.headers.get("Content-Type", "") or "text" in r.headers.get("Content-Type", "") else "")
            probes[f"{method} {url}"] = info
            if r.status_code == 200 and len(r.content) > 1500:
                (OUT / f"probe_{slug(path)}_{method}.bin").write_bytes(r.content[:40_000_000])
                note(probe=url, method=method, status=200, size=len(r.content), ctype=info["ctype"])
        except Exception as e:
            probes[f"{method} {url}"] = dict(error=str(e)[:120])
# the legacy MVC export seen in the Wayback index
for u in ["https://www.pjm.com/Scripts/MVC/Custom/ProjectConstructionUpgrades.xlsx", "https://www.pjm.com/Scripts/MVC/Custom/ProjectConstructionUpgrades",
          "https://www.pjm.com/planning/project-construction/ProjectConstructionUpgrades.xlsx"]:
    r = get(u)
    if r is not None:
        probes[f"GET {u}"] = dict(status=r.status_code, ctype=r.headers.get("Content-Type", ""), size=len(r.content), final=r.url, head=r.text[:300] if "html" in r.headers.get("Content-Type", "") else "")
        if r.status_code == 200 and len(r.content) > 1500 and "html" not in r.headers.get("Content-Type", ""):
            (OUT / f"probe_{slug(u)}.bin").write_bytes(r.content[:40_000_000])
json.dump(probes, open(OUT / "api_probes.json", "w"), indent=1)

# ---------------------------------------------------------------- C. Wayback CDX captures
def cdx(label, url, match="prefix", collapse=True, filt=None, limit=20000):
    params = dict(url=url, output="json", fl="original,timestamp,mimetype,length,statuscode", limit=limit)
    if match:
        params["matchType"] = match
    if collapse:
        params["collapse"] = "urlkey"
    if filt:
        params["filter"] = filt
    try:
        r = requests.get("https://web.archive.org/cdx/search/cdx", params=params, headers=UA, timeout=180)
        rows = r.json() if r.status_code == 200 and r.text.strip() else []
    except Exception as e:
        note(cdx=label, error=str(e)[:160]); rows = []
    json.dump(rows, open(OUT / f"cdx_{label}.json", "w"))
    note(cdx=label, rows=max(0, len(rows) - 1))
    time.sleep(2)


cdx("tcs_export_all", "www.pjm.com/Scripts/MVC/Custom/ProjectConstructionUpgrades.xlsx", match="exact", collapse=False)
cdx("tcs_export_prefix", "www.pjm.com/Scripts/MVC/Custom/", collapse=False)
cdx("project_construction_old", "www.pjm.com/planning/project-construction", collapse=True)
cdx("project_construction_old_all", "www.pjm.com/planning/project-construction", collapse=False, limit=5000)
cdx("project_construction_m", "www.pjm.com/planning/m/project-construction", collapse=False)
cdx("planning_api_host", "services.pjm.com/PJMPlanningApi/", collapse=True)
cdx("pub_planning", "www.pjm.com/pub/planning/", collapse=True, filt="!mimetype:text/html")
cdx("media_planning_rtep_dev", "www.pjm.com/-/media/DotCom/planning/rtep-dev/", collapse=True)
cdx("media_planning_legacy", "www.pjm.com/~/media/planning/", collapse=True)
cdx("media_planning_legacy2", "www.pjm.com/-/media/planning/", collapse=True)
cdx("rtep_development", "www.pjm.com/planning/rtep-development", collapse=True)
cdx("rtep_upgrades_legacy", "www.pjm.com/planning/rtep-upgrades", collapse=True)
cdx("planning_xls_any", "www.pjm.com/", collapse=True, filt="original:.*(rtep|baseline|network-upgrade|construction|tcs).*\\.(xls|xlsx|csv)$")
cdx("documents_reports_rtep", "www.pjm.com/-/media/DotCom/library/reports-notices/rtep-documents/", collapse=True)
cdx("documents_reports_rtep_legacy", "www.pjm.com/~/media/documents/reports/", collapse=True, filt="original:.*rtep.*")

# ---------------------------------------------------------------- D. sample M-3 needs-status workbooks
samples = ["https://www.pjm.com/-/media/DotCom/committees-groups/committees/srrtep-ma/20190325/20190325-m-3-process-needs-status.xlsx",
           "https://www.pjm.com/-/media/DotCom/committees-groups/committees/srrtep-ma/2022/20220613/informational-only---m-3-process-needs-status.xlsx",
           "https://www.pjm.com/-/media/DotCom/committees-groups/committees/srrtep-ma/2026/20260616/20260616-informational-only---m-3-process-needs-status.xlsx"]
for u in samples:
    r = get(u)
    if r is not None:
        note(sample=u, status=r.status_code, size=len(r.content), ctype=r.headers.get("Content-Type", ""))
        if r.status_code == 200 and len(r.content) > 5000:
            (OUT / "samples" / (u.rsplit("/", 1)[1][:90])).write_bytes(r.content)

# ---------------------------------------------------------------- E. RTEP report + TEAC page links
for u in ["https://www.pjm.com/planning/rtep-development/baseline-reports", "https://www.pjm.com/library/reports-notices/rtep-documents",
          "https://www.pjm.com/committees-and-groups/committees/teac", "https://www.pjm.com/planning/service-requests/serial-service-request-status"]:
    r = get(u)
    if r is None:
        continue
    note(page=u, status=r.status_code, size=len(r.content))
    if r.status_code == 200:
        hrefs = sorted(set(re.findall(r'href="([^"]+)"', r.text)))
        json.dump([h for h in hrefs if re.search(r"\.(pdf|xls|xlsx|csv|zip)(\?|$)|rtep|teac|planning", h, re.I)], open(OUT / ("links_" + slug(u) + ".json"), "w"), indent=1)
json.dump(log, open(OUT / "log.json", "w"), indent=1)
