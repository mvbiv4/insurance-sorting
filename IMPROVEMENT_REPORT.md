# Insurance Sorting — Improvement Report

*Generated: March 9, 2026 — 4 parallel research agents*

---

## Critical Fixes (do these first)

### 1. Duplicate Filename Bug
The `filename` column has a UNIQUE constraint, but if two different folders contain `scan001.pdf`, the second is silently skipped. Use `filepath` as the unique key instead.

### 2. Startup Catchup Scan
When the watcher restarts, files dropped during downtime are **lost forever**. Add a catchup scan on startup that checks the watch folder against the DB and queues any unprocessed files.

### 3. Double Tesseract Call (2x Speedup)
`assess_ocr_quality()` calls BOTH `image_to_data` and `image_to_string` per page — running Tesseract twice. Reconstruct text from the `image_to_data` output instead. Immediate 2x speedup, zero risk.

---

## High Priority — OCR Accuracy

### 4. DPI Normalization
Faxes are typically 200 DPI or lower. Tesseract works best at 300 DPI. The current pipeline does NOT normalize DPI for TIFF/image inputs — only PDFs get `dpi=300`. Upscale low-DPI images before OCR.

### 5. Orientation Detection
Use `pytesseract.image_to_osd()` to detect 90/180/270 degree rotation BEFORE preprocessing. Faxes can arrive upside-down — current deskew only handles small angles.

### 6. Switch to PSM 3
Current config uses `--psm 6` (uniform text block). Medical forms have mixed layout. PSM 3 (automatic segmentation) lets Tesseract decide — better for structured forms.

### 7. Morphological Cleanup After Thresholding
Missing step: close broken characters and remove speckle noise after adaptive threshold:
```python
kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)  # repair broken chars
binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)   # remove speckle
```

### 8. Horizontal/Vertical Line Removal
Fax form lines confuse Tesseract. Use morphological operations to detect and remove lines:
```python
horiz_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
detected = cv2.morphologyEx(binary, cv2.MORPH_OPEN, horiz_kernel, iterations=2)
binary[detected == 0] = 255  # remove detected lines
```

### 9. Faster Denoising
Replace `fastNlMeansDenoising(h=10)` with `cv2.medianBlur(gray, 3)` — much faster, equally effective for fax speckle. Current `h=10` can blur thin strokes on small fonts.

### 10. White Border Padding
Add 10px white border to prevent edge artifacts from confusing Tesseract's page segmentation.

### 11. Raise Quality Threshold
Current "good" threshold at 70% is too lenient for medical documents. Raise to 78%. A word at 65% confidence has a significant chance of being wrong — risky for member IDs.

### Recommended Preprocessing Pipeline Order
1. Load image + DPI metadata
2. DPI normalization (upscale to 300)
3. Orientation detection (rotate 90/180/270)
4. Grayscale
5. Fax header masking (blank top 4%)
6. Median blur (kernel=3)
7. Adaptive threshold
8. Horizontal/vertical line removal
9. Morphological close + open
10. Connected component noise removal (kill blobs < 5px)
11. Deskew (Hough-based)
12. White border padding (10px)
13. OCR with `--oem 3 --psm 3 --dpi 300`

---

## High Priority — Reliability

### 12. File-Based Logging with Rotation
All logging currently goes to console only. Add `RotatingFileHandler`:
- `logs/insurance_sorting.log`
- 5 MB per file, keep 5 files
- Call `setup_logging()` once in `run.py main()`

### 13. Watcher Heartbeat + Dashboard Banner
Write a heartbeat file every processing cycle. Dashboard checks the heartbeat age — if stale (>2 min), show a red banner: "WARNING: File watcher is not running!"

### 14. Production Server — Waitress
Flask dev server is single-threaded, not for production. Replace with Waitress:
```python
from waitress import serve
serve(app, host='0.0.0.0', port=5000, threads=4)
```
Add `waitress` to requirements.txt. Use Flask dev server only with `--debug` flag.

### 15. NSSM Service Wrapper
Use NSSM (Non-Sucking Service Manager) to run watcher + web as proper Windows services with auto-restart, instead of Task Scheduler for always-on processes.

### 16. Remove Per-Request init_db()
`init_db()` runs on nearly every web request (CREATE TABLE IF NOT EXISTS + migration check). Call it once at startup only.

---

## Medium Priority — Web UX

### 17. Reprocess Button
Poor scans and errors are dead ends. Add `/reprocess/<id>` that deletes the old record and re-runs `process_file()`. Show the button for `error` and `poor_scan` statuses.

### 18. Search and Date Filters
Add to the all-cases view:
- Date range picker (from/to)
- Text search (filename or insurance name)
- Keep existing status filter
- Build dynamic SQL query with parameters

### 19. Pagination
Replace hard `LIMIT 500` with proper pagination — 50 per page with Previous/Next controls. Include total count display.

### 20. Smart Auto-Refresh
Replace jarring `<meta http-equiv="refresh" content="15">` with fetch()-based polling:
- Poll `/api/counts` every 10 seconds
- Show a subtle "N new cases — click to refresh" bar instead of full page reload
- Pause polling when tab is hidden

### 21. Audit Log Table
Track who did what:
```sql
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    requisition_id INTEGER,
    action TEXT NOT NULL,
    old_value TEXT, new_value TEXT,
    user_name TEXT, ip_address TEXT
);
```
Use `request.remote_addr` or Windows USERNAME for the "who".

### 22. Health Check Endpoint
`/health` that checks DB connectivity, watcher heartbeat age, and disk space. Returns JSON with status codes.

