"""Service for ai-sync bootstrap config persistence."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import tomli as tomllib
import tomli_w

CONFIG_FILE_NAME = "config.toml"
DEFAULT_SECRET_PROVIDER = "1password"


class ConfigStoreService:
    """Manage ai-sync bootstrap config read/write operations."""

    def __init__(self, *, environ: Mapping[str, str] | None = None) -> None:
        self._environ = os.environ if environ is None else environ

    def get_config_root(self) -> Path:
        return Path.home() / ".ai-sync"

    def get_config_path(self, config_root: Path | None = None) -> Path:
        root = config_root or self.get_config_root()
        return root / CONFIG_FILE_NAME

    def ensure_layout(self, config_root: Path | None = None) -> Path:
        root = config_root or self.get_config_root()
        (root / "repos").mkdir(parents=True, exist_ok=True)
        (root / "cache").mkdir(parents=True, exist_ok=True)
        return root

    def load_config(self, config_root: Path | None = None) -> dict[str, Any]:
        path = self.get_config_path(config_root)
        if not path.exists():
            raise RuntimeError(f"Missing config file: {path}")
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
        except OSError as exc:
            raise RuntimeError(f"Failed to read {path}: {exc}") from exc
        if not isinstance(data, dict):
            raise RuntimeError(f"Invalid config file: {path}")
        return data

    def write_config(self, data: dict[str, Any], config_root: Path | None = None) -> Path:
        root = self.ensure_layout(config_root)
        path = self.get_config_path(root)
        try:
            path.write_text(tomli_w.dumps(data), encoding="utf-8")
        except OSError as exc:
            raise RuntimeError(f"Failed to write {path}: {exc}") from exc
        return path

    def resolve_op_account_identifier(self, config_root: Path | None = None) -> str | None:
        env_account = self._environ.get("OP_ACCOUNT")
        if env_account:
            return env_account
        try:
            config = self.load_config(config_root)
        except RuntimeError:
            return None
        value = config.get("op_account_identifier")
        return str(value) if value else None
