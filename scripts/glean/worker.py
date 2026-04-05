"""Worker CLI: --drain, --session, --sweep, --status, --review.

Holds fcntl flock on worker.lock to prevent concurrent workers.
Emits JSON to stdout; human-readable logs to worker.log.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any

from .config import Config, load_config, ensure_dirs
from .queue import (
    list_pending,
    list_processing,
    list_failed,
    read_queue_item,
    to_processing,
    to_pending,
    to_failed,
    remove_queue_file,
    record_delivered,
    has_delivered,
    sweep_orphans,
    enqueue,
)
from .extract import run_extraction
from .deliver import build_writer, deliver_fragments
from .hashes import record_hash
from .feedback import record_feedback, VALID_SIGNALS


class LockHeld(Exception):
    pass


class WorkerLock:
    """fcntl LOCK_EX | LOCK_NB wrapper."""

    def __init__(self, lock_path: Path):
        self.lock_path = lock_path
        self._handle = None

    def acquire(self) -> bool:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = open(self.lock_path, "a+")
        try:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            self._handle.close()
            self._handle = None
            return False

    def release(self) -> None:
        if self._handle is not None:
            try:
                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
            try:
                self._handle.close()
            except OSError:
                pass
            self._handle = None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _log(config: Config, message: str) -> None:
    try:
        config.worker_log_path.parent.mkdir(parents=True, exist_ok=True)
        with config.worker_log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{_utc_now_iso()}] {message}\n")
    except OSError:
        pass


def _emit_json(payload: Dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def process_session(config: Config, pending_path: Path) -> Dict[str, Any]:
    """Process a single queued session. Returns result dict."""
    item = read_queue_item(pending_path) or {}
    session_id = item.get("session_id") or pending_path.stem
    transcript_path = item.get("transcript_path", "")
    attempts = int(item.get("attempts", 0))

    _log(config, f"PROCESSING session={session_id} attempts={attempts}")

    processing_path = to_processing(pending_path)
    if processing_path is None:
        return {
            "session_id": session_id,
            "status": "error",
            "reason": "failed to enter processing state",
        }

    # Already delivered at this prompt_version? Skip.
    if has_delivered(config.delivered_dir, session_id, config.prompt_version):
        remove_queue_file(processing_path)
        _log(config, f"SKIP session={session_id} already delivered")
        return {"session_id": session_id, "status": "skipped", "reason": "already delivered"}

    if not transcript_path:
        to_failed(processing_path, "missing transcript_path")
        _log(config, f"FAILED session={session_id} missing transcript_path")
        return {"session_id": session_id, "status": "failed", "reason": "missing transcript_path"}

    try:
        result = run_extraction(config, session_id, transcript_path)
    except Exception as exc:
        attempts += 1
        if attempts >= config.retry_limit:
            to_failed(processing_path, f"exception: {exc}")
            _log(config, f"FAILED session={session_id} exception={exc}")
            return {"session_id": session_id, "status": "failed", "reason": str(exc)}
        to_pending(processing_path, increment_attempts=True)
        _log(config, f"RETRY session={session_id} exception={exc}")
        return {"session_id": session_id, "status": "retry", "reason": str(exc)}

    status = result.status

    if status in ("skipped", "duplicate", "no_ideas"):
        remove_queue_file(processing_path)
        _log(config, f"{status.upper()} session={session_id} reason={result.reason}")
        if status == "no_ideas" and result.dedup_key:
            record_hash(config.hashes_path, result.dedup_key, session_id, "no_ideas")
        return {"session_id": session_id, "status": status, "reason": result.reason}

    if status in ("invalid", "error"):
        attempts += 1
        if attempts >= config.retry_limit:
            to_failed(processing_path, result.reason)
            _log(config, f"FAILED session={session_id} reason={result.reason}")
            return {"session_id": session_id, "status": "failed", "reason": result.reason}
        to_pending(processing_path, increment_attempts=True)
        _log(config, f"RETRY session={session_id} reason={result.reason}")
        return {"session_id": session_id, "status": "retry", "reason": result.reason}

    # status == 'ok'
    writer = build_writer(config)
    delivered_ids, outboxed_ids = deliver_fragments(config, writer, result.fragments)

    # Record hash only after we have a delivery or outbox outcome
    for fragment in result.fragments:
        record_hash(
            config.hashes_path,
            result.dedup_key,
            session_id,
            fragment.get("fragment_id", ""),
            fragment.get("content_hash", ""),
        )

    if delivered_ids:
        record_delivered(
            config.delivered_dir,
            session_id,
            delivered_ids,
            config.prompt_version,
        )

    remove_queue_file(processing_path)
    _log(
        config,
        f"DELIVERED session={session_id} delivered={len(delivered_ids)} outbox={len(outboxed_ids)}",
    )
    return {
        "session_id": session_id,
        "status": "delivered" if delivered_ids else "outbox",
        "delivered": delivered_ids,
        "outbox": outboxed_ids,
        "reason": result.reason,
    }


def drain(config: Config, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    pending = list_pending(config.queue_dir)
    if limit is not None:
        pending = pending[:limit]
    for path in pending:
        results.append(process_session(config, path))
    return results


def process_single_session(config: Config, session_id: str) -> Dict[str, Any]:
    target = config.queue_dir / f"{session_id}.pending"
    if not target.exists():
        return {"session_id": session_id, "status": "not_found"}
    return process_session(config, target)


def compute_status(config: Config) -> Dict[str, Any]:
    return {
        "timestamp": _utc_now_iso(),
        "pending": len(list_pending(config.queue_dir)),
        "processing": len(list_processing(config.queue_dir)),
        "failed": len(list_failed(config.queue_dir)),
        "queue_dir": str(config.queue_dir),
        "plugin_data": config.plugin_data,
        "output_mode": config.output_mode,
        "prompt_version": config.prompt_version,
    }


def interactive_review(config: Config) -> Dict[str, Any]:
    """Simple interactive review loop over outbox. Reads stdin lines:
       <fragment_id> <signal>
    """
    count = 0
    for _ in sys.stdin:
        line = _.strip()
        if not line:
            continue
        parts = line.split(None, 2)
        if len(parts) < 2:
            continue
        fragment_id, signal = parts[0], parts[1]
        note = parts[2] if len(parts) > 2 else None
        if signal not in VALID_SIGNALS:
            _emit_json({"fragment_id": fragment_id, "status": "invalid_signal"})
            continue
        ok = record_feedback(config.feedback_path, fragment_id, signal, note)
        _emit_json({
            "fragment_id": fragment_id,
            "signal": signal,
            "status": "recorded" if ok else "error",
        })
        count += 1
    return {"status": "done", "reviewed": count}


def _install_signal_handlers(config: Config, lock: WorkerLock) -> None:
    def _handler(signum, frame):
        # Revert any .processing files back to .pending on exit
        for path in list_processing(config.queue_dir):
            to_pending(path, increment_attempts=False)
        _log(config, f"SIGNAL {signum}: released lock, reverted processing items")
        lock.release()
        sys.exit(130 if signum == signal.SIGINT else 143)

    signal.signal(signal.SIGINT, _handler)
    signal.signal(signal.SIGTERM, _handler)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="glean.worker", description="glean worker")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--drain", action="store_true", help="Process all pending")
    group.add_argument("--session", metavar="SESSION_ID", help="Process specific session")
    group.add_argument("--sweep", action="store_true", help="Recover orphaned processing files")
    group.add_argument("--status", action="store_true", help="Print queue stats as JSON")
    group.add_argument("--review", action="store_true", help="Interactive review via stdin")
    group.add_argument("--enqueue", metavar="SESSION_ID", help="Enqueue a session (for testing)")
    parser.add_argument("--transcript", help="Transcript path (for --enqueue)")
    parser.add_argument("--limit", type=int, default=None, help="Max items to drain")
    parser.add_argument("--stale-seconds", type=int, default=3600, help="Sweep threshold")
    args = parser.parse_args(argv)

    config = load_config()
    ensure_dirs(config)

    # --status and --enqueue do not need the lock
    if args.status:
        _emit_json(compute_status(config))
        return 0

    if args.enqueue:
        if not args.transcript:
            _emit_json({"status": "error", "reason": "--transcript required with --enqueue"})
            return 2
        path = enqueue(config.queue_dir, args.enqueue, args.transcript)
        _emit_json({"status": "enqueued", "path": str(path), "session_id": args.enqueue})
        return 0

    lock = WorkerLock(config.worker_lock_path)
    if not lock.acquire():
        _emit_json({"status": "locked", "reason": "another worker is running"})
        return 0

    _install_signal_handlers(config, lock)

    try:
        if args.review:
            _emit_json(interactive_review(config))
            return 0

        if args.sweep:
            recovered = sweep_orphans(config.queue_dir, args.stale_seconds)
            _emit_json({
                "status": "swept",
                "recovered": [str(p) for p in recovered],
                "count": len(recovered),
            })
            return 0

        if args.session:
            result = process_single_session(config, args.session)
            _emit_json(result)
            return 0

        if args.drain:
            results = drain(config, limit=args.limit)
            summary = {
                "status": "drained",
                "processed": len(results),
                "results": results,
            }
            _emit_json(summary)
            return 0

    finally:
        lock.release()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
