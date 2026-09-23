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

def test_same_day_roleless_receipts_for_one_company_collapse():
    events = [
        {"subject":"We received your application", "company_hint":"Verizon", "role_hint":"", "stage":"applied", "date":"2026-09-01T09:00:00Z", "date_iso":"2026-09-01T09:00:00+00:00", "mailbox_account":"me@example.com"},
        {"subject":"Application received", "company_hint":"Verizon", "role_hint":"", "stage":"applied", "date":"2026-09-01T09:02:00Z", "date_iso":"2026-09-01T09:02:00+00:00", "mailbox_account":"me@example.com"},
    ]
    items = merge_tracker({"jobs":[]}, {"applications":events}, {})
    assert len(items) == 1 and len(items[0]["events"]) == 2

def test_distinct_day_roleless_applications_stay_separate():
    events = [
        {"subject":"Thank you for your application!", "company_hint":"Microsoft", "role_hint":"", "stage":"applied", "date":"2026-09-01T09:00:00Z", "date_iso":"2026-09-01T09:00:00+00:00", "mailbox_account":"me@example.com"},
        {"subject":"Thank you for your application!", "company_hint":"Microsoft", "role_hint":"", "stage":"applied", "date":"2026-09-05T09:00:00Z", "date_iso":"2026-09-05T09:00:00+00:00", "mailbox_account":"me@example.com"},
    ]
    items = merge_tracker({"jobs":[]}, {"applications":events}, {})
    assert len(items) == 2

def test_roleless_rejection_routes_to_preceding_application_not_a_new_row():
    events = [
        {"subject":"Thank you for your application!", "company_hint":"Microsoft", "role_hint":"", "stage":"applied", "date":"2026-09-01T09:00:00Z", "date_iso":"2026-09-01T09:00:00+00:00", "mailbox_account":"me@example.com"},
        {"subject":"Update on your application", "company_hint":"Microsoft", "role_hint":"", "stage":"rejected", "date":"2026-09-10T09:00:00Z", "date_iso":"2026-09-10T09:00:00+00:00", "mailbox_account":"me@example.com"},
    ]
    items = merge_tracker({"jobs":[]}, {"applications":events}, {})
    assert len(items) == 1 and items[0]["status"] == "rejected"

def test_older_offer_does_not_overwrite_newer_rejection():
    events = [
        {"subject":"Update on your application", "company_hint":"Acme", "role_hint":"Data Intern", "stage":"rejected", "date":"2026-09-10T09:00:00Z", "date_iso":"2026-09-10T09:00:00+00:00", "mailbox_account":"me@example.com"},
        {"subject":"Your offer", "company_hint":"Acme", "role_hint":"Data Intern", "stage":"offer", "date":"2026-09-02T09:00:00Z", "date_iso":"2026-09-02T09:00:00+00:00", "mailbox_account":"me@example.com"},
    ]
    items = merge_tracker({"jobs":[]}, {"applications":events}, {})
    assert items[0]["status"] == "rejected"
    assert items[0]["last_update"] == "2026-09-10T09:00:00Z"

def test_two_openings_same_company_generic_email_is_not_attached():
    jobs = [
        {"key":"m1", "company":"Microsoft", "title":"Software Engineer Intern", "location":"Redmond", "url":"u1", "assessment":{"score":60,"reasons":[],"flags":[]}},
        {"key":"m2", "company":"Microsoft", "title":"Data Scientist Intern", "location":"Redmond", "url":"u2", "assessment":{"score":60,"reasons":[],"flags":[]}},
    ]
    event = {"subject":"Thank you for your application!", "company_hint":"Microsoft", "role_hint":"", "stage":"applied", "date":"2026-09-01T09:00:00Z", "date_iso":"2026-09-01T09:00:00+00:00", "mailbox_account":"me@example.com"}
    items = merge_tracker({"jobs":jobs}, {"applications":[event]}, {})
    statuses = {i["key"]: i["status"] for i in items}
    assert statuses.get("m1") == "ready" and statuses.get("m2") == "ready"
    assert any(i["status"] == "applied" and i["key"] not in ("m1", "m2") for i in items)

def test_vendor_masked_sender_does_not_fork_company_row():
    events = [
        {"subject":"Thank you for applying to Waymo", "company_hint":"Waymo", "role_hint":"", "stage":"applied", "date":"2026-09-01", "mailbox_account":"me@example.com"},
        {"subject":"Thank You for Applying to Waymo!", "company_hint":"Waymo", "role_hint":"", "stage":"applied", "date":"2026-09-01", "mailbox_account":"me@example.com"},
    ]
    items = merge_tracker({"jobs":[]}, {"applications":events}, {})
    assert len(items) == 1


def test_save_status_is_atomic(tmp_path):
    import json
    from unittest.mock import patch
    from tracker import save_status
    path = tmp_path / "status.json"
    save_status(path, "a", "applied")
    with patch("tracker.os.replace", side_effect=OSError("crash before rename")):
        try:
            save_status(path, "b", "dismissed")
        except OSError:
            pass
    assert list(json.loads(path.read_text())) == ["a"]     # earlier statuses survive
    assert not list(tmp_path.glob("*.tmp"))


def test_mail_sync_without_configured_accounts_is_a_noop(tmp_path, monkeypatch, capsys):
    import importlib, sys
    monkeypatch.setenv("JOB_MONITOR_LOCAL_DIR", str(tmp_path))
    monkeypatch.delenv("JOB_MONITOR_MAIL_ACCOUNTS", raising=False)
    sys.modules.pop("mail_sync", None)
    mail_sync = importlib.import_module("mail_sync")
    mail_sync.main()
    assert "JOB_MONITOR_MAIL_ACCOUNTS" in capsys.readouterr().out
    assert not (tmp_path / "application_history.json").exists()
