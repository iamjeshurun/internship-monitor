from __future__ import annotations
import argparse, email, json, os, re, subprocess
from email.policy import default
from pathlib import Path
import requests

PATTERNS = [
    re.compile(r"thank you for apply(?:ing|ied)", re.I),
    re.compile(r"thank(?:s| you) for your interest", re.I),
    re.compile(r"application (?:has been )?received", re.I),
    re.compile(r"application (?:was |has been )?submitted", re.I),
    re.compile(r"we received your application", re.I),
    re.compile(r"we have received", re.I),
    re.compile(r"your application to", re.I),
    re.compile(r"candidate application", re.I),
    re.compile(r"application confirmation", re.I),
]
STAGES = [("offer", re.compile(r"offer of employment|pleased to offer|employment offer", re.I)), ("assessment", re.compile(r"assessment|coding challenge|hackerrank|codesignal", re.I)), ("interview", re.compile(r"interview|schedule a call", re.I)), ("rejected", re.compile(r"unfortunately|not moving forward|other candidates", re.I))]

def classify(subject: str, body: str, sender: str, date: str) -> dict | None:
    text = f"{subject}\n{body}"
    if not any(p.search(text) for p in PATTERNS) and not any(p.search(text) for _, p in STAGES): return None
    stage = "applied"
    for name, pattern in STAGES:
        if pattern.search(text): stage = name; break
    req = re.search(r"(?:requisition|job id|req(?:uisition)?)[ #:.-]*([A-Z0-9-]{4,})", text, re.I)
    company = sender.split("<")[0].strip(' "') or sender
    return {"subject": subject, "company_hint": company, "date": date, "stage": stage, "requisition_id": req.group(1) if req else None, "confidence": "high" if any(p.search(text) for p in PATTERNS) else "medium"}

def eml_directory(path: Path) -> list[dict]:
    results = []
    for file in path.rglob("*.eml"):
        msg = email.message_from_bytes(file.read_bytes(), policy=default)
        body = msg.get_body(preferencelist=("plain", "html"))
        item = classify(str(msg.get("subject", "")), body.get_content() if body else "", str(msg.get("from", "")), str(msg.get("date", "")))
        if item: results.append(item)
    return results

def outlook_graph(token: str) -> list[dict]:
    url = "https://graph.microsoft.com/v1.0/me/messages?$top=250&$select=subject,from,receivedDateTime,bodyPreview"
    results = []
    while url:
        data = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=30).json()
        for msg in data.get("value", []):
            sender = ((msg.get("from") or {}).get("emailAddress") or {}).get("name", "")
            item = classify(msg.get("subject", ""), msg.get("bodyPreview", ""), sender, msg.get("receivedDateTime", ""))
            if item: results.append(item)
        url = data.get("@odata.nextLink")
    return results

def gmail_api(token: str) -> list[dict]:
    headers = {"Authorization": f"Bearer {token}"}
    data = requests.get("https://gmail.googleapis.com/gmail/v1/users/me/messages", headers=headers, params={"q": '"application received" OR "thank you for applying" OR "coding challenge" OR interview', "maxResults": 250}, timeout=30).json()
    results = []
    for row in data.get("messages", []):
        msg = requests.get(f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{row['id']}", headers=headers, params={"format": "metadata", "metadataHeaders": ["Subject", "From", "Date"]}, timeout=30).json()
        hs = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
        item = classify(hs.get("subject", ""), msg.get("snippet", ""), hs.get("from", ""), hs.get("date", ""))
        if item: results.append(item)
    return results

def apple_mail(account_address: str, years: int = 5, days: int | None = None) -> list[dict]:
    """Read matching message metadata through Mail's approved Automation access.

    Message bodies and credentials never leave Mail. AppleScript returns only the
    subject, sender, and received date for messages matching application keywords.
    """
    safe_address = account_address.replace('\\', '\\\\').replace('"', '\\"')
    lookback_days = days if days is not None else years * 365
    script = f'''
tell application "Mail"
  set cutoffDate to (current date) - ({lookback_days} * days)
  set keywords to {{"application", "applied", "interest", "received", "assessment", "coding challenge", "interview", "offer", "not moving forward", "unfortunately"}}
  set usefulMailboxes to {{"INBOX", "Inbox"}}
  set recordSep to ASCII character 30
  set fieldSep to ASCII character 31
  set outputText to ""
  repeat with acct in every account
    if (email addresses of acct) contains "{safe_address}" then
      repeat with box in every mailbox of acct
        if usefulMailboxes contains (name of box) then
          repeat with keywordText in keywords
            try
              set matchingMessages to (every message of box whose date received > cutoffDate and subject contains keywordText)
              repeat with msg in matchingMessages
                set outputText to outputText & (message id of msg) & fieldSep & (subject of msg) & fieldSep & (sender of msg) & fieldSep & ((date received of msg) as string) & recordSep
              end repeat
            end try
          end repeat
        end if
      end repeat
    end if
  end repeat
  return outputText
end tell
'''
    try:
        proc = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=True, timeout=90)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Apple Mail scan exceeded 90 seconds and was stopped safely") from exc
    found, seen = [], set()
    for row in proc.stdout.split(chr(30)):
        fields = row.strip().split(chr(31))
        if len(fields) != 4 or fields[0] in seen:
            continue
        seen.add(fields[0])
        item = classify(fields[1], "", fields[2], fields[3])
        if item:
            item["mailbox_account"] = account_address
            found.append(item)
    return found

def main():
    p = argparse.ArgumentParser(); p.add_argument("--eml-dir", type=Path); p.add_argument("--provider", choices=["outlook", "gmail", "apple-mail"]); p.add_argument("--account"); p.add_argument("--years", type=int, default=5); p.add_argument("--days", type=int); p.add_argument("--merge-input", type=Path, nargs="+"); p.add_argument("--output", type=Path, default=Path("data/application_history.json")); args = p.parse_args()
    if args.merge_input:
        combined = [item for path in args.merge_input for item in json.loads(path.read_text()).get("applications", [])]
        results, seen = [], set()
        for item in combined:
            key = (item.get("subject"), item.get("date"), item.get("mailbox_account"))
            if key not in seen:
                seen.add(key); results.append(item)
    elif args.eml_dir: results = eml_directory(args.eml_dir)
    elif args.provider == "outlook": results = outlook_graph(os.environ["OUTLOOK_ACCESS_TOKEN"])
    elif args.provider == "gmail": results = gmail_api(os.environ["GMAIL_ACCESS_TOKEN"])
    elif args.provider == "apple-mail":
        if not args.account: p.error("--account is required with --provider apple-mail")
        results = apple_mail(args.account, args.years, args.days)
    else: p.error("provide --eml-dir or --provider")
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps({"applications": results}, indent=2)); print(f"Found {len(results)} likely application events")

if __name__ == "__main__": main()
