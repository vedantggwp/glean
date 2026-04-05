#!/usr/bin/env bash
# sweep.sh - SessionStart hook
#
# Fires when a new session starts. Kicks off worker to drain any orphaned
# .pending files from crashed/force-quit sessions. Async, never blocks startup.

set -euo pipefail

if [[ -z "${CLAUDE_PLUGIN_ROOT:-}" ]]; then
  exit 0
fi

if [[ -z "${CLAUDE_PLUGIN_DATA:-}" ]]; then
  CLAUDE_PLUGIN_DATA="${HOME}/.claude/plugins/data/glean"
fi

QUEUE_DIR="${CLAUDE_PLUGIN_DATA}/queue"

# Nothing to sweep if queue doesn't exist yet
if [[ ! -d "${QUEUE_DIR}" ]]; then
  exit 0
fi

# Check if any .pending files exist
if ! compgen -G "${QUEUE_DIR}/*.pending" > /dev/null; then
  exit 0
fi

LOG_FILE="${CLAUDE_PLUGIN_DATA}/worker.log"
mkdir -p "$(dirname "${LOG_FILE}")"

nohup env \
  CLAUDE_PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT}" \
  CLAUDE_PLUGIN_DATA="${CLAUDE_PLUGIN_DATA}" \
  PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" \
  python3 -m glean.worker --drain \
  >> "${LOG_FILE}" 2>&1 &

disown

exit 0
