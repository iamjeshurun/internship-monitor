from __future__ import annotations
import os, smtplib
from email.mime.text import MIMEText
import requests

ALERT_ISSUE_TITLE = "Job Monitor Alerts"

def send_github_alert(subject: str, body: str) -> bool:
    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        return False
    api = f"https://api.github.com/repos/{repo}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    response = requests.get(f"{api}/issues", headers=headers, params={"state": "open", "per_page": 100}, timeout=30)
    response.raise_for_status()
    issue = next((row for row in response.json() if row.get("title") == ALERT_ISSUE_TITLE and "pull_request" not in row), None)
    mention = os.environ.get("GITHUB_ALERT_MENTION", "").lstrip("@")
    content = f"### {subject}\n\n" + (f"@{mention}\n\n" if mention else "") + body
    if issue is None:
        response = requests.post(f"{api}/issues", headers=headers, json={"title": ALERT_ISSUE_TITLE, "body": "Private notification thread for internship matches and daily summaries.\n\n" + content}, timeout=30)
    else:
        response = requests.post(f"{api}/issues/{issue['number']}/comments", headers=headers, json={"body": content}, timeout=30)
    response.raise_for_status()
    return True

def send_email(subject: str, body: str) -> bool:
    user, password = os.environ.get("SMTP_USER"), os.environ.get("SMTP_PASSWORD")
    recipient = os.environ.get("NOTIFY_EMAIL", user or "")
    if not user or not password or not recipient:
        print("Email not configured; durable queue retained.\n" + subject + "\n" + body); return False
    msg = MIMEText(body); msg["Subject"], msg["From"], msg["To"] = subject, user, recipient
    with smtplib.SMTP(os.environ.get("SMTP_HOST", "smtp.gmail.com"), int(os.environ.get("SMTP_PORT", "587")), timeout=30) as server:
        server.starttls(); server.login(user, password); server.send_message(msg)
    return True

def send_digest(jobs: list[dict], errors: list[str]) -> bool:
    if not jobs: return True
    lines = [f"{len(jobs)} applications are ready for review", ""]
    for job in jobs:
        a = job["assessment"]
        priority = job.get("priority_program") or {}
        label = f"PRIORITY PROGRAM: {priority['name']} ({'official source verified' if priority.get('official_source') else 'verify on official board'})" if priority else ""
        lines += [label, f"[{a['score']}/100] {job['company']} — {job['title']}", job.get("location", ""), job["url"], "Why: " + "; ".join(a["reasons"][:4]), "Review: " + "; ".join(a["flags"]), ""]
    if errors: lines += ["Source warnings:", *errors]
    priority_count = sum(bool(job.get("priority_program")) for job in jobs)
    prefix = "PRIORITY PROGRAM" if priority_count else "ACTION READY"
    subject, body = f"{prefix}: {len(jobs)} internship match(es)", "\n".join(lines)
    try:
        if send_github_alert(subject, body): return True
    except Exception as exc: print(f"GitHub alert delivery failed: {exc}")
    try: return send_email(subject, body)
    except Exception as exc: print(f"Email delivery failed: {exc}"); return False
