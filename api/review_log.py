"""Private, low-volume JSONL storage; no model or classification logic here.

Every read/write uses a stable lock file shared by threads and server processes.
A complete snapshot is flushed before atomic replacement, so a failed write
cannot leave half a JSONL record in the live file. All cooperating processes
must use this module; use a database for higher-volume or distributed hosting.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import threading
from uuid import uuid4

from api import config
from api.schemas import ReviewRecord
from api.service import ServiceError


_THREAD_LOCK = threading.RLock()


def unavailable_error():
    return ServiceError(
        503, "REVIEW_LOG_UNAVAILABLE",
        "The manual-review record could not be stored or read. Ask the administrator "
        "to check REVIEW_LOG_PATH, directory permissions, and available storage. "
        "Configure a private .jsonl file outside frontend/, data/, and models/.",
    )


def corrupted_error():
    return ServiceError(
        503, "REVIEW_LOG_CORRUPTED",
        "The manual-review log contains invalid records. The original file has "
        "been preserved. Ask the administrator to restore or repair it before retrying.",
    )


def log_path():
    """Resolve configuration each time, rejecting publicly served/protected paths."""
    if config.REVIEW_LOG_PATH is None:
        raise unavailable_error()
    path = Path(config.REVIEW_LOG_PATH).expanduser()
    if not path.is_absolute():
        path = config.PROJECT_DIR / path
    path = path.resolve()
    forbidden = [config.PROJECT_DIR / directory for directory in (
        "frontend", "data", "models", ".git", ".agents", ".codex", ".aws",
    )]
    forbidden += [config.FRONTEND_DIST, config.MODELS_DIR, config.EVALUATION_PATH]
    if path.suffix.lower() != ".jsonl" or any(
        path == folder.resolve() or folder.resolve() in path.parents
        for folder in forbidden
    ):
        raise unavailable_error()
    return path


@contextmanager
def locked_log(path):
    """Never delete the lock file: replacement would split process coordination."""
    with _THREAD_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = path.with_name(path.name + ".lock")
        with lock_path.open("a+b") as lock_handle:
            if os.name == "nt":
                import msvcrt

                # Windows byte-range locks need at least one byte to lock.
                lock_handle.seek(0, os.SEEK_END)
                if lock_handle.tell() == 0:
                    lock_handle.write(b"\0")
                    lock_handle.flush()
                lock_handle.seek(0)
                msvcrt.locking(lock_handle.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    lock_handle.seek(0)
                    msvcrt.locking(lock_handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)


def read_records(path):
    """Reject corruption instead of skipping records or overwriting evidence."""
    try:
        records = []
        seen_ids = set()
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                record = ReviewRecord.model_validate(json.loads(line))
                if record.ticket_id in seen_ids:
                    raise ValueError("Duplicate ticket identifier")
                seen_ids.add(record.ticket_id)
                records.append(record)
        return records
    except FileNotFoundError:
        return []
    except (ValueError, UnicodeError):
        raise corrupted_error() from None


def write_snapshot(path, records):
    """Replace only after a complete snapshot has been flushed to local storage."""
    temporary_path = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".manual_review-", suffix=".tmp", dir=path.parent,
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            for record in records:
                handle.write(json.dumps(record.model_dump(mode="json"), ensure_ascii=True))
                handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        # POSIX can also flush the directory entry. Windows has no portable
        # directory fsync; this remains demonstration-level local persistence.
        if os.name != "nt":
            directory_descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                # A storage failure can leave a private temp file to clean up.
                # Never log its path or contents.
                pass


def log_review_ticket(original_text, prediction):
    """Save only genuine review decisions and fail the request if saving fails."""
    if not prediction["decision"]["needs_review"]:
        return
    record = ReviewRecord(
        ticket_id=uuid4(), timestamp=datetime.now(timezone.utc),
        ticket_text=original_text,
        category=prediction["category"]["label"],
        category_confidence=prediction["category"]["confidence"],
        urgency=prediction["urgency"]["label"],
        urgency_confidence=prediction["urgency"]["confidence"],
        reasons=prediction["decision"]["reasons"],
        suggested_queue=prediction["decision"]["suggested_queue"], status="pending",
    )
    try:
        path = log_path()
        with locked_log(path):
            records = read_records(path)
            records.append(record)
            write_snapshot(path, records)
    except (OSError, RuntimeError, ValueError):
        raise unavailable_error() from None


def read_review_page(page, page_size):
    try:
        path = log_path()
        with locked_log(path):
            records = read_records(path)
    except (OSError, RuntimeError, ValueError):
        raise unavailable_error() from None
    # Reverse first so equal timestamps retain newest-insertion-first order.
    records = sorted(reversed(records), key=lambda record: record.timestamp, reverse=True)
    total = len(records)
    start = (page - 1) * page_size
    return {
        "items": records[start:start + page_size], "page": page,
        "page_size": page_size, "total": total,
        "total_pages": (total + page_size - 1) // page_size,
    }
