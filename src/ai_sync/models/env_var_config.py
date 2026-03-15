"""Environment variable model."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, model_validator


class EnvVarConfig(BaseModel):
    """Configuration for a single environment variable declared in env.yaml."""

    value: str | None = None
    scope: Literal["global", "local"] = "global"
    description: str | None = None

    @model_validator(mode="after")
    def _check_value_scope_consistency(self) -> "EnvVarConfig":
        if self.scope == "global" and self.value is None:
            raise ValueError("Global-scoped env vars must have a value")
        if self.scope == "local" and self.value is not None:
            raise ValueError("Local-scoped env vars must not have a value")
        return self
