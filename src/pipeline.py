"""End-to-end processing pipeline: file -> OCR -> parse -> match -> store."""

import logging
from pathlib import Path
from datetime import datetime

from . import db
from .ocr import assess_ocr_quality, OCR_QUALITY_POOR
from .parser import parse_insurance
from .matcher import match_insurance, load_blocklist, MatchResult

log = logging.getLogger(__name__)


def process_file(filepath: Path, blocklist=None) -> MatchResult:
    """Process a single requisition file through the full pipeline.

    Returns the MatchResult from the rules engine.
    """
    filepath = Path(filepath)

    with db.connection() as conn:
        db.init_db(conn)

        # Resolve filepath early so we can use it for dedup check
        try:
            resolved = str(filepath.resolve())
        except OSError:
            resolved = str(filepath)

        # Skip if already processed
        if db.file_already_processed(conn, resolved):
            return MatchResult(False, "skipped", None, 0.0, None, "Already processed")

        if blocklist is None:
            blocklist = load_blocklist()

        try:
            # Step 1: OCR with quality assessment
            ocr_result = assess_ocr_quality(filepath)
            ocr_text = ocr_result["text"]
            quality_score = ocr_result["quality_score"]
            quality_label = ocr_result["quality_label"]
            quality_details = ocr_result["quality_details"]

            # Step 2: Parse insurance info
            info = parse_insurance(ocr_text)

            # Step 3: Match against blocklist
            result = match_insurance(info, blocklist)

            # Step 4: Override status if scan quality is too poor to trust
            if quality_label in ("poor", "unreadable"):
                result = MatchResult(
                    is_flagged=False,
                    status="poor_scan",
                    match_type=result.match_type,
                    confidence=result.confidence,
                    matched_against=result.matched_against,
                    reason=f"{quality_details} | Original result: {result.reason}",
                )
            elif quality_label == "fair" and result.status == "clear":
                # Fair quality + clear = still needs review since we can't fully trust OCR
                result = MatchResult(
                    is_flagged=False,
                    status="needs_review",
                    match_type=result.match_type,
                    confidence=result.confidence,
                    matched_against=result.matched_against,
                    reason=f"Scan quality fair — verify this is truly clear | {quality_details}",
                )

            # Step 5: Store in database
            db.insert_result(
                conn,
                filename=filepath.name,
                filepath=resolved,
                processed_at=datetime.now().isoformat(),
                ocr_text=ocr_text,
                insurance_name_extracted=info.name,
                insurance_id_extracted=info.member_id,
                status=result.status,
                match_type=result.match_type,
                match_confidence=result.confidence,
                matched_against=result.matched_against,
                notes=result.reason,
                ocr_quality=quality_score,
                ocr_quality_label=quality_label,
            )

        except Exception as e:
            log.error(f"Error processing {filepath.name}: {e}", exc_info=True)
            try:
                resolved = str(filepath.resolve())
            except OSError:
                resolved = str(filepath)

            db.insert_result(
                conn,
                filename=filepath.name,
                filepath=resolved,
                processed_at=datetime.now().isoformat(),
                status="error",
                notes=str(e)[:1000],
                ocr_quality=0.0,
                ocr_quality_label="error",
            )
            result = MatchResult(False, "error", None, 0.0, None, str(e)[:1000])

    return result


def process_folder(folder: Path, blocklist=None) -> list[MatchResult]:
    """Process all supported files in a folder."""
    folder = Path(folder)
    supported = {".pdf", ".tif", ".tiff", ".jpg", ".jpeg", ".png", ".bmp"}

    if not folder.is_dir():
        raise FileNotFoundError(f"Folder not found: {folder}")

    if blocklist is None:
        blocklist = load_blocklist()

    results = []
    try:
        files = sorted(folder.iterdir())
    except PermissionError:
        log.error(f"Permission denied reading folder: {folder}")
        raise

    for f in files:
        if f.suffix.lower() in supported and not f.name.startswith("."):
            try:
                result = process_file(f, blocklist)
                results.append(result)
            except Exception as e:
                log.error(f"Unhandled error processing {f.name}: {e}", exc_info=True)
                results.append(MatchResult(False, "error", None, 0.0, None, str(e)[:1000]))

    return results
