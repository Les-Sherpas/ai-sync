"""Service for plan context assembly and the plan command."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from ai_sync.data_classes.plan_context import PlanContext
from ai_sync.services.config_store_service import ConfigStoreService
from ai_sync.services.display_service import DisplayService
from ai_sync.services.environment_service import EnvironmentService
from ai_sync.services.mcp_server_service import McpServerService
from ai_sync.services.plan_builder_service import PlanBuilderService
from ai_sync.services.plan_persistence_service import PlanPersistenceService
from ai_sync.services.project_locator_service import ProjectLocatorService
from ai_sync.services.project_manifest_service import ProjectManifestService
from ai_sync.services.source_resolver_service import SourceResolverService
from ai_sync.services.tool_requirement_service import ToolRequirementService
from ai_sync.services.tool_version_service import ToolVersionService


class PlanService:
    """Assemble plan context and handle the plan command."""

    def __init__(
        self,
        *,
        source_resolver_service: SourceResolverService,
        environment_service: EnvironmentService,
        project_locator_service: ProjectLocatorService,
        project_manifest_service: ProjectManifestService,
        mcp_server_service: McpServerService,
        tool_requirement_service: ToolRequirementService,
        plan_builder_service: PlanBuilderService,
        plan_persistence_service: PlanPersistenceService,
        config_store_service: ConfigStoreService,
        tool_version_service: ToolVersionService,
        validate_client_settings_fn: Callable[[dict[str, Any]], list[str]] | None = None,
    ) -> None:
        from ai_sync.helpers import validate_client_settings

        self._source_resolver_service = source_resolver_service
        self._project_locator_service = project_locator_service
        self._project_manifest_service = project_manifest_service
        self._mcp_server_service = mcp_server_service
        self._tool_requirement_service = tool_requirement_service
        self._plan_builder_service = plan_builder_service
        self._plan_persistence_service = plan_persistence_service
        self._config_store_service = config_store_service
        self._tool_version_service = tool_version_service
        self._validate_client_settings = validate_client_settings_fn or validate_client_settings
        self._environment_service = environment_service

    def run(self, *, config_root: Path, display: DisplayService, out: str | None) -> int:
        """Execute the plan command: assemble context, render, and save."""
        prepared = self._prepare_project_context(config_root=config_root, display=display)
        if prepared is None:
            return 1
        project_root, plan_context = prepared

        self._plan_persistence_service.render_plan(plan_context.plan, display)
        out_path = (
            Path(out).expanduser()
            if out
            else self._plan_persistence_service.default_plan_path(project_root)
        )
        self._plan_persistence_service.save_plan(plan_context.plan, out_path)
        display.print(f"Saved plan to {out_path}", style="success")
        return 0

    def assemble_plan_context(
        self, project_root: Path, config_root: Path | None, display: DisplayService
    ) -> PlanContext:
        """Build PlanContext inputs and delegate action planning to PlanBuilderService."""
        manifest_path = self._project_manifest_service.resolve_project_manifest_path(project_root)
        manifest = self._project_manifest_service.resolve_project_manifest(project_root)
        manifest_hash = self._project_manifest_service.manifest_fingerprint(manifest_path)
        resolved_sources = self._source_resolver_service.resolve_sources(project_root, manifest)

        errors = self._validate_client_settings(manifest.settings)
        if errors:
            raise RuntimeError("\n".join(errors))

        mcp_manifest = self._mcp_server_service.load_and_filter_mcp(
            resolved_sources, manifest.mcp_servers, display
        )
        req_results = self._tool_requirement_service.check_requirements(
            self._tool_requirement_service.load_and_filter_requirements(
                resolved_sources,
                manifest.mcp_servers,
                display,
            )
        )
        for result in req_results:
            if not result.ok and result.error:
                display.print(f"Warning: {result.error}", style="warning")

        runtime_env = self._environment_service.resolve_runtime_env(
            project_root,
            resolved_sources,
            config_root,
        )
        required_vars = self._mcp_server_service.collect_env_refs(mcp_manifest)
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
            resolved_mcp_manifest = self._mcp_server_service.resolve_env_refs(
                mcp_manifest, runtime_env.env
            )
            if not isinstance(resolved_mcp_manifest, dict):
                raise RuntimeError("Resolved MCP manifest must remain a mapping.")
            mcp_manifest = resolved_mcp_manifest

        plan, resolved_artifact_set = self._plan_builder_service.build_plan(
            project_root,
            manifest_path,
            manifest,
            manifest_hash,
            resolved_sources,
            runtime_env,
            mcp_manifest,
        )
        return PlanContext(
            plan=plan,
            manifest=manifest,
            resolved_sources=resolved_sources,
            mcp_manifest=mcp_manifest,
            runtime_env=runtime_env,
            secrets={"servers": {}},
            resolved_artifacts=resolved_artifact_set,
        )

    def _prepare_project_context(
        self,
        *,
        config_root: Path,
        display: DisplayService,
    ) -> tuple[Path, PlanContext] | None:
        if not self._ensure_installed(config_root, display):
            return None

        project_root = self._project_locator_service.find_project_root()
        if project_root is None:
            display.panel(
                "No .ai-sync.local.yaml or .ai-sync.yaml found. Create one first.",
                title="No project",
                style="error",
            )
            return None

        self._warn_on_client_version_drift(display)
        context = self.assemble_plan_context(project_root, config_root, display)
        return (project_root, context)

    def _ensure_installed(self, config_root: Path, display: DisplayService) -> bool:
        if config_root.exists() and (config_root / "config.toml").exists():
            return True
        display.panel("Run `ai-sync install` first.", title="Not set up", style="error")
        return False

    def _warn_on_client_version_drift(self, display: DisplayService) -> None:
        versions_path = self._tool_version_service.get_default_versions_path()
        ok, message = self._tool_version_service.check_client_versions(versions_path)
        if not ok or message != "OK":
            display.print(f"Warning: {message}", style="warning")
