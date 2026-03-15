"""Service for loading, filtering, and validating runtime tool requirements."""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import TYPE_CHECKING, Mapping

import yaml
from pydantic import ValidationError

from ai_sync.data_classes.requirement_check_result import RequirementCheckResult
from ai_sync.models import Requirement, RequirementsManifest, split_scoped_ref
from ai_sync.services.display_service import DisplayService

from .tool_version_service import VERSION_RE, ToolVersionService

if TYPE_CHECKING:
    from ai_sync.data_classes.resolved_source import ResolvedSource


class ToolRequirementService:
    """Load selected requirements and validate them against local tool versions."""

    def __init__(self, *, version_check_service: ToolVersionService) -> None:
        self._version_check_service = version_check_service

    def load_requirements(self, repo_root: Path, display: DisplayService) -> list[Requirement]:
        requirements_path = repo_root / "requirements.yaml"
        if not requirements_path.exists():
            return []
        try:
            with open(requirements_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except (yaml.YAMLError, OSError) as exc:
            display.print(f"Failed to load {requirements_path}: {exc}", style="warning")
            return []
        try:
            model = RequirementsManifest.model_validate(data)
        except ValidationError as exc:
            raise RuntimeError(f"requirements.yaml validation failed: {exc}") from exc
        return model.requirements

    def load_and_filter_requirements(
        self,
        resolved_sources: Mapping[str, ResolvedSource],
        enabled_server_refs: list[str],
        display: DisplayService,
    ) -> list[Requirement]:
        selected_by_alias: dict[str, set[str]] = {}
        for ref in enabled_server_refs:
            alias, server_id = split_scoped_ref(ref)
            selected_by_alias.setdefault(alias, set()).add(server_id)

        merged: dict[str, Requirement] = {}
        for alias, server_ids in selected_by_alias.items():
            if alias not in resolved_sources:
                raise RuntimeError(f"Unknown source alias {alias!r} in requirements selection.")
            for req in self.load_requirements(resolved_sources[alias].root, display):
                if not (set(req.servers) & server_ids):
                    continue
                existing = merged.get(req.name)
                if existing is None:
                    merged[req.name] = req
                    continue
                if existing.version.model_dump() != req.version.model_dump():
                    raise RuntimeError(
                        f"Requirement collision for {req.name!r} across selected sources. "
                        "ai-sync does not merge conflicting requirement definitions."
                    )
                existing.servers = sorted(set(existing.servers) | set(req.servers))
        return list(merged.values())

    def check_requirements(
        self, requirements: list[Requirement]
    ) -> list[RequirementCheckResult]:
        results: list[RequirementCheckResult] = []
        for req in requirements:
            name = req.name
            constraint = req.version.require

            if req.version.get_cmd is not None:
                try:
                    cmd = shlex.split(req.version.get_cmd)
                    output = self._version_check_service.run_command_capture_output(cmd)
                except (ValueError, OSError) as exc:
                    results.append(
                        RequirementCheckResult(
                            name=name,
                            ok=False,
                            actual=None,
                            required=constraint,
                            error=f"{name}: invalid get_cmd – {exc}",
                        )
                    )
                    continue
            else:
                output = self._version_check_service.run_command_capture_output(
                    [name, "--version"]
                )

            match = VERSION_RE.search(output)
            if match is None:
                results.append(
                    RequirementCheckResult(
                        name=name,
                        ok=False,
                        actual=None,
                        required=constraint,
                        error=f"{name}: not found",
                    )
                )
                continue

            actual = f"{match.group(1)}.{match.group(2)}.{match.group(3)}"
            actual_tuple = (int(match.group(1)), int(match.group(2)), int(match.group(3)))

            if self._satisfies(actual_tuple, constraint):
                results.append(
                    RequirementCheckResult(
                        name=name, ok=True, actual=actual, required=constraint
                    )
                )
            else:
                results.append(
                    RequirementCheckResult(
                        name=name,
                        ok=False,
                        actual=actual,
                        required=constraint,
                        error=f"{name}: found {actual}, require {constraint}",
                    )
                )

        return results

    @staticmethod
    def _parse_version(version: str) -> tuple[int, int, int]:
        match = VERSION_RE.search(version)
        if match is None:
            raise ValueError(f"Cannot parse version from: {version!r}")
        return (int(match.group(1)), int(match.group(2)), int(match.group(3)))

    def _satisfies(
        self, actual_tuple: tuple[int, int, int], constraint: str
    ) -> bool:
        prefix = constraint[0]
        required_tuple = self._parse_version(constraint[1:])
        if prefix == "~":
            upper = (required_tuple[0], required_tuple[1] + 1, 0)
            return actual_tuple >= required_tuple and actual_tuple < upper

        upper = (required_tuple[0] + 1, 0, 0)
        return actual_tuple >= required_tuple and actual_tuple < upper
