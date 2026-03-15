"""Service for project source resolution."""

from __future__ import annotations

from pathlib import Path

from ai_sync.data_classes.resolved_source import ResolvedSource
from ai_sync.models import ProjectManifest, SourceConfig
from ai_sync.services.git_source_fetcher_service import GitSourceFetcherService
from ai_sync.services.source_fingerprint_service import SourceFingerprintService


class SourceResolverService:
    """Resolve manifest sources to local checked out directories."""

    def __init__(self, *, git_fetcher: GitSourceFetcherService, fingerprinter: SourceFingerprintService) -> None:
        self._git_fetcher = git_fetcher
        self._fingerprinter = fingerprinter

    def is_local_source(self, project_root: Path, source: str) -> bool:
        if source.startswith(("./", "../", "/", "~")):
            return True
        candidate = (project_root / source).expanduser()
        return candidate.exists()

    def resolve_sources(self, project_root: Path, manifest: ProjectManifest) -> dict[str, ResolvedSource]:
        sources_dir = project_root / ".ai-sync" / "sources"
        sources_dir.mkdir(parents=True, exist_ok=True)

        resolved: dict[str, ResolvedSource] = {}
        for alias, cfg in manifest.sources.items():
            resolved[alias] = self.resolve_source(project_root, sources_dir, alias, cfg)
        return resolved

    def resolve_source(self, project_root: Path, sources_dir: Path, alias: str, cfg: SourceConfig) -> ResolvedSource:
        if self.is_local_source(project_root, cfg.source):
            root = self.resolve_local_source(project_root, cfg.source)
            if not root.is_dir():
                raise RuntimeError(
                    f"Local source {cfg.source!r} for alias {alias!r} does not exist or is not a directory."
                )
            return ResolvedSource(
                alias=alias,
                source=cfg.source,
                version=cfg.version,
                root=root,
                kind="local",
                fingerprint=self._fingerprinter.fingerprint_path(root),
                portability_warning="Local path source; portability depends on the current machine state.",
            )

        if not cfg.version:
            raise RuntimeError(f"Remote source {cfg.source!r} for alias {alias!r} must define a pinned version.")

        root = sources_dir / alias
        self._git_fetcher.clone_remote_source(cfg.source, cfg.version, root)
        return ResolvedSource(
            alias=alias,
            source=cfg.source,
            version=cfg.version,
            root=root,
            kind="remote",
            fingerprint=self._fingerprinter.git_head_or_fingerprint(root),
        )

    def resolve_local_source(self, project_root: Path, source: str) -> Path:
        return (Path(source).expanduser() if source.startswith("~") else (project_root / source)).resolve()
