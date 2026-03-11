# Insurance Claim Segregation — Product Requirements Document

## Overview
CPG (Carolina Pathology Group) needs to automatically identify cases with non-participating insurances from scanned patient requisition forms, so a worker can pull those cases and send them to a different lab. Currently this is manual — someone eyeballs each req.

**Constraint:** The system must run **fully local** (no cloud APIs) to avoid HIPAA/PHI concerns.

## Architecture
```
[Scanned Reqs Folder] → [OCR + Quality Check] → [Text Extraction] → [Rules Engine] → [Web Dashboard + DB]
     (PDF/images)        (Tesseract + conf)      (insurance name      (blocklist         (Flask UI + SQLite
                                                   + ID prefix)         matching)          + CSV export)
```

## Tech Stack
- **Python 3.12** — main language
- **Tesseract 5.5** (via `pytesseract`) — OCR with per-word confidence scoring
- **Pillow / OpenCV** — image pre-processing (deskew, denoise, adaptive threshold)
- **rapidfuzz** — fuzzy string matching for OCR error tolerance
- **SQLite** — local database with WAL mode, 30s busy timeout for concurrent access
- **pandas / openpyxl** — report generation (CSV + Excel export)
- **watchdog** — folder monitoring with queue-based processing (non-blocking)
- **Flask** — web dashboard for staff real-time alerts

## Components

### 1. Configuration / Lookup Table
- **File:** `config/insurance_blocklist.csv`
- Editable CSV with columns: `insurance_name`, `id_prefix`, `notes`
- Supports multiple name variants per insurance (e.g., "BCBS-NC", "Blue Cross Blue Shield NC")
- ID prefix column for matching the first N characters of member IDs
- Editable from web UI or directly as CSV by non-technical staff

### 2. OCR Module + Quality Scoring (`src/ocr.py`)
- Tesseract OCR with auto-detection (PATH, then common Windows install locations)
- Accepts PDF, TIFF (multi-page), JPEG, PNG, BMP inputs
- Pre-processing pipeline: grayscale → denoise → adaptive threshold → deskew
- **Scan quality assessment** via Tesseract per-word confidence data:
  - Returns average confidence score (0-100%), word count, low-confidence word count
  - Quality labels: `good` (70%+), `fair` (40-70%), `poor` (<40%), `unreadable` (0 words)
- Non-ASCII Windows path support via numpy buffer fallback for OpenCV
- Page-break-delimited output for multi-page documents

### 3. Insurance Parser (`src/parser.py`)
- Locates insurance section by scanning for keywords (insurance, payer, carrier, member ID, subscriber)
- Extracts insurance company name via labeled field patterns ("Insurance:", "Payer:", "Ins Co:", etc.)
- Extracts member/subscriber ID and group number via regex
- Fallback: scans for known insurance company names when no labeled field is found

### 4. Rules Engine / Matcher (`src/matcher.py`)
- Compares extracted insurance name against blocklist (exact + fuzzy via token_sort_ratio)
- Compares extracted ID prefix against blocklist prefixes
- Flags if EITHER matches
- Confidence scoring:
  - **1.0** — exact name + ID prefix both match
  - **0.95** — exact name match only
  - **0.90** — ID prefix match only
  - **0.65–0.85** — fuzzy name match (≥85% = flagged, 65–84% = needs_review)
  - **0.0** — no match (clear)
- Cases with no extractable insurance info → `needs_review`
- Empty/missing blocklist → `needs_review` with explanation

