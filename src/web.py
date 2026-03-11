"""Flask web dashboard for insurance requisition sorting.

Staff scanning documents see real-time results:
- Flagged cases highlighted in red
- Needs-review cases in yellow
- Clear cases in green
- Ability to mark cases as handled
- Edit blocklist from the UI
"""

import csv
import io
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, render_template_string, request, redirect, url_for, flash, send_file

from . import db
from .matcher import BLOCKLIST_PATH, load_blocklist
from .reporter import generate_report

log = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(32))
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50MB upload limit

VALID_STATUSES = {"flagged", "needs_review", "clear", "handled", "error", "poor_scan"}

TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CPG Insurance Sorting</title>
    <meta http-equiv="refresh" content="15">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f0f2f5; color: #1a1a2e; }
        .header { background: #1a1a2e; color: white; padding: 16px 24px; display: flex; align-items: center; justify-content: space-between; }
        .header h1 { font-size: 20px; font-weight: 600; }
        .header .stats { display: flex; gap: 16px; font-size: 14px; }
        .header .stat { background: rgba(255,255,255,0.1); padding: 6px 14px; border-radius: 20px; }
        .header .stat.flagged { background: #e74c3c; }
        .header .stat.review { background: #f39c12; color: #1a1a2e; }
        nav { background: #16213e; padding: 0 24px; display: flex; gap: 0; }
        nav a { color: #aaa; text-decoration: none; padding: 12px 20px; font-size: 14px; border-bottom: 3px solid transparent; }
        nav a:hover { color: white; }
        nav a.active { color: white; border-bottom-color: #3498db; }
        .container { max-width: 1200px; margin: 24px auto; padding: 0 24px; }
        .flash { padding: 12px 16px; margin-bottom: 16px; border-radius: 8px; font-size: 14px; }
        .flash.success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .flash.error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        .card { background: white; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 20px; overflow: hidden; }
        .card-header { padding: 16px 20px; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; align-items: center; }
        .card-header h2 { font-size: 16px; font-weight: 600; }
        table { width: 100%; border-collapse: collapse; font-size: 14px; }
        th { background: #f8f9fa; text-align: left; padding: 10px 16px; font-weight: 600; color: #555; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; }
        td { padding: 12px 16px; border-top: 1px solid #f0f0f0; }
        tr:hover { background: #f8f9fa; }
        .status { display: inline-block; padding: 4px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; }
        .status.flagged { background: #fde8e8; color: #c0392b; }
        .status.needs_review { background: #fef3cd; color: #856404; }
        .status.clear { background: #d4edda; color: #155724; }
        .status.handled { background: #e2e3e5; color: #383d41; }
        .status.error { background: #f8d7da; color: #721c24; }
        .status.poor_scan { background: #fff3cd; color: #856404; border: 2px solid #ffc107; }
        .scan-quality { display: inline-block; padding: 2px 8px; border-radius: 8px; font-size: 11px; font-weight: 600; }
        .scan-quality.good { background: #d4edda; color: #155724; }
        .scan-quality.fair { background: #fff3cd; color: #856404; }
        .scan-quality.poor { background: #f8d7da; color: #721c24; }
        .scan-quality.unreadable { background: #721c24; color: white; }
        .scan-alert { background: #ff9800; color: white; padding: 12px 24px; text-align: center; font-size: 15px; font-weight: 600; }
        .confidence { font-weight: 600; }
        .confidence.high { color: #c0392b; }
        .confidence.medium { color: #e67e22; }
        .confidence.low { color: #27ae60; }
        .btn { display: inline-block; padding: 6px 14px; border-radius: 6px; font-size: 13px; text-decoration: none; border: none; cursor: pointer; font-weight: 500; }
        .btn-primary { background: #3498db; color: white; }
        .btn-primary:hover { background: #2980b9; }
        .btn-success { background: #27ae60; color: white; }
        .btn-success:hover { background: #219a52; }
        .btn-danger { background: #e74c3c; color: white; }
        .btn-danger:hover { background: #c0392b; }
        .btn-sm { padding: 4px 10px; font-size: 12px; }
        .empty { padding: 40px; text-align: center; color: #999; }
        form.inline { display: inline; }
        textarea { width: 100%; font-family: monospace; font-size: 13px; padding: 12px; border: 1px solid #ddd; border-radius: 6px; }
        .filter-bar { padding: 12px 20px; background: #f8f9fa; display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
        .filter-bar select, .filter-bar input { padding: 6px 10px; border: 1px solid #ddd; border-radius: 6px; font-size: 13px; }
        .alert-banner { background: #e74c3c; color: white; padding: 16px 24px; text-align: center; font-size: 16px; font-weight: 600; animation: pulse 2s infinite; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.85; } }
        .timestamp { color: #888; font-size: 12px; }
    </style>
</head>
<body>
    {% if alert_count > 0 %}
    <div class="alert-banner">{{ alert_count }} requisition{{ 's' if alert_count != 1 }} flagged as non-participating insurance — action needed</div>
    {% endif %}
    {% if poor_scan_count is defined and poor_scan_count > 0 %}
    <div class="scan-alert">{{ poor_scan_count }} document{{ 's' if poor_scan_count != 1 }} could not be read properly — poor scan quality, manual review required</div>
    {% endif %}

    <div class="header">
        <h1>CPG Insurance Sorting</h1>
        <div class="stats">
            <span class="stat flagged">{{ counts.flagged }} Flagged</span>
            <span class="stat review">{{ counts.needs_review }} Review</span>
            {% if counts.poor_scan %}<span class="stat review">{{ counts.poor_scan }} Poor Scan</span>{% endif %}
            <span class="stat">{{ counts.clear }} Clear</span>
            <span class="stat">{{ counts.total }} Total</span>
        </div>
    </div>
    <nav>
        <a href="{{ url_for('dashboard') }}" class="{{ 'active' if page == 'dashboard' }}">Dashboard</a>
        <a href="{{ url_for('all_cases') }}" class="{{ 'active' if page == 'all' }}">All Cases</a>
        <a href="{{ url_for('blocklist_page') }}" class="{{ 'active' if page == 'blocklist' }}">Blocklist</a>
    </nav>

    <div class="container">
        {% with messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}
        {% for category, message in messages %}
        <div class="flash {{ category }}">{{ message }}</div>
        {% endfor %}
        {% endif %}
        {% endwith %}

        {% block content %}{% endblock %}
    </div>
</body>
</html>
"""

DASHBOARD_TEMPLATE = """
{% extends "base" %}
{% block content %}
<div class="card">
    <div class="card-header">
        <h2>Upload Scan</h2>
    </div>
    <div style="padding: 20px;">
        <form method="POST" action="{{ url_for('upload_scan') }}" enctype="multipart/form-data" style="display:flex; gap:12px; align-items:center; flex-wrap:wrap;">
            <input type="file" name="scan_file" accept=".pdf,.tiff,.tif,.png,.jpg,.jpeg,.bmp" required
                   style="flex:1; min-width:200px; padding:8px; border:2px dashed #ccc; border-radius:8px; background:#f8f9fa; cursor:pointer;">
            <button type="submit" class="btn btn-primary">Process Scan</button>
        </form>
        <p style="margin-top:8px; color:#888; font-size:12px;">Supported: PDF, TIFF, PNG, JPG, BMP</p>
    </div>
</div>

<div class="card">
    <div class="card-header">
        <h2>Flagged & Needs Review</h2>
        <div>
            <a href="{{ url_for('export_report') }}" class="btn btn-primary btn-sm">Export CSV</a>
        </div>
    </div>
    {% if cases %}
    <table>
        <tr>
            <th>File</th>
            <th>Insurance</th>
            <th>Member ID</th>
            <th>Status</th>
            <th>Scan Quality</th>
            <th>Confidence</th>
            <th>Matched</th>
            <th>Processed</th>
            <th>Action</th>
        </tr>
        {% for case in cases %}
        <tr>
            <td><strong>{{ case.filename }}</strong></td>
            <td>{{ case.insurance_name_extracted or '—' }}</td>
            <td>{{ case.insurance_id_extracted or '—' }}</td>
            <td><span class="status {{ case.status }}">{{ case.status | replace('_', ' ') | title }}</span></td>
            <td>
                {% if case.ocr_quality is not none %}
                <span class="scan-quality {{ case.ocr_quality_label or 'good' }}">
                    {{ case.ocr_quality | int }}%
                    {% if case.ocr_quality_label in ('poor', 'unreadable') %} !!{% endif %}
                </span>
                {% else %}—{% endif %}
            </td>
            <td>
                {% if case.match_confidence %}
                <span class="confidence {{ 'high' if case.match_confidence >= 0.85 else 'medium' if case.match_confidence >= 0.65 else 'low' }}">
                    {{ (case.match_confidence * 100) | int }}%
                </span>
                {% else %}—{% endif %}
            </td>
            <td>{{ case.matched_against or '—' }}</td>
            <td class="timestamp">{{ case.processed_at[:16] | replace('T', ' ') }}</td>
            <td>
                <form class="inline" method="POST" action="{{ url_for('mark_handled', req_id=case.id) }}">
                    <button type="submit" class="btn btn-success btn-sm">Mark Handled</button>
                </form>
            </td>
        </tr>
        {% endfor %}
    </table>
    {% else %}
    <div class="empty">No flagged or review cases. All clear!</div>
    {% endif %}
</div>
{% endblock %}
"""

ALL_CASES_TEMPLATE = """
{% extends "base" %}
{% block content %}
<div class="card">
    <div class="card-header">
        <h2>All Processed Requisitions</h2>
        <a href="{{ url_for('export_report') }}?all=1" class="btn btn-primary btn-sm">Export All CSV</a>
    </div>
    <div class="filter-bar">
        <form method="GET">
            <select name="status" onchange="this.form.submit()">
                <option value="">All Statuses</option>
                {% for s in ['flagged', 'needs_review', 'poor_scan', 'clear', 'handled', 'error'] %}
                <option value="{{ s }}" {{ 'selected' if filter_status == s }}>{{ s | replace('_', ' ') | title }}</option>
                {% endfor %}
            </select>
        </form>
    </div>
    {% if cases %}
    <table>
        <tr>
            <th>File</th>
            <th>Insurance</th>
            <th>Member ID</th>
            <th>Status</th>
            <th>Scan Quality</th>
            <th>Confidence</th>
            <th>Reason</th>
            <th>Processed</th>
        </tr>
        {% for case in cases %}
        <tr>
            <td><strong>{{ case.filename }}</strong></td>
            <td>{{ case.insurance_name_extracted or '—' }}</td>
            <td>{{ case.insurance_id_extracted or '—' }}</td>
            <td><span class="status {{ case.status }}">{{ case.status | replace('_', ' ') | title }}</span></td>
            <td>
                {% if case.ocr_quality is not none %}
                <span class="scan-quality {{ case.ocr_quality_label or 'good' }}">
                    {{ case.ocr_quality | int }}%
                    {% if case.ocr_quality_label in ('poor', 'unreadable') %} !!{% endif %}
                </span>
                {% else %}—{% endif %}
            </td>
            <td>
                {% if case.match_confidence %}
                <span class="confidence {{ 'high' if case.match_confidence >= 0.85 else 'medium' if case.match_confidence >= 0.65 else 'low' }}">
                    {{ (case.match_confidence * 100) | int }}%
                </span>
                {% else %}—{% endif %}
            </td>
            <td style="max-width:300px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">{{ case.notes or '—' }}</td>
            <td class="timestamp">{{ case.processed_at[:16] | replace('T', ' ') }}</td>
        </tr>
        {% endfor %}
    </table>
    {% else %}
    <div class="empty">No cases found.</div>
    {% endif %}
</div>
{% endblock %}
"""

BLOCKLIST_TEMPLATE = """
{% extends "base" %}
{% block content %}
<div class="card">
    <div class="card-header">
        <h2>Non-Participating Insurance Blocklist</h2>
    </div>
    <div style="padding: 20px;">
        <p style="margin-bottom: 12px; color: #666; font-size: 14px;">
            Edit the CSV below. Columns: <strong>insurance_name</strong>, <strong>id_prefix</strong>, <strong>notes</strong>.
            One entry per line. Changes take effect immediately on next processed requisition.
        </p>
        <form method="POST" action="{{ url_for('save_blocklist') }}">
            <textarea name="blocklist_csv" rows="20">{{ blocklist_csv }}</textarea>
            <div style="margin-top: 12px;">
                <button type="submit" class="btn btn-primary">Save Blocklist</button>
            </div>
        </form>
    </div>
</div>

<div class="card">
    <div class="card-header"><h2>Current Entries ({{ entries | length }})</h2></div>
    {% if entries %}
    <table>
        <tr><th>Insurance Name</th><th>ID Prefix</th><th>Notes</th></tr>
        {% for e in entries %}
        <tr>
            <td>{{ e.insurance_name }}</td>
            <td><code>{{ e.id_prefix }}</code></td>
            <td style="color:#888;">{{ e.notes }}</td>
        </tr>
        {% endfor %}
    </table>
    {% endif %}
</div>
{% endblock %}
"""


def get_counts(conn):
    total = conn.execute("SELECT COUNT(*) as c FROM requisitions").fetchone()["c"]
    counts = {"total": total}
    for status in ("flagged", "needs_review", "clear", "handled", "error", "poor_scan"):
        row = conn.execute("SELECT COUNT(*) as c FROM requisitions WHERE status = ?", (status,)).fetchone()
        counts[status] = row["c"]
    return counts


@app.template_global()
def render_base():
    return TEMPLATE


# Jinja2 needs templates — we'll use render_template_string with extends
from jinja2 import BaseLoader, TemplateNotFound

class InlineLoader(BaseLoader):
    templates = {
        "base": TEMPLATE,
        "dashboard": DASHBOARD_TEMPLATE,
        "all_cases": ALL_CASES_TEMPLATE,
        "blocklist": BLOCKLIST_TEMPLATE,
    }
    def get_source(self, environment, template):
        if template in self.templates:
            source = self.templates[template]
            return source, template, lambda: True
        raise TemplateNotFound(template)

app.jinja_loader = InlineLoader()

_db_initialized = False

def _ensure_db():
    global _db_initialized
    if not _db_initialized:
        with db.connection() as conn:
            db.init_db(conn)
        _db_initialized = True

@app.before_request
def before_request():
    _ensure_db()


@app.errorhandler(Exception)
def handle_error(e):
    log.error(f"Unhandled web error: {e}", exc_info=True)
    return render_template_string(
        """<!DOCTYPE html><html><body style="font-family:sans-serif;padding:40px;">
        <h1>Internal Error</h1><p>An error occurred. Check server logs for details.</p>
        <a href="/">Back to Dashboard</a></body></html>"""
    ), 500


@app.route("/")
def dashboard():
    with db.connection() as conn:
        counts = get_counts(conn)
        cases = conn.execute(
            "SELECT * FROM requisitions WHERE status IN ('flagged', 'needs_review', 'poor_scan') ORDER BY "
            "CASE status WHEN 'poor_scan' THEN 0 WHEN 'flagged' THEN 1 WHEN 'needs_review' THEN 2 END, processed_at DESC"
        ).fetchall()
        cases = [dict(r) for r in cases]
        alert_count = counts["flagged"]
        poor_scan_count = counts["poor_scan"]
    return render_template_string(
        "{% extends 'dashboard' %}",
        page="dashboard", counts=counts, cases=cases, alert_count=alert_count, poor_scan_count=poor_scan_count,
    )


@app.route("/all")
def all_cases():
    with db.connection() as conn:
        counts = get_counts(conn)
        filter_status = request.args.get("status", "")
        # Validate status filter to prevent unexpected queries
        if filter_status and filter_status not in VALID_STATUSES:
            filter_status = ""
        if filter_status:
            cases = conn.execute(
                "SELECT * FROM requisitions WHERE status = ? ORDER BY processed_at DESC LIMIT 500",
                (filter_status,),
            ).fetchall()
        else:
            cases = conn.execute(
                "SELECT * FROM requisitions ORDER BY processed_at DESC LIMIT 500"
            ).fetchall()
        cases = [dict(r) for r in cases]
    return render_template_string(
        "{% extends 'all_cases' %}",
        page="all", counts=counts, cases=cases, filter_status=filter_status, alert_count=0,
    )


@app.route("/blocklist")
def blocklist_page():
    with db.connection() as conn:
        counts = get_counts(conn)

    try:
        blocklist_csv = BLOCKLIST_PATH.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        blocklist_csv = "insurance_name,id_prefix,notes\n"
        flash("Blocklist file not found — created empty template.", "error")
    except PermissionError:
        blocklist_csv = ""
        flash("Permission denied reading blocklist file.", "error")

    entries = load_blocklist()

    return render_template_string(
        "{% extends 'blocklist' %}",
        page="blocklist", counts=counts, blocklist_csv=blocklist_csv, entries=entries, alert_count=0,
    )


@app.route("/blocklist/save", methods=["POST"])
def save_blocklist():
    csv_content = request.form.get("blocklist_csv", "")

    # Limit size to prevent abuse (100KB should be more than enough)
    if len(csv_content) > 102400:
        flash("Blocklist too large (max 100KB).", "error")
        return redirect(url_for("blocklist_page"))

    # Validate CSV structure
    try:
        reader = csv.DictReader(io.StringIO(csv_content))
        fieldnames = reader.fieldnames
        if not fieldnames:
            flash("CSV has no header row.", "error")
            return redirect(url_for("blocklist_page"))
        required = {"insurance_name", "id_prefix"}
        if not required.issubset(set(fieldnames)):
            flash(f"CSV must have columns: insurance_name, id_prefix (found: {', '.join(fieldnames)})", "error")
            return redirect(url_for("blocklist_page"))
        rows = list(reader)
        if not rows:
            flash("Blocklist has no data rows (only header).", "error")
            return redirect(url_for("blocklist_page"))
    except Exception as e:
        flash(f"Invalid CSV: {e}", "error")
        return redirect(url_for("blocklist_page"))

    try:
        # Write atomically: write to temp file then rename
        temp_path = BLOCKLIST_PATH.with_suffix(".csv.tmp")
        temp_path.write_text(csv_content, encoding="utf-8")
        temp_path.replace(BLOCKLIST_PATH)
        flash(f"Blocklist saved — {len(rows)} entries.", "success")
    except PermissionError:
        flash("Permission denied writing blocklist file.", "error")
    except Exception as e:
        flash(f"Failed to save blocklist: {e}", "error")

    return redirect(url_for("blocklist_page"))


UPLOAD_DIR = Path(__file__).parent.parent / "scans"
ALLOWED_EXTENSIONS = {".pdf", ".tiff", ".tif", ".png", ".jpg", ".jpeg", ".bmp"}


@app.route("/upload", methods=["POST"])
def upload_scan():
    if "scan_file" not in request.files:
        flash("No file selected.", "error")
        return redirect(url_for("dashboard"))

    f = request.files["scan_file"]
    if not f.filename:
        flash("No file selected.", "error")
        return redirect(url_for("dashboard"))

    # Validate extension
    ext = Path(f.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        flash(f"Unsupported file type: {ext}. Use PDF, TIFF, PNG, JPG, or BMP.", "error")
        return redirect(url_for("dashboard"))

    # Sanitize filename and save
    from werkzeug.utils import secure_filename
    safe_name = secure_filename(f.filename)
    if not safe_name:
        safe_name = f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    save_path = UPLOAD_DIR / safe_name

    # Avoid overwriting — append timestamp if file exists
    if save_path.exists():
        stem = save_path.stem
        safe_name = f"{stem}_{datetime.now().strftime('%H%M%S')}{ext}"
        save_path = UPLOAD_DIR / safe_name

    f.save(str(save_path))

    # Process through the full pipeline
    from .pipeline import process_file
    from .matcher import load_blocklist
    blocklist = load_blocklist()
    result = process_file(save_path, blocklist)

    if result.status == "flagged":
        flash(f"FLAGGED: {safe_name} — {result.reason}", "error")
    elif result.status == "poor_scan":
        flash(f"Poor scan quality: {safe_name} — manual review needed.", "error")
    elif result.status == "needs_review":
        flash(f"Needs review: {safe_name} — {result.reason}", "error")
    else:
        flash(f"Processed: {safe_name} — {result.status} ({result.reason})", "success")

    return redirect(url_for("dashboard"))


@app.route("/mark-handled/<int:req_id>", methods=["POST"])
def mark_handled(req_id):
    with db.connection() as conn:
        # Verify the record exists
        row = conn.execute("SELECT id, status FROM requisitions WHERE id = ?", (req_id,)).fetchone()
        if not row:
            flash(f"Case #{req_id} not found.", "error")
            return redirect(url_for("dashboard"))
        db.update_status(conn, req_id, "handled", f"Marked handled via web UI at {datetime.now().isoformat()}")
    flash("Case marked as handled.", "success")
    return redirect(url_for("dashboard"))


@app.route("/export")
def export_report():
    try:
        include_all = request.args.get("all") == "1"
        since = (datetime.now() - timedelta(days=30)).isoformat()
        path = generate_report(since=since, include_clear=include_all)
        return send_file(str(path), as_attachment=True)
    except Exception as e:
        log.error(f"Report export failed: {e}", exc_info=True)
        flash(f"Report export failed: {e}", "error")
        return redirect(url_for("dashboard"))


def run_web(host="0.0.0.0", port=5000, debug=False):
    """Start the web dashboard."""
    with db.connection() as conn:
        db.init_db(conn)
    print(f"Starting CPG Insurance Sorting dashboard at http://{host}:{port}")
    if debug:
        app.run(host=host, port=port, debug=True)
    else:
        try:
            from waitress import serve
            print("Using Waitress production server (4 threads)")
            serve(app, host=host, port=port, threads=4)
        except ImportError:
            print("WARNING: waitress not installed, using Flask dev server")
            print("Install waitress for production: pip install waitress")
            app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    run_web(debug=True)
