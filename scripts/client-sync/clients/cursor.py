"""Cursor client adapter."""
import json
from pathlib import Path

from helpers import deep_merge, ensure_dir, parse_duration_seconds, write_content_if_different

from .base import Client


class CursorClient(Client):
    @property
    def name(self) -> str:
        return "cursor"

    @property
    def config_dir(self) -> Path:
        return Path.home() / ".cursor"

    def write_agent(
        self,
        slug: str,
        meta: dict,
        raw_content: str,
        prompt_src_path: Path,
    ) -> None:
        ensure_dir(self.get_agents_dir())
        agent_path = self.get_agents_dir() / f"{slug}.md"
        display_name = meta.get("name", slug)
        description = meta.get("description", "AI Agent")
        cursor_model = meta.get("models", {}).get("cursor", "gpt-5.2")
        is_background = "true" if meta.get("is_background", False) else "false"
        content = f"""---
name: {display_name}
description: {description}
model: {cursor_model}
is_background: {is_background}
---

{raw_content}
"""
        write_content_if_different(agent_path, content, backup=False)

    def _build_mcp_entry(self, server_id: str, server: dict, secrets: dict) -> dict:
        method = server.get("method", "stdio")
        entry: dict = {}
        if method == "stdio":
            entry["command"] = server.get("command", "npx")
            entry["args"] = server.get("args", [])
        servers_secrets = secrets.get("servers", {})
        if server_id not in servers_secrets:
            raise ValueError(
                f"No secret found for MCP server '{server_id}'. "
                f"Add an entry in config/mcp-servers/secrets/secrets.yaml (use {{}} for no env)."
            )
        secret_srv = servers_secrets[server_id]
        env_parts: list[dict] = []
        if server.get("env"):
            env_parts.append({k: str(v) if v is not None else "" for k, v in server["env"].items()})
        if secret_srv.get("env"):
            env_parts.append({k: str(v) if v is not None else "" for k, v in secret_srv["env"].items()})
        if env_parts:
            merged_env: dict = {}
            for e in env_parts:
                merged_env.update(e)
            entry["env"] = merged_env
        if secret_srv.get("auth"):
            entry["auth"] = {k: str(v) if v is not None else "" for k, v in secret_srv["auth"].items()}
        if method in ("http", "sse"):
            if server.get("url"):
                entry["url"] = server["url"]
            if server.get("httpUrl"):
                entry["httpUrl"] = server["httpUrl"]
        if server.get("trust") is True:
            entry["trust"] = True
        if server.get("description"):
            entry["description"] = str(server["description"])
        if "timeout" in server:
            try:
                entry["timeout"] = parse_duration_seconds(server["timeout"]) * 1000  # ms
            except ValueError:
                pass
        return entry

    def sync_mcp(self, servers: dict, secrets: dict, for_client) -> None:
        cursor_mcp: dict = {}
        for sid, srv in servers.items():
            if not for_client(srv, self.name):
                continue
            cursor_mcp[sid] = self._build_mcp_entry(sid, srv, secrets)
        if not cursor_mcp:
            return
        ensure_dir(self.config_dir)
        mcp_path = self.config_dir / "mcp.json"
        existing: dict = {}
        if mcp_path.exists():
            try:
                with open(mcp_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        merged_servers = dict(existing.get("mcpServers", {}))
        for sid, entry in cursor_mcp.items():
            merged_servers[sid] = entry  # full replace so deprecated keys are removed
        merged = deep_merge(existing, {"mcpServers": merged_servers})
        write_content_if_different(
            mcp_path, json.dumps(merged, indent=2), backup=False
        )

    def _build_client_config(self, settings: dict) -> dict:
        mode = settings.get("mode", "ask")
        if mode == "full-access":
            return {
                "permissions": {
                    "allow": ["Shell(*)", "Read(*)", "Write(*)", "WebFetch(*)", "Mcp(*:*)"],
                    "deny": []
                }
            }
        return {"permissions": {"allow": [], "deny": []}}

    def sync_client_config(self, settings: dict) -> None:
        updates = self._build_client_config(settings)
        if not updates:
            return
        ensure_dir(self.config_dir)
        config_path = self.config_dir / "cli-config.json"
        existing: dict = {}
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        existing = deep_merge(existing, updates)
        write_content_if_different(
            config_path, json.dumps(existing, indent=2), backup=False
        )

    def clear_agents(self) -> None:
        import shutil
        agents_dir = self.get_agents_dir()
        if agents_dir.exists():
            shutil.rmtree(agents_dir)
            print(f"    Cleared agents: {agents_dir}")

    def clear_skills(self) -> None:
        import shutil
        skills_dir = self.get_skills_dir()
        if skills_dir.exists():
            shutil.rmtree(skills_dir)
            print(f"    Cleared skills: {skills_dir}")

    def clear_settings(self) -> None:
        mcp_path = self.config_dir / "mcp.json"
        if mcp_path.exists():
            try:
                with open(mcp_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                if "mcpServers" in existing:
                    del existing["mcpServers"]
                    write_content_if_different(mcp_path, json.dumps(existing, indent=2), backup=False)
                    print(f"    Cleared MCP servers from {mcp_path}")
            except (json.JSONDecodeError, OSError) as e:
                print(f"  Warning: Could not clear MCP from Cursor config: {e}")
        self.clear_mcp_instructions()

    def clear_mcp_instructions(self) -> None:
        rule_path = self.config_dir / "rules" / "mcp-instructions.mdc"
        if rule_path.exists():
            rule_path.unlink()
            print(f"    Removed {rule_path}")

    def get_oauth_src_path(self) -> Path | None:
        return None  # TBD

    def get_oauth_stash_filename(self) -> str | None:
        return None

    def sync_mcp_instructions(self, instructions: str) -> None:
        if not instructions or not instructions.strip():
            return
        rules_dir = self.config_dir / "rules"
        ensure_dir(rules_dir)
        content = f"""---
description: MCP server selection guidance (e.g. which Google Workspace to use)
alwaysApply: true
---

# MCP Server Instructions

{instructions.strip()}
"""
        write_content_if_different(
            rules_dir / "mcp-instructions.mdc", content, backup=False
        )
