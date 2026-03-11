"""Tests for the insurance parser module."""

import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

from src.parser import parse_insurance


def test_basic_labeled_insurance():
    text = """Patient Name: John Doe
DOB: 01/15/1980
Insurance: Blue Cross Blue Shield of NC
Member ID: YMM123456789
Group #: GRP5678
"""
    info = parse_insurance(text)
    assert info.name is not None
    assert "Blue Cross" in info.name
    assert info.member_id == "YMM123456789"
    assert info.group_number == "GRP5678"


def test_alternate_labels():
    text = """Payer: Aetna
Subscriber ID: W99887766
"""
    info = parse_insurance(text)
    assert info.name is not None
    assert "Aetna" in info.name
    assert info.member_id == "W99887766"


def test_primary_insurance_label():
    text = """Primary Insurance: United Healthcare
Policy Number: UHC555123
"""
    info = parse_insurance(text)
    assert info.name is not None
    assert "United" in info.name


def test_no_insurance_info():
    text = """Patient Name: Jane Smith
DOB: 03/22/1995
Phone: 555-1234
"""
    info = parse_insurance(text)
    # Should still return an InsuranceInfo, just with None fields
    assert info is not None


def test_known_name_fallback():
    text = """The patient has Cigna coverage through their employer.
ID number is CIG998877.
"""
    info = parse_insurance(text)
    assert info.name is not None
    assert "Cigna" in info.name


if __name__ == "__main__":
    for name, func in list(globals().items()):
        if name.startswith("test_") and callable(func):
            try:
                func()
                print(f"  PASS: {name}")
            except AssertionError as e:
                print(f"  FAIL: {name} — {e}")
            except Exception as e:
                print(f"  ERROR: {name} — {e}")
