"""Main orchestration for project-scoped apply."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import tomli
import yaml

from ai_sync.clients import Client, create_clients
from ai_sync.display import Display
from ai_sync.helpers import (
    ensure_dir,
    extract_description,
    to_kebab_case,
    validate_client_settings,
)
from ai_sync.mcp_sync import resolve_servers_for_client, sync_mcp_servers
from ai_sync.path_ops import escape_path_segment
from ai_sync.project import ProjectManifest, split_scoped_ref
from ai_sync.state_store import StateStore
from ai_sync.track_write import DELETE, WriteSpec, _is_full_file_target, track_write_blocks

GENERIC_METADATA_KEYS = {"slug", "name", "description"}
SKIP_PATTERNS = {".venv", "node_modules", "__pycache__", ".git", ".DS_Store"}


class _ApplyDisplayProxy:
    def __init__(self, base: Display) -> None:
        self._base = base

    def rule(self, title: str, style: str = "section") -> None:
        return

    def print(self, msg: str, style: str = "normal") -> None:
        if style == "warning":
            self._base.print(msg, style=style)

    def panel(self, content: str, *, title: str = "", style: str = "normal") -> None:
        if style == "error":
            self._base.panel(content, title=title, style=style)

    def table(self, headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> None:
        return


def _collect_desired_target_keys(
    *,
    project_root: Path,
    source_roots: Mapping[str, Path],
    manifest: ProjectManifest,
    mcp_manifest: dict,
    runtime_env: dict[str, str],
    clients: Sequence[Client],
    display: Display,
) -> set[tuple[str, str, str]]:
    desired: set[tuple[str, str, str]] = set()

    def add_specs(specs: list[WriteSpec]) -> None:
        for spec in specs:
            desired.add((str(spec.file_path), spec.format, spec.target))

    for agent_ref in manifest.agents:
        alias, agent_name = split_scoped_ref(agent_ref)
        source_root = source_roots[alias]
        prompt_path = source_root / "prompts" / f"{agent_name}.md"
        raw_content = prompt_path.read_text(encoding="utf-8")
        meta = load_prompt_metadata(prompt_path, raw_content, display)
        slug = meta.get("slug", to_kebab_case(prompt_path.stem))
        for client in clients:
            add_specs(client.build_agent_specs(slug, meta, raw_content, prompt_path))

    for skill_ref in manifest.skills:
        alias, skill_name = split_scoped_ref(skill_ref)
        skill_dir = source_roots[alias] / "skills" / skill_name
        kebab_name = to_kebab_case(skill_name)
        for client in clients:
            target_skill_dir = client.get_skills_dir() / kebab_name
            for sub in skill_dir.rglob("*"):
                rel = sub.relative_to(skill_dir)
                if any(part in SKIP_PATTERNS for part in rel.parts) or sub.is_dir():
                    continue
                target = target_skill_dir / rel
                if sub.name.endswith(".json"):
                    fmt = "json"
                elif sub.name.endswith(".toml"):
                    fmt = "toml"
                elif sub.name.endswith(".yaml") or sub.name.endswith(".yml"):
                    fmt = "yaml"
                else:
                    fmt = "text"
                content = sub.read_text(encoding="utf-8")
                if fmt == "text":
                    add_specs(
                        [
                            WriteSpec(
                                file_path=target,
                                format=fmt,
                                target=f"ai-sync:skill:{kebab_name}:{rel.as_posix()}",
                                value=content,
                            )
                        ]
                    )
                else:
                    add_specs(_flatten_structured_to_specs(target, fmt, _parse_structured_content(content, fmt)))

    for command_ref in manifest.commands:
        alias, rel_posix = split_scoped_ref(command_ref)
        command_path = source_roots[alias] / "commands" / rel_posix
        raw_content = command_path.read_text(encoding="utf-8")
        rel = Path(rel_posix)
        for client in clients:
            add_specs(client.build_command_specs(command_ref, raw_content, rel))

    if manifest.rules:
        sections: list[str] = []
        for rule_ref in manifest.rules:
            alias, rule_name = split_scoped_ref(rule_ref)
            rule_path = source_roots[alias] / "rules" / f"{rule_name}.md"
            sections.append(rule_path.read_text(encoding="utf-8").strip())
        parts: list[str] = []
        if runtime_env:
            parts.append(ENV_HINT)
        parts.extend(sections)
        add_specs(
            [
                WriteSpec(
                    file_path=project_root / GENERATED_AGENTS_FILENAME,
                    format="text",
                    target="ai-sync:rules",
                    value="\n\n".join(parts) + "\n",
                ),
                WriteSpec(
                    file_path=project_root / "AGENTS.md",
                    format="text",
                    target=RULES_LINK_TARGET,
                    value=_rules_link_content(),
                ),
            ]
        )

    for client in clients:
        add_specs(client.build_mcp_specs(resolve_servers_for_client(mcp_manifest, client.name), {"servers": {}}))

    if runtime_env:
        add_specs(
            [
                WriteSpec(
                    file_path=project_root / ".env.ai-sync",
                    format="text",
                    target="ai-sync:env",
                    value="\n".join(f"{key}={value}" for key, value in sorted(runtime_env.items())) + "\n",
                )
            ]
        )

    if manifest.settings:
        for client in clients:
            add_specs(client.build_client_config_specs(manifest.settings))

    instructions_path = project_root / ".ai-sync" / "instructions.md"
    if instructions_path.exists():
        content = instructions_path.read_text(encoding="utf-8")
        if content.strip():
            for client in clients:
                add_specs(client.build_instructions_specs(content))

    return desired


def _build_stale_delete_specs(
    store: StateStore, desired_targets: set[tuple[str, str, str]]
) -> list[WriteSpec]:
    stale_specs: list[WriteSpec] = []
    desired_targets_by_file: dict[tuple[str, str], set[str]] = {}
    for file_path, fmt, target in desired_targets:
        desired_targets_by_file.setdefault((file_path, fmt), set()).add(target)
    for entry in store.list_entries():
        file_path = entry.get("file_path")
        fmt = entry.get("format")
        target = entry.get("target")
        if not isinstance(file_path, str) or not isinstance(fmt, str) or not isinstance(target, str):
            continue
        if (file_path, fmt, target) in desired_targets:
            continue
        same_file_targets = desired_targets_by_file.get((file_path, fmt), set())
        if _is_full_file_target(target) and any(other != target for other in same_file_targets):
            continue
        stale_specs.append(WriteSpec(file_path=Path(file_path), format=fmt, target=target, value=DELETE))
    return stale_specs


def load_prompt_metadata(prompt_path: Path, content: str, display: Display) -> dict:
    metadata_path = prompt_path.with_suffix(".metadata.yaml")
    result: dict = {
        "name": to_kebab_case(prompt_path.stem),
        "description": extract_description(content),
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


def sync_agents(
    source_roots: Mapping[str, Path],
    agent_list: list[str],
    clients: Sequence[Client],
    store: StateStore,
    display: Display,
) -> None:
    display.rule("Syncing Agents")
    if not agent_list:
        display.print("No agents selected", style="dim")
        return

    rows: list[tuple[str, ...]] = []
    for agent_ref in agent_list:
        alias, agent_name = split_scoped_ref(agent_ref)
        source_root = source_roots.get(alias)
        if source_root is None:
            display.print(f"Agent source {alias!r} not found for {agent_ref!r}", style="warning")
            continue
        prompt_path = source_root / "prompts" / f"{agent_name}.md"
        if not prompt_path.exists():
            display.print(f"Agent {agent_ref!r} not found in source {alias!r}", style="warning")
            continue
        raw_content = prompt_path.read_text(encoding="utf-8")
        meta = load_prompt_metadata(prompt_path, raw_content, display)
        slug = meta.get("slug", to_kebab_case(prompt_path.stem))
        rows.append((agent_ref, slug, ", ".join(c.name for c in clients)))
        for client in clients:
            client.write_agent(slug, meta, raw_content, prompt_path, store)
    if rows:
        display.table(("Agent", "Slug", "Clients"), rows)
    else:
        display.print("No agents selected", style="dim")


def sync_skills(
    source_roots: Mapping[str, Path],
    skill_list: list[str],
    clients: Sequence[Client],
    store: StateStore,
    display: Display,
) -> None:
    display.rule("Syncing Skills")
    if not skill_list:
        display.print("No skills selected", style="dim")
        return

    rows: list[tuple[str, ...]] = []
    for skill_ref in skill_list:
        alias, skill_name = split_scoped_ref(skill_ref)
        source_root = source_roots.get(alias)
        if source_root is None:
            display.print(f"Skill source {alias!r} not found for {skill_ref!r}", style="warning")
            continue
        resolved_skill_dir = source_root / "skills" / skill_name
        if not (resolved_skill_dir.is_dir() and (resolved_skill_dir / "SKILL.md").exists()):
            display.print(f"Skill {skill_ref!r} not found in source {alias!r}", style="warning")
            continue
        skill_dir = resolved_skill_dir
        kebab_name = to_kebab_case(skill_dir.name)
        rows.append((skill_ref, kebab_name, ", ".join(c.name for c in clients)))
        for client in clients:
            target_base = client.get_skills_dir()
            ensure_dir(target_base)
            target_skill_dir = target_base / kebab_name
            ensure_dir(target_skill_dir)
            specs: list[WriteSpec] = []
            for sub in skill_dir.rglob("*"):
                rel = sub.relative_to(skill_dir)
                if any(part in SKIP_PATTERNS for part in rel.parts):
                    continue
                if sub.is_dir():
                    continue
                target = target_skill_dir / rel
                if sub.name.endswith(".json"):
                    fmt = "json"
                elif sub.name.endswith(".toml"):
                    fmt = "toml"
                elif sub.name.endswith(".yaml") or sub.name.endswith(".yml"):
                    fmt = "yaml"
                else:
                    fmt = "text"
                content = sub.read_text(encoding="utf-8")
                marker_id = f"ai-sync:skill:{kebab_name}:{rel.as_posix()}"
                if fmt == "text":
                    specs.append(
                        WriteSpec(
                            file_path=target,
                            format=fmt,
                            target=marker_id,
                            value=content,
                        )
                    )
                    continue
                data = _parse_structured_content(content, fmt)
                leaf_specs = _flatten_structured_to_specs(target, fmt, data)
                existing_targets = set(store.list_targets(target, fmt, "/"))
                current_targets = {spec.target for spec in leaf_specs}
                for stale_target in sorted(existing_targets - current_targets):
                    leaf_specs.append(
                        WriteSpec(
                            file_path=target,
                            format=fmt,
                            target=stale_target,
                            value=DELETE,
                        )
                    )
                specs.extend(leaf_specs)
            if specs:
                track_write_blocks(specs, store)
    if rows:
        display.table(("Skill", "Slug", "Clients"), rows)
    else:
        display.print("No skills selected", style="dim")


def sync_commands(
    source_roots: Mapping[str, Path],
    command_list: list[str],
    clients: Sequence[Client],
    store: StateStore,
    display: Display,
) -> None:
    display.rule("Syncing Commands")
    if not command_list:
        display.print("No commands selected", style="dim")
        return

    rows: list[tuple[str, ...]] = []
    for command_ref in command_list:
        alias, rel_posix = split_scoped_ref(command_ref)
        source_root = source_roots.get(alias)
        if source_root is None:
            display.print(f"Command source {alias!r} not found for {command_ref!r}", style="warning")
            continue
        command_path = source_root / "commands" / rel_posix
        if not command_path.is_file():
            display.print(f"Command {command_ref!r} not found in source {alias!r}", style="warning")
            continue
        raw_content = command_path.read_text(encoding="utf-8")
        rel = Path(rel_posix)
        rows.append((command_ref, ", ".join(c.name for c in clients)))
        for client in clients:
            client.write_command(command_ref, raw_content, rel, store)
    if rows:
        display.table(("Command", "Clients"), rows)
    else:
        display.print("No commands selected", style="dim")


ENV_HINT = (
    "> **Environment variables** are defined in `.env.ai-sync` at the project root."
    " Source it before running commands that need credentials: `source .env.ai-sync`\n"
)
GENERATED_AGENTS_FILENAME = "AGENTS.generated.md"
RULES_LINK_TARGET = "ai-sync:rules-link"


def _rules_link_content() -> str:
    return (
        "## ai-sync\n\n"
        f"Additional project instructions managed by ai-sync live in "
        f"[`{GENERATED_AGENTS_FILENAME}`](./{GENERATED_AGENTS_FILENAME}).\n"
    )


def sync_rules(
    project_root: Path,
    source_roots: Mapping[str, Path],
    rule_list: list[str],
    has_env: bool,
    store: StateStore,
    display: Display,
) -> None:
    """Write generated rules and maintain a small link block in AGENTS.md."""
    display.rule("Syncing Rules")
    generated_path = project_root / GENERATED_AGENTS_FILENAME
    agents_md_path = project_root / "AGENTS.md"
    if not rule_list:
        track_write_blocks(
            [
                WriteSpec(file_path=generated_path, format="text", target="ai-sync:rules", value=DELETE),
                WriteSpec(file_path=agents_md_path, format="text", target=RULES_LINK_TARGET, value=DELETE),
            ],
            store,
        )
        if generated_path.exists() and not generated_path.read_text(encoding="utf-8").strip():
            generated_path.unlink(missing_ok=True)
        display.print("No rules selected", style="dim")
        return

    sections: list[str] = []
    rows: list[tuple[str, ...]] = []
    for rule_ref in rule_list:
        alias, rule_name = split_scoped_ref(rule_ref)
        source_root = source_roots.get(alias)
        if source_root is None:
            display.print(f"Rule source {alias!r} not found for {rule_ref!r}", style="warning")
            continue
        rule_path = source_root / "rules" / f"{rule_name}.md"
        if not rule_path.exists():
            display.print(f"Rule {rule_ref!r} not found in source {alias!r}", style="warning")
            continue
        content = rule_path.read_text(encoding="utf-8")
        sections.append(content.strip())
        rows.append((rule_ref,))

    if not sections:
        track_write_blocks(
            [
                WriteSpec(file_path=generated_path, format="text", target="ai-sync:rules", value=DELETE),
                WriteSpec(file_path=agents_md_path, format="text", target=RULES_LINK_TARGET, value=DELETE),
            ],
            store,
        )
        if generated_path.exists() and not generated_path.read_text(encoding="utf-8").strip():
            generated_path.unlink(missing_ok=True)
        display.print("No rules resolved", style="dim")
        return

    parts: list[str] = []
    if has_env:
        parts.append(ENV_HINT)
    parts.extend(sections)
    generated_content = "\n\n".join(parts) + "\n"

    track_write_blocks(
        [
            WriteSpec(
                file_path=generated_path,
                format="text",
                target="ai-sync:rules",
                value=generated_content,
            ),
            WriteSpec(
                file_path=agents_md_path,
                format="text",
                target=RULES_LINK_TARGET,
                value=_rules_link_content(),
            )
        ],
        store,
    )

    if rows:
        display.table(("Rule",), rows)


def sync_client_config(
    settings: dict,
    clients: Sequence[Client],
    store: StateStore,
    display: Display,
) -> None:
    if not settings:
        display.print("Client Config: skipping (no settings)", style="dim")
        return
    display.rule("Syncing Client Config")
    errors = validate_client_settings(settings)
    if errors:
        display.panel("\n".join(errors), title="Invalid Client Config", style="error")
        return
    mode = settings.get("mode") or "normal"
    if mode == "yolo":
        display.panel(
            "mode=yolo grants full access (no sandbox, no approval prompts).",
            title="Warning",
            style="error",
        )
    rows: list[tuple[str, ...]] = []
    for client in clients:
        client.sync_client_config(settings, store)
        rows.append((client.name, "OK"))
    display.table(("Client", "Status"), rows)


def sync_instructions(
    project_root: Path,
    clients: Sequence[Client],
    store: StateStore,
    display: Display,
) -> None:
    instructions_path = project_root / ".ai-sync" / "instructions.md"
    if not instructions_path.exists():
        return
    display.rule("Syncing Instructions")
    content = instructions_path.read_text(encoding="utf-8")
    if not content.strip():
        return
    for client in clients:
        client.sync_instructions(content, store)
    display.print(f"  Synced to {', '.join(c.name for c in clients)}", style="info")


def _parse_structured_content(content: str, fmt: str) -> dict | list:
    if not content.strip():
        return {}
    if fmt == "json":
        return json.loads(content)
    if fmt == "toml":
        return tomli.loads(content)
    if fmt == "yaml":
        data = yaml.safe_load(content)
        return data if isinstance(data, (dict, list)) else {}
    raise ValueError(f"Unsupported format: {fmt}")


def _flatten_structured_to_specs(file_path: Path, fmt: str, data: object) -> list[WriteSpec]:
    specs: list[WriteSpec] = []

    def walk(node: object, prefix: str) -> None:
        if isinstance(node, dict):
            if not node:
                specs.append(WriteSpec(file_path=file_path, format=fmt, target=prefix or "/", value={}))
                return
            for key, value in node.items():
                next_prefix = f"{prefix}/{escape_path_segment(str(key))}"
                walk(value, next_prefix)
            return
        if isinstance(node, list):
            specs.append(WriteSpec(file_path=file_path, format=fmt, target=prefix or "/", value=[]))
            if not node:
                return
            for idx, value in enumerate(node):
                next_prefix = f"{prefix}/{idx}"
                walk(value, next_prefix)
            return
        specs.append(WriteSpec(file_path=file_path, format=fmt, target=prefix or "/", value=node))

    walk(data, "")
    return specs


def sync_env_file(
    project_root: Path,
    runtime_env: dict[str, str],
    store: StateStore,
    display: Display,
) -> None:
    """Write resolved environment variables to .env.ai-sync at the project root."""
    if not runtime_env:
        return
    display.rule("Syncing Environment File")
    lines = [f"{key}={value}" for key, value in sorted(runtime_env.items())]
    content = "\n".join(lines) + "\n"
    env_path = project_root / ".env.ai-sync"
    track_write_blocks(
        [
            WriteSpec(
                file_path=env_path,
                format="text",
                target="ai-sync:env",
                value=content,
            )
        ],
        store,
    )
    display.print(f"  Wrote {len(runtime_env)} variables to .env.ai-sync", style="info")


def run_apply(
    *,
    project_root: Path,
    source_roots: Mapping[str, Path],
    manifest: ProjectManifest,
    mcp_manifest: dict,
    secrets: dict,
    runtime_env: dict[str, str],
    display: Display,
) -> int:
    display.print("")
    display.rule("Starting Apply", style="info")
    display.print(f"Project: {project_root}", style="info")
    display.print(
        f"Sources ({len(source_roots)}): {', '.join(sorted(source_roots))}",
        style="info",
    )

    clients = create_clients(project_root)
    store = StateStore(project_root)
    store.load()
    apply_display = _ApplyDisplayProxy(display)
    desired_targets = _collect_desired_target_keys(
        project_root=project_root,
        source_roots=source_roots,
        manifest=manifest,
        mcp_manifest=mcp_manifest,
        runtime_env=runtime_env,
        clients=clients,
        display=display,
    )

    has_env = bool(runtime_env)
    sync_env_file(project_root, runtime_env, store, apply_display)
    sync_agents(source_roots, manifest.agents, clients, store, apply_display)
    sync_skills(source_roots, manifest.skills, clients, store, apply_display)
    sync_commands(source_roots, manifest.commands, clients, store, apply_display)
    sync_rules(project_root, source_roots, manifest.rules, has_env, store, apply_display)
    sync_mcp_servers(mcp_manifest, clients, secrets, store, apply_display)
    sync_client_config(manifest.settings, clients, store, apply_display)
    sync_instructions(project_root, clients, store, apply_display)
    stale_delete_specs = _build_stale_delete_specs(store, desired_targets)
    if stale_delete_specs:
        track_write_blocks(stale_delete_specs, store)
        desired_files = {file_path for file_path, _, _ in desired_targets}
        for spec in stale_delete_specs:
            file_path = spec.file_path
            if str(file_path) in desired_files or not file_path.exists():
                continue
            if file_path.is_file() and not file_path.read_text(encoding="utf-8").strip():
                file_path.unlink(missing_ok=True)

    store.save()

    display.print("")
    display.panel("Apply complete", title="Done", style="success")
    return 0
