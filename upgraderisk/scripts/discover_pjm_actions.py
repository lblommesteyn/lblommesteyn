"""Discovery job (runs on a GitHub Actions runner with internet access).
Finds where PJM publishes transmission-upgrade status/cost data and which historical snapshots exist.
Writes small JSON/text results under upgraderisk/data/raw/discovery/.
"""
from __future__ import annotations
import json, re, time
from pathlib import Path
import requests

OUT = Path(__file__).resolve().parents[1] / "data" / "raw" / "discovery"
OUT.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
KEY = {"api-subscription-key": "E29477D0-70E0-4825-89B0-43F460BF9AB4", "Host": "services.pjm.com", "Origin": "https://www.pjm.com", "Referer": "https://www.pjm.com/"}
log = []


def note(**kw):
    kw["t"] = time.strftime("%H:%M:%S"); log.append(kw); print(json.dumps(kw)[:300], flush=True)


def get(url, **kw):
    try:
        r = requests.get(url, headers=UA, timeout=60, **kw); return r
    except Exception as e:
        note(url=url, error=str(e)[:120]); return None


# 1. PJM pages that may link to construction-status / upgrade exports
pages = ["https://www.pjm.com/planning/project-construction", "https://www.pjm.com/planning/project-construction/transmission-construction-status",
         "https://www.pjm.com/planning/rtep-development/rtep-upgrades", "https://www.pjm.com/planning/rtep-development", "https://www.pjm.com/planning",
         "https://www.pjm.com/planning/rtep-development/rtep-upgrade-status", "https://www.pjm.com/planning/project-construction/construction-status"]
links = {}
for u in pages:
    r = get(u)
    if r is None:
        continue
    note(url=u, status=r.status_code, size=len(r.content))
    if r.status_code == 200:
        (OUT / (re.sub(r"[^a-z0-9]+", "_", u.lower()) + ".html")).write_text(r.text[:400000])
        for m in re.finditer(r'(?:href|src)="([^"]+)"', r.text):
            h = m.group(1)
            if re.search(r"(construction|upgrade|rtep|status|\.xls|\.xlsx|\.csv|\.pdf|\.js)", h, re.I):
                links.setdefault(u, []).append(h)
json.dump(links, open(OUT / "page_links.json", "w"), indent=1)

# 2. JS bundles: look for Planning API endpoints
api_hits = {}
for u, hs in links.items():
    for h in hs:
        if h.endswith(".js") and ("planning" in h.lower() or "upgrade" in h.lower() or "construction" in h.lower() or "dist" in h.lower()):
            full = h if h.startswith("http") else "https://www.pjm.com" + h
            r = get(full)
            if r is not None and r.status_code == 200:
                found = sorted(set(re.findall(r"(?:api/[A-Za-z0-9_/\-]{3,80})", r.text)))
                keys = sorted(set(re.findall(r"[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}", r.text)))
                if found or keys:
                    api_hits[full] = dict(endpoints=found[:200], keys=keys[:10])
                    note(js=full, n_endpoints=len(found), keys=keys[:3])
json.dump(api_hits, open(OUT / "js_api_hits.json", "w"), indent=1)

# 3. Probe Planning API export endpoints for upgrades
probes = {}
for name in ["Upgrade", "Upgrades", "RtepUpgrade", "RTEPUpgrade", "RtepUpgrades", "Project", "Projects", "ConstructionStatus", "TransmissionConstructionStatus",
             "TCS", "BaselineUpgrade", "NetworkUpgrade", "Upgrade/Search", "Upgrades/Search"]:
    for method in ("POST", "GET"):
        url = f"https://services.pjm.com/PJMPlanningApi/api/{name}/ExportToXls"
        try:
            r = requests.request(method, url, headers=KEY, timeout=60)
            probes[f"{method} {url}"] = dict(status=r.status_code, ctype=r.headers.get("Content-Type", ""), size=len(r.content))
            if r.status_code == 200 and len(r.content) > 2000:
                (OUT / f"probe_{name.replace('/', '_')}_{method}.bin").write_bytes(r.content[:20_000_000])
                note(probe=url, method=method, status=200, size=len(r.content), ctype=r.headers.get("Content-Type", ""))
        except Exception as e:
            probes[f"{method} {url}"] = dict(error=str(e)[:100])
json.dump(probes, open(OUT / "api_probes.json", "w"), indent=1)

# 4. Wayback CDX: historical PJM files about construction status / RTEP upgrades
cdx_out = {}
for pat, label in [(r".*(construction|tcs).*\.(xls|xlsx|pdf|csv)", "construction"), (r".*(rtep).*(status|upgrade|project).*\.(xls|xlsx|pdf|csv)", "rtep"),
                   (r".*upgrade.*\.(xls|xlsx|csv)", "upgrade_xls"), (r".*PJMPlanningApi.*", "planning_api"), (r".*(teac).*\.(xls|xlsx|csv)", "teac_xls")]:
    url = ("http://web.archive.org/cdx/search/cdx?url=pjm.com&matchType=domain&output=json&fl=original,timestamp,mimetype,length,statuscode"
           f"&filter=original:(?i){pat}&collapse=digest&limit=20000")
    r = get(url)
    if r is not None and r.status_code == 200:
        try:
            rows = r.json()
        except Exception:
            rows = []
        cdx_out[label] = rows
        note(cdx=label, rows=len(rows))
        (OUT / f"cdx_{label}.json").write_text(json.dumps(rows))
    else:
        note(cdx=label, status=(r.status_code if r is not None else None))

# 5. Wayback availability of the current PJM upgrade page over the years
avail = {}
for y in range(2012, 2026):
    for u in ["https://www.pjm.com/planning/project-construction/transmission-construction-status", "https://www.pjm.com/planning/rtep-development/rtep-upgrades"]:
        r = get(f"http://archive.org/wayback/available?url={u}&timestamp={y}0601")
        if r is not None and r.status_code == 200:
            try:
                avail[f"{y} {u}"] = r.json().get("archived_snapshots", {})
            except Exception:
                pass
json.dump(avail, open(OUT / "wayback_availability.json", "w"), indent=1)
json.dump(log, open(OUT / "log.json", "w"), indent=1)
print("discovery done")
