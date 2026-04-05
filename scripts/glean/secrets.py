"""Regex-based secret stripping for transcript text."""

from __future__ import annotations

import re


_PEM_PRIVATE_KEY = re.compile(
    r"-----BEGIN [A-Z0-9 ]+ PRIVATE KEY-----.*?-----END [A-Z0-9 ]+ PRIVATE KEY-----",
    re.DOTALL,
)
_OPENSSH_PRIVATE_KEY = re.compile(
    r"-----BEGIN OPENSSH PRIVATE KEY-----.*?-----END OPENSSH PRIVATE KEY-----",
    re.DOTALL,
)
_DB_URL = re.compile(
    r"(?i)\b(?:postgres|postgresql|mysql|mongodb|mongodb\+srv|redis|amqp)://[^\s\"'<>]+"
)
_ANTHROPIC = re.compile(r"(?i)\bsk-ant-[A-Za-z0-9_-]{8,}\b")
_OPENAI = re.compile(r"\bsk-[A-Za-z0-9]{32,}\b")
_STRIPE = re.compile(r"(?i)\bsk_(?:live|test)_[A-Za-z0-9]{8,}\b")
_AWS_ACCESS_ID = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
_BEARER = re.compile(r"(?i)\bBearer\s+['\"]?[A-Za-z0-9_\-/.+=]{16,}['\"]?")
_GITHUB = re.compile(r"\bgh[opusr]_[A-Za-z0-9]{20,}\b")
_SLACK = re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")
_JWT = re.compile(
    r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"
)
_GENERIC_SECRET = re.compile(
    r"""(?ix)
    \b(api[_-]?key|token|secret|password|passwd|authorization|auth[_-]?token)\b
    (\s*[:=]\s*)
    (["']?)
    ([^\s"']{8,})
    \3
    """
)
_AWS_SECRET = re.compile(
    r"""(?ix)
    \baws[_-]?secret[_-]?access[_-]?key\b
    (\s*[:=]\s*)
    (["']?)
    ([A-Za-z0-9/+=]{16,})
    \2
    """
)


def strip_secrets(text: str) -> str:
    """Redact obvious secret material from text."""
    text = _PEM_PRIVATE_KEY.sub("[REDACTED_KEY]", text)
    text = _OPENSSH_PRIVATE_KEY.sub("[REDACTED_KEY]", text)
    text = _DB_URL.sub("[REDACTED_URL]", text)
    text = _ANTHROPIC.sub("[REDACTED]", text)
    text = _OPENAI.sub("[REDACTED]", text)
    text = _STRIPE.sub("[REDACTED]", text)
    text = _AWS_ACCESS_ID.sub("[REDACTED]", text)
    text = _BEARER.sub("Bearer [REDACTED]", text)
    text = _GITHUB.sub("[REDACTED]", text)
    text = _SLACK.sub("[REDACTED]", text)
    text = _JWT.sub("[REDACTED]", text)
    text = _GENERIC_SECRET.sub(
        lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}[REDACTED]{m.group(3)}",
        text,
    )
    text = _AWS_SECRET.sub(
        lambda m: f"aws_secret_access_key{m.group(1)}{m.group(2)}[REDACTED]{m.group(2)}",
        text,
    )
    return text
