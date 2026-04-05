"""Queue management: enqueue, atomic state transitions, retry logic."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any


PENDING_SUFFIX = ".pending"
PROCESSING_SUFFIX = ".processing"
FAILED_SUFFIX = ".failed"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    """Write JSON atomically using a tempfile + os.replace()."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def read_queue_item(path: Path) -> Optional[Dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError):
        return None
    return None


def enqueue(
    queue_dir: Path,
    session_id: str,
    transcript_path: str,
    hook_event: str = "SessionEnd",
) -> Path:
    """Create a {session_id}.pending file. Returns path."""
    queue_dir.mkdir(parents=True, exist_ok=True)
    target = queue_dir / f"{session_id}{PENDING_SUFFIX}"
    payload = {
        "session_id": session_id,
        "transcript_path": transcript_path,
        "enqueued_at": _utc_now_iso(),
        "hook_event": hook_event,
        "attempts": 0,
    }
    _atomic_write_json(target, payload)
    return target


def list_pending(queue_dir: Path) -> List[Path]:
    if not queue_dir.exists():
        return []
    return sorted(queue_dir.glob(f"*{PENDING_SUFFIX}"))


def list_processing(queue_dir: Path) -> List[Path]:
    if not queue_dir.exists():
        return []
    return sorted(queue_dir.glob(f"*{PROCESSING_SUFFIX}"))


def list_failed(queue_dir: Path) -> List[Path]:
    if not queue_dir.exists():
        return []
    return sorted(queue_dir.glob(f"*{FAILED_SUFFIX}"))


def to_processing(pending_path: Path) -> Optional[Path]:
    """Atomic rename pending -> processing. Returns new path or None on failure."""
    if not pending_path.exists():
        return None
    target = pending_path.with_suffix(PROCESSING_SUFFIX)
    try:
        os.replace(pending_path, target)
        return target
    except OSError:
        return None


def to_pending(processing_path: Path, increment_attempts: bool = False) -> Optional[Path]:
    """Revert processing -> pending. Optionally increments attempts."""
    if not processing_path.exists():
        return None
    target = processing_path.with_suffix(PENDING_SUFFIX)
    if increment_attempts:
        data = read_queue_item(processing_path) or {}
        data["attempts"] = int(data.get("attempts", 0)) + 1
        try:
            _atomic_write_json(processing_path, data)
        except OSError:
            pass
    try:
        os.replace(processing_path, target)
        return target
    except OSError:
        return None


def to_failed(processing_path: Path, reason: str = "") -> Optional[Path]:
    """Move processing -> failed with reason recorded."""
    if not processing_path.exists():
        return None
    data = read_queue_item(processing_path) or {}
    data["failed_at"] = _utc_now_iso()
    if reason:
        data["failure_reason"] = reason
    target = processing_path.with_suffix(FAILED_SUFFIX)
    try:
        _atomic_write_json(processing_path, data)
        os.replace(processing_path, target)
        return target
    except OSError:
        return None


def remove_queue_file(path: Path) -> bool:
    """Remove a queue file (called after delivery or outbox)."""
    try:
        path.unlink()
        return True
    except OSError:
        return False


def sweep_orphans(queue_dir: Path, stale_threshold_seconds: int = 3600) -> List[Path]:
    """Find .processing files older than threshold and move them back to .pending.

    Returns list of recovered paths.
    """
    import time

    recovered: List[Path] = []
    now = time.time()
    for processing in list_processing(queue_dir):
        try:
            mtime = processing.stat().st_mtime
        except OSError:
            continue
        if now - mtime > stale_threshold_seconds:
            new_path = to_pending(processing, increment_attempts=True)
            if new_path:
                recovered.append(new_path)
    return recovered


def record_delivered(
    delivered_dir: Path,
    session_id: str,
    fragment_ids: List[str],
    prompt_version: int,
) -> None:
    """Write a delivery record."""
    delivered_dir.mkdir(parents=True, exist_ok=True)
    target = delivered_dir / f"{session_id}.json"
    payload = {
        "session_id": session_id,
        "delivered_at": _utc_now_iso(),
        "fragment_ids": fragment_ids,
        "prompt_version": prompt_version,
    }
    _atomic_write_json(target, payload)


def has_delivered(delivered_dir: Path, session_id: str, prompt_version: int) -> bool:
    target = delivered_dir / f"{session_id}.json"
    if not target.exists():
        return False
    data = read_queue_item(target)
    if not data:
        return False
    return int(data.get("prompt_version", -1)) == int(prompt_version)
