"""Main orchestration (preflight + execute)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import yaml

from sync_ai_configs.clients import CLIENTS
from sync_ai_configs.display import Display
from sync_ai_configs.env_loader import resolve_env_refs_in_obj
from sync_ai_configs.helpers import (
    copy_file_if_different,
    ensure_dir,
    extract_description,
    sync_tree_if_different,
    to_kebab_case,
)
from sync_ai_configs.interactive import SyncOptions, run_interactive_prompts
from sync_ai_configs.manifest_loader import load_manifest
from sync_ai_configs.mcp_sync import sync_mcp_servers
from sync_ai_configs.op_inject import load_runtime_env_from_op
from sync_ai_configs.precedence import apply_overrides
from sync_ai_configs.version_checks import check_client_versions, detect_client_versions

GENERIC_METADATA_KEYS = {"slug", "name", "description"}
SKIP_PATTERNS = {".venv", "node_modules", "__pycache__", ".git", ".DS_Store"}


@dataclass
class RunConfig:
    repo_root: Path
    source_prompts: Path
    source_skills: Path
    source_mcp: Path
    source_client_config: Path
    source_env_template: Path
    overrides: list[tuple[str, object]]
    options: SyncOptions


def load_prompt_metadata(prompt_path: Path, content: str, display: Display) -> dict:
    metadata_path = prompt_path.with_suffix(".metadata.yaml")
    result: dict = {
        "name": to_kebab_case(prompt_path.stem),
        "description": extract_description(content),
        "models": {"codex": "gpt-5", "cursor": "gpt-5.2", "gemini": "gemini-2.0-flash-thinking-exp"},
        "reasoning_effort": "high",
        "is_background": False,
        "web_search": True,
        "tools": ["google_web_search"],
    }
    if metadata_path.exists():
        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                user_meta = yaml.safe_load(f)
            if user_meta and isinstance(user_meta, dict):
                for key in GENERIC_METADATA_KEYS:
                    if key in user_meta and user_meta[key] is not None:
                        result[key] = user_meta[key]
        except (yaml.YAMLError, OSError) as exc:
            display.print(f"Failed to load metadata for {prompt_path.name}: {exc}", style="warning")
    return result


def sync_agents(config: RunConfig, display: Display) -> None:
    display.rule("Syncing Agents")
    prompts = sorted(config.source_prompts.glob("*.md"))
    prompts = [p for p in prompts if p.stem in config.options.agent_stems]
    if not prompts:
        display.print("No agents selected", style="dim")
        return
    if not (config.source_client_config / "settings.yaml").exists():
        gemini = next((c for c in CLIENTS if c.name == "gemini"), None)
        if gemini:
            gemini.enable_subagents_fallback()

    rows: list[tuple[str, ...]] = []
    for prompt_path in prompts:
        raw_content = prompt_path.read_text(encoding="utf-8")
        meta = load_prompt_metadata(prompt_path, raw_content, display)
        slug = meta.get("slug", to_kebab_case(prompt_path.stem))
        rows.append((prompt_path.stem, to_kebab_case(prompt_path.stem), ", ".join(c.name for c in CLIENTS)))
        for client in CLIENTS:
            client.write_agent(slug, meta, raw_content, prompt_path)
    display.table(("Agent", "Slug", "Clients"), rows)


def sync_skills(config: RunConfig, display: Display) -> None:
    display.rule("Syncing Skills")
    skill_dirs = sorted(d for d in config.source_skills.iterdir() if d.is_dir() and (d / "SKILL.md").exists())
    skill_dirs = [d for d in skill_dirs if d.name in config.options.skill_names]
    if not skill_dirs:
        display.print("No skills selected", style="dim")
        return
    rows: list[tuple[str, ...]] = []
    for skill_dir in skill_dirs:
        kebab_name = to_kebab_case(skill_dir.name)
        rows.append((skill_dir.name, kebab_name, ", ".join(c.name for c in CLIENTS)))
        for client in CLIENTS:
            target_base = client.get_skills_dir()
            ensure_dir(target_base)
            target_skill_dir = target_base / kebab_name
            ensure_dir(target_skill_dir)
            copy_file_if_different(skill_dir / "SKILL.md", target_skill_dir / "SKILL.md")
            for sub in skill_dir.iterdir():
                if sub.is_dir() and sub.name not in SKIP_PATTERNS:
                    sync_tree_if_different(sub, target_skill_dir / sub.name, SKIP_PATTERNS)
    display.table(("Skill", "Slug", "Clients"), rows)


def sync_client_config(config: RunConfig, display: Display) -> None:
    settings_path = config.source_client_config / "settings.yaml"
    if not settings_path.exists():
        display.print("Client Config: skipping (config/client-settings/settings.yaml not found)", style="dim")
        return
    display.rule("Syncing Client Config")
    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            settings = yaml.safe_load(f) or {}
    except (yaml.YAMLError, OSError) as exc:
        display.print(f"Failed to load {settings_path}: {exc}", style="warning")
        return
    rows: list[tuple[str, ...]] = []
    for client in CLIENTS:
        client.sync_client_config(settings)
        rows.append((client.name, "OK"))
    display.table(("Client", "Status"), rows)


def preflight(config: RunConfig, display: Display) -> dict:
    runtime_env = load_runtime_env_from_op(config.source_env_template)
    manifest = load_manifest(config.source_mcp, display)
    if runtime_env:
        manifest = resolve_env_refs_in_obj(manifest, runtime_env)
    if config.overrides:
        manifest = apply_overrides(manifest, config.overrides)
    if not config.source_prompts.exists() or not config.source_skills.exists():
        raise RuntimeError("config/prompts or config/skills directories not found")
    return manifest


def execute(config: RunConfig, manifest: dict, display: Display) -> int:
    display.print("")
    display.rule("Starting Sync", style="info")
    display.print(f"Source: {config.repo_root}", style="info")
    if config.options.clear_first:
        display.rule("Clearing Client Configs", style="error")
        for client in CLIENTS:
            display.print(f"  Clearing {client.name}...", style="info")
            client.clear(use_backups=config.options.use_backups)
        display.print("Clear complete", style="success")
        display.print("")
    sync_agents(config, display)
    sync_skills(config, display)
    sync_mcp_servers(manifest, display)
    if config.options.install_settings:
        sync_client_config(config, display)
    display.print("")
    display.panel("Sync complete", title="Done", style="success")
    return 0


def run_sync(
    *,
    repo_root: Path,
    force: bool,
    clear: bool,
    backup: bool,
    no_interactive: bool,
    plain: bool,
    overrides: list[tuple[str, object]],
    display: Display,
) -> int:
    versions_path = repo_root / "scripts" / ".client-versions.json"
    if force:
        versions = detect_client_versions()
        if not versions:
            raise RuntimeError("No client versions detected; ensure codex/cursor/gemini CLIs are on PATH")
        versions_path.write_text(json.dumps(versions, indent=2) + "\n", encoding="utf-8")
        display.print(f"✓ Updated {versions_path}", style="success")
    else:
        ok, msg = check_client_versions(versions_path)
        if not ok:
            raise RuntimeError(msg)

    source_prompts = repo_root / "config" / "prompts"
    source_skills = repo_root / "config" / "skills"
    source_mcp = repo_root / "config" / "mcp-servers"
    source_client_config = repo_root / "config" / "client-settings"
    source_env_template = repo_root / ".env.tpl"

    agent_stems = sorted(p.stem for p in source_prompts.glob("*.md")) if source_prompts.exists() else []
    skill_names = sorted(d.name for d in source_skills.iterdir() if d.is_dir() and (d / "SKILL.md").exists()) if source_skills.exists() else []
    if not agent_stems and not skill_names:
        raise RuntimeError("No agents or skills found in config")
    if backup and not clear:
        display.print("--backup ignored without --clear (sync is idempotent).", style="warning")

    if no_interactive or plain:
        options = SyncOptions(
            agent_stems=frozenset(agent_stems),
            skill_names=frozenset(skill_names),
            install_settings=True,
            use_backups=clear and backup,
            clear_first=clear,
        )
    else:
        opts = run_interactive_prompts(display, agent_stems, skill_names, clear_default=clear, backup_default=backup)
        if opts is None:
            raise RuntimeError("Cancelled")
        options = opts

    config = RunConfig(
        repo_root=repo_root,
        source_prompts=source_prompts,
        source_skills=source_skills,
        source_mcp=source_mcp,
        source_client_config=source_client_config,
        source_env_template=source_env_template,
        overrides=overrides,
        options=options,
    )
    manifest = preflight(config, display)
    return execute(config, manifest, display)
