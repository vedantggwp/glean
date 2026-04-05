"""Extraction orchestrator: filter -> dedup check -> call claude CLI -> parse output."""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from .config import Config
from .transcript import (
    filter_transcript,
    filter_to_string,
    filtered_byte_length,
    filtered_transcript_hash,
    trim_to_max_bytes,
    extract_project_name,
)
from .hashes import compute_dedup_key, compute_content_hash, is_duplicate


EXTRACTION_TIMEOUT_SECONDS = 120
DEFAULT_PROMPT = """You read a Claude Code session transcript and extract up to 3 STORY FRAGMENTS
worth turning into content.

A story fragment is a genuine moment of surprise, tension, learning, or
insight - NOT a boring status update. Skip sessions where nothing interesting
happened and output exactly: NO_IDEAS

For each fragment output this structure:

### {short title}

**Moment:** {what happened - one sentence}
**Surprise:** {what was unexpected}
**Tension:** {the conflict/problem}
**Draft:** {a 1-2 sentence content angle}
**Verbatim:** {a direct quote from the transcript}
**Concepts:** {2-4 comma-separated tag-like concepts}

Be ruthless. Only extract if the moment is genuinely worth writing about.
"""


def resolve_prompt(config: Config) -> str:
    """Resolve extraction prompt: config.prompt_path -> plugin prompts -> default."""
    if config.prompt_path:
        path = Path(config.prompt_path)
        if path.is_file():
            try:
                return path.read_text(encoding="utf-8")
            except OSError:
                pass
    if config.plugin_root:
        candidate = Path(config.plugin_root) / "prompts" / "default.md"
        if candidate.is_file():
            try:
                return candidate.read_text(encoding="utf-8")
            except OSError:
                pass
    return DEFAULT_PROMPT


def build_prompt(
    extraction_prompt: str,
    project_name: str,
    session_id: str,
    filtered_text: str,
    max_fragments: int,
) -> str:
    """Combine prompt template with session context and filtered transcript."""
    return (
        f"{extraction_prompt}\n\n"
        f"Extract up to {max_fragments} fragments.\n\n"
        f"---\n\n"
        f"## Session context\n\n"
        f"Project: {project_name}\n"
        f"Session ID: {session_id}\n\n"
        f"## Filtered transcript\n\n"
        f"{filtered_text}\n"
    )


def _normalize_output(output: str) -> str:
    text = output.strip()
    if text.startswith("```") and text.endswith("```"):
        text = text[3:-3].strip()
    lines: List[str] = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(">"):
            stripped = stripped[1:].lstrip()
        lines.append(stripped)
    return "\n".join(lines).strip()


def is_no_ideas(output: str) -> bool:
    return _normalize_output(output).upper() == "NO_IDEAS"


def count_fragments(output: str) -> int:
    return sum(1 for line in output.splitlines() if line.startswith("### "))


def validate_extraction(output: str, max_fragments: int) -> Tuple[bool, str]:
    text = output.strip()
    if not text:
        return False, "empty output"
    if is_no_ideas(text):
        return True, "NO_IDEAS"
    fragments = count_fragments(text)
    if fragments == 0:
        return False, "missing fragment headers"
    if fragments > max_fragments:
        return False, f"too many fragments: {fragments} > {max_fragments}"
    # Accept both **Moment:** and *Moment:* and Moment: variants
    if not re.search(r"(?mi)^\*{0,2}Moment\*{0,2}:", text):
        return False, "missing required Moment field"
    return True, "valid extraction"


def _slugify(title: str, max_words: int = 5) -> str:
    title = title.lower().strip()
    title = re.sub(r"[^a-z0-9\s-]", "", title)
    title = re.sub(r"\s+", "-", title).strip("-")
    parts = [p for p in title.split("-") if p]
    return "-".join(parts[:max_words]) or "fragment"


def parse_fragments(
    output: str,
    session_id: str,
    project_name: str,
    prompt_version: int,
) -> List[Dict[str, Any]]:
    """Parse claude's markdown output into structured fragment dicts."""
    if is_no_ideas(output):
        return []

    fragments: List[Dict[str, Any]] = []

    # Parse global CONCEPTS line (at end of output, shared across fragments)
    concepts: List[str] = []
    concepts_match = re.search(r"(?mi)^CONCEPTS:\s*(.+?)$", output)
    if concepts_match:
        concepts_line = concepts_match.group(1).strip()
        # Support: "[concept one] [concept two]", "[c1 c2 c3]", "c1, c2, c3"
        bracketed = re.findall(r"\[([^\]]+)\]", concepts_line)
        if bracketed:
            # Each bracket may contain one concept OR multiple space-separated
            raw: List[str] = []
            for item in bracketed:
                # If item has commas/semicolons, split on those
                if "," in item or ";" in item:
                    raw.extend(c.strip() for c in re.split(r"[,;]", item))
                else:
                    # Split on whitespace (concepts are hyphenated, no internal spaces)
                    raw.extend(item.strip().split())
            concepts = [c.strip() for c in raw if c.strip()]
        else:
            # No brackets - split on commas/semicolons first, fallback to whitespace
            if "," in concepts_line or ";" in concepts_line:
                concepts = [c.strip() for c in re.split(r"[,;]", concepts_line) if c.strip()]
            else:
                concepts = [c.strip() for c in concepts_line.split() if c.strip()]
        # Cap at 3 concepts max, normalize
        concepts = [c.lower().strip("[]") for c in concepts[:3] if c]

    blocks = re.split(r"(?m)^###\s+", output)
    captured = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    capture_date = captured[:10]

    for block in blocks[1:]:
        lines = block.splitlines()
        if not lines:
            continue
        title = lines[0].strip()
        # Strip leading/trailing brackets from title (prompt template artifact)
        title = re.sub(r"^\[|\]$", "", title).strip()
        body = "\n".join(lines[1:]).strip()

        moment = _field(body, "Moment")
        surprise = _field(body, "Surprise")
        tension = _field(body, "Tension")
        # Thread is the current field name; Draft is legacy fallback
        draft = _field(body, "Thread") or _field(body, "Draft")
        verbatim = _field(body, "Verbatim")

        canonical = f"{title}|{moment}|{surprise}|{tension}|{draft}|{verbatim}"
        content_hash = compute_content_hash(canonical)
        fragment_id = f"{session_id[:8]}-{content_hash[:8]}"

        fragments.append({
            "fragment_id": fragment_id,
            "content_hash": content_hash,
            "title": title,
            "slug": _slugify(title),
            "moment": moment,
            "surprise": surprise,
            "tension": tension,
            "draft_angle": draft,
            "verbatim": verbatim,
            "concepts": concepts,
            "session_id": session_id,
            "project": project_name,
            "captured": captured,
            "capture_date": capture_date,
            "prompt_version": prompt_version,
        })
    return fragments


