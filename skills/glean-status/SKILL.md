---
name: glean-status
description: Show glean pipeline health - pending queue, delivered fragments, outbox, recent activity, last extraction timestamp, and config summary
allowed-tools: Bash, Read
user-invocable: true
---

# glean-status

Show the current health of the glean extraction pipeline.

## Steps

1. Run the worker status command. The worker outputs a JSON object on stdout:

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m glean.worker --status
```

2. Parse the JSON. Expect fields like: `pending`, `processing`, `failed`, `delivered_7d`, `outbox`, `last_extraction`, `config` (with `output_mode`, `vault_path`, `vault_folder`, `extraction_model`, `prompt_version`, `max_fragments_per_session`). If the actual JSON shape differs, adapt to what is returned and surface any unknown fields verbatim.

3. Render a compact human-readable status table. Suggested layout:

```
glean pipeline status
---------------------
Queue       pending: N   processing: N   failed: N
Delivered   last 7d: N   total: N
Outbox      N            (items needing attention)
Last run    2026-04-05T18:45:00Z

Config
  mode:              obsidian
  vault:             /Users/ved/.../VedOS/Fragments
  model:             haiku
  prompt_version:    1
  max fragments:     3 / session
```

4. If `outbox` count > 0, list each outbox item with its `fragment_id` and `reason` (vault write failure, etc). Read files from `${CLAUDE_PLUGIN_DATA}/outbox/` only if the status JSON does not already include the details.

5. If `failed` count > 0, mention that `.failed` files exist in the queue dir and suggest the user inspect `${CLAUDE_PLUGIN_DATA}/worker.log`.

6. Keep output tight - one screen, no decoration beyond what is shown above. Do not add emojis.

## Error handling

- If the worker command fails (non-zero exit), show stderr and the exit code. Do not attempt to fabricate status.
- If `${CLAUDE_PLUGIN_DATA}` is unset or the config is missing, report that clearly and suggest the user re-run the plugin install.
