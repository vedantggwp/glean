"""Obsidian vault writer: per-fragment .md with wikilinks."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Dict, Any

from .base import render_fragment_markdown, render_fragment_filename


class ObsidianWriter:
    """Writes fragments into an Obsidian vault as individual .md notes."""

    def __init__(self, vault_path: str, vault_folder: str = "Fragments"):
        self.vault_path = Path(vault_path).expanduser() if vault_path else None
        self.vault_folder = vault_folder

    def deliver(self, fragment: Dict[str, Any]) -> bool:
        if not self.vault_path:
            return False
        try:
            target_dir = self.vault_path / self.vault_folder
            target_dir.mkdir(parents=True, exist_ok=True)

            filename = render_fragment_filename(fragment)
            target = target_dir / filename
            content = render_fragment_markdown(fragment)

            fd, tmp_name = tempfile.mkstemp(
                prefix=f".{filename}.", suffix=".tmp", dir=str(target_dir)
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