def _field(body: str, name: str) -> str:
    # Match **Name:**, *Name:*, or Name:
    pattern = (
        rf"(?mi)^\*{{0,2}}{re.escape(name)}\*{{0,2}}:\*{{0,2}}\s*"
        rf"(.+?)(?=\n\*{{0,2}}(?:Moment|Surprise|Tension|Draft|Thread|Verbatim|Concepts)\*{{0,2}}:|\Z)"
    )
    match = re.search(pattern, body, re.DOTALL)
    if not match:
        return ""
    value = match.group(1).strip()
    # Strip leading markdown artifacts from each line
    cleaned_lines = []
    for line in value.splitlines():
        line = re.sub(r"^\s*\*+\s*", "", line)
        line = re.sub(r"^\s*-\s+", "", line)
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip()


def call_claude_cli(
    prompt: str,
    model: str,
    timeout: int = EXTRACTION_TIMEOUT_SECONDS,
) -> Tuple[bool, str, str]:
    """Invoke `claude --model <model> -p` with prompt on stdin.

    Returns (ok, stdout, stderr).
    """
    try:
        proc = subprocess.run(
            ["claude", "--model", model, "-p"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if proc.returncode != 0:
            return False, proc.stdout or "", proc.stderr or f"exit {proc.returncode}"
        return True, proc.stdout or "", proc.stderr or ""
    except subprocess.TimeoutExpired:
        return False, "", f"timeout after {timeout}s"
    except FileNotFoundError:
        return False, "", "claude CLI not found on PATH"
    except Exception as exc:
        return False, "", f"{type(exc).__name__}: {exc}"


class ExtractionResult:
    """Container for an extraction outcome."""

    def __init__(
        self,
        status: str,
        reason: str = "",
        fragments: Optional[List[Dict[str, Any]]] = None,
        dedup_key: str = "",
        raw_output: str = "",
    ):
        self.status = status  # 'ok' | 'skipped' | 'no_ideas' | 'duplicate' | 'invalid' | 'error'
        self.reason = reason
        self.fragments = fragments or []
        self.dedup_key = dedup_key
        self.raw_output = raw_output

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "reason": self.reason,
            "fragment_count": len(self.fragments),
            "dedup_key": self.dedup_key,
        }


def run_extraction(
    config: Config,
    session_id: str,
    transcript_path: str,
) -> ExtractionResult:
    """End-to-end extraction for a single session."""
    entries = filter_transcript(transcript_path)
    if not entries:
        return ExtractionResult("skipped", "empty transcript after filtering")

    byte_length = filtered_byte_length(entries)
    if byte_length < config.min_text_bytes:
        return ExtractionResult(
            "skipped",
            f"too short: {byte_length} bytes < {config.min_text_bytes}",
        )

    fhash = filtered_transcript_hash(entries)
    dedup_key = compute_dedup_key(session_id, config.prompt_version, fhash)

    if is_duplicate(config.hashes_path, dedup_key):
        return ExtractionResult("duplicate", "dedup_key present", dedup_key=dedup_key)

    filtered_text = filter_to_string(entries)
    filtered_text = trim_to_max_bytes(filtered_text, config.max_text_bytes)

    project_name = extract_project_name(transcript_path)
    prompt_template = resolve_prompt(config)
    prompt = build_prompt(
        prompt_template,
        project_name,
        session_id,
        filtered_text,
        config.max_fragments_per_session,
    )

    ok, stdout, stderr = call_claude_cli(prompt, config.extraction_model)
    if not ok:
        return ExtractionResult("error", f"claude CLI: {stderr.strip()[:200]}", dedup_key=dedup_key)

    valid, reason = validate_extraction(stdout, config.max_fragments_per_session)
    if not valid:
        return ExtractionResult("invalid", reason, dedup_key=dedup_key, raw_output=stdout)

    if is_no_ideas(stdout):
        return ExtractionResult("no_ideas", "NO_IDEAS", dedup_key=dedup_key, raw_output=stdout)

    fragments = parse_fragments(stdout, session_id, project_name, config.prompt_version)
    if not fragments:
        return ExtractionResult("invalid", "no fragments parsed", dedup_key=dedup_key, raw_output=stdout)

    return ExtractionResult(
        "ok",
        f"{len(fragments)} fragment(s)",
        fragments=fragments,
        dedup_key=dedup_key,
        raw_output=stdout,
    )
