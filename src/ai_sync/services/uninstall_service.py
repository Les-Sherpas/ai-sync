"""Service for the uninstall command."""

from __future__ import annotations

from pathlib import Path

from ai_sync.services.display_service import DisplayService
from ai_sync.services.git_safety_service import GitSafetyService
from ai_sync.services.managed_output_service import ManagedOutputService
from ai_sync.services.project_locator_service import ProjectLocatorService


class UninstallService:
    """Orchestrate uninstall: delegate restoration to ManagedOutputService, then clean up."""

    def __init__(
        self,
        *,
        git_safety_service: GitSafetyService,
        project_locator_service: ProjectLocatorService,
        managed_output_service: ManagedOutputService,
    ) -> None:
        self._git_safety_service = git_safety_service
        self._project_locator_service = project_locator_service
        self._managed_output_service = managed_output_service

    def run(self, *, display: DisplayService, apply: bool) -> int:
        """Execute the uninstall command: locate project and restore baselines."""
        project_root = self._project_locator_service.find_project_root()
        if project_root is None:
            display.panel(
                "No .ai-sync.local.yaml or .ai-sync.yaml found. Nothing to uninstall.",
                title="No project",
                style="error",
            )
            return 1
        return self.run_uninstall(project_root, apply=apply)

    def run_uninstall(self, project_root: Path, *, apply: bool) -> int:
        has_state, did_change = self._managed_output_service.uninstall_project_outputs(
            project_root=project_root,
            apply=apply,
        )
        if not has_state:
            print("No ai-sync state found.")
            return 0

        if apply:
            if self._git_safety_service.remove_pre_commit_hook(project_root):
                print("Removed ai-sync pre-commit hook.")
            print("ai-sync state removed.")
        if not apply:
            print("Dry run complete. Use --apply to make changes.")
        if did_change:
            print("ai-sync uninstall complete.")
        else:
            print("No tracked changes found to remove.")
        return 0
