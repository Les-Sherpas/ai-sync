"""Service for the apply command and managed-output reconciliation."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Callable, TextIO

from ai_sync.clients import Client
from ai_sync.services.config_store_service import ConfigStoreService
from ai_sync.services.display_service import DisplayService
from ai_sync.services.git_safety_service import GitSafetyService
from ai_sync.services.managed_output_service import ManagedOutputService
from ai_sync.services.plan_persistence_service import PlanPersistenceService
from ai_sync.services.project_locator_service import ProjectLocatorService
from ai_sync.services.tool_version_service import ToolVersionService

if TYPE_CHECKING:
    from ai_sync.data_classes.resolved_artifact_set import ResolvedArtifactSet
    from ai_sync.data_classes.runtime_env import RuntimeEnv
    from ai_sync.models import ApplyPlan
    from ai_sync.services.plan_service import PlanService


class ApplyService:
    """Apply resolved artifact specs and reconcile stale tracked entries."""

    def __init__(
        self,
        *,
        managed_output_service: ManagedOutputService,
        git_safety_service: GitSafetyService,
        plan_service: PlanService,
        plan_persistence_service: PlanPersistenceService,
        project_locator_service: ProjectLocatorService,
        config_store_service: ConfigStoreService,
        tool_version_service: ToolVersionService,
        stdin: TextIO | None = None,
        prompt_input: Callable[[str], str] = input,
    ) -> None:
        self._managed_output_service = managed_output_service
        self._git_safety_service = git_safety_service
        self._plan_service = plan_service
        self._plan_persistence_service = plan_persistence_service
        self._project_locator_service = project_locator_service
        self._config_store_service = config_store_service
        self._tool_version_service = tool_version_service
        self._stdin = sys.stdin if stdin is None else stdin
        self._prompt_input = prompt_input

    def run(self, *, config_root: Path, display: DisplayService, planfile: str | None) -> int:
        """Execute the apply command: assemble context, confirm, and apply."""
        if not self._ensure_installed(config_root, display):
            return 1

        project_root = self._project_locator_service.find_project_root()
        if project_root is None:
            display.panel(
                "No .ai-sync.local.yaml or .ai-sync.yaml found. Create one first.",
                title="No project",
                style="error",
            )
            return 1

        self._warn_on_client_version_drift(display)
        plan_context = self._plan_service.assemble_plan_context(
            project_root, config_root, display
        )

        if planfile:
            plan_to_apply = self._plan_persistence_service.validate_saved_plan(
                Path(planfile).expanduser(),
                plan_context.plan,
            )
            display.print(f"Validated saved plan: {planfile}", style="success")
        else:
            plan_to_apply = plan_context.plan
            display.print(
                "Applying a fresh plan computed from the current project state.", style="info"
            )

        self._plan_persistence_service.render_plan(plan_to_apply, display)
        if not self.confirm_plan_deletions(plan_to_apply, display):
            return 1

        return self.run_apply(
            project_root=project_root,
            resolved_artifacts=plan_context.resolved_artifacts,
            runtime_env=plan_context.runtime_env,
            display=display,
        )

    def run_apply(
        self,
        *,
        project_root: Path,
        resolved_artifacts: ResolvedArtifactSet,
        runtime_env: RuntimeEnv,
        display: DisplayService,
    ) -> int:
        display.print("")
        display.rule("Starting Apply", style="info")
        secret_file_paths: set[Path] = set()

        for artifact, specs in resolved_artifacts.entries:
            if artifact.secret_backed:
                for spec in specs:
                    secret_file_paths.add(spec.file_path)

        self._managed_output_service.apply_resolved_artifacts(
            project_root=project_root,
            entries=resolved_artifacts.entries,
            desired_targets=resolved_artifacts.desired_targets,
        )

        for path in secret_file_paths:
            if path.exists():
                Client.set_restrictive_permissions(path)

        has_env = bool(runtime_env.env) or bool(runtime_env.local_vars)
        if has_env:
            installed = self._git_safety_service.install_pre_commit_hook(project_root)
            if installed:
                display.print("  Installed pre-commit hook guarding .env.ai-sync", style="info")

        display.print("")
        display.panel("Apply complete", title="Done", style="success")
        return 0

    def confirm_plan_deletions(self, plan: ApplyPlan, display: DisplayService) -> bool:
        delete_actions = [action for action in plan.actions if action.action == "delete"]
        if not delete_actions:
            return True

        display.print(
            f"Warning: plan includes {len(delete_actions)} deletion(s). Review before applying.",
            style="warning",
        )
        for action in delete_actions:
            display.print(
                f"  - {action.kind}: {action.resource} -> {action.target}",
                style="warning",
            )

        if not self._stdin.isatty():
            display.panel(
                "Refusing to apply deletions in non-interactive mode.\n"
                "Run interactively and confirm, or update the plan to remove deletions.",
                title="Deletion confirmation required",
                style="error",
            )
            return False

        answer = self._prompt_input("Continue with these deletions? [y/N]: ").strip().lower()
        if answer not in {"y", "yes"}:
            display.print("Apply cancelled by user.", style="warning")
            return False
        return True

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