### 23. Statistics/Trends Page
New nav tab with:
- Cases per day (last 30 days) — CSS bar chart
- Top flagged insurances — horizontal bar chart
- Average OCR quality trend
- Processing volume by hour of day
All via SQLite aggregate queries, no JS charting library needed.

### 24. Session-Based Authentication
Add a `/login` page using Flask sessions. Store user/password-hash pairs in `config/users.json`. Provides the `session["user"]` value for the audit log. No extra packages needed.

---

## Medium Priority — Architecture

### 25. Retry Subcommand
Add `run.py retry` that finds all `status='error'` records, deletes them, and re-runs `process_file()` on the original filepath. Add a `retry_count` column to limit retries.

### 26. Database Backup Subcommand
Use SQLite's built-in `connection.backup()` API for hot backups. Add `run.py backup` and schedule weekly via Task Scheduler.

### 27. Archive Old Records
Move `clear` and `handled` records older than 90 days to a `requisitions_archive` table. Run `VACUUM` after. Schedule weekly.

### 28. Stabilize File-Ready Check
Current check waits for stable file size once. Some scanners close-then-reopen files. Require size stable for 3 consecutive checks instead of 1.

### 29. Worker Thread Crash Recovery
If the watcher's worker thread dies from an unhandled exception, the queue backs up silently. Wrap the worker loop in crash recovery with logging.

### 30. Multi-Page PDF Memory
`pdf2image.convert_from_path()` loads ALL pages at 300 DPI into memory at once. A 50-page fax = gigabytes of RAM. Process one page at a time using `first_page`/`last_page` parameters. Add a page limit safeguard (default 20).

---

## Future — AI Enhancements

### 31. Local LLM Fallback (Ollama + Qwen2.5-3B)
When OCR quality is poor or regex extraction fails, pass noisy text to a local LLM:
- **Setup:** `ollama pull qwen2.5:3b` — single installer, REST API
- **RAM:** ~5-6 GB for 3B model (Q4 quantized)
- **Speed:** 6-15 seconds per document on CPU — fine for 200 forms/day
- **Prompt:** "Extract insurance company name, member ID, group number from this text. Return JSON."
- Ollama supports `format: "json"` for constrained output
- **Verdict:** Highest-value AI improvement. Start here.

### 32. PaddleOCR as Secondary Engine
Consistently outperforms Tesseract on degraded/faxed documents in benchmarks.
- `pip install paddlepaddle paddleocr`
- ~1-2 GB RAM for models
- Run both Tesseract and PaddleOCR, use higher-confidence result
- Also includes table recognition and document structure parsing
- Known Windows issue with `shapely` dependency — may need manual .whl

### 33. Template-Based ROI Extraction
If CPG uses 1-3 standard req form layouts:
1. Record (x, y, width, height) of each field on a clean sample
2. For each scan: align to template via OpenCV, crop each ROI, OCR just that region
3. Zero ML overhead, milliseconds per form, most reliable approach
- Best combined with OCR improvements above
- Only works for standardized forms

### 34. Phonetic Matching (Double Metaphone)
OCR commonly substitutes visually similar chars (l/1, O/0, rn/m). "AETMA" sounds like "AETNA". Add Double Metaphone as a secondary matching signal:
```python
score = 0.6 * rapidfuzz.token_set_ratio(ocr, canonical)
      + 0.4 * (1.0 if metaphone(ocr) == metaphone(canonical) else 0.0)
```
Python library: `fuzzy` (pip install Fuzzy)

### 35. Insurance Name Alias Table
Build a manual lookup table: BCBS -> Blue Cross Blue Shield, UHC -> United Healthcare, etc. Match against aliases BEFORE fuzzy matching. More reliable than any algorithm for the ~50-100 insurers a pathology lab sees. Get this list from CPG billing along with the blocklist.

---

## Implementation Priority

### Do Now (while waiting for CPG data)
| # | Item | Effort | Impact |
|---|------|--------|--------|
| 3 | Eliminate double Tesseract call | 30 min | 2x speedup |
| 1 | Fix duplicate filename bug | 30 min | Prevents silent data loss |
| 14 | Add Waitress production server | 15 min | Required for multi-user |
| 12 | Add file-based logging | 30 min | Required for production |
| 16 | Remove per-request init_db() | 15 min | Cleaner, fewer DB round-trips |
| 17 | Add reprocess button | 1 hr | Unblocks dead-end cases |
| 4-11 | OCR preprocessing improvements | 2-3 hrs | Major accuracy gains |
| 20 | Smart auto-refresh | 1 hr | Better UX |

### Do Before Deployment
| # | Item | Effort | Impact |
|---|------|--------|--------|
| 2 | Startup catchup scan | 1 hr | Prevents lost files |
| 13 | Watcher heartbeat + banner | 1 hr | Staff know when it's down |
| 15 | NSSM service wrapper | 30 min | Reliable Windows service |
| 19 | Pagination | 1 hr | Handles growth |
| 24 | Basic authentication | 1-2 hrs | Security baseline |
| 26 | Database backup subcommand | 30 min | Data safety |

### Do After Go-Live
| # | Item | Effort | Impact |
|---|------|--------|--------|
| 31 | Local LLM fallback (Ollama) | 1 day | Catches what regex misses |
| 33 | Template-based ROI extraction | 1-2 days | Best accuracy for standard forms |
| 32 | PaddleOCR secondary engine | 1 day | Better degraded-doc accuracy |
| 23 | Statistics/trends page | 2-3 hrs | Management reporting |
| 21 | Audit log | 2 hrs | Accountability |
| 34 | Phonetic matching | 2 hrs | Catches OCR-garbled names |

---

*This report was generated by 4 specialized review agents analyzing: OCR/preprocessing, web UX, reliability/architecture, and AI alternatives.*
