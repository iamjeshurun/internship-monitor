import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import notifications


class Response:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload

    def raise_for_status(self):
        return None


def test_github_alert_comments_on_existing_thread(monkeypatch):
    sent = {}
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_ALERT_MENTION", "owner")
    monkeypatch.setattr(
        notifications.requests,
        "get",
        lambda *a, **k: Response([{"number": 7, "title": "Job Monitor Alerts"}]),
    )

    def post(url, **kwargs):
        sent.update(url=url, body=kwargs["json"]["body"])
        return Response({})

    monkeypatch.setattr(notifications.requests, "post", post)
    assert notifications.send_github_alert("Ready", "One match")
    assert sent["url"].endswith("/issues/7/comments")
    assert "@owner" in sent["body"]


def test_digest_subject_and_body(monkeypatch):
    sent = {}
    monkeypatch.setattr(
        notifications,
        "send_github_alert",
        lambda subject, body: sent.update(subject=subject, body=body) or True,
    )
    job = {
        "company": "Acme",
        "title": "SWE Intern",
        "location": "NYC",
        "url": "https://example.com/1",
        "assessment": {"score": 80, "reasons": ["role match"], "flags": ["sponsorship unknown"]},
    }
    assert notifications.send_digest([job], []) is True
    assert sent["subject"] == "ACTION READY: 1 internship match(es)"
    assert "[80/100] Acme" in sent["body"] and "sponsorship unknown" in sent["body"]


def test_priority_digest_has_priority_subject_and_verification(monkeypatch):
    sent = {}
    monkeypatch.setattr(
        notifications,
        "send_github_alert",
        lambda subject, body: sent.update(subject=subject, body=body) or True,
    )
    job = {
        "company": "Google",
        "title": "STEP Intern",
        "location": "USA",
        "url": "https://careers.google.com/job/1",
        "assessment": {"score": 90, "reasons": ["program match"], "flags": []},
        "priority_program": {"name": "Google STEP", "official_source": True},
    }
    assert notifications.send_digest([job], []) is True
    assert sent["subject"].startswith("PRIORITY PROGRAM")
    assert "official source verified" in sent["body"]
