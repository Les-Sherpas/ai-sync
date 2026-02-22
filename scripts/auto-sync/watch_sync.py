#!/usr/bin/env python3
"""Long-running file watcher that runs sync in-process to reuse 1Password DesktopAuth session."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from watchfiles import watch

REPO_ROOT = Path(__file__).resolve().parents[2]
NOTIFY_SCRIPT = REPO_ROOT / "scripts" / "auto-sync" / "notify_sync.sh"
SUMMARY_SCRIPT = REPO_ROOT / "scripts" / "shared" / "sync_summary.py"
WATCH_PATHS = [REPO_ROOT / "config"]
OP_ACCOUNT_PATTERN = re.compile(r'^\s*export\s+OP_ACCOUNT=["\']([^"\']*)["\']')


def _load_op_account_from_rc() -> str | None:
    """Load OP_ACCOUNT from shell rc files if not set in env."""
    for rc_name in (".zshrc", ".bashrc"):
        rc = Path.home() / rc_name
        if not rc.exists():
            continue
        try:
            content = rc.read_text(encoding="utf-8", errors="ignore")
            for line in content.splitlines():
                m = OP_ACCOUNT_PATTERN.match(line)
                if m:
                    return m.group(1)
        except OSError:
            pass
    return None


def _ensure_op_account() -> None:
    """Ensure OP_ACCOUNT or OP_SERVICE_ACCOUNT_TOKEN is set."""
    if os.environ.get("OP_SERVICE_ACCOUNT_TOKEN"):
        return
    if os.environ.get("OP_ACCOUNT"):
        return
    account = _load_op_account_from_rc()
    if account:
        os.environ["OP_ACCOUNT"] = account
        return
    print(
        "OP_ACCOUNT or OP_SERVICE_ACCOUNT_TOKEN required. Run install_auto_sync.sh --op-account NAME first.",
        file=sys.stderr,
    )
    sys.exit(1)


def _notify(msg: str) -> None:
    """Send macOS notification."""
    if NOTIFY_SCRIPT.exists() and NOTIFY_SCRIPT.is_file():
        try:
            subprocess.run(
                [str(NOTIFY_SCRIPT), msg],
                capture_output=True,
                timeout=5,
                check=False,
            )
        except (subprocess.TimeoutExpired, OSError):
            pass


def _get_summary() -> str:
    """Get sync summary from sync_summary.py."""
    if not SUMMARY_SCRIPT.exists():
        return "agents=? skills=? servers=?"
    try:
        result = subprocess.run(
            [sys.executable, str(SUMMARY_SCRIPT)],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(REPO_ROOT),
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        pass
    return "agents=? skills=? servers=?"


def _extract_error(output: str) -> str:
    """Extract error message from sync output (same heuristics as run_sync_once.sh)."""
    lines = output.splitlines()
    for line in reversed(lines):
        if "Sync failed: " in line:
            idx = line.find("Sync failed: ") + len("Sync failed: ")
            return line[idx:idx + 200]
    for line in reversed(lines):
        if re.search(r"Version mismatch:|Error:|ERROR:|Failed|Missing ", line):
            return line[:200]
    non_empty = [ln for ln in lines if ln.strip()]
    if non_empty:
        return non_empty[-1][:200]
    trimmed = output.replace("\n", " ").strip()
    return trimmed[-200:] if len(trimmed) > 200 else trimmed or "(no output captured)"


def do_sync() -> tuple[int, str]:
    """Run sync in-process. Returns (exit_code, raw_output). On failure, output holds the error message."""
    from sync_ai_configs.display import PlainDisplay
    from sync_ai_configs.sync_runner import run_sync

    display = PlainDisplay()
    try:
        run_sync(
            repo_root=REPO_ROOT,
            force=False,
            clear=False,
            backup=False,
            no_interactive=True,
            plain=True,
            overrides=[],
            display=display,
        )
        return (0, "")
    except Exception as exc:
        return (1, str(exc))


def main() -> int:
    _ensure_op_account()

    def on_change() -> None:
        exit_code, output = do_sync()
        if output:
            print(output, flush=True)
        summary = _get_summary()
        if exit_code == 0:
            _notify(f"Sync finished ({summary})")
        else:
            err = _extract_error(output)
            _notify(f"Sync failed: {err}")

    paths = [p for p in WATCH_PATHS if p.exists()]
    if not paths:
        print("No watch paths exist. Check config directory.", file=sys.stderr)
        return 1

    try:
        for changes in watch(*paths, debounce=1600):
            if changes:
                on_change()
    except KeyboardInterrupt:
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
