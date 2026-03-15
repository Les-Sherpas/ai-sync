"""Service for computing source fingerprints."""

from __future__ import annotations

import subprocess
from pathlib import Path

from ai_sync.adapters.filesystem import FileSystem
from ai_sync.adapters.process_runner import ProcessRunner

DEFAULT_SKIP_FINGERPRINT_PARTS = {".git", ".venv", "node_modules", "__pycache__", ".DS_Store"}


class SourceFingerprintService:
    """Compute source fingerprints with optional git optimization."""

    def __init__(
        self,
        *,
        process_runner: ProcessRunner,
        filesystem: FileSystem,
        skip_parts: set[str] | None = None,
    ) -> None:
        self._process_runner = process_runner
        self._filesystem = filesystem
        self._skip_parts = skip_parts or set(DEFAULT_SKIP_FINGERPRINT_PARTS)

    def git_head_or_fingerprint(self, root: Path) -> str:
        try:
            result = self._process_runner.run(
                ["git", "-C", str(root), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            )
            head = result.stdout.strip() if isinstance(result.stdout, str) else ""
            if head:
                return head
        except (OSError, subprocess.CalledProcessError):
            pass
        return self.fingerprint_path(root)

    def fingerprint_path(self, root: Path) -> str:
        import hashlib

        digest = hashlib.sha256()
        for path in sorted(root.rglob("*")):
            rel = path.relative_to(root)
            if any(part in self._skip_parts for part in rel.parts):
                continue
            digest.update(rel.as_posix().encode("utf-8"))
            if path.is_file():
                try:
                    digest.update(self._filesystem.read_bytes(path))
                except OSError as exc:
                    raise RuntimeError(f"Failed to read {path}: {exc}") from exc
        return digest.hexdigest()
