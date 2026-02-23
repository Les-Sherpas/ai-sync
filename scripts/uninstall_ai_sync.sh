#!/usr/bin/env bash
set -euo pipefail

DRY_RUN=1
NO_BACKUP=0
REMOVE_OP_ACCOUNT=0

usage() {
  cat <<'USAGE'
Usage: uninstall_ai_sync.sh [--yes] [--no-backup] [--remove-op-account]

Removes ai-sync artifacts and client settings from this user account.
Defaults to dry-run (no changes).

Options:
  --yes               Execute removals (not a dry-run)
  --no-backup         Do not write backups when editing shell profiles
  --remove-op-account Remove export OP_ACCOUNT lines from shell profiles
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes)
      DRY_RUN=0
      shift
      ;;
    --no-backup)
      NO_BACKUP=1
      shift
      ;;
    --remove-op-account)
      REMOVE_OP_ACCOUNT=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

run() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "DRY RUN: $*"
    return 0
  fi
  "$@"
}

maybe_backup() {
  local src="$1"
  if [[ "$NO_BACKUP" -eq 1 ]]; then
    return 0
  fi
  mkdir -p "$BACKUP_DIR"
  cp "$src" "$BACKUP_DIR/$(basename "$src")"
}

BACKUP_DIR="/tmp/ai-sync-cleanup-$(date +%Y%m%d-%H%M%S)"

HOME_DIR="${HOME:?HOME not set}"

BASE_DIRS=(
  "$HOME_DIR/.ai-sync"
  "$HOME_DIR/.codex"
  "$HOME_DIR/.cursor"
  "$HOME_DIR/.gemini"
)

EXTRA_DIRS=()

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
GIT_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -n "$GIT_ROOT" ]]; then
  while IFS= read -r dir; do
    [[ -n "$dir" ]] || continue
    EXTRA_DIRS+=("$HOME_DIR/$dir")
  done < <(
    git -C "$GIT_ROOT" grep -oE 'Path\.home\(\) / "\.[^"]+"' -- src 2>/dev/null \
      | sed -E 's/.*"(\.[^"]+)"/\1/' \
      | sort -u
  )
fi

TARGET_DIRS=("${BASE_DIRS[@]}" "${EXTRA_DIRS[@]}")

echo "=== ai-sync cleanup ==="
if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "Mode: DRY RUN (no changes)"
else
  echo "Mode: APPLY (changes will be made)"
fi
echo ""

echo "Targets (directories):"
for d in "${TARGET_DIRS[@]}"; do
  echo "  - $d"
done
echo ""

remove_path() {
  local path="$1"
  if [[ -e "$path" ]]; then
    run rm -rf "$path"
  fi
}

echo "Removing directories..."
for d in "${TARGET_DIRS[@]}"; do
  remove_path "$d"
done
echo ""

echo "Removing specific known files (legacy/sidecar)..."
remove_path "$HOME_DIR/.codex/mcp.env"
remove_path "$HOME_DIR/.codex/.sync_managed_mcp.json"
remove_path "$HOME_DIR/.cursor/.sync_managed_mcp.json"
remove_path "$HOME_DIR/.gemini/.sync_managed_mcp.json"
remove_path "$HOME_DIR/.cursor/rules/mcp-instructions.mdc"
remove_path "/tmp/ai-tools-sync.out.log"
remove_path "/tmp/ai-tools-sync.err.log"
remove_path "/tmp/ai-sync-sync.out.log"
remove_path "/tmp/ai-sync-sync.err.log"
echo ""

echo "Checking LaunchAgents..."
LA_DIR="$HOME_DIR/Library/LaunchAgents"
LA_MATCHES=()
if [[ -d "$LA_DIR" ]]; then
  while IFS= read -r -d '' plist; do
    if [[ "$(basename "$plist")" =~ ai-sync|ai_sync|sync-ai|ai-tools|ai_tools ]]; then
      LA_MATCHES+=("$plist")
      continue
    fi
    if /usr/bin/grep -qiE 'ai-sync|ai_sync|sync-ai|sync_ai|ai-tools|ai_tools' "$plist"; then
      LA_MATCHES+=("$plist")
    fi
  done < <(find "$LA_DIR" -maxdepth 1 -name "*.plist" -print0)
fi

