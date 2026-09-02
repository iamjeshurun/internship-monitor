from __future__ import annotations
import json, os
from pathlib import Path
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from notifier import notify as native_notify

ROOT = Path(__file__).resolve().parent.parent
LOCAL = Path(os.environ.get("JOB_MONITOR_LOCAL_DIR", Path.home()/"Library/Application Support/JobMonitor"))
LOCAL.mkdir(parents=True, exist_ok=True)
STATE = LOCAL/"notified.json"; CACHE = LOCAL/"review_queue.json"
SESSION = requests.Session()
SESSION.mount("https://", HTTPAdapter(max_retries=Retry(total=3, connect=3, read=2, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"])))

def fetch_queue():
    local = os.environ.get("JOB_MONITOR_QUEUE_FILE")
    if local: return json.loads(Path(local).read_text())
    repo, token = os.environ["JOB_MONITOR_GITHUB_REPO"], os.environ["JOB_MONITOR_GITHUB_TOKEN"]
    jobs, generated = {}, ""
    for filename in ("review_queue.json", "priority_queue.json"):
        url = f"https://api.github.com/repos/{repo}/contents/data/{filename}"
        r = SESSION.get(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.raw+json"}, timeout=(10, 25))
        if r.status_code == 404 and filename == "priority_queue.json": continue
        r.raise_for_status(); payload = r.json(); generated = max(generated, payload.get("generated_at") or "")
        for job in payload.get("jobs", []): jobs[job["key"]] = job
    return {"generated_at": generated, "jobs": list(jobs.values())}

def notify(job):
    priority = job.get("priority_program") or {}
    title = f"{priority.get('name') or job['company']} — {job['title']}".replace('"', "'")
    verified = "official source verified" if priority.get("official_source") else "ready for review"
    message = f"{job['assessment']['score']}/100 · {job.get('location','')} · {verified}".replace('"', "'")
    app_title = "Priority Program" if priority else "Job Monitor"
    if os.environ.get("JOB_MONITOR_DRY_RUN") == "1": print("NOTIFY", app_title, title, message); return
    native_notify(app_title, message, title, job.get("url") or "http://127.0.0.1:8765")

def once():
    queue = fetch_queue(); CACHE.write_text(json.dumps(queue, indent=2))
    notified = set(json.loads(STATE.read_text())) if STATE.exists() else set()
    status_path = LOCAL/"status.json"
    statuses = json.loads(status_path.read_text()) if status_path.exists() else {}
    for job in queue.get("jobs", []):
        value = statuses.get(job["key"], {})
        local_status = value.get("status") if isinstance(value, dict) else value
        if job["key"] not in notified and local_status not in {"applied", "rejected", "dismissed", "offer"}: notify(job); notified.add(job["key"])
    STATE.write_text(json.dumps(sorted(notified), indent=2))

if __name__ == "__main__": once()
