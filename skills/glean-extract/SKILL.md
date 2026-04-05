---
name: glean-extract
description: Manually trigger glean extraction on pending sessions, or on a specific session by ID. Reports processed, extracted, skipped, and errors
argument-hint: "[session-id]"
allowed-tools: Bash
user-invocable: true
---

# glean-extract

Manually trigger the glean worker. Feels like `make deploy` - show progress, end with a summary.

## Steps

1. Decide which mode to run based on `$ARGUMENTS`:

   - If `$ARGUMENTS` is non-empty, treat it as a session id and run:
     ```bash
     PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m glean.worker --session "$1"
     ```

   - If `$ARGUMENTS` is empty, drain the pending queue:
     ```bash
     PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m glean.worker --drain
     ```

2. Stream stdout/stderr to the user as the worker runs. The worker emits structured progress lines for each session it touches.

3. After the worker exits, parse its final output (JSON summary on stdout) and render a summary block:

```
glean extract summary
---------------------
Sessions processed:  N
Fragments extracted: N
Sessions skipped:    N
  - {session_short}: {reason}   (e.g. too short, dedup hit, already delivered)
Errors:              N
  - {session_short}: {error}
```

4. If the worker returned non-zero, surface its exit code and the last lines of stderr. Do not retry automatically - let the user decide.

5. If no pending sessions existed in drain mode, say so plainly:
   `Nothing to do. Queue is empty.`

## Notes

- Only one worker runs at a time (flock on `worker.lock`). If locked, the worker will say so - relay that to the user.
- Do not invent flags beyond `--drain` and `--session` defined in CONTRACTS.md.
