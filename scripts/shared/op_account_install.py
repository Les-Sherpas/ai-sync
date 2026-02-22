#!/usr/bin/env python3
"""Idempotently install export OP_ACCOUNT in the user's shell rc file."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path


DEFAULT_ACCOUNT = "Employee"
OP_ACCOUNT_PATTERN = re.compile(r"^\s*export\s+OP_ACCOUNT\s*=")


def get_rc_path() -> Path:
    shell = os.environ.get("SHELL", "")
    if "zsh" in shell:
        return Path.home() / ".zshrc"
    if "bash" in shell:
        return Path.home() / ".bashrc"
    return Path.home() / ".zshrc"


def install_op_account_export(account: str = DEFAULT_ACCOUNT) -> bool:
    """Add or update export OP_ACCOUNT=... in rc file. Replaces any existing line in place. Returns True if changed."""
    rc = get_rc_path()
    new_line = f'export OP_ACCOUNT="{account}"'
    if not rc.exists():
        rc.write_text(new_line + "\n", encoding="utf-8")
        return True
    lines = rc.read_text(encoding="utf-8").splitlines()
    changed = False
    seen_op_account = False
    new_lines: list[str] = []
    for ln in lines:
        if OP_ACCOUNT_PATTERN.search(ln):
            if not seen_op_account:
                if ln.strip() != new_line:
                    changed = True
                new_lines.append(new_line)
                seen_op_account = True
            else:
                changed = True
        else:
            new_lines.append(ln)
    if not seen_op_account:
        new_lines.append(new_line)
        changed = True
    if changed:
        rc.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return changed


def main() -> int:
    account = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ACCOUNT
    rc = get_rc_path()
    if install_op_account_export(account):
        print(f"Set export OP_ACCOUNT=\"{account}\" in {rc}")
    else:
        print(f"OP_ACCOUNT already set to \"{account}\" in {rc}, nothing to do")
    return 0


if __name__ == "__main__":
    sys.exit(main())
