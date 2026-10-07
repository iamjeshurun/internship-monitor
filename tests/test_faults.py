import json
import socket
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests

ROOT = Path(__file__).resolve().parent.parent
import mac_agent as agent

import run_monitor as runner
import sources
import state
from dedupe import deduplicate
from models import Job


@pytest.fixture(autouse=True)
def isolation(monkeypatch, tmp_path):
    monkeypatch.setattr(
        socket.socket,
        "connect",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("External network prohibited")),
    )
    for attr, name in [("STATE", "notified.json"), ("CACHE", "queue.json"), ("HEALTH", "health.json")]:
        monkeypatch.setattr(agent, attr, tmp_path / name)
    monkeypatch.setattr(agent, "LOCAL", tmp_path)
    monkeypatch.setattr(agent, "native_notify", Mock())
    monkeypatch.setattr(agent, "notify", Mock())


def job(source="greenhouse", url="https://example.test/jobs/1", title="Software Engineer Intern"):
    return Job(source, "1", "Example", title, "NYC", url).as_dict()


def config():
    return {"boards": {"greenhouse": {"Broken": "broken", "Healthy": "healthy"}}}


def response(code):
    r = requests.Response()
    r.status_code = code
    r.url = "https://example.test"
    r._content = b"{}"
    return r


@pytest.mark.parametrize(
    "error", [requests.Timeout("timeout"), requests.HTTPError("429"), requests.HTTPError("503")]
)
def test_failed_source_does_not_stop_other_sources(monkeypatch, error):
    def fake(company, token):
        if token == "broken":
            raise error
        return [job()]

    monkeypatch.setattr(runner, "greenhouse", fake)
    jobs, errors = runner.collect(config())
    assert len(jobs) == 1 and len(errors) == 1


@pytest.mark.parametrize("code", [429, 500, 502, 503, 504])
def test_source_recovers_from_transient_http_error_in_same_run(monkeypatch, code):
    monkeypatch.setattr(sources.time, "sleep", lambda s: None)
    getter = Mock(side_effect=[response(code), response(200)])
    monkeypatch.setattr(sources.SESSION, "get", getter)
    assert sources._get_json("https://example.test") == {}
    assert getter.call_count == 2


def test_retry_after_header_is_honored_and_capped(monkeypatch):
    slept = []
    monkeypatch.setattr(sources.time, "sleep", slept.append)
    limited = response(429)
    limited.headers["Retry-After"] = "7"
    absurd = response(503)
    absurd.headers["Retry-After"] = "99999"
    monkeypatch.setattr(sources.SESSION, "get", Mock(side_effect=[limited, absurd, response(200)]))
    assert sources._get_json("https://example.test") == {}
    assert slept == [7.0, sources.MAX_RETRY_WAIT]


def test_retries_are_bounded_then_the_source_fails(monkeypatch):
    monkeypatch.setattr(sources.time, "sleep", lambda s: None)
    getter = Mock(side_effect=lambda *a, **k: response(503))
    monkeypatch.setattr(sources.SESSION, "get", getter)
    with pytest.raises(requests.HTTPError):
        sources._get_json("https://example.test")
    assert getter.call_count == sources.MAX_ATTEMPTS


def test_non_transient_errors_are_not_retried(monkeypatch):
    monkeypatch.setattr(sources.time, "sleep", lambda s: None)
    getter = Mock(side_effect=lambda *a, **k: response(404))
    monkeypatch.setattr(sources.SESSION, "get", getter)
    with pytest.raises(requests.HTTPError):
        sources._get_json("https://example.test")
    assert getter.call_count == 1


def test_timeout_is_retried_then_recovers(monkeypatch):
    monkeypatch.setattr(sources.time, "sleep", lambda s: None)
    getter = Mock(side_effect=[requests.Timeout("slow"), response(200)])
    monkeypatch.setattr(sources.SESSION, "get", getter)
    assert sources._get_json("https://example.test") == {}
    assert getter.call_count == 2


def test_duplicate_tracking_urls_collapse():
    a = Job("greenhouse", "1", "Example", "SWE Intern", "NYC", "https://example.test/jobs/1?utm_source=x")
    b = Job("simplify", "1", "Example", "SWE Intern", "NYC", "https://example.test/jobs/1?ref=feed")
    assert a.key == b.key
    assert len(deduplicate([a.as_dict(), b.as_dict()])) == 1


def test_cross_source_same_role_prefers_official():
    items = deduplicate([job("simplify", "https://example.test/aggregator/1"), job()])
    assert len(items) == 1 and items[0]["source"] == "greenhouse"


def test_distinct_requisitions_are_not_lost():
    # Same company/title/city, distinct requisition IDs.
    a = job(url="https://example.test/jobs/101")
    a["source_id"] = "101"
    b = job(url="https://example.test/jobs/102")
    b["source_id"] = "102"
    assert len(deduplicate([a, b])) == 2


def test_aggregator_copy_still_dropped_when_multiple_official_requisitions_exist():
    a = job(url="https://example.test/jobs/101")
    a["source_id"] = "101"
    b = job(url="https://example.test/jobs/102")
    b["source_id"] = "102"
    agg = job("simplify", "https://example.test/aggregator/1")
    result = deduplicate([agg, a, b])
    assert sorted(r["source_id"] for r in result) == ["101", "102"]


def test_same_requisition_listed_twice_still_collapses():
    a = job(url="https://example.test/jobs/101")
    a["source_id"] = "101"
    b = dict(a, description="full JD")
    assert len(deduplicate([a, b])) == 1


