"""Resolved runtime environment dataclass."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai_sync.models.env_var_config import EnvVarConfig


@dataclass(frozen=True)
class RuntimeEnv:
    """Resolved environment for a project."""

    env: dict[str, str] = field(default_factory=dict)
    local_vars: dict[str, "EnvVarConfig"] = field(default_factory=dict)
    unfilled_local_vars: set[str] = field(default_factory=set)
