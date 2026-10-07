import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from parse_simplify_readme import age_to_hours, parse_readme

SAMPLE = Path(__file__).parent / "fixtures" / "sample_readme.md"  # synthetic fixture


def test_parses_real_snapshot_without_error():
    text = SAMPLE.read_text()
    listings = parse_readme(text)
    assert len(listings) == 7


def test_continuation_rows_inherit_company_name():
    text = SAMPLE.read_text()
    listings = parse_readme(text)
    example = [listing for listing in listings if "ExampleCo" in listing.company]
    assert len(example) >= 2  # both the initial row and its "↳" continuation


def test_every_listing_has_a_real_url():
    text = SAMPLE.read_text()
    listings = parse_readme(text)
    for listing in listings:
        assert listing.url.startswith("http")
        assert "simplify.jobs/p/" not in listing.url  # should extract the real employer link, not Simplify's


def test_age_parsing():
    assert age_to_hours("0d") == 0
    assert age_to_hours("1d") == 24
    assert age_to_hours("5h") == 5


if __name__ == "__main__":
    import subprocess

    subprocess.run(["python3", "-m", "pytest", __file__, "-v"])
