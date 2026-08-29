from __future__ import annotations
import argparse, json
from pathlib import Path
import yaml

def main():
    p = argparse.ArgumentParser(); p.add_argument("job_key"); p.add_argument("--answers", type=Path, default=Path.home()/".config/job-monitor/application_answers.yaml"); p.add_argument("--state", type=Path, default=Path("data/state.json")); p.add_argument("--output", type=Path, default=Path("mac/state/prep_packet.json")); args = p.parse_args()
    state = json.loads(args.state.read_text()); job = state["jobs"][args.job_key]
    answers = yaml.safe_load(args.answers.read_text()) if args.answers.exists() else {}
    packet = {"job": job, "safe_answers": {k: v for k, v in answers.items() if k not in {"review_required", "demographics"}}, "review_required": answers.get("review_required", []), "submission_policy": "Never submit without in-the-moment user review."}
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(packet, indent=2)); print(args.output)

if __name__ == "__main__": main()
