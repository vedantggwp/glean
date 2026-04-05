"""Writer protocol."""

from __future__ import annotations

from typing import Protocol, Dict, Any


class Writer(Protocol):
    """A writer delivers a fragment to its destination.

    Returns True on success, False on failure (caller routes to outbox).
    """

    def deliver(self, fragment: Dict[str, Any]) -> bool:
        ...


def render_fragment_markdown(fragment: Dict[str, Any]) -> str:
    """Render a fragment dict as markdown with frontmatter + body."""
    concepts = fragment.get("concepts", []) or []
    project = fragment.get("project", "unknown") or "unknown"
    capture_date = fragment.get("capture_date", "")
    fragment_id = fragment.get("fragment_id", "")
    session_id = fragment.get("session_id", "")
    verbatim = (fragment.get("verbatim") or "").strip()
    verbatim_block = _blockquote(verbatim) if verbatim else ""

    concept_links = "\n".join(
        f"- [[{_clean_wikilink(concept)}]]" for concept in concepts if concept
    )
    project_link = _clean_wikilink(project)

    frontmatter = (
        "---\n"
        "type: story-fragment\n"
        "source: claude-code\n"
        f"project: {_yaml_scalar(project)}\n"
        f"captured: {fragment.get('captured', '')}\n"
        "status: inbox\n"
        "tags: []\n"
        "draft: false\n"
        f"prompt_version: {fragment.get('prompt_version', 1)}\n"
        "schema_version: 1\n"
        f"session_id: {_yaml_scalar(session_id)}\n"
        f"fragment_id: {_yaml_scalar(fragment_id)}\n"
        "---\n"
    )

    body = (
        f"# {fragment.get('title', 'Untitled fragment')}\n\n"
        f"## What happened\n{fragment.get('moment', '')}\n\n"
        f"## The surprise\n{fragment.get('surprise', '')}\n\n"
        f"## The tension\n{fragment.get('tension', '')}\n\n"
        f"## Thread\n{fragment.get('draft_angle', '')}\n\n"
        f"## Verbatim\n{verbatim_block}\n\n"
        "## Related\n"
        f"- [[{project_link}]]\n"
        f"- [[Captured on {capture_date}]]\n"
        f"{concept_links}\n\n"
        f"<!-- fragment_id: {fragment_id} | session: {session_id} -->\n"
    )

    return frontmatter + "\n" + body


def render_fragment_filename(fragment: Dict[str, Any]) -> str:
    """`{YYYY-MM-DD}-{slug}-{session_short}-{hash_short}.md`."""
    capture_date = fragment.get("capture_date", "0000-00-00")
    slug = fragment.get("slug", "fragment")
    session_id = fragment.get("session_id", "")
    content_hash = fragment.get("content_hash", "")
    session_short = session_id[:8] if session_id else "nosess"
    hash_short = content_hash[:8] if content_hash else "nohash"
    return f"{capture_date}-{slug}-{session_short}-{hash_short}.md"


def _blockquote(text: str) -> str:
    return "\n".join(f"> {line}" if line.strip() else ">" for line in text.splitlines())


def _clean_wikilink(text: str) -> str:
    """Sanitize a string for use inside [[wikilinks]]."""
    cleaned = (text or "").replace("[", "(").replace("]", ")").replace("|", "-")
    return cleaned.strip() or "unknown"


def _yaml_scalar(value: str) -> str:
    """Quote a YAML scalar if it contains special characters."""
    text = (value or "").replace("\\", "\\\\").replace('"', '\\"')
    if any(ch in text for ch in ":#\n'\"[]{}&*!|>%@`") or text.strip() != text:
        return f'"{text}"'
    return text
