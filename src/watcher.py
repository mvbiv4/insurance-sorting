"""Folder watcher — monitors a directory for new scanned requisitions and processes them."""

import sys
import time
import logging
import threading
from pathlib import Path
from queue import Queue, Empty

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from .pipeline import process_file

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".tif", ".tiff", ".jpg", ".jpeg", ".png", ".bmp"}


class ReqHandler(FileSystemEventHandler):
    """Queues new files for processing instead of blocking the watchdog event loop."""

    def __init__(self, file_queue: Queue):
        super().__init__()
        self.file_queue = file_queue

    def on_created(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() in SUPPORTED_EXTENSIONS:
            log.info(f"New file detected: {path.name}")
            self.file_queue.put(path)


def _wait_for_file_ready(filepath: Path, timeout: float = 30, interval: float = 1, stable_count: int = 3) -> bool:
    """Wait until a file is no longer being written to (stable size for multiple checks)."""
    prev_size = -1
    consecutive_stable = 0
    elapsed = 0.0
    while elapsed < timeout:
        try:
            current_size = filepath.stat().st_size
            if current_size == prev_size and current_size > 0:
                consecutive_stable += 1
                if consecutive_stable >= stable_count:
                    return True
            else:
                consecutive_stable = 0
            prev_size = current_size
        except OSError:
            consecutive_stable = 0
        time.sleep(interval)
        elapsed += interval
    return filepath.exists()


def _process_worker(file_queue: Queue):
    """Worker thread that processes files from the queue."""
    while True:
        try:
            filepath = file_queue.get(timeout=1)
        except Empty:
            continue

        try:
            if not _wait_for_file_ready(filepath):
                log.warning(f"File not ready after timeout, skipping: {filepath.name}")
                continue

            result = process_file(filepath)
            log.info(f"  → {result.status} (confidence: {result.confidence:.0%}) — {result.reason}")
        except Exception as e:
            log.error(f"  → Error processing {filepath.name}: {e}", exc_info=True)
        finally:
            file_queue.task_done()


def _catchup_scan(folder_path: Path, file_queue: Queue):
    """Process files that arrived while the watcher was offline."""
    from . import db
    with db.connection() as conn:
        db.init_db(conn)
        for f in sorted(folder_path.iterdir()):
            if f.suffix.lower() in SUPPORTED_EXTENSIONS and not f.name.startswith("."):
                try:
                    resolved = str(f.resolve())
                except OSError:
                    resolved = str(f)
                if not db.file_already_processed(conn, resolved):
                    log.info(f"Catchup: queuing {f.name}")
                    file_queue.put(f)


def watch_folder(folder: str, recursive: bool = False):
    """Watch a folder for new requisition files and process them."""
    folder_path = Path(folder)
    if not folder_path.is_dir():
        log.error(f"Watch folder does not exist: {folder}")
        sys.exit(1)

    log.info(f"Watching folder: {folder_path.resolve()}")
    log.info(f"Supported file types: {', '.join(sorted(SUPPORTED_EXTENSIONS))}")

    file_queue = Queue()

    # Catch up on files that arrived while watcher was offline
    _catchup_scan(folder_path, file_queue)

    # Start worker thread for processing (non-blocking)
    worker = threading.Thread(target=_process_worker, args=(file_queue,), daemon=True)
    worker.start()

    observer = Observer()
    observer.schedule(ReqHandler(file_queue), str(folder_path), recursive=recursive)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("Stopping folder watcher...")
        observer.stop()
    observer.join()


if __name__ == "__main__":
    folder = sys.argv[1] if len(sys.argv) > 1 else "."
    watch_folder(folder)
