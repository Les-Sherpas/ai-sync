"""Service for resolving 1Password refs via `op inject`."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path

from ai_sync.adapters.process_runner import ProcessRunner
from ai_sync.services.one_password_auth_service import OnePasswordAuthService

ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class OnePasswordCliService:
    """Resolve refs via `op inject` CLI."""

    def __init__(
        self, *, process_runner: ProcessRunner, auth_resolver: OnePasswordAuthService
    ) -> None:
        self._process_runner = process_runner
        self._auth_resolver = auth_resolver

    def inject(
        self,
        content: str,
        *,
        config_root: Path | None,
        environ: Mapping[str, str],
    ) -> dict[str, str]:
        env = os.environ.copy()
        env.update(self._auth_resolver.resolve_cli_env(config_root, environ))
        result = self._process_runner.run(
            ["op", "inject"],
            input=content,
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        stdout = result.stdout if isinstance(result.stdout, str) else ""
        return self.parse_injected_env(stdout)

    @staticmethod
    def parse_injected_env(content: str) -> dict[str, str]:
        env: dict[str, str] = {}
        for idx, raw in enumerate(content.splitlines(), start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                raise RuntimeError(f"Invalid env line {idx}: expected NAME=VALUE format")
            name, value = line.split("=", 1)
            key = name.strip()
            if not ENV_NAME_RE.match(key):
                raise RuntimeError(f"Invalid env variable name at line {idx}: {key!r}")
            env[key] = value
        return env
