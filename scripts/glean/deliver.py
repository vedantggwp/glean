"""Fragment delivery: dispatch to writer, handle outbox on failure."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Dict, Any, List, Tuple

from .config import Config
from .writers.base import Writer, render_fragment_markdown, render_fragment_filename
from .writers.obsidian import ObsidianWriter
from .writers.markdown import MarkdownWriter


def build_writer(config: Config) -> Writer:
    """Construct a Writer from config."""
    mode = (config.output_mode or "obsidian").lower()
    if mode == "obsidian" and config.vault_path:
        return ObsidianWriter(config.vault_path, config.vault_folder)
    if mode == "markdown" and config.output_dir:
        return MarkdownWriter(config.output_dir)
    # Fallback: flat markdown in plugin data dir
    fallback_dir = Path(config.plugin_data) / "fragments"
    return MarkdownWriter(str(fallback_dir))


def _write_to_outbox(outbox_dir: Path, fragment: Dict[str, Any]) -> bool:
    try:
        outbox_dir.mkdir(parents=True, exist_ok=True)
        fragment_id = fragment.get("fragment_id", "unknown")
        target = outbox_dir / f"{fragment_id}.md"
        content = render_fragment_markdown(fragment)

        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{fragment_id}.", suffix=".tmp", dir=str(outbox_dir)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, target)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
        return True
    except OSError:
        return False


def deliver_fragments(
    config: Config,
    writer: Writer,
    fragments: List[Dict[str, Any]],
) -> Tuple[List[str], List[str]]:
    """Attempt to deliver each fragment via writer; on failure move to outbox.

    Returns (delivered_fragment_ids, outbox_fragment_ids).
    """
    delivered: List[str] = []
    outboxed: List[str] = []
    for fragment in fragments:
        ok = False
        try:
            ok = writer.deliver(fragment)
        except Exception:
            ok = False
        if ok:
            delivered.append(fragment.get("fragment_id", ""))
        else:
            if _write_to_outbox(config.outbox_dir, fragment):
                outboxed.append(fragment.get("fragment_id", ""))
    return delivered, outboxed
