"""Append-only dedup log for content hashes."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def compute_dedup_key(
    session_id: str,
    prompt_version: int,
    filtered_transcript_hash: str,
) -> str:
    """SHA-256 of session_id + prompt_version + filtered_transcript_hash."""
    hasher = hashlib.sha256()
    hasher.update(session_id.encode("utf-8"))
    hasher.update(b"|")
    hasher.update(str(prompt_version).encode("utf-8"))
    hasher.update(b"|")
    hasher.update(filtered_transcript_hash.encode("utf-8"))
    return hasher.hexdigest()


def compute_content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def is_duplicate(hashes_path: Path, dedup_key: str) -> bool:
    if not hashes_path.exists():
        return False
    try:
        with hashes_path.open("r", encoding="utf-8", errors="replace") as handle:
            for raw in handle:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if obj.get("dedup_key") == dedup_key:
                    return True
    except OSError:
        return False
    return False


def record_hash(
    hashes_path: Path,
    dedup_key: str,
    session_id: str,
    fragment_id: str,
    content_hash: Optional[str] = None,
) -> None:
    """Append a new entry to hashes.jsonl atomically."""
    hashes_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "dedup_key": dedup_key,
        "session_id": session_id,
        "fragment_id": fragment_id,
        "content_hash": content_hash or "",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    # Append is atomic on POSIX for small writes
    with hashes_path.open("a", encoding="utf-8") as handle:
        handle.write(line)
