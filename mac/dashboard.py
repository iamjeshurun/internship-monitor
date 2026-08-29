from __future__ import annotations
import json
from pathlib import Path
import os
from flask import Flask, redirect, render_template_string, request

DATA = Path(os.environ.get("JOB_MONITOR_LOCAL_DIR", Path.home()/"Library/Application Support/JobMonitor"))
DATA.mkdir(parents=True, exist_ok=True)
QUEUE, STATUS = DATA/"review_queue.json", DATA/"status.json"
app = Flask(__name__)
HTML = '''<!doctype html><title>Job Monitor</title><style>body{font:15px system-ui;max-width:1050px;margin:35px auto;color:#14202b}article{border:1px solid #ccd7df;border-radius:12px;padding:18px;margin:14px 0}small{color:#627482}.score{font-size:24px;font-weight:700}button,a{margin-right:9px}h1{margin-bottom:4px}</style><h1>Applications ready for review</h1><small>{{jobs|length}} current matches</small>{% for j in jobs %}<article><div class=score>{{j.assessment.score}}/100</div><h2>{{j.company}} — {{j.title}}</h2><p>{{j.location}}</p><p>{{j.assessment.reasons|join(' · ')}}</p><p><b>Verify:</b> {{j.assessment.flags|join(' · ')}}</p><a href="{{j.url}}" target=_blank>Open application</a><form style="display:inline" method=post action="/status/{{j.key}}"><button name=status value=reviewing>Reviewing</button><button name=status value=dismissed>Dismiss</button><button name=status value=applied>Applied</button></form></article>{% endfor %}'''

def statuses(): return json.loads(STATUS.read_text()) if STATUS.exists() else {}
@app.get("/")
def index():
    jobs = json.loads(QUEUE.read_text()).get("jobs", []) if QUEUE.exists() else []
    state = statuses(); jobs = [dict(j, local_status=state.get(j["key"], "new")) for j in jobs if state.get(j["key"]) != "dismissed"]
    return render_template_string(HTML, jobs=jobs)
@app.post("/status/<key>")
def update(key):
    state = statuses(); state[key] = request.form["status"]; STATUS.write_text(json.dumps(state, indent=2)); return redirect("/")
if __name__ == "__main__": app.run(host="127.0.0.1", port=8765)
