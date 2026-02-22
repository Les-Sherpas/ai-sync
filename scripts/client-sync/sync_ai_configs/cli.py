"""CLI entrypoint."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from .display import PlainDisplay, RichDisplay
from .precedence import parse_override
from .sync_runner import run_sync


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync AI configs (agents, skills, MCP servers) to Codex, Cursor, Gemini."
    )
    parser.add_argument("--force", action="store_true", help="Force sync and overwrite scripts/.client-versions.json.")
    parser.add_argument("--no-interactive", action="store_true", help="Skip interactive prompts.")
    parser.add_argument("--plain", action="store_true", help="Plain output mode. Implies --no-interactive.")
    parser.add_argument("--override", action="append", default=[], help="Override leaf value: /path/to/key=value")
    parser.add_argument(
        "--override-json",
        action="append",
        default=[],
        help="Override leaf value with JSON: /path/to/key=<json>",
    )
    parser.add_argument(
        "--op-account",
        metavar="NAME",
        help="1Password account name (required for desktop app auth). Installs export in shell rc if missing.",
    )
    return parser.parse_args()


def _install_op_account_export(repo_root: Path, account: str) -> None:
    script = repo_root / "scripts" / "shared" / "op_account_install.py"
    subprocess.run([sys.executable, str(script), account], check=True)


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[3]
    if (
        args.op_account is None
        and "OP_SERVICE_ACCOUNT_TOKEN" not in os.environ
        and "OP_ACCOUNT" not in os.environ
    ):
        print(
            "Sync failed: --op-account NAME, OP_ACCOUNT env, or OP_SERVICE_ACCOUNT_TOKEN required for 1Password auth",
            file=sys.stderr,
        )
        return 1
    if args.op_account is not None:
        _install_op_account_export(repo_root, args.op_account)
        os.environ["OP_ACCOUNT"] = args.op_account
    display = PlainDisplay() if args.plain else RichDisplay()
    overrides: list[tuple[str, object]] = []
    try:
        for item in args.override:
            overrides.append(parse_override(item, parse_json=False))
        for item in args.override_json:
            overrides.append(parse_override(item, parse_json=True))
    except RuntimeError as exc:
        print(f"Sync failed: {exc}", file=sys.stderr)
        return 1

    try:
        return run_sync(
            repo_root=repo_root,
            force=args.force,
            no_interactive=(args.no_interactive or args.plain),
            plain=args.plain,
            overrides=overrides,
            display=display,
        )
    except Exception as exc:
        try:
            display.panel(str(exc), title="Sync failed", style="error")
        except Exception:
            pass
        print(f"Sync failed: {exc}", file=sys.stderr)
        return 1
