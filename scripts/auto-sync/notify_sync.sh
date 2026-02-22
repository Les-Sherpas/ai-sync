#!/usr/bin/env bash
set -euo pipefail

OSASCRIPT="/usr/bin/osascript"
TITLE="AI Config Sync"
MESSAGE="${1:-Sync finished}"
# Normalize: strip newlines/control chars, then escape for AppleScript
MESSAGE="${MESSAGE//$'\n'/ }"
MESSAGE="${MESSAGE//$'\r'/}"
MESSAGE="${MESSAGE//$'\t'/ }"
MESSAGE_ESC="${MESSAGE//\\/\\\\}"
MESSAGE_ESC="${MESSAGE_ESC//\"/\\\"}"

"${OSASCRIPT}" -e "display notification \"${MESSAGE_ESC}\" with title \"${TITLE}\""