@pytest.mark.parametrize("method", ["save", "save_queue"])
def test_process_exit_before_atomic_replace_preserves_old_file(tmp_path, method):
    target = tmp_path / "state.json"
    target.write_text('{"schema_version":2,"jobs":{},"runs":[]}')
    before = target.read_bytes()
    code = f"""import sys,os\nsys.path.insert(0,{str(ROOT / "src")!r})\nfrom pathlib import Path\nimport state\ns=state.StateStore(Path({str(target)!r}))\ns.add_run({{'checked':1}})\nstate.os.replace=lambda *args: os._exit(77)\ns.{method}({("Path(" + repr(str(target)) + ")") if method == "save_queue" else ""})\n"""
    p = subprocess.run([sys.executable, "-c", code])
    assert p.returncode == 77 and target.read_bytes() == before
    json.loads(target.read_text())
    # Restart and save over the abandoned temporary file.
    s = state.StateStore(target)
    s.save()
    assert json.loads(target.read_text())["jobs"] == {}


def test_disconnect_then_reconnect_catches_up_once(monkeypatch):
    j = job()
    q = {"jobs": [j], "generated_at": "2026-09-23T00:00:00+00:00"}
    monkeypatch.setattr(agent, "fetch_queue", Mock(side_effect=[requests.ConnectionError("offline"), q, q]))
    with pytest.raises(requests.ConnectionError):
        agent.once()
    assert not agent.STATE.exists()
    agent.once()
    agent.once()
    assert agent.notify.call_count == 1
    assert json.loads(agent.HEALTH.read_text())["consecutive_failures"] == 0


def test_repeated_disconnect_warns_once_then_resets(monkeypatch):
    fetch = Mock(side_effect=requests.ConnectionError("offline"))
    monkeypatch.setattr(agent, "fetch_queue", fetch)
    for _ in range(6):
        with pytest.raises(requests.ConnectionError):
            agent.once()
    assert agent.native_notify.call_count == 1
    fetch.side_effect = None
    fetch.return_value = {"jobs": []}
    agent.once()
    assert json.loads(agent.HEALTH.read_text())["consecutive_failures"] == 0


def _fail_ledger_write_on(nth):
    """Make the nth write to the notification ledger raise, like a crash would."""
    real = agent._atomic_write
    count = {"n": 0}

    def wrapper(path, text):
        if path == agent.STATE:
            count["n"] += 1
            if count["n"] == nth:
                raise OSError("simulated crash while writing ledger")
        return real(path, text)

    return wrapper


def test_crash_before_intent_is_recorded_sends_exactly_once(monkeypatch):
    monkeypatch.setattr(agent, "fetch_queue", lambda: {"jobs": [job()]})
    with patch.object(agent, "_atomic_write", _fail_ledger_write_on(1)):
        with pytest.raises(OSError):
            agent.once()
    assert agent.notify.call_count == 0  # crashed before sending: nothing lost
    agent.once()
    agent.once()
    assert agent.notify.call_count == 1


def test_crash_between_send_and_receipt_resends_at_most_once(monkeypatch):
    # Documented tradeoff: at-least-once, capped. Exactly-once is impossible with a
    # non-idempotent notifier, and a missed job alert is worse than one duplicate.
    monkeypatch.setattr(agent, "fetch_queue", lambda: {"jobs": [job()]})
    with patch.object(agent, "_atomic_write", _fail_ledger_write_on(2)):
        with pytest.raises(OSError):
            agent.once()
    assert agent.notify.call_count == 1
    agent.once()  # restart: one bounded retry
    assert agent.notify.call_count == 2
    agent.once()
    agent.once()  # ...and never again
    assert agent.notify.call_count == 2


def test_notifier_failure_retries_next_poll_up_to_the_cap(monkeypatch):
    monkeypatch.setattr(agent, "fetch_queue", lambda: {"jobs": [job()]})
    agent.notify.side_effect = [RuntimeError("notifier down"), None]
    agent.once()  # failed send stays pending, no crash
    agent.once()  # retried, now recorded as sent
    agent.once()
    assert agent.notify.call_count == 2
    assert json.loads(agent.STATE.read_text())[job()["key"]]["state"] == "sent"


def test_one_bad_alert_does_not_block_the_rest_or_lose_receipts(monkeypatch):
    j1, j2 = job(url="https://example.test/jobs/1"), job(url="https://example.test/jobs/2")
    monkeypatch.setattr(agent, "fetch_queue", lambda: {"jobs": [j1, j2]})
    agent.notify.side_effect = [RuntimeError("boom"), None, None]
    agent.once()
    ledger = json.loads(agent.STATE.read_text())
    assert ledger[j1["key"]]["state"] == "pending" and ledger[j2["key"]]["state"] == "sent"


def test_legacy_list_ledger_is_migrated_without_renotifying(monkeypatch):
    j = job()
    agent.STATE.write_text(json.dumps([j["key"]]))
    monkeypatch.setattr(agent, "fetch_queue", lambda: {"jobs": [j]})
    agent.once()
    assert agent.notify.call_count == 0


def test_atomic_write_never_leaves_a_torn_file(tmp_path):
    target = tmp_path / "ledger.json"
    target.write_text('{"ok": true}')
    with patch.object(agent.os, "replace", side_effect=OSError("crash before rename")):
        with pytest.raises(OSError):
            agent._atomic_write(target, '{"partial"')
    assert json.loads(target.read_text()) == {"ok": True}
    assert not list(tmp_path.glob("*.tmp"))
