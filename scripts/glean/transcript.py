"""Parse Claude Code JSONL transcripts and filter to user/assistant text blocks."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import List, Dict, Optional

from .secrets import strip_secrets


MAX_CHARS_PER_BLOCK = 2000


def filter_transcript(
    transcript_path: str,
    max_chars_per_block: int = MAX_CHARS_PER_BLOCK,
) -> List[Dict[str, str]]:
    """Parse the JSONL transcript and return a list of {role, text} entries.

    Skips tool_use, tool_result, thinking, image blocks. Strips secrets.
    """
    entries: List[Dict[str, str]] = []
    path = Path(transcript_path)
    if not path.exists():
        return entries

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = obj.get("type")
            if msg_type not in ("user", "assistant"):
                continue

            message = obj.get("message")
            if not isinstance(message, dict):
                continue

            text = _extract_text(message.get("content"), max_chars_per_block)
            if not text.strip():
                continue

            role = "human" if msg_type == "user" else "assistant"
            entries.append({"role": role, "text": strip_secrets(text)})

    return entries


def filter_to_string(entries: List[Dict[str, str]]) -> str:
    """Serialize filtered entries as newline-delimited JSON."""
    return "\n".join(
        json.dumps(entry, ensure_ascii=False) for entry in entries
    )


def filtered_byte_length(entries: List[Dict[str, str]]) -> int:
    """Total UTF-8 byte count of filtered transcript content."""
    total = 0
    for entry in entries:
        total += len(entry.get("text", "").encode("utf-8"))
    return total


def filtered_transcript_hash(entries: List[Dict[str, str]]) -> str:
    """SHA-256 of the filtered transcript content (role + text)."""
    hasher = hashlib.sha256()
    for entry in entries:
        hasher.update(entry.get("role", "").encode("utf-8"))
        hasher.update(b"\x00")
        hasher.update(entry.get("text", "").encode("utf-8"))
        hasher.update(b"\n")
    return hasher.hexdigest()


def trim_to_max_bytes(text: str, max_bytes: int) -> str:
    """If text exceeds max_bytes, take first half + last half with marker."""
    raw = text.encode("utf-8")
    if len(raw) <= max_bytes:
        return text
    half = max_bytes // 2
    first = raw[:half].decode("utf-8", errors="ignore")
    last = raw[-half:].decode("utf-8", errors="ignore")
    return f"{first}\n[... middle omitted ...]\n{last}"


def extract_project_name(transcript_path: str) -> str:
    """Derive a human-readable project name from the transcript path / content."""
    path = Path(transcript_path)
    parent = path.parent.name
    project = _project_from_dirname(parent)
    if not project:
        cwd = _first_cwd(path)
        project = Path(cwd).name if cwd else parent
    return _humanize_project(project)


def _extract_text(content: object, max_chars: int) -> str:
    if isinstance(content, str):
        return content[:max_chars]
    if not isinstance(content, list):
        return ""
    parts: List[str] = []
    for block in content:
        if isinstance(block, dict):
            btype = block.get("type")
            if btype in ("tool_use", "tool_result", "thinking", "image"):
                continue
            text = block.get("text")
            if isinstance(text, str) and text:
                parts.append(text[:max_chars])
        elif isinstance(block, str):
            parts.append(block[:max_chars])
    return "\n".join(parts)


def _project_from_dirname(dirname: str) -> str:
    if not dirname.startswith("-"):
        return dirname
    stripped = dirname.lstrip("-")
    parts = stripped.split("-")
    if len(parts) <= 2:
        return ""
    if parts[0] == "Users":
        return "-".join(parts[2:])
    return "-".join(parts[1:])


def _humanize_project(name: str) -> str:
    if not name:
        return "personal"
    for prefix in ("Downloads-", "Developer-", "Developer-tools-", "Developer-projects-"):
        if name.startswith(prefix):
            name = name[len(prefix):]
    name = re.sub(r"-\d{4}-[A-Z][a-z]{2}-\d{2}[-\d]*$", "", name)
    name = name.replace("---", " - ")
    name = name.replace("-", " ").strip()
    name = re.sub(r"\s+", " ", name)
    return name or "personal"


def _first_cwd(path: Path) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for raw in handle:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                cwd = obj.get("cwd")
                if isinstance(cwd, str) and cwd:
                    return cwd
    except OSError:
        return ""
    return ""
