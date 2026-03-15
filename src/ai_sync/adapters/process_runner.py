"""Subprocess adapter for injectable command execution."""

from __future__ import annotations

import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


class ProcessRunner:
    """Small adapter around ``subprocess.run`` for DI-friendly services."""

    def run(
        self,
        args: Sequence[str],
        *,
        check: bool = False,
        capture_output: bool = False,
        text: bool = False,
        input: str | None = None,
        env: Mapping[str, str] | None = None,
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess[Any]:
        return subprocess.run(
            list(args),
            check=check,
            capture_output=capture_output,
            text=text,
            input=input,
            env=env,
            cwd=str(cwd) if cwd is not None else None,
        )
