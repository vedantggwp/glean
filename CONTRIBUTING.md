# Contributing to glean

Thanks for helping improve glean. This project is a Claude Code plugin for local reflective capture, so changes should keep the runtime simple, private by default, and easy to audit.

## Development setup

glean is stdlib-only Python. No package install is required for the core checks.

```bash
python3 -m compileall scripts
PYTHONPATH="$PWD/scripts" python3 -m unittest discover -s tests -v
```

If you test the plugin in Claude Code, install it from a working copy and use a throwaway output directory or test vault.

## Project constraints

- Keep `scripts/glean/` stdlib-only.
- Keep hooks dumb: enqueue work and fork the worker, but do not call LLMs from hooks.
- Keep SessionEnd hook work under 500ms.
- Strip secrets before any transcript text is sent to the `claude` CLI.
- Route delivery failures to the outbox instead of dropping fragments.
- Update `CONTRACTS.md` when you change component interfaces, queue schemas, fragment frontmatter, or writer behavior.

## Pull requests

Open a focused PR with:

- A short description of the behavior change.
- Tests or a clear explanation for why a test is not practical.
- Notes about privacy, local filesystem behavior, or API calls if the change touches extraction.

## Issues

Bug reports are most useful when they include:

- OS and Python version.
- Claude Code plugin version or commit.
- Output mode (`obsidian` or `markdown`).
- Relevant `worker.log` lines with secrets removed.

