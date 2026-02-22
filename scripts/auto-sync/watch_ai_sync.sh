#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUN_ONCE_SCRIPT="${ROOT}/scripts/auto-sync/run_sync_once.sh"
WATCHEXEC="$(command -v watchexec || true)"
ERR_LOG="/tmp/ai-tools-sync.err.log"
MAX_LOG_SIZE=$((5 * 1024 * 1024))
MAX_LOG_FILES=3

rotate_log() {
  local path="$1"
  local max_bytes="$2"
  local max_files="$3"

  if [ ! -f "$path" ]; then
    return 0
  fi

  local size
  size="$(/usr/bin/stat -f%z "$path" 2>/dev/null || echo 0)"
  if [ "$size" -lt "$max_bytes" ]; then
    return 0
  fi

  local i
  i=$((max_files - 1))
  while [ "$i" -ge 1 ]; do
    if [ -f "${path}.${i}" ]; then
      if [ "$i" -eq $((max_files - 1)) ]; then
        /bin/rm -f "${path}.${i}"
      else
        /bin/mv -f "${path}.${i}" "${path}.$((i + 1))"
      fi
    fi
    i=$((i - 1))
  done

  /bin/mv -f "$path" "${path}.1"
}

if [ ! -x "$WATCHEXEC" ]; then
  echo "watchexec not found at ${WATCHEXEC}. Install with: brew install watchexec" >&2
  exit 1
fi

rotate_log "$ERR_LOG" "$MAX_LOG_SIZE" "$MAX_LOG_FILES"

exec "$WATCHEXEC" \
  -w "${ROOT}/config/mcp-servers" \
  -w "${ROOT}/config/prompts" \
  -w "${ROOT}/config/skills" \
  -w "${ROOT}/config/client-settings" \
  --shell none \
  -- "$RUN_ONCE_SCRIPT"
