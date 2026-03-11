"""Generate daily flagged-cases reports (CSV and Excel)."""

import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from . import db

log = logging.getLogger(__name__)

REPORTS_DIR = Path(__file__).parent.parent / "reports"


def generate_report(
    since: str = None,
    output_dir: Path = None,
    include_clear: bool = False,
) -> Path:
    """Generate a CSV/Excel report of flagged cases.

    Args:
        since: ISO date string — only include cases processed after this time.
               Defaults to last 24 hours.
        output_dir: Where to save the report. Defaults to reports/.
        include_clear: If True, include 'clear' status cases too.

    Returns:
        Path to the generated report file.
    """
    output_dir = output_dir or REPORTS_DIR
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        log.error(f"Permission denied creating reports directory: {output_dir}")
        raise

    if since is None:
        since = (datetime.now() - timedelta(days=1)).isoformat()

    with db.connection() as conn:
        db.init_db(conn)

        if include_clear:
            rows = conn.execute(
                "SELECT * FROM requisitions WHERE processed_at >= ? ORDER BY status, processed_at DESC",
                (since,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM requisitions WHERE status IN ('flagged', 'needs_review') AND processed_at >= ? ORDER BY status, processed_at DESC",
                (since,),
            ).fetchall()

    records = [dict(r) for r in rows]
    df = pd.DataFrame(records)

    if df.empty:
        # Write empty report with headers
        df = pd.DataFrame(columns=[
            "id", "filename", "processed_at", "insurance_name_extracted",
            "insurance_id_extracted", "status", "match_type",
            "match_confidence", "matched_against", "notes",
        ])

    # Drop raw OCR text and filepath from report (PHI minimization)
    for col in ["ocr_text", "filepath", "raw_section"]:
        if col in df.columns:
            df = df.drop(columns=[col])

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = output_dir / f"flagged_cases_{timestamp}.csv"
    df.to_csv(csv_path, index=False)

    # Also write Excel
    try:
        xlsx_path = output_dir / f"flagged_cases_{timestamp}.xlsx"
        df.to_excel(xlsx_path, index=False, sheet_name="Flagged Cases")
    except Exception as e:
        log.warning(f"Excel export failed (CSV still created): {e}")

    return csv_path


if __name__ == "__main__":
    path = generate_report()
    print(f"Report saved to: {path}")
