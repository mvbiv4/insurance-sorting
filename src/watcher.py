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


def _wait_for_file_ready(filepath: Path, timeout: float = 30, interval: float = 1) -> bool:
    """Wait until a file is no longer being written to (stable size)."""
    prev_size = -1
    elapsed = 0.0
    while elapsed < timeout:
        try:
            current_size = filepath.stat().st_size
            if current_size == prev_size and current_size > 0:
                return True
            prev_size = current_size
        except OSError:
            pass  # File may not exist yet or still locked
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


def watch_folder(folder: str, recursive: bool = False):
    """Watch a folder for new requisition files and process them."""
    folder_path = Path(folder)
    if not folder_path.is_dir():
        log.error(f"Watch folder does not exist: {folder}")
        sys.exit(1)

    log.info(f"Watching folder: {folder_path.resolve()}")
    log.info(f"Supported file types: {', '.join(sorted(SUPPORTED_EXTENSIONS))}")

    file_queue = Queue()

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
