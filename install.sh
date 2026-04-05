#!/usr/bin/env bash
# glean post-install setup
# Prompts for output mode, writes config, runs canary extraction.

set -euo pipefail

# Claude Code sets these when a plugin runs its install script.
: "${CLAUDE_PLUGIN_ROOT:?CLAUDE_PLUGIN_ROOT not set — run this via the plugin installer}"
: "${CLAUDE_PLUGIN_DATA:?CLAUDE_PLUGIN_DATA not set — run this via the plugin installer}"

CONFIG_FILE="${CLAUDE_PLUGIN_DATA}/config.json"
QUEUE_DIR="${CLAUDE_PLUGIN_DATA}/queue"
SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT}/scripts"

info() { printf '\033[1;34m[INFO]\033[0m  %s\n' "$1"; }
ok()   { printf '\033[1;32m[OK]\033[0m    %s\n' "$1"; }
warn() { printf '\033[1;33m[WARN]\033[0m  %s\n' "$1"; }
fail() { printf '\033[1;31m[FAIL]\033[0m  %s\n' "$1" >&2; exit 1; }

prompt() {
  # prompt "question" "default" -> echoes answer
  local q="$1"
  local default="${2:-}"
  local answer=""
  if [[ -n "$default" ]]; then
    printf '%s [%s]: ' "$q" "$default" >&2
  else
    printf '%s: ' "$q" >&2
  fi
  read -r answer
  if [[ -z "$answer" ]]; then answer="$default"; fi
  printf '%s' "$answer"
}

expand_path() {
  local p="$1"
  p="${p/#\~/$HOME}"
  printf '%s' "$p"
}

# -----------------------------------------------------------------------------
# 1. Prerequisites
# -----------------------------------------------------------------------------

info "Checking prerequisites"

if ! command -v python3 >/dev/null 2>&1; then
  fail "python3 not found. Install Python 3.9+ and re-run."
fi

PY_VERSION="$(python3 -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")' 2>/dev/null || echo "0.0")"
PY_MAJOR="${PY_VERSION%%.*}"
PY_MINOR="${PY_VERSION##*.}"
if [[ "$PY_MAJOR" -lt 3 ]] || { [[ "$PY_MAJOR" -eq 3 ]] && [[ "$PY_MINOR" -lt 9 ]]; }; then
  fail "Python 3.9+ required (found $PY_VERSION)."
fi
ok "Python $PY_VERSION"

if ! command -v claude >/dev/null 2>&1; then
  fail "claude CLI not found. Install Claude Code CLI and re-run.
   See: https://docs.claude.com/claude-code"
fi
ok "claude CLI found at $(command -v claude)"

if [[ ! -t 0 ]]; then
  fail "install.sh must run interactively (stdin is not a TTY)."
fi

# -----------------------------------------------------------------------------
# 2. Prepare data dirs
# -----------------------------------------------------------------------------

mkdir -p "$CLAUDE_PLUGIN_DATA" "$QUEUE_DIR" \
         "${CLAUDE_PLUGIN_DATA}/delivered" \
         "${CLAUDE_PLUGIN_DATA}/outbox"
ok "Data directory: $CLAUDE_PLUGIN_DATA"

# -----------------------------------------------------------------------------
# 3. Config (don't clobber without consent)
# -----------------------------------------------------------------------------

if [[ -f "$CONFIG_FILE" ]]; then
  warn "Existing config found: $CONFIG_FILE"
  OVERWRITE="$(prompt "Overwrite? (y/N)" "N")"
  if [[ "${OVERWRITE,,}" != "y" ]]; then
    info "Keeping existing config"
    KEEP_CONFIG=1
  else
    KEEP_CONFIG=0
  fi
else
  KEEP_CONFIG=0
fi

