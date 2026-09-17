"""Fetch public PJM inputs on a machine with internet access (used by the GitHub Actions workflow
.github/workflows/fetch_pjm.yml; also runnable locally). Writes under data/raw_real/pjm/:
  queue_snapshots/<YYYY-MM-DD>.xlsx (+ .csv)   the PJM New Services Queue export (dated)
  studies/<queue>_imp.pdf + .meta               impact studies with URL, fetch time, sha256, Last-Modified
  manifest.csv                                   what was fetched and why

Study selection is deterministic: projects with an impact-study link, submitted in [start_year,
end_year], sorted by submitted date, sampled evenly to max_studies. Nothing here touches the model.
"""
from __future__ import annotations
import argparse, hashlib, io, re, sys, time
from pathlib import Path
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw_real" / "pjm"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Accept": "application/pdf,*/*"}
EXPORT_URL = "https://services.pjm.com/PJMPlanningApi/api/Queue/ExportToXls"
# public key embedded in https://www.pjm.com/dist/interconnectionqueues.*.js (as used by gridstatus)
EXPORT_HEADERS = {"api-subscription-key": "E29477D0-70E0-4825-89B0-43F460BF9AB4", "Host": "services.pjm.com",
                  "Origin": "https://www.pjm.com", "Referer": "https://www.pjm.com/"}
STUDY_URL = "https://www.pjm.com/pub/planning/project-queues/impact_studies/{q}_imp.pdf"


def fetch_queue() -> pd.DataFrame:
    (RAW / "queue_snapshots").mkdir(parents=True, exist_ok=True)
    r = requests.post(EXPORT_URL, headers=EXPORT_HEADERS, timeout=120)
    r.raise_for_status()
    today = time.strftime("%Y-%m-%d")
    xlsx = RAW / "queue_snapshots" / f"{today}.xlsx"
    xlsx.write_bytes(r.content)
    df = pd.read_excel(io.BytesIO(r.content))
    df.to_csv(RAW / "queue_snapshots" / f"{today}.csv", index=False)
    print(f"queue export: {len(df)} rows, columns: {list(df.columns)[:40]}", flush=True)
    return df


def pick_studies(df: pd.DataFrame, start_year: int, end_year: int, max_studies: int) -> pd.DataFrame:
    col = {c.strip().lower(): c for c in df.columns}
    qn = col.get("project id") or col.get("queue number") or col.get("queue id")
    sub = col.get("submitted date") or col.get("queue date")
    sis = col.get("system impact study")
    d = df.copy()
    d["q_"] = d[qn].astype(str).str.strip()
    d["sub_"] = pd.to_datetime(d[sub], errors="coerce")
    d["sis_"] = d[sis].astype(str) if sis else ""
    has_link = d["sis_"].str.contains("http|\\.pdf", case=False, na=False) | d["sis_"].str.len().gt(3)
    d = d[has_link & d.sub_.dt.year.between(start_year, end_year)].sort_values("_sub")
    if len(d) > max_studies:
        step = len(d) / max_studies
        d = d.iloc[[int(i * step) for i in range(max_studies)]]
    print(f"selected {len(d)} candidate studies ({start_year}-{end_year})", flush=True)
    return d


def study_url(q: str, sis_value: str) -> str:
    m = re.search(r"https?://\S+\.pdf", str(sis_value))
    if m:
        return m.group(0)
    return STUDY_URL.format(q=q.replace("-", "").lower())


def fetch_studies(sel: pd.DataFrame, max_bytes: int = 150_000_000) -> pd.DataFrame:
    (RAW / "studies").mkdir(parents=True, exist_ok=True)
    rows = []; total = 0
    for r in sel.itertuples():
        q = r.q_; url = study_url(q, r.sis_)
        dest = RAW / "studies" / f"{q.replace('-', '').lower()}_imp.pdf"
        try:
            resp = requests.get(url, headers=UA, timeout=60)
        except requests.RequestException as e:
            rows.append(dict(queue=q, url=url, status="error", note=str(e)[:100])); continue
        ok = resp.status_code == 200 and resp.content[:4] == b"%PDF" and len(resp.content) < 6_000_000
        if ok:
            dest.write_bytes(resp.content); total += len(resp.content)
            dest.with_suffix(".pdf.meta").write_text(
                f"url={url}\nfetched={time.strftime('%Y-%m-%dT%H:%M:%S')}\nsha256={hashlib.sha256(resp.content).hexdigest()}\n"
                f"last_modified={resp.headers.get('Last-Modified', '')}\nsubmitted_date={r.sub_.date() if pd.notna(r.sub_) else ''}\n")
        rows.append(dict(queue=q, url=url, status=("ok" if ok else f"http_{resp.status_code}"), bytes=len(resp.content),
                         last_modified=resp.headers.get("Last-Modified", ""), submitted=str(r.sub_.date()) if pd.notna(r.sub_) else ""))
        time.sleep(0.4)
        if total > max_bytes:
            print("byte budget reached", flush=True); break
    man = pd.DataFrame(rows); man.to_csv(RAW / "manifest.csv", index=False)
    print(man.status.value_counts().to_dict(), f"total {total/1e6:.1f} MB", flush=True)
    return man


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-year", type=int, default=2016); ap.add_argument("--end-year", type=int, default=2021)
    ap.add_argument("--max-studies", type=int, default=300)
    a = ap.parse_args()
    df = fetch_queue()
    sel = pick_studies(df, a.start_year, a.end_year, a.max_studies)
    man = fetch_studies(sel)
    if (man.status == "ok").sum() < 50:
        print("WARNING: fewer than 50 studies fetched", flush=True)
