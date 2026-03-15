"""Abstract client adapter and shared helpers."""

from __future__ import annotations

import os
import stat
from abc import ABC, abstractmethod
from pathlib import Path

import tomli_w

from ai_sync.data_classes.write_spec import WriteSpec


class Client(ABC):
    def __init__(self, project_root: Path) -> None:
        self._project_root = project_root

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    def config_dir(self) -> Path:
        return self._project_root / f".{self.name}"

    def get_agents_dir(self) -> Path:
        return self.config_dir / "agents"

    def get_skills_dir(self) -> Path:
        return self.config_dir / "skills"

    @staticmethod
    def _write_toml_config(data: dict) -> str:
        return tomli_w.dumps(data)

    def _build_mcp_env(self, server: dict, secret_srv: dict) -> dict:
        env_parts: list[dict] = []
        if server.get("env"):
            env_parts.append({k: str(v) if v is not None else "" for k, v in server["env"].items()})
        if secret_srv.get("env"):
            env_parts.append({k: str(v) if v is not None else "" for k, v in secret_srv["env"].items()})
        if not env_parts:
            return {}
        merged: dict = {}
        for e in env_parts:
            merged.update(e)
        return merged

    def _get_secret_for_server(self, server_id: str, secrets: dict) -> dict:
        return secrets.get("servers", {}).get(server_id, {})

    @staticmethod
    def set_restrictive_permissions(path: Path) -> None:
        try:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError as exc:
            print(f"  Warning: Could not set restrictive permissions on {path}: {exc}")

    @abstractmethod
    def build_agent_specs(
        self, alias: str, slug: str, meta: dict, raw_content: str, prompt_src_path: Path
    ) -> list[WriteSpec]: ...

    @abstractmethod
    def build_command_specs(
        self, alias: str, slug: str, meta: dict, raw_content: str, command_name: str
    ) -> list[WriteSpec]: ...

    @abstractmethod
    def build_mcp_specs(self, servers: dict, secrets: dict) -> list[WriteSpec]: ...

    @abstractmethod
    def build_client_config_specs(self, settings: dict) -> list[WriteSpec]: ...

    def build_instructions_specs(self, instructions_content: str) -> list[WriteSpec]:
        return []
