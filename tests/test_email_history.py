import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent/"src"))
from email_history import classify
def test_application_confirmation():
    r = classify("Application received — Software Intern", "Thank you for applying. Requisition 12345", "Acme Recruiting", "today"); assert r["stage"] == "applied" and r["requisition_id"] == "12345"
def test_unrelated_email_ignored(): assert classify("Lunch", "Where should we eat?", "Friend", "today") is None
def test_offer_classified():
    r = classify("Employment offer", "We are pleased to offer you this internship.", "Example Corp", "today"); assert r["stage"] == "offer"
def test_interest_confirmation_classified():
    r = classify("Thank you for your interest in Example Corp", "We have received your information.", "Example Corp", "today"); assert r["stage"] == "applied"
