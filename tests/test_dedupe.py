from dedupe import deduplicate, dedupe_key, location_bucket, normalized_title


def job(source="simplify", url="https://example.com/job", title="Software Engineer Intern", location="New York", source_id=None, description=""):
    return {"source": source, "source_id": source_id or url, "company": "Example", "title": title,
            "description": description, "location": location, "url": url}


def test_official_listing_beats_aggregator_copy():
    result = deduplicate([job(), job("greenhouse", "https://boards.greenhouse.io/example/jobs/1")])
    assert len(result) == 1 and result[0]["source"] == "greenhouse"


def test_different_locations_remain_distinct():
    assert len(deduplicate([job(location="New York", url="https://e/a"), job(location="California", url="https://e/b")])) == 2


def test_location_and_title_normalization():
    assert location_bucket("NYC") == location_bucket("New York, NY")
    assert location_bucket("San Francisco, CA") == location_bucket("SF Bay Area")
    assert normalized_title("SWE Intern - Summer 2027") == normalized_title("SWE Internship (Summer 2027)")


def test_same_role_from_aggregator_and_official_board_collapses():
    simplify_copy = job(title="SWE Intern - Summer 2027", location="NYC", url="https://simplify.jobs/p/x")
    official = job("greenhouse", "https://boards.greenhouse.io/example/jobs/1", "SWE Internship (Summer 2027)", "New York, NY", "1", "full JD")
    assert dedupe_key(simplify_copy) == dedupe_key(official)
    result = deduplicate([simplify_copy, official])
    assert len(result) == 1 and result[0]["source"] == "greenhouse"
