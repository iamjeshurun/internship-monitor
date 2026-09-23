from __future__ import annotations
import argparse, email, json, os, re, subprocess
from email.utils import parseaddr
from email.policy import default
from pathlib import Path
import requests

PATTERNS = [
    re.compile(r"thank(?:s| you) for apply(?:ing)", re.I),
    re.compile(r"thank(?:s| you) for your (?:application|interest)", re.I),
    re.compile(r"application (?:has been |was )?received", re.I),
    re.compile(r"application (?:was |has been )?submitted", re.I),
    re.compile(r"we received your application", re.I),
    re.compile(r"we have received your application", re.I),
    re.compile(r"candidate application", re.I),
    re.compile(r"application confirmation", re.I),
    re.compile(r"important information about your application", re.I),
]

# A "received" signal in the SUBJECT is a strong indicator that the message is an
# acknowledgement, even when the body quotes conditional rejection wording.
SUBJECT_RECEIVED = re.compile(
    r"thank(?:s| you) for (?:apply|your (?:application|interest))|application (?:received|submitted|confirmation)|"
    r"we(?:'| ha)?ve got your .*application|received your application|application to |applied to ",
    re.I,
)

# Decisive rejection wording. "unfortunately"/"regret" alone are NOT here — they
# appear constantly in acknowledgement boilerplate ("unfortunately we cannot
# respond to every applicant"). They only count via REJECTION_SOFT + context.
REJECTION_STRONG = re.compile(
    r"regret to inform|"
    r"will not be (?:moving|proceeding|progressing) (?:forward|ahead)|"
    r"not (?:be )?(?:moving|proceeding|progressing) (?:forward|ahead) with your (?:application|candidacy)|"
    r"decided not to (?:move|proceed|continue|progress)|"
    r"(?:decided|choosing|chosen|elected|opted|going) to (?:move|proceed|continue|go) (?:forward |ahead )?with other (?:candidate|applicant)|"
    r"(?:move|proceed|continue) (?:forward |ahead )?with (?:other|different) (?:candidate|applicant)|"
    r"won'?t be (?:proceeding|moving forward|progressing)|"
    r"unable to (?:move forward|offer you a|progress your application)|"
    r"no longer (?:be )?(?:consider|in consideration)|"
    r"your application has not been successful|not been selected to (?:move|proceed|continue)|"
    r"we will not be extending (?:you )?an offer|"
    r"pursu(?:e|ing) other candidate",
    re.I,
)
REJECTION_SOFT = re.compile(r"\bunfortunately\b|\bwe regret\b|\bregretfully\b", re.I)
DECISION_CONTEXT = re.compile(
    r"mov\w*\s+forward|proceed|continu\w*|advanc\w*|your (?:application|candidacy)|"
    r"other candidate|other applicant|this (?:role|position|time)|an offer|not (?:be )?select",
    re.I,
)

OFFER = re.compile(r"offer of employment|pleased to (?:extend|offer)|(?:internship|employment|formal) offer|offer letter", re.I)
INTERVIEW = re.compile(
    r"interview invitation|invit(?:e|ed|ation)[^.\n]{0,40}interview|would like to (?:interview|schedule)|"
    r"schedule (?:a|your|an) (?:interview|call|conversation|chat)|next step[^.\n]{0,50}interview|"
    r"phone screen|recruiter (?:call|screen)|hiring manager (?:call|conversation)",
    re.I,
)
# Assessment requires an ACTION the candidate must take. A bare vendor name or a
# "you may be asked to..." sentence is not an assessment.
ASSESSMENT = re.compile(
    r"assessment invitation|invitation (?:for|to)[^.\n]{0,30}(?:assessment|online assessment)|"
    r"(?:complete|start|begin|take|finish|submit)[^.\n]{0,30}(?:online |coding |technical |skills )?(?:assessment|challenge|exercise|test)\b|"
    r"(?:complete|start|take|begin|invited?[^.\n]{0,20}to)[^.\n]{0,20}(?:hackerrank|codesignal|hackerearth|codility|coderpad)|"
    r"coding challenge (?:is|link|by|due|invitation)|technical (?:screen|exercise) (?:is|link|by|invitation)|"
    r"thank you for complet(?:ing|ed)[^.\n]{0,40}(?:assessment|challenge|exercise)",
    re.I,
)

