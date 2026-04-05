# glean

**Your coding sessions are full of insights you're losing. glean catches them.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Claude Code Plugin](https://img.shields.io/badge/Claude%20Code-Plugin-7C3AED)](https://docs.claude.com/claude-code)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Platform: macOS | Linux](https://img.shields.io/badge/platform-macOS%20%7C%20Linux-lightgrey)]()

glean is a Claude Code plugin that quietly mines finished sessions for the moments that mattered - the surprises, the "huh, that didn't work", the times reality disagreed with your model. It writes them to disk as structured fragments you can review later.

This is **reflective capture**, not content extraction. Whether you're a developer who writes, or a developer who wants better recall of what you're learning, glean gives you a running log of the moments worth remembering.

## Data flow

```
  Claude Code session
          |
          v
   SessionEnd hook  (fires once, < 500ms, non-blocking)
          |
          v
    Queue (.pending)  ---------+
          |                    |
          v                    |
  Worker picks up session      |
          |                    |
          v                    |
  Filter transcript            |
  Strip secrets (regex)        |
  Check dedup hash             |
          |                    |
          v                    |
  Haiku extraction via claude CLI
          |
          v
  Parse fragments + concepts
          |
          v
  Write to vault / markdown dir   -> .delivered record
          |                          (queue file removed)
          failed write
          |
          v
       Outbox (retry later)
```

Hooks stay dumb. All real work happens in the worker, in the background, after your session ends.

## What it captures

glean is not summarizing your session. It is hunting for **story fragments** - specific moments worth remembering. Each fragment has five fields:

- **Moment** - What actually happened. Concrete, with real values and file names.
- **Surprise** - The expectation that got violated in one sentence.
- **Tension** - The unresolved question this raises. A real question, not rhetorical.
- **Verbatim** - A quotable line from the session, if there was one.
- **Thread** - A hook line for the post, essay, or followup this could become.

Most sessions produce zero fragments. That is correct. The prompt is tuned to say `NO_IDEAS` aggressively rather than force extraction.

Example fragment (truncated):

```markdown
# The one knob that fixed everything

## What happened
Spent two hours chasing a stale bundle in the Remotion render. Tried clearing
node_modules, rebuilding the bundle, restarting Chrome. The fix was a single
cache-busting flag we'd disabled six months ago for "performance"...

## The surprise
The performance optimization from six months ago was actively making every
render silently wrong.

## The tension
How many of our other "performance" flags are active footguns?

## Thread
The cache flag we disabled for speed was silently breaking every render.
```

## What leaves your machine

Be explicit: glean calls the Anthropic API (via the `claude` CLI using your existing OAuth). Here is exactly what is sent:

1. **Filtered transcript text.** Only `human` and `assistant` text messages. Tool calls, tool results, system prompts, and raw file blobs are stripped.
2. **Secrets stripped first** via regex, before the API call. Patterns redacted:
   - AWS keys (`AKIA[0-9A-Z]{16}`, `aws_secret_access_key`)
   - GitHub tokens (`ghp_`, `gho_`, `ghu_`, `ghs_`, `ghr_`)
   - OpenAI / Anthropic keys (`sk-...`, `sk-ant-...`)
   - Google API keys (`AIza[0-9A-Za-z\-_]{35}`)
   - Slack tokens (`xox[baprs]-...`)
   - Stripe keys (`sk_live_`, `rk_live_`)
   - Private keys (`-----BEGIN (RSA|EC|OPENSSH|PGP) PRIVATE KEY-----`)
   - Bearer tokens, `Authorization:` headers
   - Common `.env`-style assignments (`[A-Z_]+_(KEY|TOKEN|SECRET|PASSWORD)=...`)
3. **Nothing else.** No file contents outside the transcript. No tool invocation results. No environment variables. No git state.

The output (fragments) lives on your disk. No telemetry. No phone-home. Code is stdlib-only Python and auditable.

## Installation

```bash
# From inside Claude Code
claude plugin install glean

# Then run the post-install setup
/install
```

The `/install` step will:

1. Verify Python 3.9+ and the `claude` CLI are available
2. Ask whether you want **Obsidian** output (one file per fragment, wikilinks) or **flat markdown** (directory of .md files)
3. Ask for the vault path + folder, or the output directory
4. Run a canary extraction against your most recent Claude Code session so you can see output immediately

