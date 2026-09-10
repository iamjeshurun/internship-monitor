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
def test_microsoft_receipt_status_help_is_not_a_rejection():
    body = "We received your application. Closed means the position is either no longer open, you withdrew from consideration, or you were not selected for the role. How's your profile?"
    r = classify("Thank you for your application!", body, "Microsoft Careers <donotreply@email.careers.microsoft.com>", "today")
    assert r["stage"] == "applied"
def test_security_code_is_not_an_application_receipt():
    assert classify("Security code for your application to Hooli AI", "Use 123456 to continue.", "Greenhouse", "today") is None
def test_company_is_inferred_from_ats_email_address():
    assert infer_company("Thank You for Your Interest - Engineering Intern", "disney@myworkday.com") == "Disney"
    assert infer_company("Prepare for your application process", "no-reply@optiver.us") == "Optiver"
    assert infer_company("Important information about your C3 AI application", "Greenhouse Mail <no-reply@greenhouse.io>") == "C3 AI"
    assert infer_company("Reminder: Complete your EY skills assessment", "SHL <no-reply@shl.com>") == "EY"
def test_bare_not_selected_help_text_is_not_rejection():
    r = classify("Thank you for your Application!", "If you are not selected, please consider other roles.", "S&P Global", "today")
    assert r["stage"] == "applied"
def test_direct_decided_not_to_proceed_is_rejection():
    r = classify("Application update", "We have decided not to proceed with your candidacy.", "Acme", "today")
    assert r["stage"] == "rejected"
def test_assessment_vendor_in_security_boilerplate_is_not_assessment():
    body = "We received your application. You may receive test invitations via our trusted platforms HackerRank.com and Criteria.com."
    r = classify("Thank you for your interest in Akuna Capital!", body, "Akuna Capital", "today")
    assert r["stage"] == "applied"
def test_direct_hackerrank_request_is_assessment():
    r = classify("Next steps", "Please complete your HackerRank challenge by Friday.", "Acme", "today")
    assert r["stage"] == "assessment"
def test_request_word_is_not_mistaken_for_requisition_id():
    assert classify("Application received", "We received your request.", "Acme", "today")["requisition_id"] is None

def test_unfortunately_boilerplate_in_receipt_is_not_rejection():
    body = "Thank you for applying! Unfortunately, due to the very high volume of applications we are unable to respond to everyone individually."
    r = classify("Your application to Stripe", body, "Stripe", "today")
    assert r["stage"] == "applied"

def test_high_volume_disclaimer_is_not_rejection():
    body = "We have received your application. We regret that we cannot provide individual feedback to every candidate."
    r = classify("Application received", body, "Acme Talent", "today")
    assert r["stage"] == "applied"

def test_real_rejection_with_unfortunately_and_context_is_rejected():
    body = "Unfortunately, after careful review we will not be moving forward with your application at this time."
    r = classify("Update on your application", body, "Acme", "today")
    assert r["stage"] == "rejected"

def test_moving_forward_with_other_candidates_is_rejection_despite_received_subject():
    r = classify("Thank you for applying to Acme", "We have decided to move forward with other candidates.", "Acme", "today")
    assert r["stage"] == "rejected"

def test_online_assessment_reminder_is_assessment():
    r = classify("Reminder: complete your online assessment", "Please finish your online assessment before Friday.", "Acme", "today")
    assert r["stage"] == "assessment"

def test_you_may_be_asked_to_take_an_assessment_is_not_assessment():
    body = "Thank you for your interest. Later in the process you may be asked to complete a coding challenge."
    r = classify("Thank you for your interest in Acme", body, "Acme", "today")
    assert r["stage"] == "applied"

def test_phone_screen_invitation_is_interview():
    r = classify("Next steps with Acme", "We'd like to schedule a phone screen with you next week.", "Acme", "today")
    assert r["stage"] == "interview"
