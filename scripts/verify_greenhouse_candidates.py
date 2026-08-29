from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
import yaml


def verify(name: str, token: str) -> tuple[str, str, int, str]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
    try:
        response = requests.get(url, timeout=12, headers={"User-Agent": "internship-job-monitor/2.0"})
        if response.status_code != 200:
            return name, token, -response.status_code, ""
        jobs = response.json().get("jobs", [])
        sample = " | ".join(str(job.get("absolute_url", "")) for job in jobs[:3])
        return name, token, len(jobs), sample
    except Exception as exc:
        return name, token, -1, type(exc).__name__


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--companies", type=Path, default=Path("config/companies.yaml"))
    parser.add_argument("--priority", action="append")
    args = parser.parse_args()
    companies = yaml.safe_load(args.companies.read_text())["companies"]
    candidates = [
        (name, row["greenhouse_token_guess"])
        for name, row in companies.items()
        if row.get("greenhouse_token_guess") and (not args.priority or row.get("priority") in args.priority)
    ]
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = [pool.submit(verify, *candidate) for candidate in candidates]
        for future in as_completed(futures):
            name, token, count, sample = future.result()
            if count >= 0:
                print(f"{name}\t{token}\t{count}\t{sample}")


if __name__ == "__main__":
    main()
