"""Tests for the database module."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src import db


def test_init_and_insert():
    with tempfile.TemporaryDirectory() as tmpdir:
        conn = db.get_connection(Path(tmpdir) / "test.db")
        db.init_db(conn)

        rid = db.insert_result(
            conn,
            filename="test_req.pdf",
            filepath="/tmp/test_req.pdf",
            ocr_text="Insurance: BCBS\nMember ID: YMM123",
            insurance_name_extracted="BCBS",
            insurance_id_extracted="YMM123",
            status="flagged",
            match_type="exact_name",
            match_confidence=0.95,
            matched_against="BCBS-NC",
            notes="Exact match",
        )
        assert rid == 1

        assert db.file_already_processed(conn, "test_req.pdf")
        assert not db.file_already_processed(conn, "other.pdf")

        flagged = db.get_flagged(conn)
        assert len(flagged) == 1
        assert flagged[0]["filename"] == "test_req.pdf"

        db.update_status(conn, rid, "handled", "Sent to external lab")
        flagged = db.get_flagged(conn)
        assert len(flagged) == 0

        conn.close()


if __name__ == "__main__":
    test_init_and_insert()
    print("  PASS: test_init_and_insert")
