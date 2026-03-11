#!/usr/bin/env python3
"""Main entry point for the insurance requisition sorting system.

Usage:
    python run.py process <file_or_folder>   Process a single file or all files in a folder
    python run.py watch <folder>             Watch a folder for new files
    python run.py report [--all] [--since YYYY-MM-DD]
                                             Generate a flagged cases report
    python run.py status                     Show database summary
    python run.py web [--port 5000]          Launch web dashboard
"""

import sys
import argparse
import logging
from pathlib import Path
from datetime import datetime, timedelta

from src.pipeline import process_file, process_folder
from src.matcher import load_blocklist
from src.reporter import generate_report
from src.watcher import watch_folder
from src import db


def cmd_process(args):
    path = Path(args.path)
    blocklist = load_blocklist()

    if path.is_file():
        print(f"Processing: {path.name}")
        result = process_file(path, blocklist)
        print(f"  Status: {result.status}")
        print(f"  Confidence: {result.confidence:.0%}")
        print(f"  Reason: {result.reason}")
        if result.matched_against:
            print(f"  Matched: {result.matched_against}")

    elif path.is_dir():
        print(f"Processing all files in: {path}")
        results = process_folder(path, blocklist)
        flagged = sum(1 for r in results if r.status == "flagged")
        review = sum(1 for r in results if r.status == "needs_review")
        clear = sum(1 for r in results if r.status == "clear")
        errors = sum(1 for r in results if r.status == "error")
        skipped = sum(1 for r in results if r.status == "skipped")

        print(f"\nResults: {len(results)} files processed")
        print(f"  Flagged:      {flagged}")
        print(f"  Needs Review: {review}")
        print(f"  Clear:        {clear}")
        print(f"  Errors:       {errors}")
        print(f"  Skipped:      {skipped}")
    else:
        print(f"Error: {path} does not exist")
        sys.exit(1)


def cmd_watch(args):
    watch_folder(args.folder, recursive=args.recursive)


def cmd_report(args):
    since = args.since
    if since is None:
        since = (datetime.now() - timedelta(days=1)).isoformat()

    path = generate_report(since=since, include_clear=args.all)
    print(f"Report saved to: {path}")


def cmd_status(args):
    with db.connection() as conn:
        db.init_db(conn)

        row = conn.execute("SELECT COUNT(*) as total FROM requisitions").fetchone()
        print(f"Total processed: {row['total']}")

        for status in ("flagged", "needs_review", "poor_scan", "clear", "handled", "error"):
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM requisitions WHERE status = ?", (status,)
            ).fetchone()
            print(f"  {status:>15}: {row['cnt']}")


def cmd_web(args):
    from src.web import run_web
    run_web(host=args.host, port=args.port, debug=args.debug)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Insurance Requisition Sorting System")
    sub = parser.add_subparsers(dest="command")

    p_proc = sub.add_parser("process", help="Process a file or folder")
    p_proc.add_argument("path", help="Path to file or folder of scanned requisitions")

    p_watch = sub.add_parser("watch", help="Watch a folder for new files")
    p_watch.add_argument("folder", help="Folder path to watch")
    p_watch.add_argument("-r", "--recursive", action="store_true", help="Watch subdirectories too")

    p_report = sub.add_parser("report", help="Generate flagged cases report")
    p_report.add_argument("--since", help="Only include cases after this date (YYYY-MM-DD)")
    p_report.add_argument("--all", action="store_true", help="Include clear cases too")

    p_status = sub.add_parser("status", help="Show database summary")

    p_web = sub.add_parser("web", help="Launch web dashboard")
    p_web.add_argument("--host", default="0.0.0.0", help="Host to bind to (default: 0.0.0.0)")
    p_web.add_argument("--port", type=int, default=5000, help="Port (default: 5000)")
    p_web.add_argument("--debug", action="store_true", help="Enable debug mode")

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        sys.exit(1)

    {"process": cmd_process, "watch": cmd_watch, "report": cmd_report, "status": cmd_status, "web": cmd_web}[args.command](args)


if __name__ == "__main__":
    main()
