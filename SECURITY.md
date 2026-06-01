# Security Policy

## Supported versions

Security fixes are handled on the default branch until the project publishes versioned releases.

## Reporting a vulnerability

Please do not open a public issue for a vulnerability. Email `vedant.g26@gmail.com` with:

- A description of the issue.
- Steps to reproduce it.
- The affected file or workflow.
- Any logs or transcripts needed to understand the problem, with secrets removed.

I will acknowledge credible reports within 72 hours and coordinate a fix or mitigation.

## Security model

glean runs locally as a Claude Code plugin. Its core privacy boundary is:

- Tool calls, tool results, thinking blocks, images, system prompts, and raw file blobs are excluded from the filtered transcript.
- Obvious secrets are redacted before the filtered transcript is sent to the `claude` CLI.
- Fragments, queue state, hashes, feedback, and logs are written locally under `${CLAUDE_PLUGIN_DATA}` or the configured output directory.
- There is no telemetry or phone-home path in the plugin code.

This does not make transcript extraction risk-free. Users should treat generated fragments as local notes and review them before sharing.

