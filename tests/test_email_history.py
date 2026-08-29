import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent/"src"))
from email_history import classify
def test_application_confirmation():
    r = classify("Application received — Software Intern", "Thank you for applying. Requisition 12345", "Acme Recruiting", "today"); assert r["stage"] == "applied" and r["requisition_id"] == "12345"
def test_unrelated_email_ignored(): assert classify("Lunch", "Where should we eat?", "Friend", "today") is None
