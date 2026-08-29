from __future__ import annotations

import json
import re
from html import unescape
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from models import Job
from parse_simplify_readme import age_to_hours, parse_readme


SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "internship-job-monitor/2.0 (+personal job search)"})


def _get_json(url: str, timeout: int = 25):
    response = SESSION.get(url, timeout=timeout)
    response.raise_for_status()
    return response.json()


def greenhouse(company: str, token: str) -> list[Job]:
    data = _get_json(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true")
    return [Job("greenhouse", str(j["id"]), company, j.get("title", ""), (j.get("location") or {}).get("name", ""), j.get("absolute_url", ""), unescape(j.get("content", "")), j.get("updated_at")) for j in data.get("jobs", [])]


def lever(company: str, site: str) -> list[Job]:
    data = _get_json(f"https://api.lever.co/v0/postings/{site}?mode=json")
    return [Job("lever", str(j.get("id", "")), company, j.get("text", ""), (j.get("categories") or {}).get("location", ""), j.get("hostedUrl") or j.get("applyUrl", ""), BeautifulSoup(j.get("descriptionPlain", "") or "", "html.parser").get_text(" ")) for j in data]


def ashby(company: str, board: str) -> list[Job]:
    data = _get_json(f"https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true")
    return [Job("ashby", str(j.get("jobUrl") or j.get("applyUrl")), company, j.get("title", ""), j.get("location", ""), j.get("jobUrl") or j.get("applyUrl", ""), BeautifulSoup(j.get("descriptionHtml", ""), "html.parser").get_text(" "), j.get("publishedAt"), metadata={"compensation": j.get("compensation")}) for j in data.get("jobs", []) if j.get("isListed", True)]


def simplify(config: dict) -> list[Job]:
    repo, branch = config["repo"], config.get("branch", "dev")
    response = SESSION.get(f"https://raw.githubusercontent.com/{repo}/{branch}/README.md", timeout=30)
    response.raise_for_status()
    categories = [x.lower() for x in config.get("categories", [])]
    jobs = []
    for row in parse_readme(response.text):
        if categories and not any(x in row.category.lower() for x in categories):
            continue
        jobs.append(Job("simplify", row.url, row.company.lstrip("🔥").strip(), row.role, row.location, row.url, age_hours=age_to_hours(row.age_raw)))
    return jobs


def x_recent(config: dict, bearer_token: str) -> list[Job]:
    query = config.get("query", "")
    accounts = [f"from:{a}" for a in config.get("watched_accounts", [])]
    if accounts:
        query = f"({query}) OR ({' OR '.join(accounts)})"
    response = SESSION.get("https://api.x.com/2/tweets/search/recent", headers={"Authorization": f"Bearer {bearer_token}"}, params={"query": query, "max_results": 100, "tweet.fields": "created_at,author_id,entities"}, timeout=30)
    response.raise_for_status()
    jobs = []
    for post in response.json().get("data", []):
        text = post.get("text", "")
        urls = [u.get("expanded_url") for u in (post.get("entities") or {}).get("urls", []) if u.get("expanded_url")]
        url = urls[0] if urls else f"https://x.com/i/web/status/{post['id']}"
        jobs.append(Job("x", post["id"], "Social lead", text[:140], "", url, text, post.get("created_at"), metadata={"author_id": post.get("author_id")}))
    return jobs


def custom_jsonld(company: str, page_url: str) -> list[Job]:
    response = SESSION.get(page_url, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "lxml")
    jobs = []
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            objects = json.loads(script.string or "null")
        except json.JSONDecodeError:
            continue
        objects = objects if isinstance(objects, list) else [objects]
        for obj in objects:
            if not isinstance(obj, dict) or obj.get("@type") != "JobPosting":
                continue
            loc = obj.get("jobLocation", "")
            if isinstance(loc, list):
                loc = ", ".join(str(x) for x in loc)
            jobs.append(Job("custom_jsonld", str(obj.get("identifier") or obj.get("url")), company, obj.get("title", ""), str(loc), urljoin(page_url, obj.get("url", page_url)), BeautifulSoup(obj.get("description", ""), "html.parser").get_text(" "), obj.get("datePosted")))
    return jobs
