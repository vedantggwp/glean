#!/usr/bin/env bash
# enqueue.sh - SessionEnd / StopFailure hook
#
# Reads hook JSON from stdin, writes a queue item, spawns worker in background.
# Sub-100ms. No LLM calls. Never blocks the session.

set -euo pipefail

# ---------------------------------------------------------------------------
# Read hook input
# ---------------------------------------------------------------------------

INPUT=$(cat)

SESSION_ID=$(echo "${INPUT}" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    print(data.get('session_id', ''))
except Exception:
    print('')
" 2>/dev/null || echo "")

TRANSCRIPT_PATH=$(echo "${INPUT}" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    print(data.get('transcript_path', ''))
except Exception:
    print('')
" 2>/dev/null || echo "")

HOOK_EVENT=$(echo "${INPUT}" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    print(data.get('hook_event_name', 'unknown'))
except Exception:
    print('unknown')
" 2>/dev/null || echo "unknown")

# Exit silently if missing data
if [[ -z "${SESSION_ID}" || -z "${TRANSCRIPT_PATH}" ]]; then
  exit 0
fi

if [[ ! -f "${TRANSCRIPT_PATH}" ]]; then
  exit 0
fi

# ---------------------------------------------------------------------------
# Resolve CLAUDE_PLUGIN_DATA
# ---------------------------------------------------------------------------

if [[ -z "${CLAUDE_PLUGIN_DATA:-}" ]]; then
  # Fallback: derive from plugin root
  CLAUDE_PLUGIN_DATA="${HOME}/.claude/plugins/data/glean"
fi

QUEUE_DIR="${CLAUDE_PLUGIN_DATA}/queue"
mkdir -p "${QUEUE_DIR}"

# ---------------------------------------------------------------------------
# Write queue item (atomic via temp + rename)
# ---------------------------------------------------------------------------

PENDING_FILE="${QUEUE_DIR}/${SESSION_ID}.pending"
TEMP_FILE="${PENDING_FILE}.tmp.$$"

TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)

cat > "${TEMP_FILE}" <<EOF
{
  "session_id": "${SESSION_ID}",
  "transcript_path": "${TRANSCRIPT_PATH}",
  "enqueued_at": "${TIMESTAMP}",
  "hook_event": "${HOOK_EVENT}",
  "attempts": 0
}
EOF

mv -f "${TEMP_FILE}" "${PENDING_FILE}"

# ---------------------------------------------------------------------------
# Spawn worker in background (fire and forget)
# ---------------------------------------------------------------------------

if [[ -n "${CLAUDE_PLUGIN_ROOT:-}" ]]; then
  LOG_FILE="${CLAUDE_PLUGIN_DATA}/worker.log"
  mkdir -p "$(dirname "${LOG_FILE}")"

  nohup env \
    CLAUDE_PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT}" \
    CLAUDE_PLUGIN_DATA="${CLAUDE_PLUGIN_DATA}" \
    PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" \
    python3 -m glean.worker --drain \
    >> "${LOG_FILE}" 2>&1 &

  disown
fi

exit 0