# "Hard" evidence — a concrete next step aimed at the candidate right now, not a
# description of the process. Used to allow a stage advance when the SUBJECT is a
# plain application receipt (which otherwise stays "applied").
OFFER_HARD = re.compile(r"offer of employment|offer letter|pleased to (?:extend|offer) you|your offer (?:details|is attached)", re.I)
INTERVIEW_HARD = re.compile(
    r"interview (?:invitation|is (?:scheduled|confirmed)|request)|invit(?:e|ed|ation)[^.\n]{0,30}(?:to )?interview|"
    r"schedule your interview|book (?:a|your) (?:time|interview)|your interview (?:with|on|is)|"
    r"available (?:times|slots) for (?:your |a )?interview|calendly\.com|"
    r"phone screen (?:is|scheduled|with)|(?:pick|choose|select) a time",
    re.I,
)
ASSESSMENT_HARD = re.compile(
    r"assessment invitation|your assessment (?:link|is ready|is due|must be completed)|"
    r"complete (?:your |the |this )(?:online |coding |technical |skills )?(?:assessment|challenge|exercise)[^.\n]{0,40}\b(?:by|before|within|link|here)\b|"
    r"(?:hackerrank|codesignal|hackerearth|codility|coderpad)[^.\n]{0,30}(?:link|invitation|by|due|complete)|"
    r"thank you for complet(?:ing|ed)[^.\n]{0,40}(?:assessment|challenge|exercise)",
    re.I,
)

GENERIC_SENDERS = {"greenhouse", "workday", "ashby", "lever", "icims", "smartrecruiters", "jobvite", "successfactors", "no reply", "noreply"}

# Sentences that describe hypotheticals, definitions, or vendor lists rather than
# the outcome of THIS message. Dropped before stage detection.
NON_STATUS_BOILERPLATE = [
    re.compile(r"means the position is either no longer open,\s*you withdrew from consideration,\s*or you were not selected for the role", re.I),
    re.compile(r"you (?:may|might|could)[^.\n]{0,80}(?:assessment|challenge|test|hackerrank|codesignal|invitation)", re.I),
    re.compile(r"(?:trusted platforms?|our vendors?|partners? such as)[^.\n]{0,120}", re.I),
    # Legal disclaimers: "this is not an offer of employment", "does not
    # constitute/guarantee an offer/interview", "no offer is implied".
    re.compile(r"\b(?:is|are|was|were|be|does|do|did|shall|will|should|can|cannot|could)\s+not\b[^.\n]{0,60}\b(?:an?\s+)?(?:offer|guarantee|promise|commitment|contract)\b[^.\n]{0,60}", re.I),
    re.compile(r"\b(?:not|no|never|neither|nor|without)\b[^.\n]{0,40}\boffers?\b[^.\n]{0,60}", re.I),
    re.compile(r"\b(?:nothing|none)\b[^.\n]{0,60}\b(?:constitutes?|creates?|implies|guarantees?)\b[^.\n]{0,60}\b(?:offer|employment|contract)\b[^.\n]{0,40}", re.I),
    re.compile(r"\bconstitutes?\b[^.\n]{0,30}\b(?:an?\s+)?offer\b[^.\n]{0,60}", re.I),
]
_CONDITIONAL_SENTENCE = re.compile(
    r"^\s*(?:if|should|in the event|please note that if|were you|unless)\b|"
    r"\b(?:means (?:the|that|a|closed)|may be (?:asked|invited|required|contacted)|you may (?:receive|be|need|have to)|"
    r"if (?:you are |you're |you have |not |we |your |selected)|should you (?:be|not|advance|progress|proceed))",
    re.I,
)
# Forward-looking "here's how our process works" sentences in a receipt — they
# describe possible future steps, not this message's outcome.
_PROCESS_DESCRIPTION = re.compile(
    r"\b(?:in the coming (?:days|weeks)|over the (?:coming|next) (?:days|weeks)|"
    r"our (?:team|recruiter|recruiting team|talent team) will (?:review|be in touch|reach out|contact|follow up)|"
    r"we will (?:review|be in touch|reach out|contact you|follow up|let you know)|"
    r"you will (?:hear (?:from|back)|be (?:contacted|notified))|"
    r"if (?:your|there is a) (?:qualifications?|background|match)|"
    r"next steps (?:in (?:our|the) (?:process|hiring process))|"
    r"typically|generally|the (?:next|following) (?:phase|stage|steps?) (?:may|might|could|would|involve|include))\b",
    re.I,
)


