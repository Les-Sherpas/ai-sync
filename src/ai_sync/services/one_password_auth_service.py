"""Service for resolving 1Password authentication inputs."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from onepassword.defaults import DesktopAuth

from ai_sync.services.config_store_service import ConfigStoreService


class OnePasswordAuthService:
    """Resolve CLI and SDK authentication inputs."""

    def __init__(self, *, config_store_service: ConfigStoreService) -> None:
        self._config_store_service = config_store_service

    def resolve_cli_env(
        self, config_root: Path | None, environ: Mapping[str, str]
    ) -> dict[str, str]:
        token = environ.get("OP_SERVICE_ACCOUNT_TOKEN")
        if token:
            return {"OP_SERVICE_ACCOUNT_TOKEN": token}

        account = environ.get("OP_ACCOUNT") or (
            self._config_store_service.resolve_op_account_identifier(config_root)
        )
        if account:
            return {"OP_ACCOUNT": account}

        raise RuntimeError(
            "1Password auth required. Run `ai-sync install` or set OP_SERVICE_ACCOUNT_TOKEN/OP_ACCOUNT."
        )

    def resolve_auth(
        self, config_root: Path | None, environ: Mapping[str, str]
    ) -> str | DesktopAuth:
        token = environ.get("OP_SERVICE_ACCOUNT_TOKEN")
        account = environ.get("OP_ACCOUNT") or (
            self._config_store_service.resolve_op_account_identifier(config_root)
        )
        if token:
            return token
        if account:
            return DesktopAuth(account_name=account)
        raise RuntimeError(
            "1Password auth required. Run `ai-sync install` or set OP_SERVICE_ACCOUNT_TOKEN/OP_ACCOUNT."
        )
