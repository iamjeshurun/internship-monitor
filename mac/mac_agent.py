from __future__ import annotations
import json, os, time
from datetime import datetime, timezone
from pathlib import Path
import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import ConnectionError as ReqConnectionError, Timeout
from urllib3.util.retry import Retry
from notifier import notify as native_notify

ROOT = Path(__file__).resolve().parent.parent
LOCAL = Path(os.environ.get("JOB_MONITOR_LOCAL_DIR", Path.home()/"Library/Application Support/JobMonitor"))
LOCAL.mkdir(parents=True, exist_ok=True)
STATE = LOCAL/"notified.json"
CACHE = LOCAL/"review_queue.json"
HEALTH = LOCAL/"agent_health.json"
# After this many consecutive failed polls (~15 min at a 180s interval) tell the
# user once that notifications are paused, so silence never looks like "no jobs".
STALE_ALERT_AFTER = 5

SESSION = requests.Session()
SESSION.mount("https://", HTTPAdapter(max_retries=Retry(
    total=4, connect=4, read=3, backoff_factor=1.5,
    status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"])))

DONE_STATUSES = {"applied", "assessment", "interview", "offer", "rejected", "dismissed"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path, fallback):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return fallback


def _get(url: str, token: str):
    """GET with the pooled session, then one fresh-connection retry on a
    transient network error (api.github.com occasionally stalls a kept-alive
    socket from this host)."""
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.raw+json"}
    try:
        return SESSION.get(url, headers=headers, timeout=(6, 20))
    except (Timeout, ReqConnectionError):
        time.sleep(2)
        with requests.Session() as fresh:
            fresh.headers["Connection"] = "close"
            return fresh.get(url, headers=headers, timeout=(8, 35))


def fetch_queue():
    local = os.environ.get("JOB_MONITOR_QUEUE_FILE")
    if local:
        return json.loads(Path(local).read_text())
    repo, token = os.environ["JOB_MONITOR_GITHUB_REPO"], os.environ["JOB_MONITOR_GITHUB_TOKEN"]
    jobs, generated = {}, ""
    for filename in ("review_queue.json", "priority_queue.json"):
        url = f"https://api.github.com/repos/{repo}/contents/data/{filename}"
        r = _get(url, token)
        if r.status_code == 404 and filename == "priority_queue.json":
            continue
        r.raise_for_status()
        payload = r.json()
        generated = max(generated, payload.get("generated_at") or "")
        for job in payload.get("jobs", []):
            jobs[job["key"]] = job
    # The fast priority watcher runs on this Mac. Merge its queue over the
    # slower cloud queues so newly opened programs are available immediately.
    local_priority = Path(os.environ.get("JOB_MONITOR_LOCAL_PRIORITY_QUEUE", LOCAL / "priority_queue.local.json"))
    if local_priority.exists():
        payload = json.loads(local_priority.read_text())
        generated = max(generated, payload.get("generated_at") or "")
        for job in payload.get("jobs", []):
            jobs[job["key"]] = job
    return {"generated_at": generated, "jobs": list(jobs.values())}


def notify(job):
    priority = job.get("priority_program") or {}
    title = f"{priority.get('name') or job['company']} — {job['title']}".replace('"', "'")
    verified = "official source verified" if priority.get("official_source") else "ready for review"
    message = f"{job['assessment']['score']}/100 · {job.get('location','')} · {verified}".replace('"', "'")
    app_title = "Priority Program" if priority else "Job Monitor"
    if os.environ.get("JOB_MONITOR_DRY_RUN") == "1":
        print("NOTIFY", app_title, title, message)
        return
    native_notify(app_title, message, title, job.get("url") or "http://127.0.0.1:8765")


def _write_health(ok: bool, error: str | None):
    health = _load(HEALTH, {})
    fails = 0 if ok else int(health.get("consecutive_failures", 0)) + 1
    health.update({
        "last_attempt": _now(),
        "consecutive_failures": fails,
        "last_error": None if ok else error,
    })
    if ok:
        health["last_success"] = _now()
    if fails == STALE_ALERT_AFTER and os.environ.get("JOB_MONITOR_DRY_RUN") != "1":
        native_notify("Job Monitor", "Can't reach GitHub — new-job notifications are paused.", "Check your network / token")
    HEALTH.write_text(json.dumps(health, indent=2))


def once():
    try:
        queue = fetch_queue()
    except Exception as exc:
        _write_health(False, f"{type(exc).__name__}: {exc}")
        raise
    CACHE.write_text(json.dumps(queue, indent=2))
    _write_health(True, None)

    notified = set(_load(STATE, []))
    statuses = _load(LOCAL / "status.json", {})
    for job in queue.get("jobs", []):
        value = statuses.get(job["key"], {})
        local_status = value.get("status") if isinstance(value, dict) else value
        if job["key"] not in notified and local_status not in DONE_STATUSES:
            notify(job)
            notified.add(job["key"])
    STATE.write_text(json.dumps(sorted(notified), indent=2))


if __name__ == "__main__":
    once()
