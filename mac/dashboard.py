from __future__ import annotations
import os
from datetime import datetime
from pathlib import Path
from flask import Flask, redirect, render_template_string, request
from tracker import load_json, merge_tracker, save_status, STAGE_ORDER

DATA = Path(os.environ.get("JOB_MONITOR_LOCAL_DIR", Path.home()/"Library/Application Support/JobMonitor"))
DATA.mkdir(parents=True, exist_ok=True)
QUEUE, STATUS, HISTORY = DATA/"review_queue.json", DATA/"status.json", DATA/"application_history.json"
app = Flask(__name__)
HTML = '''<!doctype html><meta name="viewport" content="width=device-width"><title>Job Monitor Tracker</title><style>
:root{color-scheme:light}body{font:15px system-ui;margin:0;background:#f4f7f9;color:#14202b}.wrap{max-width:1180px;margin:32px auto;padding:0 18px}header{display:flex;justify-content:space-between;align-items:end;gap:16px}.counts{display:flex;gap:8px;flex-wrap:wrap;margin:20px 0}.pill{background:white;border:1px solid #ccd7df;border-radius:999px;padding:8px 12px}.toolbar{display:flex;gap:10px;margin-bottom:16px}.toolbar input,.toolbar select{padding:10px;border:1px solid #b8c6d0;border-radius:8px;background:white}article{background:white;border:1px solid #ccd7df;border-radius:12px;padding:18px;margin:12px 0;box-shadow:0 2px 8px #17324d0a}.priority{border:2px solid #d59600;background:#fffaf0}.priority-label{display:inline-block;background:#9b6500;color:white;border-radius:999px;padding:5px 9px;font-weight:700}.unverified{background:#9a4b16}.top{display:flex;justify-content:space-between;gap:16px}.score{font-size:22px;font-weight:750}.status{text-transform:capitalize;border-radius:999px;background:#e6f0f7;padding:5px 9px;white-space:nowrap}small,.muted{color:#627482}button,.link{display:inline-block;margin:5px 6px 0 0;padding:8px 10px;border:0;border-radius:7px;background:#e7edf2;color:#14202b;text-decoration:none;cursor:pointer}.primary{background:#124e78;color:white}details{margin-top:9px}@media(max-width:650px){header,.top{align-items:start;flex-direction:column}.toolbar{flex-direction:column}}
</style><div class=wrap><header><div><h1>Internship Application Tracker</h1><div class=muted>Cloud queue + Apple Mail status updates · {{total}} tracked</div></div><div class=muted>Updated {{updated}}</div></header>
<div class=counts>{% for name,count in counts.items() %}<span class=pill>{{name|capitalize}}: <b>{{count}}</b></span>{% endfor %}</div>
<form class=toolbar method=get><input name=q value="{{query}}" placeholder="Search company or role"><select name=stage><option value="">All applications</option>{% for s in stages %}<option value="{{s}}" {{'selected' if stage==s else ''}}>{{s|capitalize}}</option>{% endfor %}</select><button class=primary>Filter</button>{% if query or stage %}<a class=link href="/">Clear filter</a>{% endif %}</form>
{% for j in items %}<article class="{{'priority' if j.priority_program else ''}}"><div class=top><div>{% if j.priority_program %}<span class="priority-label {{'unverified' if not j.priority_program.official_source else ''}}">Priority: {{j.priority_program.name}} · {{'Official source' if j.priority_program.official_source else 'Verify source'}}</span>{% endif %}<div class=score>{{j.assessment.score}}{% if j.assessment.score != '—' %}/100{% endif %}</div><h2>{{j.company}} — {{j.title}}</h2><div class=muted>{{j.location}}</div></div><span class=status>{{j.status}} · {{j.status_source}}</span></div>
{% if j.assessment.reasons %}<p>{{j.assessment.reasons|join(' · ')}}</p>{% endif %}{% if j.assessment.flags %}<p><b>Verify:</b> {{j.assessment.flags|join(' · ')}}</p>{% endif %}
{% if j.url %}<a class="link primary" href="{{j.url}}" target=_blank>Open application</a>{% endif %}<form style="display:inline" method=post action="/status/{{j.key}}">{% for s in stages %}<button name=status value="{{s}}">{{s|capitalize}}</button>{% endfor %}</form>
{% if j.events %}<details><summary>{{j.events|length}} mailbox update(s)</summary>{% for e in j.events %}<p><b>{{e.stage|capitalize}}</b> · {{e.date}}<br>{{e.subject}}<br><small>{{e.mailbox_account}}</small></p>{% endfor %}</details>{% endif %}</article>{% else %}<article>No applications match this filter.</article>{% endfor %}</div>'''

def tracker_items(): return merge_tracker(load_json(QUEUE, {"jobs": []}), load_json(HISTORY, {"applications": []}), load_json(STATUS, {}))

@app.get("/")
def index():
    all_items, query, stage = tracker_items(), request.args.get("q", "").strip().lower(), request.args.get("stage", "")
    counts = {name: sum(item.get("status") == name for item in all_items) for name in STAGE_ORDER}
    items = [item for item in all_items if not query or query in f"{item.get('company','')} {item.get('title','')}".lower()]
    if stage: items = [item for item in items if item.get("status") == stage]
    updated = datetime.fromtimestamp(QUEUE.stat().st_mtime).strftime("%b %d, %I:%M %p") if QUEUE.exists() else "waiting for first sync"
    return render_template_string(HTML, items=items, total=len(all_items), counts=counts, stages=list(STAGE_ORDER), query=query, stage=stage, updated=updated)

@app.post("/status/<key>")
def update(key): save_status(STATUS, key, request.form["status"]); return redirect(request.referrer or "/")

@app.get("/health")
def health(): return {"ok": True, "items": len(tracker_items())}

if __name__ == "__main__": app.run(host="127.0.0.1", port=8765)