if [[ ${#LA_MATCHES[@]} -gt 0 ]]; then
  for plist in "${LA_MATCHES[@]}"; do
    if command -v launchctl >/dev/null; then
      run launchctl bootout "gui/$(id -u)" "$plist" || true
    fi
    remove_path "$plist"
  done
else
  echo "  No user LaunchAgents matching ai-sync found."
fi
echo ""

echo "Checking crontab..."
if command -v crontab >/dev/null; then
  current_cron="$(crontab -l 2>/dev/null || true)"
  if echo "$current_cron" | /usr/bin/grep -qiE 'ai-sync|ai_sync|sync-ai|sync_ai|ai-tools|ai_tools'; then
    if [[ "$DRY_RUN" -eq 1 ]]; then
      echo "  DRY RUN: would remove ai-sync entries from crontab"
    else
      echo "$current_cron" | /usr/bin/grep -viE 'ai-sync|ai_sync|sync-ai|sync_ai|ai-tools|ai_tools' | crontab -
      echo "  Updated crontab (ai-sync entries removed)."
    fi
  else
    echo "  No ai-sync entries in crontab."
  fi
else
  echo "  crontab not found."
fi
echo ""

echo "Cleaning shell profiles..."
PROFILE_FILES=(
  "$HOME_DIR/.zshrc"
  "$HOME_DIR/.zprofile"
  "$HOME_DIR/.bashrc"
  "$HOME_DIR/.bash_profile"
  "$HOME_DIR/.profile"
  "$HOME_DIR/.config/fish/config.fish"
)
PROFILE_PATTERN='ai-sync|ai_sync|sync-ai|sync_ai|ai-tools|ai_tools|codex/mcp\.env|\.codex/mcp\.env|mcp\.env'
OP_ACCOUNT_PATTERN='^\s*export\s+OP_ACCOUNT='

for f in "${PROFILE_FILES[@]}"; do
  if [[ -f "$f" ]]; then
    if /usr/bin/grep -qE "$PROFILE_PATTERN" "$f" || ([[ "$REMOVE_OP_ACCOUNT" -eq 1 ]] && /usr/bin/grep -qE "$OP_ACCOUNT_PATTERN" "$f"); then
      if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "  DRY RUN: would remove ai-sync lines from $f"
      else
        maybe_backup "$f"
        cleaned="$(/usr/bin/grep -vE "$PROFILE_PATTERN" "$f")"
        if [[ "$REMOVE_OP_ACCOUNT" -eq 1 ]]; then
          cleaned="$(echo "$cleaned" | /usr/bin/grep -vE "$OP_ACCOUNT_PATTERN")"
        fi
        printf "%s\n" "$cleaned" > "${f}.tmp.ai-sync-clean"
        mv "${f}.tmp.ai-sync-clean" "$f"
        echo "  Updated $f"
      fi
    fi
  fi
done

echo ""
echo "Checking user-level binaries..."
BIN_DIRS=("$HOME_DIR/.local/bin" "$HOME_DIR/bin" "/usr/local/bin" "/opt/homebrew/bin")
BIN_NAMES=("ai-sync" "sync-ai-configs" "ai_tools_sync" "ai-tools-sync")
for dir in "${BIN_DIRS[@]}"; do
  for name in "${BIN_NAMES[@]}"; do
    remove_path "$dir/$name"
  done
done

echo ""
echo "Checking pipx installs..."
if command -v pipx >/dev/null; then
  pipx_list="$(pipx list 2>/dev/null || true)"
  if echo "$pipx_list" | /usr/bin/grep -qiE 'ai-sync|sync-ai-configs'; then
    if [[ "$DRY_RUN" -eq 1 ]]; then
      echo "  DRY RUN: would uninstall pipx packages ai-sync and sync-ai-configs"
    else
      pipx uninstall ai-sync 2>/dev/null || true
      pipx uninstall sync-ai-configs 2>/dev/null || true
      echo "  pipx packages removed (if installed)."
    fi
  else
    echo "  No pipx packages matching ai-sync found."
  fi
else
  echo "  pipx not found."
fi

if [[ "$DRY_RUN" -eq 0 && "$NO_BACKUP" -eq 0 && -d "$BACKUP_DIR" ]]; then
  echo ""
  echo "Backups saved to: $BACKUP_DIR"
  echo "Delete that folder if you want to remove backups too."
fi

echo ""
echo "Done."
