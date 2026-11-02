"""Management-change profiles are read only from the filing text, and say so when there is none."""

from ingest.management import parse_filing


def test_name_role_and_profile_come_from_the_filing():
    subject = "Appointment of Mr. Anil Kumar as Chief Financial Officer"
    text = ("Brief profile: Mr. Anil Kumar is a chartered accountant with 20 years at Tata Steel, "
            "most recently as Finance Director. He holds a B.Com from Delhi University. Other notes follow.")
    got = parse_filing(subject, text)
    assert got["name"] == "Anil Kumar"
    assert got["role"] == "Chief Financial Officer"
    assert got["bio"].startswith("Mr. Anil Kumar is a chartered accountant")
    assert "Delhi University" in got["bio"]


def test_filing_without_a_profile_has_no_bio_but_keeps_the_name():
    got = parse_filing("Resignation of Mr. Ravi Shah as Director", "Resignation effective today.")
    assert got["name"] == "Ravi Shah"
    assert got["bio"] is None