def _scrub_boilerplate(text: str) -> str:
    for pattern in NON_STATUS_BOILERPLATE:
        text = pattern.sub(" ", text)
    kept = []
    for sentence in re.split(r"(?<=[.!?\n])\s+", text):
        if _CONDITIONAL_SENTENCE.search(sentence) or _PROCESS_DESCRIPTION.search(sentence):
            continue
        kept.append(sentence)
    return " ".join(kept)


def parse_mail_date(raw) -> str | None:
    """Normalize a message date to a sortable ISO-8601 string.

    Accepts ISO, RFC-2822, and Apple Mail's localized "Tuesday, September 8,
    2026 at 3:43:31 PM" form. Returns None if nothing parses.
    """
    raw = str(raw or "").strip()
    if not raw:
        return None
    from email.utils import parsedate_to_datetime
    from datetime import datetime, timezone
    for parse in (lambda s: datetime.fromisoformat(s.replace("Z", "+00:00")), parsedate_to_datetime):
        try:
            dt = parse(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError):
            pass
    cleaned = re.sub(r"^[A-Za-z]+,\s*", "", raw).replace(" at ", " ")
    for fmt in ("%B %d, %Y %I:%M:%S %p", "%B %d, %Y %I:%M:%S%p", "%d %B %Y %I:%M:%S %p", "%B %d, %Y"):
        try:
            return datetime.strptime(cleaned, fmt).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    return None

# Employer names that recur under an ATS/vendor sender or a mangled domain.
COMPANY_ALIASES = {
    "spgi": "S&P Global", "s&p global inc": "S&P Global",
    "gevernova": "GE Vernova", "ge vernova": "GE Vernova",
    "drwholdings": "DRW", "datadoghq": "Datadog", "flyzipline": "Zipline",
    "greenhouse mail": "", "greenhouse": "", "workday": "", "myworkday": "",
    "no reply": "", "noreply": "", "donotreply": "", "notification": "",
}
_DOMAIN_NOISE = {"com", "org", "net", "us", "io", "co", "jobs", "mail", "email",
                 "careers", "myworkday", "greenhouse", "fly", "app", "hq", "inc",
                 "recruiting", "talent", "notify", "notifications", "wd1", "wd3", "wd5"}


