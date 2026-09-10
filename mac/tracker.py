from __future__ import annotations
import hashlib, json, re
from datetime import datetime, timezone
from pathlib import Path

STAGE_ORDER = {"ready": 0, "reviewing": 1, "applied": 2, "assessment": 3, "interview": 4, "offer": 5, "rejected": 5, "dismissed": 6}
STOP = {"job", "application", "intern", "internship", "the", "and", "for", "at", "you", "your", "from", "team"}
GENERIC_ROLE = {"thank", "thanks", "interest", "received", "submitted", "invitation", "assessment", "assessments", "process", "prepare", "track", "important", "information", "successfully", "applied", "update"}
GENERIC_COMPANY = {"capital", "company", "corp", "corporation", "group", "holdings", "inc", "llc", "careers", "recruiting", "talent", "trading"}

def load_json(path: Path, fallback):
    try: return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError): return fallback

def tokens(value: str) -> set[str]:
    return {x for x in re.findall(r"[a-z0-9]+", (value or "").lower()) if len(x) > 2 and x not in STOP}

def event_key(event: dict) -> str:
    raw = "\x1f".join(str(event.get(k, "")) for k in ("mailbox_account", "date", "subject"))
    return "email-" + hashlib.sha256(raw.encode()).hexdigest()[:20]

def application_key(event: dict) -> str:
    req = str(event.get("requisition_id") or "").strip().lower()
    if req:
        return "application-req-" + hashlib.sha256(req.encode()).hexdigest()[:20]
    company_tokens = tokens(event.get("company_hint", ""))
    company = "-".join(sorted(company_tokens)) or re.sub(r"[^a-z0-9]+", "-", event.get("company_hint", "").lower()).strip("-")
    role_tokens = tokens(event.get("role_hint", "")) - company_tokens - GENERIC_ROLE
    if event.get("stage") == "assessment":
        role_tokens -= {"action", "required", "reminder", "complete", "completed", "completing", "skills", "next", "step", "take"}
    role = "-".join(sorted(role_tokens)) or "general"
    if company and company not in {"greenhouse", "workday", "ashby", "lever", "icims"}:
        raw = f"{company}|{role}"
        return "application-" + hashlib.sha256(raw.encode()).hexdigest()[:20]
    return event_key(event)

def match_event(event: dict, jobs: list[dict]) -> dict | None:
    req = str(event.get("requisition_id") or "").lower()
    if req:
        exact = next((j for j in jobs if req in " ".join(str(j.get(k, "")).lower() for k in ("external_id", "url", "title"))), None)
        if exact: return exact
    event_tokens = tokens(f"{event.get('subject','')} {event.get('company_hint','')}")
    ranked = []
    for job in jobs:
        company = tokens(job.get("company", "")) - GENERIC_COMPANY
        event_company = tokens(event.get("company_hint", "")) - GENERIC_COMPANY
        title = tokens(job.get("title", ""))
        company_overlap, title_overlap = len(event_company & company), len(event_tokens & title)
        score = company_overlap * 4 + title_overlap
        # Never attach a generic ATS message to a job merely because both titles
        # contain words such as "software engineering intern".
        if company_overlap: ranked.append((score, job))
    return max(ranked, key=lambda row: row[0])[1] if ranked else None

def merge_tracker(queue: dict, history: dict, statuses: dict) -> list[dict]:
    jobs = [dict(job) for job in queue.get("jobs", [])]
    items = {job["key"]: {**job, "status": statuses.get(job["key"], {}).get("status", statuses.get(job["key"], "ready")) if isinstance(statuses.get(job["key"], {}), dict) else statuses[job["key"]], "status_source": "manual" if job["key"] in statuses else "queue"} for job in jobs}
    for event in history.get("applications", []):
        matched = match_event(event, jobs); key = matched["key"] if matched else application_key(event)
        if key not in items:
            items[key] = {"key": key, "company": event.get("company_hint") or "Email-detected application", "title": event.get("role_hint") or event.get("subject") or "Application update", "location": "", "url": "", "assessment": {"score": "—", "reasons": [], "flags": []}, "status": "applied", "status_source": "email"}
        item, manual, stage = items[key], statuses.get(key), event.get("stage", "applied")
        manual_status = manual.get("status") if isinstance(manual, dict) else manual
        email_can_update = not manual or manual_status in {"ready", "reviewing"}
        if email_can_update and STAGE_ORDER.get(stage, 0) >= STAGE_ORDER.get(item.get("status", "ready"), 0): item["status"], item["status_source"] = stage, "email"
        item.setdefault("events", []).append(event); item["last_update"] = event.get("date", "")
    return sorted(items.values(), key=lambda item: (STAGE_ORDER.get(item.get("status", "ready"), 0), item.get("last_update", "")), reverse=True)

def save_status(path: Path, key: str, status: str, source: str = "manual"):
    state = load_json(path, {}); state[key] = {"status": status, "source": source, "updated_at": datetime.now(timezone.utc).isoformat()}; path.write_text(json.dumps(state, indent=2))
