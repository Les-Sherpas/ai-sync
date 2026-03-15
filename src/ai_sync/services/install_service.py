"""Service for the install command."""

from __future__ import annotations

import os
import sys
from typing import Callable, Mapping, TextIO

from ai_sync.services.config_store_service import DEFAULT_SECRET_PROVIDER, ConfigStoreService
from ai_sync.services.display_service import DisplayService


class InstallService:
    """Bootstrap ~/.ai-sync config and store auth settings."""

    def __init__(
        self,
        *,
        config_store_service: ConfigStoreService,
        environ: Mapping[str, str] | None = None,
        stdin: TextIO | None = None,
        prompt_input: Callable[[str], str] = input,
    ) -> None:
        self._config_store_service = config_store_service
        self._environ = os.environ if environ is None else environ
        self._stdin = sys.stdin if stdin is None else stdin
        self._prompt_input = prompt_input

    def run(
        self,
        *,
        display: DisplayService,
        op_account_identifier: str | None,
        force: bool,
    ) -> int:
        root = self._config_store_service.ensure_layout()
        config_path = root / "config.toml"
        if config_path.exists() and not force:
            display.panel(
                f"Config already exists: {config_path}\nUse --force to overwrite.",
                title="Already installed",
                style="error",
            )
            return 1

        resolved_op = op_account_identifier or self._environ.get("OP_ACCOUNT")
        token = self._environ.get("OP_SERVICE_ACCOUNT_TOKEN")

        if not resolved_op and not token:
            if self._stdin.isatty():
                resolved_op = (
                    self._prompt_input(
                        "1Password sign-in address or user ID "
                        "(example: example.1password.com): "
                    ).strip()
                    or None
                )
            if not resolved_op:
                display.panel(
                    "No 1Password account configured.\n"
                    "Provide --op-account-identifier with a sign-in address or user ID "
                    "(example: example.1password.com), set OP_ACCOUNT, "
                    "or set OP_SERVICE_ACCOUNT_TOKEN.",
                    title="Missing account",
                    style="error",
                )
                return 1

        config: dict[str, str] = {"secret_provider": DEFAULT_SECRET_PROVIDER}
        if resolved_op:
            config["op_account_identifier"] = resolved_op
        self._config_store_service.write_config(config, root)
        display.print(f"Wrote {config_path}", style="success")
        return 0
