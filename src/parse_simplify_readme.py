"""
Parses SimplifyJobs/Summer2027-Internships' README.md into structured listings.

This repo is community + Simplify-maintained, updated continuously (the repo's
own FAQ states Simplify scrapes company career pages hourly and community
members submit new postings as they find them). Watching this repo via
GitHub's raw content API is NOT scraping any employer -- it's reading one
public repo file via GitHub's own sanctioned content delivery
(raw.githubusercontent.com), the same as any browser would.

This is what gives real coverage across companies with no public ATS API
(Workday, SmartRecruiters, in-house systems) -- which is most of a typical
company tracker's "Target/Standard" tier.

The README uses raw HTML tables (not markdown pipe tables) inside each
category section. This parser handles that format directly with
BeautifulSoup rather than assuming a stable JSON export exists.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup


@dataclass
class Listing:
    category: str
    company: str
    role: str
    location: str
    url: str
    age_raw: str

    def dedup_key(self) -> str:
        # URL is the most stable unique identifier available.
        return self.url


CATEGORY_HEADING_PATTERN = re.compile(r"^##\s+.*?\s+(.+?Internship Roles)\s*$", re.MULTILINE)


def parse_readme(markdown_text: str) -> list[Listing]:
    """
    The README mixes markdown headings ('## 💻 Software Engineering Internship
    Roles') with raw <table> HTML blocks underneath each heading. We split on
    the headings first (regex, since they're plain markdown lines) then parse
    each following HTML table with BeautifulSoup.
    """
    listings: list[Listing] = []

    # Split the doc at each "## <emoji> <Category> Internship Roles" heading.
    sections = re.split(r"(^##\s+.+Internship Roles\s*$)", markdown_text, flags=re.MULTILINE)
    # sections looks like: [preamble, heading1, body1, heading2, body2, ...]

    for i in range(1, len(sections) - 1, 2):
        heading = sections[i]
        body = sections[i + 1]
        category_match = re.search(r"([A-Za-z ,&]+Internship Roles)", heading)
        category = category_match.group(1).strip() if category_match else heading.strip("# \n")

        soup = BeautifulSoup(body, "lxml")
        table = soup.find("table")
        if not table:
            continue
        tbody = table.find("tbody") or table
        rows = tbody.find_all("tr")

        last_company = None
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 5:
                continue
            company_cell, role_cell, location_cell, application_cell, age_cell = cells[:5]

            company_text = company_cell.get_text(strip=True)
            if company_text == "↳":
                # Continuation row -- same company as previous row, different location/req.
                company = last_company
            else:
                company = company_text
                last_company = company

            role = role_cell.get_text(strip=True)
            location = location_cell.get_text(strip=True)
            age_raw = age_cell.get_text(strip=True)

            # First real (non-Simplify-icon) link in the application cell is the apply URL.
            url = ""
            for a in application_cell.find_all("a"):
                href = a.get("href", "")
                if href and "simplify.jobs/p/" not in href:
                    url = href
                    break
            if not url:
                # fall back to whatever link exists
                a = application_cell.find("a")
                url = a.get("href", "") if a else ""

            if not company or not role or not url:
                continue

            listings.append(
                Listing(
                    category=category,
                    company=company,
                    role=role,
                    location=location,
                    url=url,
                    age_raw=age_raw,
                )
            )

    return listings


def age_to_hours(age_raw: str) -> float:
    """Convert '0d', '1d', '5h', '30m' style ages to hours (rough, for freshness filtering)."""
    m = re.match(r"(\d+)([dhm])", age_raw.strip())
    if not m:
        return 9999
    n, unit = int(m.group(1)), m.group(2)
    return {"d": n * 24, "h": n, "m": n / 60}[unit]


if __name__ == "__main__":
    import sys

    with open(sys.argv[1] if len(sys.argv) > 1 else "tests/fixtures/sample_readme.md") as f:
        text = f.read()
    listings = parse_readme(text)
    print(f"Parsed {len(listings)} listings")
    for listing in listings[:10]:
        print(
            f"  [{listing.category}] {listing.company} - {listing.role} ({listing.location}) age={listing.age_raw}"
        )
        print(f"    {listing.url}")
