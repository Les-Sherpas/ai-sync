#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LABEL="com.loup.ai-tools.sync"
PLIST_PATH="${HOME}/Library/LaunchAgents/${LABEL}.plist"
VENV_DIR="${ROOT}/scripts/.venv"
PYTHON="$(command -v python3 || true)"

FORCE=0
OP_ACCOUNT_ARG=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --force) FORCE=1; shift ;;
    --op-account)
      if [[ -n "${2:-}" && "$2" != --* ]]; then
        OP_ACCOUNT_ARG="$2"; shift 2
      else
        echo "Error: --op-account requires a value (e.g. --op-account Employee)" >&2
        exit 1
      fi
      ;;
    -h|--help)
      echo "Usage: $0 [--op-account NAME] [--force]"
      echo "  --op-account N  Install export OP_ACCOUNT=N in shell rc (optional if OP_ACCOUNT already set)"
      echo "  --force         Discard and reinstall from scratch"
      exit 0
      ;;
    *) shift ;;
  esac
done
OP_ACCOUNT="${OP_ACCOUNT_ARG:-$OP_ACCOUNT}"
if [[ -z "${OP_ACCOUNT:-}" ]]; then
  echo "Error: --op-account NAME or OP_ACCOUNT env required. Example: $0 --op-account Employee" >&2
  exit 1
fi

# Stop, kill, and remove previous auto-sync before install
echo "Stopping previous auto-sync..."
launchctl bootout "gui/$(id -u)" "$PLIST_PATH" 2>/dev/null || true
pkill -f "watch_sync.py" 2>/dev/null || true
pkill -f "watchexec.*ai-tools" 2>/dev/null || true
pkill -f "scripts/auto-sync/run_sync_once" 2>/dev/null || true
[ -f "$PLIST_PATH" ] && /bin/rm -f "$PLIST_PATH"
if [ "$FORCE" -eq 1 ]; then
  echo "  Force: removing venv..."
  [ -d "$VENV_DIR" ] && /bin/rm -rf "$VENV_DIR"
fi
echo "  Previous auto-sync stopped and removed."

if [ -z "$PYTHON" ]; then
  cat <<'MSG' >&2
Python 3 not found. Install it, then re-run this script.
Recommended: brew install python
MSG
  exit 1
fi

# 1Password: sync uses the Python SDK (onepassword-sdk). Auth via OP_SERVICE_ACCOUNT_TOKEN
# or OP_ACCOUNT with desktop app. No op CLI required.

if [ ! -x "${VENV_DIR}/bin/python3" ]; then
  echo "Creating venv at ${VENV_DIR}..."
  "$PYTHON" -m venv "$VENV_DIR"
  echo "Installing dependencies..."
fi
"$VENV_DIR/bin/pip" install -e "${ROOT}/scripts/client-sync[dev]"

/bin/chmod +x "${ROOT}/scripts/auto-sync/watch_sync.py"
/bin/chmod +x "${ROOT}/scripts/auto-sync/run_sync_once.sh"
/bin/chmod +x "${ROOT}/scripts/auto-sync/notify_sync.sh"
[ -f "${ROOT}/scripts/shared/sync_summary.py" ] && /bin/chmod +x "${ROOT}/scripts/shared/sync_summary.py"
[ -f "${ROOT}/scripts/shared/op_account_install.py" ] && /bin/chmod +x "${ROOT}/scripts/shared/op_account_install.py"

VERSION_LOCK="${ROOT}/scripts/.client-versions.json"
if [ ! -f "$VERSION_LOCK" ]; then
  echo "Missing ${VERSION_LOCK}. This repo is version-bound; do not generate it locally." >&2
  echo "Pull the file from the repo, then re-run this installer." >&2
  exit 1
fi

cat <<PLIST > "$PLIST_PATH"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>${LABEL}</string>

    <key>ProgramArguments</key>
    <array>
      <string>/bin/zsh</string>
      <string>-l</string>
      <string>-c</string>
      <string>source ~/.zshrc 2>/dev/null || true; exec "${ROOT}/scripts/.venv/bin/python" "${ROOT}/scripts/auto-sync/watch_sync.py"</string>
    </array>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>WorkingDirectory</key>
    <string>${ROOT}</string>

    <key>StandardOutPath</key>
    <string>/tmp/ai-tools-sync.out.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/ai-tools-sync.err.log</string>
  </dict>
</plist>
PLIST

/usr/bin/plutil -lint "$PLIST_PATH" >/dev/null

launchctl bootout "gui/$(id -u)" "$PLIST_PATH" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_PATH"

launchctl list | /usr/bin/grep "$LABEL" || true

"$PYTHON" "${ROOT}/scripts/shared/op_account_install.py" "$OP_ACCOUNT"

printf "Installed %s\n" "$PLIST_PATH"
