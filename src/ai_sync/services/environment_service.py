"""Service for loading, merging, and resolving the runtime environment."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from ai_sync.data_classes.runtime_env import RuntimeEnv
from ai_sync.models import EnvVarConfig
from ai_sync.services.one_password_cli_service import OnePasswordCliService
from ai_sync.services.one_password_secret_service import OnePasswordSecretService

if TYPE_CHECKING:
    from ai_sync.data_classes.resolved_source import ResolvedSource


class EnvironmentService:
    """Merge source env declarations and project-local values into runtime env."""

    def __init__(self, *, op_secret_service: OnePasswordSecretService) -> None:
        self._op_secret_service = op_secret_service

    def load_env_config(self, path: Path) -> dict[str, EnvVarConfig]:
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
                raise RuntimeError(
                    f"Invalid env.yaml entry for {name!r} at {path}: {exc}"
                ) from exc
        return result

    def read_existing_env_file(self, project_root: Path) -> dict[str, str]:
        """Read an existing .env.ai-sync file to recover previously filled values."""
        env_path = project_root / ".env.ai-sync"
        if not env_path.exists():
            return {}
        content = env_path.read_text(encoding="utf-8")
        if not content.strip():
            return {}
        return OnePasswordCliService.parse_injected_env(content)

    def resolve_runtime_env(
        self,
        project_root: Path,
        resolved_sources: dict[str, ResolvedSource],
        config_root: Path | None,
    ) -> RuntimeEnv:
        existing_env = self.read_existing_env_file(project_root)

        env: dict[str, str] = {}
        all_local_vars: dict[str, EnvVarConfig] = {}
        owners: dict[str, str] = {}
        scopes: dict[str, str] = {}

        for alias in sorted(resolved_sources):
            env_yaml = resolved_sources[alias].root / "env.yaml"
            if not env_yaml.exists():
                continue

            config = self.load_env_config(env_yaml)
            global_values: dict[str, str] = {}

            for name, var_cfg in config.items():
                if name in owners:
                    prev_alias = owners[name]
                    prev_scope = scopes[name]
                    if prev_scope != var_cfg.scope:
                        raise RuntimeError(
                            f"Environment variable scope conflict for {name!r}: "
                            f"{prev_alias!r} declares it as {prev_scope!r}, "
                            f"{alias!r} declares it as {var_cfg.scope!r}."
                        )
                    if var_cfg.scope == "global":
                        assert var_cfg.value is not None
                        if env.get(name) != var_cfg.value:
                            raise RuntimeError(
                                f"Environment variable collision for {name!r} "
                                f"across selected sources: {prev_alias!r} and {alias!r}."
                            )
                    continue

                owners[name] = alias
                scopes[name] = var_cfg.scope

                if var_cfg.scope == "local":
                    all_local_vars[name] = var_cfg
                    if name in existing_env and existing_env[name]:
                        env[name] = existing_env[name]
                else:
                    assert var_cfg.value is not None
                    global_values[name] = var_cfg.value

            if global_values:
                resolved = self._op_secret_service.resolve(global_values, config_root)
                env.update(resolved)

        unfilled = {name for name in all_local_vars if name not in env}
        return RuntimeEnv(env=env, local_vars=all_local_vars, unfilled_local_vars=unfilled)
