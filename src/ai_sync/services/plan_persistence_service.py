"""Service for plan persistence, validation, and rendering."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ai_sync.models import PLAN_SCHEMA_VERSION, ApplyPlan
from ai_sync.services.display_service import DisplayService


class PlanPersistenceService:
    """Persist, validate, and render computed apply plans."""

    def default_plan_path(self, project_root: Path) -> Path:
        return project_root / ".ai-sync" / "last-plan.yaml"

    def save_plan(self, plan: ApplyPlan, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(plan.model_dump(), sort_keys=False), encoding="utf-8")

    def load_plan(self, path: Path) -> ApplyPlan:
        if not path.exists():
            raise RuntimeError(f"Plan file not found: {path}")
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise RuntimeError(f"Failed to parse plan file {path}: {exc}") from exc
        return ApplyPlan.model_validate(data)

    def validate_saved_plan(self, path: Path, current: ApplyPlan) -> ApplyPlan:
        saved = self.load_plan(path)
        if saved.schema_version != PLAN_SCHEMA_VERSION:
            raise RuntimeError(
                f"Plan file schema version {saved.schema_version} is not supported by this ai-sync version."
            )
        if self._normalized_plan(saved) != self._normalized_plan(current):
            raise RuntimeError(
                "Saved plan is no longer valid. Regenerate it because the manifest, "
                "sources, or planned actions changed."
            )
        return saved

    def render_plan(self, plan: ApplyPlan, display: DisplayService) -> None:
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

    @staticmethod
    def _normalized_plan(plan: ApplyPlan) -> dict[str, Any]:
        data = plan.model_dump()
        data.pop("created_at", None)
        return data
