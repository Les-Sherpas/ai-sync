"""Shared planning pipeline for ai-sync."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from .artifacts import Artifact, collect_artifacts
from .clients import create_clients
from .display import Display
from .env_config import EnvVarConfig, RuntimeEnv, load_env_config, read_existing_env_file
from .env_loader import collect_env_refs, resolve_env_refs_in_obj
from .git_safety import check_pre_commit_hook
from .helpers import validate_client_settings
from .manifest_loader import load_and_filter_mcp
from .op_inject import resolve_op_refs
from .project import (
    ProjectManifest,
    manifest_fingerprint,
    resolve_project_manifest,
    resolve_project_manifest_path,
)
from .requirements_checker import check_requirements
from .requirements_loader import load_and_filter_requirements
from .source_resolver import ResolvedSource, resolve_sources
from .state_store import StateStore
from .track_write import (
    DELETE,
    WriteSpec,
    _dump_structured,
    _is_full_file_target,
    _parse_structured,
    _should_use_full_file_text,
    apply_marker_block,
    remove_marker_block,
)

PLAN_SCHEMA_VERSION = 1


class PlanSource(BaseModel):
    alias: str
    source: str
    version: str | None = None
    kind: str
    fingerprint: str
    portability_warning: str | None = None


class PlanAction(BaseModel):
    action: str
    source_alias: str
    kind: str
    resource: str
    target: str
    target_key: str
    secret_backed: bool = False
    composable: bool = False


class ApplyPlan(BaseModel):
    schema_version: int = PLAN_SCHEMA_VERSION
    created_at: str
    project_root: str
    manifest_path: str
    manifest_fingerprint: str
    sources: list[PlanSource] = Field(default_factory=list)
    selections: dict[str, list[str]] = Field(default_factory=dict)
    settings: dict[str, Any] = Field(default_factory=dict)
    actions: list[PlanAction] = Field(default_factory=list)


@dataclass(frozen=True)
class PlanContext:
    plan: ApplyPlan
    manifest: ProjectManifest
    resolved_sources: dict[str, ResolvedSource]
    mcp_manifest: dict
    runtime_env: RuntimeEnv
    secrets: dict


def default_plan_path(project_root: Path) -> Path:
    return project_root / ".ai-sync" / "last-plan.yaml"


def save_plan(plan: ApplyPlan, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(plan.model_dump(), sort_keys=False), encoding="utf-8")


def load_plan(path: Path) -> ApplyPlan:
    if not path.exists():
        raise RuntimeError(f"Plan file not found: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise RuntimeError(f"Failed to parse plan file {path}: {exc}") from exc
    return ApplyPlan.model_validate(data)


def build_plan_context(project_root: Path, config_root: Path | None, display: Display) -> PlanContext:
    manifest_path = resolve_project_manifest_path(project_root)
    manifest = resolve_project_manifest(project_root)
    manifest_hash = manifest_fingerprint(manifest_path)
    resolved_sources = resolve_sources(project_root, manifest)

    errors = validate_client_settings(manifest.settings)
    if errors:
        raise RuntimeError("\n".join(errors))

    mcp_manifest = load_and_filter_mcp(resolved_sources, manifest.mcp_servers, display)
    req_results = check_requirements(load_and_filter_requirements(resolved_sources, manifest.mcp_servers, display))
    for result in req_results:
        if not result.ok and result.error:
            display.print(f"Warning: {result.error}", style="warning")

    runtime_env = _load_runtime_env(project_root, resolved_sources, config_root)
    required_vars = collect_env_refs(mcp_manifest)
    missing = sorted(required_vars - runtime_env.env.keys())
    if missing:
        unfilled_local = [v for v in missing if v in runtime_env.unfilled_local_vars]
        undeclared = [v for v in missing if v not in runtime_env.unfilled_local_vars]
        parts: list[str] = []
        if unfilled_local:
            for name in unfilled_local:
                cfg = runtime_env.local_vars.get(name)
                hint = f" ({cfg.description})" if cfg and cfg.description else ""
                parts.append(
                    f"{name}{hint} is local-scoped. "
                    f"Set its value in {project_root / '.env.ai-sync'} and re-run."
                )
        if undeclared:
            parts.append(
                "MCP config references env vars not defined in any selected source env.yaml: "
                + ", ".join(undeclared)
            )
        raise RuntimeError("\n".join(parts))
    if required_vars:
        resolved_mcp_manifest = resolve_env_refs_in_obj(mcp_manifest, runtime_env.env)
        if not isinstance(resolved_mcp_manifest, dict):
            raise RuntimeError("Resolved MCP manifest must remain a mapping.")
        mcp_manifest = resolved_mcp_manifest

    plan = _build_plan(
        project_root,
        manifest_path,
        manifest,
        manifest_hash,
        resolved_sources,
        runtime_env,
        mcp_manifest,
        display,
    )
    return PlanContext(
        plan=plan,
        manifest=manifest,
        resolved_sources=resolved_sources,
        mcp_manifest=mcp_manifest,
        runtime_env=runtime_env,
        secrets={"servers": {}},
    )


def validate_saved_plan(path: Path, current: ApplyPlan) -> ApplyPlan:
    saved = load_plan(path)
    if saved.schema_version != PLAN_SCHEMA_VERSION:
        raise RuntimeError(
            f"Plan file schema version {saved.schema_version} is not supported by this ai-sync version."
        )
    if _normalized_plan(saved) != _normalized_plan(current):
        raise RuntimeError(
            "Saved plan is no longer valid. Regenerate it because the manifest, sources, or planned actions changed."
        )
    return saved


def render_plan(plan: ApplyPlan, display: Display) -> None:
    display.print("")
    display.rule("Planned Sources", style="info")
    source_rows = [
        (
            source.alias,
            source.kind,
            source.version or "local",
            source.fingerprint[:12],
        )
        for source in plan.sources
    ]
    if source_rows:
        display.table(("Alias", "Kind", "Version", "Fingerprint"), source_rows)
    else:
        display.print("No sources selected", style="dim")

    warnings = [s for s in plan.sources if s.portability_warning]
    for source in warnings:
        display.print(f"Warning: {source.alias}: {source.portability_warning}", style="warning")

    display.print("")
    display.rule("Planned Actions", style="info")
    action_rows = [
        (
            action.action,
            action.kind,
            action.resource,
            action.target + (" (secret)" if action.secret_backed else ""),
        )
        for action in plan.actions
    ]
    if action_rows:
        display.table(("Action", "Kind", "Resource", "Target"), action_rows)
    else:
        display.print("No planned actions", style="dim")


def _normalized_plan(plan: ApplyPlan) -> dict[str, Any]:
    data = plan.model_dump()
    data.pop("created_at", None)
    return data


# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------


def _classify_text_specs(file_path: Path, specs: list[WriteSpec], store: StateStore) -> str:
    original = file_path.read_text(encoding="utf-8") if file_path.exists() else ""
    content = original
    if _should_use_full_file_text(specs):
        for spec in specs:
            if spec.value is DELETE:
                entry = store.get_entry(file_path, "text", spec.target) or {}
                baseline = entry.get("baseline", {}) if isinstance(entry, dict) else {}
                if baseline.get("exists"):
                    blob_id = baseline.get("blob_id")
                    if isinstance(blob_id, str):
                        restored = store.fetch_blob(blob_id)
                        content = restored if restored is not None else ""
                    else:
                        content = original
                else:
                    content = ""
            else:
                content = str(spec.value)
    else:
        for spec in specs:
            if spec.value is DELETE:
                content = remove_marker_block(content, spec.target, file_path)
            else:
                content = apply_marker_block(content, spec.target, str(spec.value), file_path)
    if content == original:
        return "unchanged"
    if not original and content:
        return "create"
    if original and not content:
        return "delete"
    return "update"


def _classify_structured_specs(file_path: Path, fmt: str, specs: list[WriteSpec]) -> str:
    raw = file_path.read_text(encoding="utf-8") if file_path.exists() else ""
    data: object = _parse_structured(raw, fmt)
    from .path_ops import delete_at_path, set_at_path

    for spec in specs:
        if spec.value is DELETE:
            data = delete_at_path(data, spec.target)
        else:
            data = set_at_path(data, spec.target, spec.value)
    new_content = _dump_structured(data, fmt)
    if new_content == raw:
        return "unchanged"
    if not raw and new_content:
        return "create"
    if raw and not new_content.strip():
        return "delete"
    return "update"


def _classify_plan_key_specs(specs: list[WriteSpec], store: StateStore) -> str:
    if not specs:
        return "unchanged"
    grouped: dict[tuple[str, str], list[WriteSpec]] = {}
    for spec in specs:
        grouped.setdefault((str(spec.file_path), spec.format), []).append(spec)
    statuses: list[str] = []
    for (file_path_str, fmt), file_specs in grouped.items():
        file_path = Path(file_path_str)
        if fmt == "text":
            statuses.append(_classify_text_specs(file_path, file_specs, store))
        else:
            statuses.append(_classify_structured_specs(file_path, fmt, file_specs))
    return _aggregate_status(statuses)


def _aggregate_status(statuses: list[str]) -> str:
    changed = [status for status in statuses if status != "unchanged"]
    if not changed:
        return "unchanged"
    if all(status == "create" for status in changed):
        return "create"
    if all(status == "delete" for status in changed):
        return "delete"
    return "update"


# ---------------------------------------------------------------------------
# Plan building
# ---------------------------------------------------------------------------


def _build_plan(
    project_root: Path,
    manifest_path: Path,
    manifest: ProjectManifest,
    manifest_hash: str,
    resolved_sources: dict[str, ResolvedSource],
    runtime_env: RuntimeEnv,
    mcp_manifest: dict,
    display: Display,
) -> ApplyPlan:
    clients = create_clients(project_root)

    source_models = [
        PlanSource(
            alias=source.alias,
            source=source.source,
            version=source.version,
            kind=source.kind,
            fingerprint=source.fingerprint,
            portability_warning=source.portability_warning,
        )
        for source in resolved_sources.values()
    ]

    artifacts = collect_artifacts(
        project_root=project_root,
        manifest=manifest,
        resolved_sources=resolved_sources,
        runtime_env=runtime_env,
        mcp_manifest=mcp_manifest,
        clients=clients,
        display=display,
    )

    store = StateStore(project_root)
    store.load()

    desired_targets: set[tuple[str, str, str]] = set()
    specs_by_plan_key: dict[str, list[WriteSpec]] = {}
    artifact_by_plan_key: dict[str, Artifact] = {}

    for artifact in artifacts:
        specs = artifact.resolve()
        artifact_by_plan_key[artifact.plan_key] = artifact
        for spec in specs:
            desired_targets.add((str(spec.file_path), spec.format, spec.target))
            specs_by_plan_key.setdefault(artifact.plan_key, []).append(spec)

    actions: list[PlanAction] = []
    for plan_key, specs in specs_by_plan_key.items():
        status = _classify_plan_key_specs(specs, store)
        if status == "unchanged":
            continue
        art = artifact_by_plan_key[plan_key]
        target_path = specs[0].file_path if specs else plan_key
        actions.append(PlanAction(
            action=status,
            source_alias=art.source_alias,
            kind=art.kind,
            resource=art.resource,
            target=str(target_path),
            target_key=plan_key,
            secret_backed=art.secret_backed,
        ))

    stale_actions = _build_stale_plan_actions(store, desired_targets)
    actions.extend(stale_actions)

    git_safety_actions = _build_git_safety_actions(
        project_root, bool(runtime_env.env) or bool(runtime_env.local_vars)
    )
    actions.extend(git_safety_actions)

    selections = {
        "agents": manifest.agents,
        "skills": manifest.skills,
        "commands": manifest.commands,
        "rules": manifest.rules,
        "mcp-servers": manifest.mcp_servers,
    }

    return ApplyPlan(
        created_at=datetime.now(UTC).isoformat(),
        project_root=str(project_root),
        manifest_path=str(manifest_path),
        manifest_fingerprint=manifest_hash,
        sources=sorted(source_models, key=lambda item: item.alias),
        selections=selections,
        settings=manifest.settings,
        actions=actions,
    )


def _build_stale_plan_actions(
    store: StateStore,
    desired_targets: set[tuple[str, str, str]],
) -> list[PlanAction]:
    desired_targets_by_file: dict[tuple[str, str], set[str]] = {}
    for file_path, fmt, target in desired_targets:
        desired_targets_by_file.setdefault((file_path, fmt), set()).add(target)

    stale_actions: list[PlanAction] = []
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

        kind = entry.get("kind", "unknown")
        resource = entry.get("resource", target)
        source_alias = entry.get("source_alias", "state")

        stale_actions.append(PlanAction(
            action="delete",
            source_alias=source_alias,
            kind=kind,
            resource=resource,
            target=file_path,
            target_key=file_path,
        ))
    return stale_actions


def _build_git_safety_actions(project_root: Path, has_env: bool) -> list[PlanAction]:
    actions: list[PlanAction] = []
    if has_env:
        hook_status = check_pre_commit_hook(project_root)
        if hook_status == "missing":
            actions.append(
                PlanAction(
                    action="create",
                    source_alias="project",
                    kind="git-safety",
                    resource="pre-commit hook",
                    target=".git/hooks/pre-commit",
                    target_key="git-safety:pre-commit-hook",
                )
            )
    return actions


def _load_runtime_env(
    project_root: Path,
    resolved_sources: dict[str, ResolvedSource],
    config_root: Path | None,
) -> RuntimeEnv:
    existing_env = read_existing_env_file(project_root)

    env: dict[str, str] = {}
    all_local_vars: dict[str, EnvVarConfig] = {}
    owners: dict[str, str] = {}
    scopes: dict[str, str] = {}

    for alias in sorted(resolved_sources):
        env_yaml = resolved_sources[alias].root / "env.yaml"
        if not env_yaml.exists():
            continue

        config = load_env_config(env_yaml)
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
            resolved = resolve_op_refs(global_values, config_root)
            env.update(resolved)

    unfilled = {name for name in all_local_vars if name not in env}

    return RuntimeEnv(env=env, local_vars=all_local_vars, unfilled_local_vars=unfilled)
