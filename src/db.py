"""SQLite database operations for tracking processed requisitions."""

import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime
from typing import Optional

log = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "data" / "flagged_cases.db"


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        log.error(f"Permission denied creating directory: {path.parent}")
        raise
    conn = sqlite3.connect(str(path), timeout=30)  # 30s lock wait for concurrent access
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")  # 30s retry on locked DB
    return conn


@contextmanager
def connection(db_path: Optional[Path] = None):
    """Context manager for safe connection handling. Always closes on exit."""
    conn = get_connection(db_path)
    try:
        yield conn
    finally:
        conn.close()


def init_db(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS requisitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            filepath TEXT UNIQUE NOT NULL,
            processed_at TEXT NOT NULL,
            ocr_text TEXT,
            insurance_name_extracted TEXT,
            insurance_id_extracted TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            -- status: 'flagged', 'clear', 'needs_review', 'handled', 'error', 'poor_scan'
            match_type TEXT,
            -- match_type: 'exact_name', 'fuzzy_name', 'id_prefix', 'both', null
            match_confidence REAL,
            matched_against TEXT,
            notes TEXT,
            ocr_quality REAL,
            -- ocr_quality: 0-100 average word confidence from Tesseract
            ocr_quality_label TEXT
            -- ocr_quality_label: 'good', 'fair', 'poor', 'unreadable'
        );

        CREATE INDEX IF NOT EXISTS idx_req_status ON requisitions(status);
        CREATE INDEX IF NOT EXISTS idx_req_filename ON requisitions(filename);
        CREATE INDEX IF NOT EXISTS idx_req_processed ON requisitions(processed_at);
    """)
    # Migrate existing databases: add ocr_quality columns if missing
    try:
        conn.execute("SELECT ocr_quality FROM requisitions LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE requisitions ADD COLUMN ocr_quality REAL")
        conn.execute("ALTER TABLE requisitions ADD COLUMN ocr_quality_label TEXT")
    # Migrate: move UNIQUE constraint from filename to filepath
    try:
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_req_filepath_unique ON requisitions(filepath)")
    except sqlite3.OperationalError:
        pass  # Index may already exist or table was created with UNIQUE on filepath
    conn.commit()


def file_already_processed(conn: sqlite3.Connection, filepath: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM requisitions WHERE filepath = ?", (filepath,)
    ).fetchone()
    return row is not None


VALID_COLUMNS = {
    "filename", "filepath", "processed_at", "ocr_text",
    "insurance_name_extracted", "insurance_id_extracted",
    "status", "match_type", "match_confidence", "matched_against",
    "notes", "ocr_quality", "ocr_quality_label",
}


def insert_result(conn: sqlite3.Connection, **kwargs) -> int:
    kwargs.setdefault("processed_at", datetime.now().isoformat())
    invalid = set(kwargs.keys()) - VALID_COLUMNS
    if invalid:
        raise ValueError(f"Invalid column names: {invalid}")
    cols = ", ".join(kwargs.keys())
    placeholders = ", ".join(["?"] * len(kwargs))
    try:
        cur = conn.execute(
            f"INSERT INTO requisitions ({cols}) VALUES ({placeholders})",
            list(kwargs.values()),
        )
        conn.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError as e:
        log.warning(f"Duplicate entry skipped: {kwargs.get('filename', '?')} — {e}")
        conn.rollback()
        return -1


def update_status(conn: sqlite3.Connection, req_id: int, status: str, notes: str = None):
    try:
        if notes:
            conn.execute(
                "UPDATE requisitions SET status = ?, notes = ? WHERE id = ?",
                (status, notes, req_id),
            )
        else:
            conn.execute(
                "UPDATE requisitions SET status = ? WHERE id = ?", (status, req_id)
            )
        conn.commit()
    except sqlite3.Error as e:
        log.error(f"Failed to update status for req {req_id}: {e}")
        conn.rollback()
        raise


def get_flagged(conn: sqlite3.Connection, since: str = None) -> list[dict]:
    query = "SELECT * FROM requisitions WHERE status IN ('flagged', 'needs_review')"
    params = []
    if since:
        query += " AND processed_at >= ?"
        params.append(since)
    query += " ORDER BY processed_at DESC"
    rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def get_all(conn: sqlite3.Connection, limit: int = 500) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM requisitions ORDER BY processed_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]
