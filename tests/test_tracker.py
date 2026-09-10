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

def test_application_email_overrides_stale_manual_ready():
    event = {"subject":"Application received", "company_hint":"Example Corp", "stage":"applied", "date":"2026-08-29", "mailbox_account":"me@example.com"}
    items = merge_tracker({"jobs":[JOB]}, {"applications":[event]}, {"abc":{"status":"ready"}})
    assert items[0]["status"] == "applied"

def test_assessment_reminders_collapse():
    events = [
        {"subject":"Action Required: Complete your EY skills assessment", "company_hint":"EY", "role_hint":"Action Required: Complete your EY skills assessment", "stage":"assessment", "date":"2026-09-08", "mailbox_account":"me@example.com"},
        {"subject":"Reminder: Complete your EY skills assessment", "company_hint":"EY", "role_hint":"Reminder: Complete your EY skills assessment", "stage":"assessment", "date":"2026-09-09", "mailbox_account":"me@example.com"},
    ]
    items = merge_tracker({"jobs":[]}, {"applications":events}, {})
    assert len(items) == 1
    assert len(items[0]["events"]) == 2

def test_assessment_completion_and_reminder_collapse():
    events = [
        {"subject":"Reminder: Complete your EY skills assessment", "company_hint":"EY", "role_hint":"Reminder: Complete your EY skills assessment", "stage":"assessment", "date":"2026-09-09", "mailbox_account":"me@example.com"},
        {"subject":"Thank you for completing your EY skills assessment", "company_hint":"EY", "role_hint":"Thank you for completing your EY skills assessment", "stage":"assessment", "date":"2026-09-10", "mailbox_account":"me@example.com"},
    ]
    items = merge_tracker({"jobs":[]}, {"applications":events}, {})
    assert len(items) == 1
    assert len(items[0]["events"]) == 2

def test_generic_title_overlap_does_not_attach_wrong_company():
    event = {"subject":"Application received for Software Engineer Intern", "company_hint":"Other Company", "role_hint":"Software Engineer Intern", "stage":"applied", "date":"2026-08-29", "mailbox_account":"me@example.com"}
    items = merge_tracker({"jobs":[JOB]}, {"applications":[event]}, {})
    assert len(items) == 2

def test_repeated_company_role_updates_collapse_into_one_application():
    events = [
        {"subject":"Application received", "company_hint":"Acme", "role_hint":"Data Intern", "stage":"applied", "date":"2026-08-28", "mailbox_account":"me@example.com"},
        {"subject":"Interview invitation", "company_hint":"Acme", "role_hint":"Data Intern", "stage":"interview", "date":"2026-08-29", "mailbox_account":"me@example.com"},
    ]
    items = merge_tracker({"jobs":[]}, {"applications":events}, {})
    assert len(items) == 1 and items[0]["status"] == "interview" and len(items[0]["events"]) == 2

def test_generic_company_suffix_does_not_match_different_employers():
    capital_job = {**JOB, "company":"Anthelion Capital"}
    event = {"subject":"Thank you for your interest in Akuna Capital", "company_hint":"Akuna Capital", "role_hint":"Unknown role", "stage":"assessment", "date":"2026-08-29", "mailbox_account":"me@example.com"}
    items = merge_tracker({"jobs":[capital_job]}, {"applications":[event]}, {})
    assert len(items) == 2

def test_two_letter_company_name_still_matches():
    ge_job = {**JOB, "key":"ge1", "company":"GE Vernova", "title":"Energy Software Intern"}
    event = {"subject":"Thank you for applying to GE Vernova", "company_hint":"GE Vernova", "role_hint":"", "stage":"applied", "date":"2026-09-01", "mailbox_account":"me@example.com"}
    items = merge_tracker({"jobs":[ge_job]}, {"applications":[event]}, {})
    assert len(items) == 1 and items[0]["status"] == "applied"

def test_status_update_and_receipt_for_same_company_collapse():
    events = [
        {"subject":"We received your application", "company_hint":"Verizon", "role_hint":"", "stage":"applied", "date":"2026-09-01", "mailbox_account":"me@example.com"},
        {"subject":"Application status update", "company_hint":"Verizon", "role_hint":"", "stage":"applied", "date":"2026-09-03", "mailbox_account":"me@example.com"},
    ]
    items = merge_tracker({"jobs":[]}, {"applications":events}, {})
    assert len(items) == 1 and len(items[0]["events"]) == 2

def test_vendor_masked_sender_does_not_fork_company_row():
    events = [
        {"subject":"Thank you for applying to Waymo", "company_hint":"Waymo", "role_hint":"", "stage":"applied", "date":"2026-09-01", "mailbox_account":"me@example.com"},
        {"subject":"Thank You for Applying to Waymo!", "company_hint":"Waymo", "role_hint":"", "stage":"applied", "date":"2026-09-01", "mailbox_account":"me@example.com"},
    ]
    items = merge_tracker({"jobs":[]}, {"applications":events}, {})
    assert len(items) == 1
