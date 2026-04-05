"""Flat-file markdown writer: fallback when no vault configured."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Dict, Any

from .base import render_fragment_markdown, render_fragment_filename


class MarkdownWriter:
    """Writes fragments as flat .md files in a fragments directory."""

    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir).expanduser() if output_dir else None

    def deliver(self, fragment: Dict[str, Any]) -> bool:
        if not self.output_dir:
            return False
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            filename = render_fragment_filename(fragment)
            target = self.output_dir / filename
            content = render_fragment_markdown(fragment)

            fd, tmp_name = tempfile.mkstemp(
                prefix=f".{filename}.", suffix=".tmp", dir=str(self.output_dir)
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
        except (OSError, ValueError):
            return False
