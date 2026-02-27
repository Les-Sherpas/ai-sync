"""Runtime requirement version checking."""

from __future__ import annotations

import shlex
from dataclasses import dataclass

from .models import Requirement
from .version_checks import VERSION_RE, run_command_capture_output


@dataclass
class RequirementCheckResult:
    name: str
    ok: bool
    actual: str | None
    required: str
    error: str | None = None


def _parse_version(v: str) -> tuple[int, int, int]:
    m = VERSION_RE.search(v)
    if m is None:
        raise ValueError(f"Cannot parse version from: {v!r}")
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def _satisfies(actual_tuple: tuple[int, int, int], constraint: str) -> bool:
    prefix = constraint[0]
    req_tuple = _parse_version(constraint[1:])
    if prefix == "~":
        upper = (req_tuple[0], req_tuple[1] + 1, 0)
        return actual_tuple >= req_tuple and actual_tuple < upper
    else:  # "^"
        upper = (req_tuple[0] + 1, 0, 0)
        return actual_tuple >= req_tuple and actual_tuple < upper


def check_requirements(requirements: list[Requirement]) -> list[RequirementCheckResult]:
    results: list[RequirementCheckResult] = []
    for req in requirements:
        name = req.name
        constraint = req.version.require

        if req.version.get_cmd is not None:
            try:
                cmd = shlex.split(req.version.get_cmd)
                output = run_command_capture_output(cmd)
            except (ValueError, OSError) as exc:
                results.append(
                    RequirementCheckResult(
                        name=name,
                        ok=False,
                        actual=None,
                        required=constraint,
                        error=f"{name}: invalid get_cmd \u2013 {exc}",
                    )
                )
                continue
        else:
            output = run_command_capture_output([name, "--version"])

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

        if _satisfies(actual_tuple, constraint):
            results.append(RequirementCheckResult(name=name, ok=True, actual=actual, required=constraint))
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