if [[ "${KEEP_CONFIG:-0}" -eq 0 ]]; then
  printf '\nglean can write fragments in two modes:\n'
  printf '  1) obsidian  - one .md file per fragment inside your vault, with wikilinks\n'
  printf '  2) markdown  - flat .md files in a directory (no vault required)\n\n'

  MODE=""
  while [[ -z "$MODE" ]]; do
    CHOICE="$(prompt "Choose output mode (1=obsidian, 2=markdown)" "1")"
    case "$CHOICE" in
      1|obsidian) MODE="obsidian" ;;
      2|markdown) MODE="markdown" ;;
      *) warn "Pick 1 or 2." ;;
    esac
  done

  VAULT_PATH=""
  VAULT_FOLDER=""
  OUTPUT_DIR=""

  if [[ "$MODE" == "obsidian" ]]; then
    while true; do
      RAW="$(prompt "Obsidian vault path" "")"
      if [[ -z "$RAW" ]]; then
        warn "Vault path is required for obsidian mode."
        continue
      fi
      VAULT_PATH="$(expand_path "$RAW")"
      if [[ ! -d "$VAULT_PATH" ]]; then
        warn "Not a directory: $VAULT_PATH"
        continue
      fi
      if [[ ! -w "$VAULT_PATH" ]]; then
        warn "Not writable: $VAULT_PATH"
        continue
      fi
      break
    done
    VAULT_FOLDER="$(prompt "Folder inside vault for fragments" "Fragments")"
    mkdir -p "${VAULT_PATH}/${VAULT_FOLDER}"
    ok "Fragments will land in: ${VAULT_PATH}/${VAULT_FOLDER}"
  else
    while true; do
      RAW="$(prompt "Output directory" "$HOME/Documents/glean-fragments")"
      OUTPUT_DIR="$(expand_path "$RAW")"
      PARENT="$(dirname "$OUTPUT_DIR")"
      if [[ ! -d "$PARENT" ]]; then
        warn "Parent does not exist: $PARENT"
        continue
      fi
      if [[ ! -w "$PARENT" ]] && [[ ! -w "$OUTPUT_DIR" ]]; then
        warn "Not writable: $PARENT"
        continue
      fi
      break
    done
    mkdir -p "$OUTPUT_DIR"
    ok "Fragments will land in: $OUTPUT_DIR"
  fi

  # Write config.json (stdlib-only python, no jq)
  python3 - "$CONFIG_FILE" "$MODE" "${VAULT_PATH:-}" "${VAULT_FOLDER:-}" "${OUTPUT_DIR:-}" <<'PY'
import json, sys
path, mode, vault, folder, outdir = sys.argv[1:6]
cfg = {
    "schema_version": 1,
    "output_mode": mode,
    "vault_path": vault or None,
    "vault_folder": folder or None,
    "output_dir": outdir or None,
    "extraction_model": "haiku",
    "prompt_path": None,
    "prompt_version": 1,
    "min_text_bytes": 2048,
    "max_text_bytes": 819200,
    "max_fragments_per_session": 3,
    "retry_limit": 3,
    "notification_enabled": True,
}
with open(path, "w") as f:
    json.dump(cfg, f, indent=2)
    f.write("\n")
PY
  ok "Wrote config: $CONFIG_FILE"
fi

# -----------------------------------------------------------------------------
# 4. Canary extraction
# -----------------------------------------------------------------------------

info "Looking for a recent Claude Code session for a canary extraction"

CANARY_TRANSCRIPT="$(python3 - <<'PY'
import os, glob
root = os.path.expanduser("~/.claude/projects")
if not os.path.isdir(root):
    raise SystemExit("")
candidates = []
for p in glob.glob(os.path.join(root, "*", "*.jsonl")):
    try:
        with open(p, "rb") as f:
            lines = sum(1 for _ in f)
        if lines >= 50:
            candidates.append((os.path.getmtime(p), p))
    except OSError:
        continue
candidates.sort(reverse=True)
if candidates:
    print(candidates[0][1])
PY
)"

if [[ -z "$CANARY_TRANSCRIPT" ]]; then
  warn "No Claude Code session with 50+ lines found. Skipping canary."
  warn "Run /glean-extract after your next real session."
else
  info "Canary transcript: $CANARY_TRANSCRIPT"
  SESSION_ID="$(basename "$CANARY_TRANSCRIPT" .jsonl)"
  export PYTHONPATH="${SCRIPTS_DIR}:${PYTHONPATH:-}"

  # Enqueue and drain, synchronously so we can show output path
  cat > "${QUEUE_DIR}/${SESSION_ID}.pending" <<EOF
{
  "session_id": "${SESSION_ID}",
  "transcript_path": "${CANARY_TRANSCRIPT}",
  "enqueued_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "hook_event": "install-canary",
  "attempts": 0
}
EOF

  info "Running extraction (this calls Haiku via the claude CLI, ~10-30s)"
  if python3 -m glean.worker --session "$SESSION_ID" 2>&1 | sed 's/^/  /'; then
    DELIVERED="${CLAUDE_PLUGIN_DATA}/delivered/${SESSION_ID}.json"
    if [[ -f "$DELIVERED" ]]; then
      ok "Canary delivered. Record: $DELIVERED"
    else
      warn "Canary ran but no delivery record. Likely NO_IDEAS (session had no moments)."
    fi
  else
    warn "Canary extraction failed. Check worker.log:"
    warn "  ${CLAUDE_PLUGIN_DATA}/worker.log"
  fi
fi

# -----------------------------------------------------------------------------
# 5. Next steps
# -----------------------------------------------------------------------------

cat <<EOF

$(printf '\033[1;32mInstalled.\033[0m')

Data flow:
  transcripts -> filtered + secrets stripped -> Haiku API -> fragments on disk

Next steps:
  /glean-status   -- queue + recent extractions
  /glean-extract  -- trigger extraction manually
  /glean-review   -- curate inbox fragments (star / drop / keep)

Config:  ${CONFIG_FILE}
Prompt:  ${CLAUDE_PLUGIN_ROOT}/prompts/default.md
Logs:    ${CLAUDE_PLUGIN_DATA}/worker.log

EOF
