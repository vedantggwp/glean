# glean - Build Contracts

Single source of truth for interfaces between components. All agents build against this.

## Directory Layout

```
${CLAUDE_PLUGIN_ROOT}/                  # plugin install dir (read-only at runtime)
  .claude-plugin/plugin.json
  hooks/hooks.json
  hooks/scripts/*.sh
  scripts/glean/*.py                    # Python package: glean
  skills/*/SKILL.md
  prompts/default.md
  install.sh
  README.md

${CLAUDE_PLUGIN_DATA}/                  # persistent state (survives updates)
  config.json                           # user config from install
  queue/
    {session_id}.pending                # enqueued work
    {session_id}.processing             # worker holds this
    {session_id}.failed                 # gave up after N retries
  delivered/{session_id}.json           # record of successful delivery
  outbox/{fragment_id}.md               # fragments that failed vault write
  hashes.jsonl                          # dedup log (append-only)
  feedback.jsonl                        # /glean-review signals (append-only)
  worker.log                            # human-readable log
  worker.lock                           # flock file
```

## Config Schema (${CLAUDE_PLUGIN_DATA}/config.json)

```json
{
  "schema_version": 1,
  "output_mode": "obsidian",
  "vault_path": "/Users/ved/Documents/Obsidian Vaults/VedOS",
  "vault_folder": "Fragments",
  "extraction_model": "haiku",
  "prompt_path": null,
  "prompt_version": 1,
  "min_text_bytes": 2048,
  "max_text_bytes": 819200,
  "max_fragments_per_session": 3,
  "retry_limit": 3,
  "notification_enabled": true
}
```

## Queue Item Format (.pending files)

JSON, one per session:
```json
{
  "session_id": "abc-123-uuid",
  "transcript_path": "/Users/ved/.claude/projects/.../abc-123.jsonl",
  "enqueued_at": "2026-04-05T18:45:00Z",
  "hook_event": "SessionEnd",
  "attempts": 0
}
```

## State Machine

```
enqueue (hook) -> pending -> processing (worker locks) -> extracted (haiku call done)
                                                           -> delivered (vault write ok) -> removed from queue
                                                           -> outbox (vault write failed) -> removed from queue
                             -> failed (after retry_limit attempts)
```

Worker MUST only remove queue file after delivery or outbox. Never after just extraction.

## Fragment Filename Format

`{YYYY-MM-DD}-{slug}-{session_short}-{hash_short}.md`

- `YYYY-MM-DD`: capture date
- `slug`: 3-5 words from fragment title, kebab-case, alphanumeric only
- `session_short`: first 8 chars of session_id
- `hash_short`: first 8 chars of content hash

Example: `2026-04-05-remotion-bundle-cache-stale-a1b2c3d4-9e8f7d6c.md`

## Fragment Frontmatter

```yaml
---
type: story-fragment
source: claude-code
project: reel-studio
captured: 2026-04-05T14:30:00Z
status: inbox
tags: []
draft: false
prompt_version: 1
schema_version: 1
session_id: abc-123-uuid
fragment_id: a1b2c3d4-9e8f7d6c
---
```

## Fragment Body

```markdown
# {Title from extraction}

## What happened
{moment}

## The surprise
{surprise}

## The tension
{tension}

## Thread
{draft_angle}

## Verbatim
> {verbatim quote}

## Related
- [[{project-name}]]
- [[Captured on {YYYY-MM-DD}]]
- [[{concept-1}]]
- [[{concept-2}]]

<!-- fragment_id: {fragment_id} | session: {session_id} -->
```

## Dedup Key

SHA-256 of: `session_id + prompt_version + filtered_transcript_hash`

Stored in `hashes.jsonl`:
```json
{"dedup_key": "...", "session_id": "...", "fragment_id": "...", "timestamp": "..."}
```

## Skip Logic

Skip extraction if:
- filtered_text_bytes < config.min_text_bytes (default 2048)
- dedup_key already in hashes.jsonl
- session_id already has .delivered record for current prompt_version

## Extraction Call

```bash
echo "$PROMPT" | claude --model haiku -p
```

No `--bare`. Uses user's OAuth. Content-hash dedup catches self-referential extraction.

## Worker Entry Point

```bash
python3 -m glean.worker --drain                # process all pending
python3 -m glean.worker --session {session_id} # process specific
python3 -m glean.worker --sweep                # find orphaned pending files
python3 -m glean.worker --status               # print queue stats as JSON
python3 -m glean.worker --review               # interactive review (stdin/stdout)
```

Worker holds flock on `worker.lock` during processing. Only one worker runs at a time.

## Hook Contract

Hook scripts:
1. Read JSON from stdin (session_id, transcript_path, hook_event_name)
2. Write queue file to `${CLAUDE_PLUGIN_DATA}/queue/{session_id}.pending`
3. Fire-and-forget: spawn worker in background (`nohup ... &`)
4. Exit 0 immediately

Hook scripts MUST complete in < 500ms. Any processing happens in worker.

## Python Module Layout

```
scripts/glean/
  __init__.py
  worker.py              # entry point, CLI arg parsing, flock management
  config.py              # frozen dataclass, load from ${CLAUDE_PLUGIN_DATA}/config.json
  queue.py               # enqueue, dequeue, state transitions
  transcript.py          # JSONL parser + filter + text length calc
  secrets.py             # regex secret stripping
  extract.py             # orchestrate: filter -> dedup -> call haiku -> parse output
  deliver.py             # writer dispatch, outbox management
  hashes.py              # dedup log read/write
  feedback.py            # /glean-review signal log
  writers/
    __init__.py
    base.py              # Writer protocol
    obsidian.py          # per-fragment .md with wikilinks
    markdown.py          # flat file fallback
```

All modules stdlib-only. No external pip dependencies.
