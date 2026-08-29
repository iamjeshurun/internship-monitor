from __future__ import annotations
import os, smtplib
from email.mime.text import MIMEText

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
        lines += [f"[{a['score']}/100] {job['company']} — {job['title']}", job.get("location", ""), job["url"], "Why: " + "; ".join(a["reasons"][:4]), "Review: " + "; ".join(a["flags"]), ""]
    if errors: lines += ["Source warnings:", *errors]
    try: return send_email(f"ACTION READY: {len(jobs)} internship match(es)", "\n".join(lines))
    except Exception as exc: print(f"Email delivery failed: {exc}"); return False
