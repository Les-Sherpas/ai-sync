"""Resolved artifact set dataclass."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai_sync.data_classes.artifact import Artifact
    from ai_sync.data_classes.write_spec import WriteSpec


@dataclass(frozen=True)
class ResolvedArtifactSet:
    """Artifacts paired with resolved WriteSpecs, computed once."""

    entries: list[tuple["Artifact", list["WriteSpec"]]]
    desired_targets: set[tuple[str, str, str]]
