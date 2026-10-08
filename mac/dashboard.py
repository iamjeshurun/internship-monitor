from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, redirect, request, send_from_directory, session
from tracker import STAGE_ORDER, load_json, merge_tracker, save_status

WEB = Path(__file__).resolve().parent.parent / "web"


def _hours_since(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 3600
    except (ValueError, TypeError):
        return None


def health_warnings(data: Path) -> list[str]:
    warnings = []
    mail = load_json(data / "mail_health.json", {})
    for account, info in (mail.get("accounts") or {}).items():
        if not info.get("ok"):
            since = _hours_since(info.get("last_ok"))
            ago = f"{since:.0f}h ago" if since is not None else "unknown"
            warnings.append(
                f"Mail scan failing for {account} (last success {ago}): {info.get('error', '')[:120]}"
            )
    agent = load_json(data / "agent_health.json", {})
    fails = int(agent.get("consecutive_failures", 0))
    if fails >= 3:
        since = _hours_since(agent.get("last_success"))
        ago = f"{since:.0f}h ago" if since is not None else "unknown"
        warnings.append(
            f"Notification agent can't reach GitHub ({fails} tries; last success {ago}). New-job alerts are paused."
        )
    stale = _hours_since(agent.get("last_success"))
    if stale is not None and stale > 2 and fails < 3:
        warnings.append(f"Notification queue last refreshed {stale:.0f}h ago.")
    return warnings


def create_app(data_dir: Path | None = None) -> Flask:
    app = Flask(__name__, static_folder=str(WEB / "assets"), static_url_path="/assets")
    app.config.update(
        SECRET_KEY=secrets.token_hex(32),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        TRUSTED_HOSTS=["localhost", "127.0.0.1", "[::1]"],
        MAX_CONTENT_LENGTH=16_384,
    )
    data = (
        Path(data_dir)
        if data_dir is not None
        else Path(
            os.environ.get("JOB_MONITOR_LOCAL_DIR", Path.home() / "Library/Application Support/JobMonitor")
        )
    )
    queue_path = data / "review_queue.json"
    status_path = data / "status.json"

    def tracker_items():
        return merge_tracker(
            load_json(queue_path, {"jobs": []}),
            load_json(data / "application_history.json", {"applications": []}),
            load_json(status_path, {}),
        )

    def snapshot():
        try:
            updated = datetime.fromtimestamp(queue_path.stat().st_mtime, timezone.utc).isoformat()
        except FileNotFoundError:
            updated = None
        return {
            "items": tracker_items(),
            "stages": list(STAGE_ORDER),
            "snapshot_at": datetime.now(timezone.utc).isoformat(),
            "queue_updated_at": updated,
            "warnings": health_warnings(data),
        }

    @app.after_request
    def response_headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/")
    def index():
        return send_from_directory(WEB, "index.html")

    @app.get("/bootstrap.js")
    def bootstrap():
        token = session.setdefault("csrf_token", secrets.token_urlsafe(32))
        body = "window.TRACKER_BOOTSTRAP = " + json.dumps({"mode": "local", "csrfToken": token}) + ";"
        return app.response_class(body, mimetype="text/javascript")

    @app.get("/api/tracker")
    def get_tracker():
        return jsonify(snapshot())

    @app.post("/api/status/<key>")
    @app.post("/status/<key>")
    def update(key):
        payload = request.get_json(silent=True) if request.is_json else request.form
        if not isinstance(payload, dict) and request.is_json:
            return jsonify(error="Expected a JSON object."), 400
        payload = payload or {}
        expected = session.get("csrf_token")
        supplied = request.headers.get("X-CSRF-Token") or payload.get("csrf_token", "")
        if not expected or not isinstance(supplied, str) or not secrets.compare_digest(expected, supplied):
            return jsonify(error="Session expired. Reload this page before saving."), 403
        status = payload.get("status")
        if not isinstance(status, str) or status not in STAGE_ORDER:
            return jsonify(error="Choose a valid application status."), 400
        if not any(item["key"] == key for item in tracker_items()):
            return jsonify(error="This record is no longer available. Refresh your tracker."), 404
        try:
            save_status(status_path, key, status)
        except OSError:
            app.logger.exception("Could not save tracker status")
            return jsonify(error="Status could not be saved. Your previous status is unchanged."), 500
        if request.path.startswith("/api/"):
            return jsonify(snapshot())
        return redirect("/")

    @app.get("/health")
    def health():
        return {"ok": True, "items": len(tracker_items())}

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8765)
