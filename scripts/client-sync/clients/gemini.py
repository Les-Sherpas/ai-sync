"""Gemini CLI client adapter."""
import json
import re
from pathlib import Path

from helpers import deep_merge, ensure_dir, parse_duration_seconds, write_content_if_different

from .base import Client


class GeminiClient(Client):
    @property
    def name(self) -> str:
        return "gemini"

    @property
    def config_dir(self) -> Path:
        return Path.home() / ".gemini"

    def write_agent(
        self,
        slug: str,
        meta: dict,
        raw_content: str,
        prompt_src_path: Path,
    ) -> None:
        ensure_dir(self.get_agents_dir())
        agent_path = self.get_agents_dir() / f"{slug}.md"
        description = meta.get("description", "AI Agent")
        gemini_model = meta.get("models", {}).get("gemini", "gemini-2.0-flash-thinking-exp")
        tools_list = json.dumps(meta.get("tools", ["google_web_search"]))
        content = f"""---
name: {slug}
description: {json.dumps(description)}
model: {gemini_model}
tools: {tools_list}
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
        if method in ("http", "sse"):
            if server.get("url"):
                entry["url"] = server["url"]
            if server.get("httpUrl"):
                entry["httpUrl"] = server["httpUrl"]
        if server.get("trust") is True:
            entry["trust"] = True
        if server.get("description"):
            entry["description"] = str(server["description"])
        if server.get("oauth", {}).get("enabled"):
            oauth_src = secret_srv.get("oauth") or secret_srv.get("auth") or {}
            oauth_cfg = server.get("oauth", {})
            client_id = (oauth_src.get("clientId") or "").strip()
            client_secret = (oauth_src.get("clientSecret") or "").strip()
            scopes = oauth_cfg.get("scopes") or oauth_src.get("scopes") or []
            if client_id:
                entry["oauth"] = {
                    "enabled": True,
                    "clientId": client_id,
                    "clientSecret": client_secret,
                }
                if scopes:
                    entry["oauth"]["scopes"] = [str(s) for s in scopes]
            # else: skip oauth block → Gemini will fail with "No client ID provided"
        if "timeout" in server:
            try:
                entry["timeout"] = parse_duration_seconds(server["timeout"]) * 1000  # ms
            except ValueError:
                pass
        return entry

    def sync_mcp(self, servers: dict, secrets: dict, for_client) -> None:
        gemini_mcp: dict = {}
        for sid, srv in servers.items():
            if not for_client(srv, self.name):
                continue
            gemini_mcp[sid] = self._build_mcp_entry(sid, srv, secrets)
        if not gemini_mcp:
            return
        ensure_dir(self.config_dir)
        settings_path = self.config_dir / "settings.json"
        existing: dict = {}
        if settings_path.exists():
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        if "mcpServers" not in existing:
            existing["mcpServers"] = {}
        merged = dict(existing["mcpServers"])
        for sid, entry in gemini_mcp.items():
            merged[sid] = entry  # full replace so deprecated keys are removed
        for sid in list(merged.keys()):
            if sid not in gemini_mcp:
                del merged[sid]  # remove orphaned servers not in manifest
            elif sid in servers and not for_client(servers[sid], self.name):
                del merged[sid]  # remove servers excluded via clients filter
        existing["mcpServers"] = merged
        write_content_if_different(
            settings_path, json.dumps(existing, indent=2), backup=False
        )

    def _build_client_config(self, settings: dict) -> dict:
        out: dict = {}
        subagents = settings.get("subagents", True)
        mode = settings.get("mode", "ask")

        if subagents:
            out.setdefault("experimental", {})
            out["experimental"]["enableAgents"] = True

        mode_map = {"ask": "default", "ask-once": "auto_edit", "full-access": "yolo"}
        out.setdefault("general", {})
        out["general"]["defaultApprovalMode"] = mode_map.get(mode, "default")

        tools = settings.get("tools")
        if isinstance(tools, dict) and "sandbox" in tools:
            out.setdefault("tools", {})
            out["tools"]["sandbox"] = bool(tools["sandbox"])
        return out

    def sync_client_config(self, settings: dict) -> None:
        updates = self._build_client_config(settings)
        if not updates:
            return
        ensure_dir(self.config_dir)
        settings_path = self.config_dir / "settings.json"
        existing: dict = {}
        if settings_path.exists():
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        existing = deep_merge(existing, updates)
        write_content_if_different(
            settings_path, json.dumps(existing, indent=2), backup=False
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
        settings_path = self.config_dir / "settings.json"
        if settings_path.exists():
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                if "mcpServers" in existing:
                    del existing["mcpServers"]
                    write_content_if_different(settings_path, json.dumps(existing, indent=2), backup=False)
                    print(f"    Cleared MCP servers from {settings_path}")
            except (json.JSONDecodeError, OSError) as e:
                print(f"  Warning: Could not clear MCP from Gemini config: {e}")
        self.clear_mcp_instructions()

    def clear_mcp_instructions(self) -> None:
        begin_marker = "<!-- BEGIN sync-ai-configs MCP instructions -->"
        end_marker = "<!-- END sync-ai-configs MCP instructions -->"
        gemini_md = self.config_dir / "GEMINI.md"
        if not gemini_md.exists():
            return
        try:
            content = gemini_md.read_text(encoding="utf-8")
            pattern = re.compile(
                rf"{re.escape(begin_marker)}.*?{re.escape(end_marker)}\n?",
                re.DOTALL,
            )
            new_content = pattern.sub("", content).strip()
            if new_content != content.strip():
                if new_content:
                    write_content_if_different(gemini_md, new_content + "\n", backup=False)
                else:
                    gemini_md.unlink()
                print("    Removed MCP instructions from Gemini GEMINI.md")
        except OSError as e:
            print(f"  Warning: Could not clear Gemini MCP instructions: {e}")

    def get_oauth_src_path(self) -> Path | None:
        return self.config_dir / "mcp-oauth-tokens.json"

    def get_oauth_stash_filename(self) -> str | None:
        return "gemini-mcp-oauth-tokens.json"

    def sync_mcp_instructions(self, instructions: str) -> None:
        if not instructions or not instructions.strip():
            return
        ensure_dir(self.config_dir)
        gemini_md = self.config_dir / "GEMINI.md"
        section = f"\n\n## MCP Server Instructions (sync-ai-configs)\n\n{instructions.strip()}\n"
        begin_marker = "<!-- BEGIN sync-ai-configs MCP instructions -->"
        end_marker = "<!-- END sync-ai-configs MCP instructions -->"
        block = f"{begin_marker}\n{section.strip()}\n{end_marker}"
        if gemini_md.exists():
            try:
                content = gemini_md.read_text(encoding="utf-8")
            except OSError as e:
                print(f"  Warning: Could not read {gemini_md}: {e}")
                return
            pattern = re.compile(
                rf"{re.escape(begin_marker)}.*?{re.escape(end_marker)}",
                re.DOTALL,
            )
            if pattern.search(content):
                new_content = pattern.sub(block, content)
            else:
                new_content = content.rstrip() + "\n\n" + block + "\n"
        else:
            new_content = block + "\n"
        write_content_if_different(gemini_md, new_content, backup=False)

    def enable_subagents_fallback(self) -> None:
        """Enable experimental subagents when config/client-settings/settings.yaml is absent. Fallback only."""
        settings_path = self.config_dir / "settings.json"
        if not settings_path.exists():
            return
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            changed = False
            if "experimental" not in data:
                data["experimental"] = {}
                changed = True
            if not data["experimental"].get("enableAgents"):
                data["experimental"]["enableAgents"] = True
                changed = True
            if changed:
                print("  Enabling experimental.enableAgents in ~/.gemini/settings.json")
                with open(settings_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
        except (json.JSONDecodeError, OSError) as e:
            print(f"  Warning: Could not update Gemini settings: {e}")
