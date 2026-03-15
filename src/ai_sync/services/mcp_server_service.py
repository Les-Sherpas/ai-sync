"""Service for MCP server manifest loading and filtering."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Mapping

import yaml
from pydantic import ValidationError

from ai_sync.models import MCPManifest, ServerConfig, split_scoped_ref
from ai_sync.services.display_service import DisplayService

if TYPE_CHECKING:
    from ai_sync.data_classes.resolved_source import ResolvedSource

ENV_REF_RE = re.compile(r"\$(\w+)|\$\{([^}]+)\}")
_ESCAPE_SENTINEL = "\x00"


class McpServerService:
    """Load and filter MCP server data from selected sources."""

    def load_manifest(self, mcp_root: Path, display: DisplayService) -> dict:
        servers_dir = mcp_root / "mcp-servers"
        if not servers_dir.exists():
            return {}

        servers: dict[str, dict] = {}
        for server_dir in sorted(servers_dir.iterdir()):
            if not server_dir.is_dir():
                continue
            config_path = server_dir / "artifact.yaml"
            if not config_path.exists():
                display.print(
                    f"Skipping malformed MCP server directory without artifact.yaml: {server_dir}",
                    style="warning",
                )
                continue
            servers[server_dir.name] = self.load_server_config(config_path)

        try:
            model = MCPManifest.model_validate({"servers": servers})
        except ValidationError as exc:
            raise RuntimeError(f"Manifest validation failed: {exc}") from exc
        return model.model_dump(by_alias=True)

    def load_and_filter_mcp(
        self,
        resolved_sources: Mapping[str, ResolvedSource],
        enabled_server_refs: list[str],
        display: DisplayService,
    ) -> dict:
        selected: dict = {}
        for ref in enabled_server_refs:
            alias, server_id = split_scoped_ref(ref)
            if alias not in resolved_sources:
                raise RuntimeError(f"Unknown source alias {alias!r} in MCP reference {ref!r}")
            manifest = self.load_manifest(resolved_sources[alias].root, display)
            servers = manifest.get("servers") or {}
            if server_id not in servers:
                raise RuntimeError(f"MCP server {ref!r} was not found in source {alias!r}")
            if server_id in selected:
                raise RuntimeError(
                    f"MCP server collision for output id {server_id!r}. "
                    "Select only one source for this server id."
                )
            selected[server_id] = servers[server_id]
        return selected

    def collect_env_refs(self, obj: object) -> set[str]:
        """Return all ``${VAR}`` / ``$VAR`` names referenced in a nested structure."""
        refs: set[str] = set()

        def walk(node: object) -> None:
            if isinstance(node, dict):
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)
            elif isinstance(node, str):
                cleaned = node.replace("$$", "")
                for match in ENV_REF_RE.finditer(cleaned):
                    refs.add(match.group(1) or match.group(2) or "")

        walk(obj)
        return refs

    def resolve_env_refs(self, obj: object, env_map: dict[str, str]) -> object:
        if isinstance(obj, dict):
            return {key: self.resolve_env_refs(value, env_map) for key, value in obj.items()}
        if isinstance(obj, list):
            return [self.resolve_env_refs(value, env_map) for value in obj]
        if isinstance(obj, str):
            return self._interpolate_env_refs(obj, env_map)
        return obj

    def load_server_config(self, path: Path) -> dict:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except (yaml.YAMLError, OSError) as exc:
            raise RuntimeError(f"Failed to load {path}: {exc}") from exc

        if not isinstance(data, dict):
            raise RuntimeError(f"Invalid MCP server config {path}: expected a mapping")

        try:
            model = ServerConfig.model_validate(data)
        except ValidationError as exc:
            raise RuntimeError(f"Invalid MCP server config {path}: {exc}") from exc
        return model.model_dump(by_alias=True)

    def _interpolate_env_refs(self, value: str, env_map: dict[str, str]) -> str:
        escaped = value.replace("$$", _ESCAPE_SENTINEL)
        missing: list[str] = []

        def replace(match: re.Match[str]) -> str:
            name = match.group(1) or match.group(2) or ""
            if name in env_map:
                return env_map[name]
            missing.append(name)
            return match.group(0)

        resolved = ENV_REF_RE.sub(replace, escaped)
        if missing:
            names = ", ".join(sorted(set(missing)))
            raise RuntimeError(f"Missing environment values in injected env for: {names}")
        return resolved.replace(_ESCAPE_SENTINEL, "$")