def _clean_company(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip().strip(".!:;-–—,")
    alias = COMPANY_ALIASES.get(value.lower())
    if alias is not None:
        return alias
    value = re.sub(r"\s+(?:inc|inc\.|llc|ltd|holdings|hq|corp|corporation|co)$", "", value, flags=re.I).strip()
    return value


def infer_company(subject: str, sender: str, body: str = "") -> str:
    display, address = parseaddr(sender)
    candidates = [
        re.search(r"important information about your (.+?) application", subject, re.I),
        re.search(r"(?:reminder:\s*)?(?:complete|completing|take|start) (?:the |your |a )?(.+?) (?:skills |online )?assessment", subject, re.I),
        re.search(r"we(?:'|’)ve got your (.+?) application", subject, re.I),
        re.search(r"^(.+?) application update$", subject, re.I),
        re.search(r"thank(?:s| you) for apply(?:ing)? to (?:the )?([^|!.\n]+?)(?:\s+[-–—:]\s+|['’]s\b|!|\.|$)", subject, re.I),
        re.search(r"thank(?:s| you) for (?:your )?(?:application|interest) (?:in|to|at) ([^!|–—,]+)", subject, re.I),
        re.search(r"(?:successfully |you have )?(?:applied|application) (?:to|for|received for) ([^!|–—,]+)", subject, re.I),
        re.search(r"we(?:'|’ve| have)? received your (?:resume |application )?(?:for |at )?([^!|–—,]+?)(?: application)?$", subject, re.I),
        re.search(r"\bat\s+([^!|–—,]+)$", subject, re.I),
        re.search(r"^([^|–—-]+?)\s*[-–—:]\s*(?:application|candidate)", subject, re.I),
        re.search(r"application (?:received|submitted).*?\b(?:at|to)\s+([^!|–—,]+)", subject, re.I),
    ]
    for match in candidates:
        if match:
            value = _clean_company(match.group(1))
            if 1 < len(value) < 80:
                return value
    shown = (display or "").strip(' "')
    if shown and not any(generic in shown.lower() for generic in GENERIC_SENDERS):
        cleaned = _clean_company(shown)
        if cleaned:
            return cleaned
    local = address.split("@", 1)[0] if "@" in address else ""
    if local and local.lower() not in GENERIC_SENDERS and not local.lower().startswith(("no-reply", "noreply", "recruit", "donotreply", "do-not-reply")):
        return _clean_company(re.sub(r"[._-]+", " ", local).title()) or "Unknown employer"
    domain = address.split("@", 1)[1].lower() if "@" in address else ""
    labels = [x for x in re.split(r"[.\-]", domain) if x and x not in _DOMAIN_NOISE]
    if labels:
        return _clean_company(labels[-1].title()) or _clean_company(labels[0].title()) or "Unknown employer"
    return _clean_company(shown) or address or "Unknown employer"

# Subjects that carry no role information — treated as role "general" so repeat
# status messages for one application collapse instead of forking new rows.
_ROLE_LESS_SUBJECT = re.compile(
    r"^(?:re:|fwd:)?\s*(?:update on your|status update|application (?:status )?update|"
    r"your application(?: has been received| update)?|important information about your|"
    r"thank(?:s| you) for (?:applying|your (?:application|interest))|we(?:'| ha)?ve (?:got|received) your|"
    r"you have successfully applied|invitation for assessments|prepare for your application)"
    r"[\s\w'’&/-]*$",
    re.I,
)


def infer_role(subject: str) -> str:
    cleaned = re.sub(r"^(?:re:|fwd:)\s*", "", subject, flags=re.I).strip()
    patterns = [
        r"thanks? for applying to (?:the )?(.+?)(?: role)? at ",
        r"thank you for your application(?: to| for)? (.+?)(?: at | role| position|$)",
        r"^.+?[-–—:]\s*application received(?:\s*[-–—:]\s*(.+))?$",
        r"applying to the .+? [-–—] (.+?)(?: role| position|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, cleaned, re.I)
        if match and match.lastindex and match.group(1):
            return match.group(1).strip()
    if _ROLE_LESS_SUBJECT.match(cleaned):
        return ""
    return cleaned

def _soft_rejection(status_text: str) -> bool:
    for match in REJECTION_SOFT.finditer(status_text):
        window = status_text[max(0, match.start() - 90): match.end() + 90]
        if DECISION_CONTEXT.search(window):
            return True
    return False


def _stage(subject: str, status_text: str) -> str:
    subject_received = bool(SUBJECT_RECEIVED.search(subject))
    if REJECTION_STRONG.search(status_text) or (not subject_received and _soft_rejection(status_text)):
        return "rejected"
    # When the SUBJECT is a plain application receipt, only advance past "applied"
    # on a concrete next step aimed at the candidate now — body text describing
    # the hiring process ("our team may reach out to schedule an interview")
    # does not make a receipt an interview.
    if subject_received and not any(p.search(subject) for p in (OFFER, INTERVIEW, ASSESSMENT)):
        offer_re, interview_re, assessment_re = OFFER_HARD, INTERVIEW_HARD, ASSESSMENT_HARD
    else:
        offer_re, interview_re, assessment_re = OFFER, INTERVIEW, ASSESSMENT
    if offer_re.search(status_text):
        return "offer"
    if interview_re.search(status_text):
        return "interview"
    if assessment_re.search(status_text):
        return "assessment"
    return "applied"


def classify(subject: str, body: str, sender: str, date: str) -> dict | None:
    subject, body = subject or "", body or ""
    text = f"{subject}\n{body}"
    matched_pattern = any(p.search(text) for p in PATTERNS)
    status_text = f"{subject}\n{_scrub_boilerplate(body)}"
    stage_signal = any(p.search(status_text) for p in (REJECTION_STRONG, OFFER, INTERVIEW, ASSESSMENT))
    if not matched_pattern and not stage_signal:
        return None
    stage = _stage(subject, status_text)
    req = re.search(r"\b(?:requisition|job id|req(?:uisition)?)\b[ #:.-]*((?=[A-Z0-9-]*\d)[A-Z0-9-]{4,})", text, re.I)
    company = infer_company(subject, sender, body)
    return {"subject": subject, "company_hint": company, "role_hint": infer_role(subject), "date": date,
            "date_iso": parse_mail_date(date), "stage": stage,
            "requisition_id": req.group(1) if req else None,
            "confidence": "high" if matched_pattern else "medium"}

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

# Subject substrings used as a fast, server-side prefilter (one compound
# ``whose`` clause). classify() makes the real decision on subject + body.
MAIL_SUBJECT_HINTS = [
    "application", "applied", "candidate", "assessment", "interview",
    "offer", "next step", "thank you for", "we received", "your resume",
    "recruit", "not moving forward", "status update",
]
MAIL_TIMEOUT_SECONDS = int(os.environ.get("JOB_MONITOR_MAIL_TIMEOUT", "150"))


def apple_mail(account_address: str, years: int = 5, days: int | None = None,
               timeout: int | None = None, max_per_box: int = 600) -> list[dict]:
    """Read matching message metadata through Mail's approved Automation access.

    Message bodies and credentials never leave Mail. AppleScript's ``whose`` is
    O(mailbox size), so we scan only the Inbox and an explicit Archive box and
    never Gmail's "All Mail" catch-all (years of mail, always times out). The
    scan also keeps its own wall-clock budget and returns partial results rather
    than being killed, so statuses keep advancing even on a slow run.
    """
    safe_address = account_address.replace('\\', '\\\\').replace('"', '\\"')
    lookback_days = days if days is not None else years * 365
    subject_clause = " or ".join('subject contains "%s"' % h.replace('"', '') for h in MAIL_SUBJECT_HINTS)
    limit = timeout if timeout is not None else MAIL_TIMEOUT_SECONDS
    inner_budget = max(20, limit - 20)
    script = f'''
tell application "Mail"
  set startedAt to (current date)
  set cutoffDate to startedAt - ({lookback_days} * days)
  set includeNames to {{"INBOX", "Inbox", "Archive", "Archived"}}
  set jobFolderHints to {{"job", "career", "internship", "intern", "applica", "recruit", "hiring", "offer"}}
  set excludeNames to {{"All Mail", "[Gmail]/All Mail", "[Gmail]", "Spam", "Junk", "Junk E-mail", "Bulk Mail", "Trash", "Bin", "Deleted Messages", "Deleted Items", "Sent", "Sent Messages", "Sent Items", "Drafts", "Outbox", "Snoozed", "Scheduled"}}
  set recordSep to ASCII character 30
  set fieldSep to ASCII character 31
  set outputText to ""
  repeat with acct in every account
    if (email addresses of acct) contains "{safe_address}" then
      set candidateBoxes to (every mailbox of acct)
      repeat with parentBox in (every mailbox of acct)
        try
          set candidateBoxes to candidateBoxes & (every mailbox of parentBox)
        end try
      end repeat
      set boxesToScan to {{}}
      repeat with box in candidateBoxes
        set boxName to (name of box)
        set includeThis to false
        if includeNames contains boxName then set includeThis to true
        if not includeThis and excludeNames does not contain boxName then
          repeat with hintText in jobFolderHints
            if boxName contains hintText then set includeThis to true
          end repeat
        end if
        if includeThis then set end of boxesToScan to box
      end repeat
      repeat with box in boxesToScan
        if ((current date) - startedAt) > {inner_budget} then exit repeat
        try
          set matches to (messages of box whose date received > cutoffDate and ({subject_clause}))
          set scanned to 0
          repeat with msg in matches
            if scanned is greater than or equal to {max_per_box} then exit repeat
            if ((current date) - startedAt) > {inner_budget} then exit repeat
            set scanned to scanned + 1
            set subjectText to ""
            try
              set subjectText to subject of msg
            end try
            set bodyText to ""
            try
              set bodyText to content of msg
              if (length of bodyText) > 1600 then set bodyText to text 1 thru 1600 of bodyText
            end try
            set outputText to outputText & (message id of msg) & fieldSep & subjectText & fieldSep & (sender of msg) & fieldSep & ((date received of msg) as string) & fieldSep & bodyText & recordSep
          end repeat
        end try
      end repeat
    end if
  end repeat
  return outputText
end tell
'''
    try:
        proc = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=True, timeout=limit)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Apple Mail scan for {account_address} exceeded {limit}s and was stopped safely") from exc
    found, seen = [], set()
    for row in proc.stdout.split(chr(30)):
        fields = row.strip().split(chr(31))
        if len(fields) != 5 or fields[0] in seen:
            continue
        seen.add(fields[0])
        item = classify(fields[1], fields[4], fields[2], fields[3])
        if item:
            item["source_message_id"] = fields[0]
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
