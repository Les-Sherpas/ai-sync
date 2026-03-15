"""Filesystem adapter for DI-friendly side-effect boundaries."""

from __future__ import annotations

import shutil
from pathlib import Path


class FileSystem:
    """Minimal filesystem operations used by services."""

    def exists(self, path: Path) -> bool:
        return path.exists()

    def is_dir(self, path: Path) -> bool:
        return path.is_dir()

    def mkdir(self, path: Path, *, parents: bool = False, exist_ok: bool = False) -> None:
        path.mkdir(parents=parents, exist_ok=exist_ok)

    def rmtree(self, path: Path, *, ignore_errors: bool = False) -> None:
        shutil.rmtree(path, ignore_errors=ignore_errors)

    def replace(self, src: Path, dest: Path) -> None:
        src.replace(dest)

    def read_bytes(self, path: Path) -> bytes:
        return path.read_bytes()

    def read_text(self, path: Path, *, encoding: str = "utf-8") -> str:
        return path.read_text(encoding=encoding)
