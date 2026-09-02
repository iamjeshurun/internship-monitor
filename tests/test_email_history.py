import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent/"src"))
from email_history import classify, infer_company
def test_application_confirmation():
    r = classify("Application received — Software Intern", "Thank you for applying. Requisition 12345", "Acme Recruiting", "today"); assert r["stage"] == "applied" and r["requisition_id"] == "12345"
def test_unrelated_email_ignored(): assert classify("Lunch", "Where should we eat?", "Friend", "today") is None
def test_offer_classified():
    r = classify("Employment offer", "We are pleased to offer you this internship.", "Example Corp", "today"); assert r["stage"] == "offer"
def test_interest_confirmation_classified():
    r = classify("Thank you for your interest in Example Corp", "We have received your information.", "Example Corp", "today"); assert r["stage"] == "applied"
def test_rejection_language_overrides_thank_you_language():
    r = classify("Thank you for applying", "Unfortunately, we decided to move forward with other candidates.", "Acme", "today")
    assert r["stage"] == "rejected"
def test_security_code_is_not_an_application_receipt():
    assert classify("Security code for your application to Hooli AI", "Use 123456 to continue.", "Greenhouse", "today") is None
def test_company_is_inferred_from_ats_email_address():
    assert infer_company("Thank You for Your Interest - Engineering Intern", "disney@myworkday.com") == "Disney"
    assert infer_company("Prepare for your application process", "no-reply@optiver.us") == "Optiver"
def test_request_word_is_not_mistaken_for_requisition_id():
    assert classify("Application received", "We received your request.", "Acme", "today")["requisition_id"] is None
