#!/usr/bin/env bash
# breadcrumb.sh - Stop hook
#
# Stop fires on every assistant turn. We just drop a breadcrumb so if the
# session ends abnormally (crash, force quit) we can still find it on
# SessionStart sweep. Does NOT spawn worker on every turn.

set -euo pipefail

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

if [[ -z "${SESSION_ID}" || -z "${TRANSCRIPT_PATH}" || ! -f "${TRANSCRIPT_PATH}" ]]; then
  exit 0
fi

if [[ -z "${CLAUDE_PLUGIN_DATA:-}" ]]; then
  CLAUDE_PLUGIN_DATA="${HOME}/.claude/plugins/data/glean"
fi

QUEUE_DIR="${CLAUDE_PLUGIN_DATA}/queue"
mkdir -p "${QUEUE_DIR}"

# Overwrite breadcrumb (newest wins, no worker spawn)
PENDING_FILE="${QUEUE_DIR}/${SESSION_ID}.pending"
TEMP_FILE="${PENDING_FILE}.tmp.$$"

TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)

cat > "${TEMP_FILE}" <<EOF
{
  "session_id": "${SESSION_ID}",
  "transcript_path": "${TRANSCRIPT_PATH}",
  "enqueued_at": "${TIMESTAMP}",
  "hook_event": "Stop",
  "attempts": 0
}
EOF

mv -f "${TEMP_FILE}" "${PENDING_FILE}"

exit 0
