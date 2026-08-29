from __future__ import annotations
import json, os
from pathlib import Path
import requests
from notifier import notify as native_notify

ROOT = Path(__file__).resolve().parent.parent
LOCAL = Path(os.environ.get("JOB_MONITOR_LOCAL_DIR", Path.home()/"Library/Application Support/JobMonitor"))
LOCAL.mkdir(parents=True, exist_ok=True)
STATE = LOCAL/"notified.json"; CACHE = LOCAL/"review_queue.json"

def fetch_queue():
    local = os.environ.get("JOB_MONITOR_QUEUE_FILE")
    if local: return json.loads(Path(local).read_text())
    repo, token = os.environ["JOB_MONITOR_GITHUB_REPO"], os.environ["JOB_MONITOR_GITHUB_TOKEN"]
    url = f"https://api.github.com/repos/{repo}/contents/data/review_queue.json"
    r = requests.get(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.raw+json"}, timeout=30); r.raise_for_status(); return r.json()

def notify(job):
    title = f"{job['company']} — {job['title']}".replace('"', "'")
    message = f"{job['assessment']['score']}/100 · {job.get('location','')} · ready for review".replace('"', "'")
    if os.environ.get("JOB_MONITOR_DRY_RUN") == "1": print("NOTIFY", title, message); return
    native_notify("Job Monitor", message, title, job.get("url") or "http://127.0.0.1:8765")

def once():
    queue = fetch_queue(); CACHE.write_text(json.dumps(queue, indent=2))
    notified = set(json.loads(STATE.read_text())) if STATE.exists() else set()
    for job in queue.get("jobs", []):
        if job["key"] not in notified: notify(job); notified.add(job["key"])
    STATE.write_text(json.dumps(sorted(notified), indent=2))

if __name__ == "__main__": once()