### 5. Pipeline (`src/pipeline.py`)
- End-to-end orchestration: file → OCR quality check → parse → match → store
- **Scan quality overrides:**
  - Poor/unreadable scan → status set to `poor_scan` regardless of match result
  - Fair scan + clear result → overridden to `needs_review` (can't trust OCR enough)
  - Good scan → normal flagged/clear/needs_review based on match
- All errors caught and stored in DB with error details (never crashes silently)

### 6. Database (`src/db.py`)
- SQLite with WAL mode + 30s busy timeout for concurrent access
- Context manager (`db.connection()`) ensures connections always close
- Tracks: filename, filepath, timestamp, OCR text, extracted fields, status, match details, **OCR quality score + label**
- Statuses: `flagged`, `clear`, `needs_review`, `handled`, `error`, `skipped`, `poor_scan`
- Deduplication by filename (duplicate inserts return -1, no crash)
- Auto-migration: adds `ocr_quality` columns to existing databases

### 7. Reporter (`src/reporter.py`)
- Generates CSV + Excel reports of flagged/needs_review/poor_scan cases
- Configurable time window (default: last 24 hours)
- Excludes raw OCR text and filepaths from reports (PHI minimization)
- Output directory: `reports/`

### 8. Folder Watcher (`src/watcher.py`)
- Uses `watchdog` with queue-based architecture (non-blocking event handler)
- Worker thread processes files from queue
- **File-ready detection**: waits for file size to stabilize before processing (handles slow network writes)
- Supports recursive subdirectory watching
- Logs all results to console

### 9. Web Dashboard (`src/web.py`)
- **Flask web UI** — staff see results in real-time as reqs are scanned
- Auto-refreshes every 15 seconds
- **Alert banners:**
  - Red banner: "X requisitions flagged as non-participating insurance — action needed"
  - Orange banner: "X documents could not be read properly — poor scan quality, manual review required"
- **Header stats:** Flagged, Review, Poor Scan, Clear, Total counts
- **Dashboard view:** flagged + needs-review + poor-scan cases with "Mark Handled" buttons
- **Scan Quality column:** color-coded badges (green/yellow/red) showing OCR confidence percentage
  - Poor/unreadable scans show `!!` indicator
- **All Cases view:** filterable by status (flagged, needs_review, poor_scan, clear, handled, error)
- **Blocklist editor:** edit CSV in browser with validation (column check, size limit, atomic write)
- **CSV/Excel export** from the UI
- **Error handling:** global error handler returns friendly page (never shows stack traces to staff)
- Binds to `0.0.0.0` so accessible from other machines on the network

### 10. CLI (`run.py`)
```
python run.py process <file_or_folder>   Process a single file or all files in a folder
python run.py watch <folder>             Watch a folder for new files (real-time)
python run.py report [--all] [--since]   Generate flagged cases report
python run.py status                     Show database summary counts
python run.py web [--port 5000]          Launch web dashboard
```

## Enterprise Hardening
The codebase has been audited and hardened for enterprise reliability:
- **SQLite concurrency:** 30s busy timeout + WAL mode prevents "database is locked" errors
- **Connection safety:** all DB access via context managers (no leaked connections)
- **Duplicate handling:** duplicate file inserts return -1 gracefully (no IntegrityError crashes)
- **Watcher reliability:** queue-based processing, file-ready detection (waits for writes to finish)
- **Blocklist safety:** atomic writes (temp file → rename), size limits, column validation
- **Web error handling:** global exception handler, input validation on all forms, status enum whitelisting
- **Non-ASCII path support:** OpenCV numpy buffer fallback for international filenames
- **Graceful degradation:** missing blocklist returns empty list, missing Tesseract gives clear error message
- **Logging:** all modules use Python logging for operational visibility

## Test Results: 34+ tests passing
- **Unit tests (12/12):** parser (5), matcher (6), database (1)
- **End-to-end pipeline (8/8):** all insurance types classified correctly
- **Web endpoints (10/10):** all routes, error cases, and edge cases verified
- **Concurrency (6/6):** 10 concurrent writes, read/write contention, blocklist reload under load
- **Real OCR (3/3):** Tesseract on generated sample images — perfect extraction + correct classification
- **Scan quality detection:** poor scan (37% confidence) correctly flagged as `poor_scan`

## Phased Rollout

### Phase 1: Core Engine + Web UI + OCR Quality — COMPLETE
- [x] OCR module with image preprocessing
- [x] **OCR quality scoring** with per-word confidence from Tesseract
- [x] **Poor scan detection** — automatic `poor_scan` status with orange alert banner
- [x] **Fair scan override** — downgrades "clear" to "needs_review" when scan quality is uncertain
- [x] Insurance name/ID/group parser with regex + fallback detection
- [x] Fuzzy matching rules engine with confidence scoring
- [x] SQLite tracking database with dedup + auto-migration
- [x] CSV/Excel report generation
- [x] Folder watcher with queue-based non-blocking processing
- [x] CLI entry point (`run.py`)
- [x] Web dashboard with real-time alerts (flagged + poor scan banners)
- [x] Scan quality column with color-coded badges
- [x] Blocklist editor in web UI with validation + atomic writes
- [x] Mark-as-handled workflow
- [x] Status filtering (including poor_scan) and CSV export from UI
- [x] Enterprise hardening (concurrency, error handling, connection safety)
- [x] Tesseract OCR installed and tested via Scoop
- [x] Full test suite passing (34+ tests)

### Phase 2: Production Integration — BLOCKED (waiting on CPG info)
- [ ] Real blocklist from CPG billing (non-participating insurance names + ID prefixes)
- [ ] Point at actual scanned reqs folder path
- [ ] End-to-end test with real scanned requisitions
- [ ] Tune fuzzy matching thresholds based on real OCR quality
- [ ] Tune scan quality thresholds based on real fax/scan quality
- [ ] Install Python + Tesseract on the enterprise VM
- [ ] Set up Windows Task Scheduler for watcher + web dashboard

## Still Needed From CPG

| Item | Status | Who |
|------|--------|-----|
| List of non-participating insurances | **Not yet** | Martin / CPG billing |
| Insurance ID number prefixes | **Not yet** | Martin / CPG billing |
| Where scanned reqs are stored (path + format) | **Not yet** | Martin / IT |
| Sample scanned requisitions (2-3 examples) | **Not yet** | Martin |

## Deployment — Enterprise VM

**Target:** Windows VM on CPG's network (no internet required after initial setup).

### Prerequisites on the VM
1. **Python 3.10+** — install from python.org or via IT's approved software catalog
2. **Tesseract OCR 5.x** — install via Scoop (`scoop install tesseract`) or UB-Mannheim installer
   - If using Scoop: also download `eng.traineddata` to the tessdata directory
   - If using installer: default path `C:\Program Files\Tesseract-OCR\` is auto-detected
3. **Python packages** — `pip install -r requirements.txt` (one-time, can be done offline with wheel files)

### Setup Steps
```
1. Copy insurance-sorting/ folder to the VM
2. Install Python + Tesseract (IT may need to do this if admin is required)
3. pip install -r requirements.txt
4. Edit config/insurance_blocklist.csv with real insurance data from CPG billing
5. Test: python run.py process <path-to-sample-req>
6. Start web dashboard: python run.py web
7. Set up Windows Task Scheduler to run watcher + web dashboard at startup
```

### Running as a Scheduled Task
- **Web dashboard:** `python run.py web` — Task Scheduler job that runs at startup, restart on failure
- **Watcher:** `python run.py watch "\\server\scanned_reqs"` — separate Task Scheduler job at startup
- **Option B — Batch (periodic):** `python run.py process "\\server\scanned_reqs" && python run.py report` every 15 minutes

### Network Considerations
- The scanned reqs folder is likely a network share (UNC path like `\\server\share\reqs`)
- The VM needs read access to that share
- Staff access the dashboard via `http://vm-ip:5000` from their workstations
- Firewall rule needed: allow port 5000 from staff workstations to the VM
- Reports output to `reports/` locally — could also be a mapped network drive
- **No outbound internet needed** — everything runs locally (HIPAA-safe)

### Permissions
- Read access to scanned reqs folder
- Write access to `data/` (SQLite DB) and `reports/` (CSV/Excel output)
- No admin needed after initial Python + Tesseract install

## Risk: OCR Quality
Scanned/faxed reqs may have poor quality. Mitigations built in:
- Image preprocessing (deskew, denoise, adaptive threshold)
- **Per-word confidence scoring** from Tesseract — poor scans automatically flagged with orange alert
- **Quality-based status overrides** — poor scan = `poor_scan`, fair scan + clear = `needs_review`
- Fuzzy string matching (rapidfuzz token_sort_ratio) for OCR errors
- Low-confidence flags go to `needs_review` queue for human check
- If local OCR proves insufficient, could add a local LLM (Llama/Mistral) as a fallback parser — still fully local

## Project Structure
```
insurance-sorting/
├── config/
│   └── insurance_blocklist.csv       # Non-participating insurances + ID prefixes
├── src/
│   ├── ocr.py                        # Tesseract OCR + quality scoring
│   ├── parser.py                     # Extract insurance name + ID from OCR text
│   ├── matcher.py                    # Rules engine — match against blocklist
│   ├── pipeline.py                   # End-to-end processing with quality overrides
│   ├── watcher.py                    # Queue-based folder watcher
│   ├── reporter.py                   # Generate daily flagged-cases report
│   ├── db.py                         # SQLite with context managers + auto-migration
│   └── web.py                        # Flask dashboard with scan quality alerts
├── data/
│   └── flagged_cases.db              # SQLite database (created at runtime)
├── reports/                           # Generated CSV/Excel reports
├── sample_reqs/                       # Test requisition images (including poor scan sample)
├── tests/
│   ├── test_parser.py                # 5 tests
│   ├── test_matcher.py               # 6 tests
│   ├── test_db.py                    # 1 test
│   └── create_sample_req.py          # Sample image generator
├── requirements.txt
├── run.py                             # CLI entry point
└── PRD.md                             # This document
```
