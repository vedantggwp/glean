from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from glean.config import load_config
from glean.extract import parse_fragments, validate_extraction
from glean.hashes import compute_dedup_key, is_duplicate, record_hash
from glean.secrets import strip_secrets
from glean.transcript import filter_transcript, filter_to_string
from glean.writers.base import render_fragment_markdown


class SecretStrippingTests(unittest.TestCase):
    def test_strip_secrets_redacts_common_tokens(self) -> None:
        raw = (
            "token=ghp_abcdefghijklmnopqrstuvwxyz012345 "
            "Authorization: Bearer abcdefghijklmnopqrstuvwxyz "
            "OPENAI_API_KEY=sk-abcdefghijklmnopqrstuvwxyzABCDEF123456"
        )

        redacted = strip_secrets(raw)

        self.assertNotIn("ghp_", redacted)
        self.assertNotIn("Bearer abcdef", redacted)
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz", redacted)
        self.assertIn("[REDACTED]", redacted)


class TranscriptFilteringTests(unittest.TestCase):
    def test_filter_transcript_keeps_text_and_drops_tool_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            transcript = Path(tmp) / "session.jsonl"
            rows = [
                {
                    "type": "user",
                    "message": {
                        "content": [
                            {"type": "text", "text": "hello"},
                            {"type": "tool_result", "content": "secret tool output"},
                        ]
                    },
                },
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {"type": "thinking", "text": "private chain"},
                            {"type": "text", "text": "world"},
                        ]
                    },
                },
            ]
            transcript.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

            entries = filter_transcript(str(transcript))
            serialized = filter_to_string(entries)

            self.assertEqual(entries, [{"role": "human", "text": "hello"}, {"role": "assistant", "text": "world"}])
            self.assertNotIn("secret tool output", serialized)
            self.assertNotIn("private chain", serialized)


class ExtractionParsingTests(unittest.TestCase):
    def test_validate_and_parse_fragment_markdown(self) -> None:
        output = """### Cache flag surprise

**Moment:** A stale bundle survived three rebuilds.
**Surprise:** The cache flag was the source of truth.
**Tension:** How many old performance shortcuts are now correctness bugs?
**Thread:** A debugging story about stale artifacts.
**Verbatim:** "The bundle is still old."
**Concepts:** cache-invalidation, build-systems
"""

        valid, reason = validate_extraction(output, max_fragments=3)
        fragments = parse_fragments(output, "session-123456", "glean", prompt_version=1)

        self.assertTrue(valid, reason)
        self.assertEqual(len(fragments), 1)
        self.assertEqual(fragments[0]["title"], "Cache flag surprise")
        self.assertEqual(fragments[0]["project"], "glean")
        rendered = render_fragment_markdown(fragments[0])
        self.assertIn("type: story-fragment", rendered)
        self.assertIn("[[glean]]", rendered)


class ConfigAndHashTests(unittest.TestCase):
    def test_load_config_uses_env_overrides_and_hash_log_dedups(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["GLEAN_MAX_FRAGMENTS"] = "1"
            try:
                config = load_config(plugin_data=tmp, plugin_root="/plugin/root")
            finally:
                os.environ.pop("GLEAN_MAX_FRAGMENTS", None)

            self.assertEqual(config.max_fragments_per_session, 1)
            self.assertEqual(config.plugin_data, tmp)

            hashes_path = Path(tmp) / "hashes.jsonl"
            dedup_key = compute_dedup_key("session-1", 1, "abc123")
            self.assertFalse(is_duplicate(hashes_path, dedup_key))
            record_hash(hashes_path, dedup_key, "session-1", "fragment-1", "content-1")
            self.assertTrue(is_duplicate(hashes_path, dedup_key))


if __name__ == "__main__":
    unittest.main()

