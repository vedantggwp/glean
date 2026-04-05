"""Append signals from /glean-review (star/archive/trash) to feedback.jsonl."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


VALID_SIGNALS = {"star", "archive", "trash", "reviewed"}


def record_feedback(
    feedback_path: Path,
    fragment_id: str,
    signal: str,
    note: Optional[str] = None,
) -> bool:
    """Append a feedback entry. Returns False if signal is invalid."""
    if signal not in VALID_SIGNALS:
        return False
    feedback_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "fragment_id": fragment_id,
        "signal": signal,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if note:
        entry["note"] = note
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    try:
        with feedback_path.open("a", encoding="utf-8") as handle:
            handle.write(line)
        return True
    except OSError:
        return False


def read_feedback(feedback_path: Path) -> list:
    """Read all feedback entries. Returns [] if file missing."""
    if not feedback_path.exists():
        return []
    entries = []
    try:
        with feedback_path.open("r", encoding="utf-8", errors="replace") as handle:
            for raw in handle:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                entries.append(obj)
    except OSError:
        return entries
    return entries
