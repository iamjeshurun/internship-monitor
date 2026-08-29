import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent/"mac"))
from tracker import merge_tracker

JOB = {"key":"abc", "company":"Example Corp", "title":"Software Engineer Intern", "location":"NY", "url":"https://example/job", "assessment":{"score":70,"reasons":[],"flags":[]}}

def test_email_interview_advances_matching_job():
    event = {"subject":"Interview for Software Engineer Intern", "company_hint":"Example Corp", "stage":"interview", "date":"2026-08-29", "mailbox_account":"me@example.com"}
    items = merge_tracker({"jobs":[JOB]}, {"applications":[event]}, {})
    assert len(items) == 1 and items[0]["status"] == "interview" and items[0]["status_source"] == "email"

def test_unmatched_email_is_retained_as_application():
    event = {"subject":"Application received", "company_hint":"Different Company", "stage":"applied", "date":"2026-08-29", "mailbox_account":"me@example.com"}
    items = merge_tracker({"jobs":[JOB]}, {"applications":[event]}, {})
    assert len(items) == 2 and any(item["status"] == "applied" for item in items)

def test_manual_status_overrides_email_stage():
    event = {"subject":"Interview for Software Engineer Intern", "company_hint":"Example Corp", "stage":"interview", "date":"2026-08-29", "mailbox_account":"me@example.com"}
    items = merge_tracker({"jobs":[JOB]}, {"applications":[event]}, {"abc":{"status":"dismissed"}})
    assert items[0]["status"] == "dismissed"
