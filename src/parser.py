"""Extract insurance name and member ID from OCR text."""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class InsuranceInfo:
    name: Optional[str] = None
    member_id: Optional[str] = None
    group_number: Optional[str] = None
    raw_section: Optional[str] = None  # the text chunk we extracted from


# Common labels that precede insurance company name on req forms
_NAME_PATTERNS = [
    # "Insurance:", "Insurance Company:", "Ins:", "Payer:", "Carrier:", etc.
    r"(?:insurance\s*(?:company|carrier|name|plan)?|ins|payer|carrier|plan\s*name)\s*[:;]\s*(.+)",
    # "Primary Insurance:" or "Secondary Insurance:"
    r"(?:primary|secondary|pri|sec)\s*(?:insurance|ins|payer)\s*[:;]\s*(.+)",
    # "Ins. Co.:" or "Ins Co:"
    r"ins\.?\s*co\.?\s*[:;]\s*(.+)",
]

# Common labels that precede member/subscriber ID
_ID_PATTERNS = [
    r"(?:member|subscriber|insured|patient)\s*(?:id|#|no|number)\s*[:;]?\s*([A-Z0-9][\w\-]{3,25})",
    r"(?:id|policy)\s*(?:#|no|number)?\s*[:;]\s*([A-Z0-9][\w\-]{3,25})",
    r"(?:insurance\s*id|ins\s*id)\s*[:;]?\s*([A-Z0-9][\w\-]{3,25})",
]

# Group number patterns
_GROUP_PATTERNS = [
    r"(?:group|grp)\s*(?:#|no|number)?\s*[:;]\s*([A-Z0-9][\w\-]{2,20})",
]


def _first_match(text: str, patterns: list[str]) -> Optional[str]:
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            value = m.group(1).strip()
            # Clean trailing junk (next field label, newlines)
            # Only split on field labels that wouldn't be part of the matched value itself
            value = re.split(r"\s{2,}|\n", value)[0]
            value = value.strip(" \t:;,.")
            if len(value) >= 2:
                return value
    return None


def extract_insurance_section(ocr_text: str) -> str:
    """Try to isolate the insurance-related portion of the OCR text.

    Looks for keywords like 'insurance', 'payer', etc. and returns
    surrounding context (a few lines before and after).
    """
    lines = ocr_text.split("\n")
    insurance_indices = []
    for i, line in enumerate(lines):
        if re.search(r"insurance|payer|carrier|ins\s*co|member\s*id|subscriber", line, re.IGNORECASE):
            insurance_indices.append(i)

    if not insurance_indices:
        return ocr_text  # Can't isolate — return everything

    start = max(0, min(insurance_indices) - 2)
    end = min(len(lines), max(insurance_indices) + 5)
    return "\n".join(lines[start:end])


def parse_insurance(ocr_text: str) -> InsuranceInfo:
    """Parse insurance name and member ID from OCR text."""
    section = extract_insurance_section(ocr_text)

    name = _first_match(section, _NAME_PATTERNS)
    member_id = _first_match(section, _ID_PATTERNS)
    group_num = _first_match(section, _GROUP_PATTERNS)

    # If we didn't find a labeled name, look for known insurance company names
    # as a fallback (common names that might appear without a label)
    if not name:
        known_names = [
            "Blue Cross", "BCBS", "Aetna", "Cigna", "United Healthcare",
            "UnitedHealthcare", "Humana", "Medicare", "Medicaid", "Tricare",
            "Kaiser", "Anthem", "Molina", "Centene", "WellCare",
            "Ambetter", "Oscar", "Bright Health", "Medica",
        ]
        for kn in known_names:
            if re.search(re.escape(kn), section, re.IGNORECASE):
                # Grab the full line containing the match
                for line in section.split("\n"):
                    if re.search(re.escape(kn), line, re.IGNORECASE):
                        name = line.strip()
                        break
                break

    return InsuranceInfo(
        name=name,
        member_id=member_id,
        group_number=group_num,
        raw_section=section,
    )


if __name__ == "__main__":
    import sys
    sample = sys.stdin.read() if not sys.stdin.isatty() else "Insurance: Blue Cross Blue Shield\nMember ID: YMM123456789\nGroup #: 12345"
    info = parse_insurance(sample)
    print(f"Name: {info.name}")
    print(f"Member ID: {info.member_id}")
    print(f"Group #: {info.group_number}")
