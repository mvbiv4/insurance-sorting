"""Tests for the matcher / rules engine."""

import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

from src.parser import InsuranceInfo
from src.matcher import match_insurance, BlocklistEntry


BLOCKLIST = [
    BlocklistEntry("Blue Cross Blue Shield of NC", "YMM"),
    BlocklistEntry("BCBS-NC", "YMM"),
    BlocklistEntry("Aetna", "W99"),
    BlocklistEntry("United Healthcare", "UHC"),
    BlocklistEntry("Cigna", "CIG"),
]


def test_exact_name_match():
    info = InsuranceInfo(name="Blue Cross Blue Shield of NC", member_id="YMM123456")
    result = match_insurance(info, BLOCKLIST)
    assert result.is_flagged
    assert result.status == "flagged"
    assert result.match_type == "both"
    assert result.confidence >= 0.95


def test_fuzzy_name_match():
    # Simulate OCR error: "BIue Cross BIue ShieId of NC" (l→I)
    info = InsuranceInfo(name="BIue Cross BIue ShieId of NC", member_id=None)
    result = match_insurance(info, BLOCKLIST)
    assert result.status in ("flagged", "needs_review")


def test_id_prefix_match():
    info = InsuranceInfo(name="Some Unknown Insurance", member_id="YMM999888777")
    result = match_insurance(info, BLOCKLIST)
    assert result.is_flagged
    assert result.match_type == "id_prefix"


def test_clear_case():
    info = InsuranceInfo(name="LabCorp Internal Plan", member_id="LC12345")
    result = match_insurance(info, BLOCKLIST)
    assert not result.is_flagged
    assert result.status == "clear"


def test_no_info_extracted():
    info = InsuranceInfo(name=None, member_id=None)
    result = match_insurance(info, BLOCKLIST)
    assert result.status == "needs_review"


def test_exact_name_only():
    info = InsuranceInfo(name="Aetna", member_id=None)
    result = match_insurance(info, BLOCKLIST)
    assert result.is_flagged
    assert result.status == "flagged"
    assert result.match_type == "exact_name"


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
