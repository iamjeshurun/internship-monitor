import json
from pathlib import Path

import pytest
from dashboard import create_app
from tracker import STAGE_ORDER

FIXTURES = Path(__file__).resolve().parent.parent / "demo/fixtures.json"


@pytest.fixture
def dashboard(tmp_path):
    fixture = json.loads(FIXTURES.read_text())
    for name, payload in [
        ("review_queue.json", fixture["queue"]),
        ("application_history.json", fixture["history"]),
        ("status.json", fixture["statuses"]),
    ]:
        (tmp_path / name).write_text(json.dumps(payload))
    app = create_app(tmp_path)
    app.config["TESTING"] = True
    client = app.test_client()
    client.get("/bootstrap.js")
    with client.session_transaction() as session:
        token = session["csrf_token"]
    return app, client, token, tmp_path


def test_live_bootstrap_has_no_fictional_snapshot(dashboard):
    _, client, _, _ = dashboard
    response = client.get("/bootstrap.js")
    assert response.status_code == 200
    assert '"mode": "local"' in response.text
    assert '"snapshot"' not in response.text
    assert response.headers["Cache-Control"] == "no-store"
    assert client.get("/").status_code == 200
    assert client.get("/assets/app.js").status_code == 200
    assert client.get("/assets/model.mjs").status_code == 200
    assert client.get("/assets/app.css").status_code == 200
    assert client.get("/fixtures.json").status_code == 404


def test_snapshot_contains_all_stages_and_health_warnings(dashboard):
    _, client, _, data = dashboard
    (data / "mail_health.json").write_text(
        json.dumps({"accounts": {"demo@example.test": {"ok": False, "error": "Permission denied"}}})
    )
    payload = client.get("/api/tracker").json
    assert len(payload["items"]) == 16
    assert set(payload["stages"]) == set(STAGE_ORDER)
    assert {item["status"] for item in payload["items"]} == set(STAGE_ORDER)
    assert "Permission denied" in payload["warnings"][0]
    assert payload["queue_updated_at"]


def test_mailbox_only_manual_status_survives_reload(dashboard):
    _, client, token, data = dashboard
    item = next(i for i in client.get("/api/tracker").json["items"] if i["company"] == "Index")
    response = client.post(
        f"/api/status/{item['key']}", json={"status": "dismissed"}, headers={"X-CSRF-Token": token}
    )
    assert response.status_code == 200
    for snapshot in [response.json, client.get("/api/tracker").json]:
        saved = next(i for i in snapshot["items"] if i["key"] == item["key"])
        assert saved["status"] == "dismissed"
        assert saved["status_source"] == "manual"
        assert saved["events"] == item["events"]
    stored = json.loads((data / "status.json").read_text())
    assert stored[item["key"]]["status"] == "dismissed"
    assert stored["demo-07"]["status"] == "reviewing"


def test_email_precedence_is_returned_after_save(dashboard):
    _, client, token, _ = dashboard
    response = client.post("/api/status/demo-00", json={"status": "ready"}, headers={"X-CSRF-Token": token})
    assert response.status_code == 200
    item = next(i for i in response.json["items"] if i["key"] == "demo-00")
    assert item["status"] == "interview" and item["status_source"] == "email"


@pytest.mark.parametrize("payload", [{"status": "invented"}, {"status": []}, {}, []])
def test_bad_status_payload_does_not_write(dashboard, payload):
    _, client, token, data = dashboard
    original = (data / "status.json").read_bytes()
    response = client.post("/api/status/demo-00", json=payload, headers={"X-CSRF-Token": token})
    assert response.status_code == 400
    assert (data / "status.json").read_bytes() == original


def test_unknown_record_and_cross_site_posts_are_rejected(dashboard):
    _, client, token, data = dashboard
    original = (data / "status.json").read_bytes()
    assert (
        client.post(
            "/api/status/missing", json={"status": "offer"}, headers={"X-CSRF-Token": token}
        ).status_code
        == 404
    )
    assert client.post("/api/status/demo-00", json={"status": "offer"}).status_code == 403
    assert client.post("/status/demo-00", data={"status": "offer"}).status_code == 403
    assert client.get("/api/tracker", headers={"Host": "foreign.example"}).status_code == 400
    assert (data / "status.json").read_bytes() == original


def test_form_save_redirects_to_local_dashboard(dashboard):
    _, client, token, _ = dashboard
    response = client.post(
        "/status/demo-03",
        data={"status": "reviewing", "csrf_token": token},
        headers={"Referer": "https://foreign.example"},
    )
    assert response.status_code == 302
    assert response.headers["Location"] == "/"


def test_storage_failure_reports_failure(dashboard, monkeypatch):
    _, client, token, data = dashboard
    original = (data / "status.json").read_bytes()

    def fail(*args):
        raise OSError("read-only volume")

    monkeypatch.setattr("dashboard.save_status", fail)
    response = client.post("/api/status/demo-03", json={"status": "applied"}, headers={"X-CSRF-Token": token})
    assert response.status_code == 500
    assert "could not be saved" in response.json["error"]
    assert (data / "status.json").read_bytes() == original


def test_empty_install_does_not_create_private_data(tmp_path):
    folder = tmp_path / "not-created"
    client = create_app(folder).test_client()
    payload = client.get("/api/tracker").json
    assert payload["items"] == []
    assert payload["queue_updated_at"] is None
    assert not folder.exists()


def test_demo_scores_come_from_the_real_scorer():
    import sys

    import yaml

    sys.path.insert(0, str(FIXTURES.parent.parent / "scripts"))
    sys.path.insert(0, str(FIXTURES.parent.parent / "src"))
    from build_demo import scored_queue

    from scoring import assess

    fixture = json.loads(FIXTURES.read_text())
    profile = yaml.safe_load((FIXTURES.parent.parent / "config/resume_profile.yaml").read_text())
    queue = scored_queue(fixture)
    assert len(queue["jobs"]) == len(fixture["queue"]["jobs"])
    for posting, job in zip(fixture["queue"]["jobs"], queue["jobs"]):
        assert "assessment" not in posting, "fixtures hold postings, not scores"
        expected = assess(posting, profile, fixture["companies"].get(posting["company"]))
        assert job["assessment"]["score"] == expected.score >= expected.notify_threshold
        assert job["assessment"]["reasons"] == expected.reasons
        assert "description" not in job