## Configuration

`/install` writes `${CLAUDE_PLUGIN_DATA}/config.json`. Edit it directly any time:

```json
{
  "schema_version": 1,
  "output_mode": "obsidian",
  "vault_path": "/Users/you/Obsidian/Vault",
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

Knobs worth knowing:

- `max_fragments_per_session` - cap per session (default 3, tune down to 1 for a stricter signal)
- `min_text_bytes` - sessions shorter than this are skipped entirely
- `prompt_path` - set to your own prompt file to override `prompts/default.md`
- `notification_enabled` - macOS banner when a fragment lands

## Usage

After install, glean runs automatically when Claude Code sessions end. Three commands let you inspect and curate:

| Command | What it does |
|---|---|
| `/glean-status` | Queue depth, recent deliveries, outbox, last worker run |
| `/glean-extract` | Trigger the worker manually (useful if a session didn't fire SessionEnd cleanly) |
| `/glean-review` | Walk inbox fragments one at a time: **k**eep, **s**tar, **d**rop. Writes signal to `feedback.jsonl` for future prompt tuning. |

## Obsidian integration

glean writes frontmatter that plays well with Dataview. Drop these queries into any note to build your review surface.

### 1. Inbox (all unreviewed fragments, newest first)

````markdown
```dataview
TABLE captured, project, tags
FROM "Fragments"
WHERE type = "story-fragment" AND status = "inbox"
SORT captured DESC
```
````

### 2. By project

````markdown
```dataview
TABLE WITHOUT ID file.link as Fragment, captured, status
FROM "Fragments"
WHERE type = "story-fragment"
GROUP BY project
SORT captured DESC
```
````

### 3. Starred fragments (the keepers)

````markdown
```dataview
TABLE captured, project
FROM "Fragments"
WHERE type = "story-fragment" AND status = "starred"
SORT captured DESC
```
````

Fragments also emit 1-3 concept wikilinks (`[[cache-invalidation]]`, `[[bundle-staleness]]`) into their Related section. Over time these form a concept graph in your vault without any manual tagging.

## How extraction is tuned

The extraction prompt lives at `prompts/default.md` inside the plugin. It is the product - it encodes the editorial judgment that turns a transcript into fragments worth keeping.

To customize:

1. Copy `prompts/default.md` somewhere in your control
2. Set `prompt_path` in `config.json` to the copy
3. Edit freely. Bump `prompt_version` when you make meaningful changes (triggers re-extraction for future sessions).

Auto-tuning based on `/glean-review` signal is planned for **v1.2**: the `feedback.jsonl` log records which fragments you starred, kept, or dropped, which the tuner will use to refine the prompt automatically.

## FAQ

**What does extraction cost per session?**
Haiku. A typical filtered transcript is 5-40KB. A session extraction is single-digit cents at most, often fractions of a cent. If you are cost-sensitive, raise `min_text_bytes` to skip more sessions.

**What if I change the prompt - do old sessions get re-extracted?**
No, unless you also bump `prompt_version` in your config. The dedup key includes `prompt_version`, so bumping it invalidates the hash and lets the worker re-process.

**How does dedup work?**
SHA-256 of `session_id + prompt_version + filtered_transcript_hash`. Stored append-only in `hashes.jsonl`. A session is skipped if its key is already present, which also means glean is safe to re-run against the same transcript.

**Can I run this without Obsidian?**
Yes. Pick `markdown` mode during `/install`. Fragments land as flat `.md` files in the directory you choose. The frontmatter and body format are identical - you just lose wikilink resolution.

**What about Windows?**
Not tested. The worker is stdlib Python, so it should mostly work, but the hooks use bash and `flock`. Patches welcome.

**Does this slow down my Claude Code sessions?**
No. The SessionEnd hook writes a queue file and forks the worker in the background. It completes in under 500ms and is marked `async: true`.

## Contributing

Issues and PRs welcome. Keep scope tight:

- Worker stays stdlib-only (no pip dependencies)
- Hooks stay dumb (queue + fork, no LLM calls)
- New writers go under `scripts/glean/writers/` implementing the `Writer` protocol

See `CONTRACTS.md` for interface definitions between components.

## License

MIT. See `LICENSE`.
