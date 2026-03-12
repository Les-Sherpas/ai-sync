"""Structured env.yaml configuration for source repos."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, model_validator

from .op_inject import parse_injected_env


class EnvVarConfig(BaseModel):
    """Configuration for a single environment variable declared in env.yaml."""

    value: str | None = None
    scope: Literal["global", "local"] = "global"
    description: str | None = None

    @model_validator(mode="after")
    def _check_value_scope_consistency(self) -> EnvVarConfig:
        if self.scope == "global" and self.value is None:
            raise ValueError("Global-scoped env vars must have a value")
        if self.scope == "local" and self.value is not None:
            raise ValueError("Local-scoped env vars must not have a value")
        return self


@dataclass(frozen=True)
class RuntimeEnv:
    """Resolved environment for a project.

    - ``env``: all resolved key-value pairs (globals + filled locals).
    - ``local_vars``: every declared local var with its metadata.
    - ``unfilled_local_vars``: local var names not yet set in .env.ai-sync.
    """

    env: dict[str, str] = field(default_factory=dict)
    local_vars: dict[str, EnvVarConfig] = field(default_factory=dict)
    unfilled_local_vars: set[str] = field(default_factory=set)


def load_env_config(path: Path) -> dict[str, EnvVarConfig]:
    """Load and validate an env.yaml file from a source repo."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise RuntimeError(f"Failed to parse {path}: {exc}") from exc

    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise RuntimeError(f"Invalid env.yaml at {path}: expected a mapping")

    result: dict[str, EnvVarConfig] = {}
    for name, entry in raw.items():
        if not isinstance(name, str):
            raise RuntimeError(f"Invalid env.yaml key at {path}: {name!r}")
        if isinstance(entry, str):
            entry = {"value": entry}
        elif entry is None:
            raise RuntimeError(
                f"Invalid env.yaml entry for {name!r} at {path}: "
                "use 'value: <string>' for globals or 'scope: local' for local vars"
            )
        try:
            result[name] = EnvVarConfig.model_validate(entry)
        except Exception as exc:
            raise RuntimeError(f"Invalid env.yaml entry for {name!r} at {path}: {exc}") from exc
    return result


def read_existing_env_file(project_root: Path) -> dict[str, str]:
    """Read an existing .env.ai-sync file to recover previously filled values."""
    env_path = project_root / ".env.ai-sync"
    if not env_path.exists():
        return {}
    content = env_path.read_text(encoding="utf-8")
    if not content.strip():
        return {}
    return parse_injected_env(content)
