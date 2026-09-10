from priority import classify_priority, deduplicate


PROGRAMS = {
    "google_step": {"name": "Google STEP", "companies": ["Google"], "aliases": [r"\bstep\b.*\bintern"], "official_domains": ["google.com"]}
}


def job(source="simplify", url="https://example.com/job", title="STEP Intern", location="New York"):
    return {"source": source, "company": "Google", "title": title, "description": "", "location": location, "url": url}


def test_alias_requires_matching_company():
    assert classify_priority(job(), PROGRAMS)["name"] == "Google STEP"
    assert classify_priority({**job(), "company": "Unrelated"}, PROGRAMS) is None


def test_official_domain_is_verified():
    result = classify_priority(job(url="https://careers.google.com/jobs/123"), PROGRAMS)
    assert result["official_source"] is True


def test_aggregator_is_not_official():
    assert classify_priority(job(), PROGRAMS)["official_source"] is False


def test_deduplication_prefers_official_priority_listing():
    indirect = {**job(), "priority_program": classify_priority(job(), PROGRAMS)}
    direct_job = job(source="custom_jsonld", url="https://careers.google.com/jobs/123")
    direct = {**direct_job, "priority_program": classify_priority(direct_job, PROGRAMS)}
    result = deduplicate([indirect, direct])
    assert len(result) == 1
    assert result[0]["url"].startswith("https://careers.google.com")


def test_different_locations_remain_distinct():
    first = {**job(location="New York"), "priority_program": classify_priority(job(location="New York"), PROGRAMS)}
    second_job = job(location="California")
    second = {**second_job, "priority_program": classify_priority(second_job, PROGRAMS)}
    assert len(deduplicate([first, second])) == 2


def test_same_role_from_aggregator_and_official_board_collapses():
    from priority import location_bucket, normalized_title
    assert location_bucket("NYC") == location_bucket("New York, NY")
    assert normalized_title("SWE Intern - Summer 2027") == normalized_title("SWE Internship (Summer 2027)")
    simplify_copy = {"source": "simplify", "company": "Jane Street", "title": "SWE Intern - Summer 2027", "location": "NYC", "url": "https://simplify.jobs/p/x", "description": ""}
    official = {"source": "greenhouse", "company": "Jane Street", "title": "SWE Internship (Summer 2027)", "location": "New York, NY", "url": "https://boards.greenhouse.io/janestreet/jobs/1", "description": "full JD"}
    result = deduplicate([simplify_copy, official])
    assert len(result) == 1 and result[0]["source"] == "greenhouse"
