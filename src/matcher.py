"""Rules engine — match extracted insurance info against the blocklist."""

import csv
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from rapidfuzz import fuzz

from .parser import InsuranceInfo

log = logging.getLogger(__name__)

BLOCKLIST_PATH = Path(__file__).parent.parent / "config" / "insurance_blocklist.csv"

# Thresholds for fuzzy matching
FUZZY_HIGH_THRESHOLD = 85   # High confidence
FUZZY_LOW_THRESHOLD = 65    # Low confidence — needs human review


@dataclass
class MatchResult:
    is_flagged: bool
    status: str           # 'flagged', 'clear', 'needs_review'
    match_type: Optional[str]   # 'exact_name', 'fuzzy_name', 'id_prefix', 'both', None
    confidence: float     # 0.0 - 1.0
    matched_against: Optional[str]  # what blocklist entry matched
    reason: str


class BlocklistEntry:
    def __init__(self, insurance_name: str, id_prefix: str, notes: str = ""):
        self.insurance_name = insurance_name.strip()[:500]  # Limit field length
        self.id_prefix = id_prefix.strip().upper()[:20]
        self.notes = notes.strip()[:500]


def load_blocklist(path: Path = None) -> list[BlocklistEntry]:
    path = path or BLOCKLIST_PATH
    if not path.exists():
        log.error(f"Blocklist file not found: {path}")
        return []
    try:
        entries = []
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                log.error(f"Blocklist CSV has no header row: {path}")
                return []
            for row in reader:
                name = row.get("insurance_name", "").strip()
                if name:  # Skip empty rows
                    entries.append(BlocklistEntry(
                        insurance_name=name,
                        id_prefix=row.get("id_prefix", ""),
                        notes=row.get("notes", ""),
                    ))
        if not entries:
            log.warning(f"Blocklist is empty (no entries with insurance_name): {path}")
        return entries
    except Exception as e:
        log.error(f"Failed to load blocklist from {path}: {e}")
        return []


def match_insurance(info: InsuranceInfo, blocklist: list[BlocklistEntry] = None) -> MatchResult:
    """Check if extracted insurance info matches any blocklist entry."""
    if blocklist is None:
        blocklist = load_blocklist()

    if not blocklist:
        return MatchResult(
            is_flagged=False,
            status="needs_review",
            match_type=None,
            confidence=0.0,
            matched_against=None,
            reason="Blocklist is empty or failed to load — cannot match",
        )

    if not info.name and not info.member_id:
        return MatchResult(
            is_flagged=False,
            status="needs_review",
            match_type=None,
            confidence=0.0,
            matched_against=None,
            reason="Could not extract insurance name or ID from requisition",
        )

    best_name_score = 0.0
    best_name_entry = None
    id_prefix_match = None

    extracted_name = (info.name or "").strip()
    extracted_id = (info.member_id or "").strip().upper()

    for entry in blocklist:
        if not entry.insurance_name:
            continue

        # Name matching: exact then fuzzy
        if extracted_name:
            # Exact (case-insensitive)
            if extracted_name.lower() == entry.insurance_name.lower():
                best_name_score = 100.0
                best_name_entry = entry
                break

            # Fuzzy
            score = fuzz.token_sort_ratio(extracted_name.lower(), entry.insurance_name.lower())
            if score > best_name_score:
                best_name_score = score
                best_name_entry = entry

    # ID prefix matching
    if extracted_id:
        for entry in blocklist:
            if entry.id_prefix and extracted_id.startswith(entry.id_prefix):
                id_prefix_match = entry
                break

    # Decision logic
    name_exact = best_name_score >= 95
    name_fuzzy_high = best_name_score >= FUZZY_HIGH_THRESHOLD
    name_fuzzy_low = best_name_score >= FUZZY_LOW_THRESHOLD
    has_id_match = id_prefix_match is not None

    if name_exact and has_id_match:
        return MatchResult(True, "flagged", "both", 1.0,
                           f"{best_name_entry.insurance_name} / prefix {id_prefix_match.id_prefix}",
                           f"Exact name match '{best_name_entry.insurance_name}' + ID prefix match '{id_prefix_match.id_prefix}'")

    if name_exact:
        return MatchResult(True, "flagged", "exact_name", 0.95,
                           best_name_entry.insurance_name,
                           f"Exact name match '{best_name_entry.insurance_name}'")

    if has_id_match:
        return MatchResult(True, "flagged", "id_prefix", 0.9,
                           f"prefix {id_prefix_match.id_prefix}",
                           f"ID prefix match '{id_prefix_match.id_prefix}' on ID '{extracted_id}'")

    if name_fuzzy_high:
        return MatchResult(True, "flagged", "fuzzy_name", best_name_score / 100,
                           best_name_entry.insurance_name,
                           f"Fuzzy name match ({best_name_score:.0f}%) to '{best_name_entry.insurance_name}'")

    if name_fuzzy_low:
        return MatchResult(False, "needs_review", "fuzzy_name", best_name_score / 100,
                           best_name_entry.insurance_name,
                           f"Possible match ({best_name_score:.0f}%) to '{best_name_entry.insurance_name}' — needs human review")

    return MatchResult(False, "clear", None, 0.0, None,
                       f"No blocklist match (best score: {best_name_score:.0f}%)")
