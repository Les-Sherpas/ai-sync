"""Service for gitignore and pre-commit hook safety checks."""

from __future__ import annotations

import stat
from pathlib import Path

import pathspec

SENSITIVE_PATHS = [
    ".cursor/*",
    ".codex/*",
    ".gemini/*",
    ".claude/*",
    ".mcp.json",
    "CLAUDE.md",
    ".ai-sync/sources/",
    ".ai-sync/state/",
    ".ai-sync/rules/",
    ".ai-sync/last-plan.yaml",
    ".ai-sync.local.yaml",
    ".env.ai-sync",
]

_HOOK_MARKER = "# ai-sync:pre-commit-guard"

_HOOK_SCRIPT = """\
#!/bin/sh
# ai-sync:pre-commit-guard -- DO NOT EDIT (managed by ai-sync)
if git diff --cached --name-only | grep -qx '.env.ai-sync'; then
    echo "BLOCKED: .env.ai-sync contains secrets and must not be committed."
    echo "Run: git reset HEAD .env.ai-sync"
    exit 1
fi
if [ -x "$(dirname "$0")/pre-commit.ai-sync-chain" ]; then
    exec "$(dirname "$0")/pre-commit.ai-sync-chain" "$@"
fi
"""


class GitSafetyService:
    """Encapsulate gitignore and pre-commit hook safety checks."""

    def check_gitignore(self, project_root: Path) -> list[str]:
        gitignore_path = project_root / ".gitignore"
        if not gitignore_path.exists():
            return list(SENSITIVE_PATHS)

        content = gitignore_path.read_text(encoding="utf-8")
        lines = content.splitlines()
        spec = pathspec.PathSpec.from_lines("gitignore", lines)

        uncovered: list[str] = []
        for sensitive_path in SENSITIVE_PATHS:
            test_path = sensitive_path.rstrip("/")
            if sensitive_path.endswith("/"):
                test_path_with_child = test_path + "/dummy"
                if not spec.match_file(test_path_with_child) and not spec.match_file(test_path):
                    uncovered.append(sensitive_path)
            else:
                if not spec.match_file(test_path):
                    uncovered.append(sensitive_path)
        return uncovered

    def find_git_entry(self, start: Path) -> Path | None:
        """Walk up from *start* looking for a ``.git`` entry (file or directory)."""
        current = start.resolve()
        while True:
            candidate = current / ".git"
            if candidate.exists():
                return candidate
            parent = current.parent
            if parent == current:
                return None
            current = parent

    def resolve_hooks_dir(self, project_root: Path) -> Path | None:
        """Return the git hooks directory for the repo containing *project_root*."""
        git_path = self.find_git_entry(project_root)
        if git_path is None:
            return None
        if git_path.is_dir():
            return git_path / "hooks"
        # .git file (worktree): parse to find the real gitdir
        try:
            content = git_path.read_text(encoding="utf-8").strip()
            if content.startswith("gitdir: "):
                gitdir = Path(content.removeprefix("gitdir: ").strip())
                if not gitdir.is_absolute():
                    gitdir = (git_path.parent / gitdir).resolve()
                return gitdir / "hooks"
        except OSError:
            pass
        return None

    def check_pre_commit_hook(self, project_root: Path) -> str:
        """Check the ai-sync pre-commit hook status."""
        hooks_dir = self.resolve_hooks_dir(project_root)
        if hooks_dir is None:
            return "not-git-repo"
        hook_path = hooks_dir / "pre-commit"
        if not hook_path.exists():
            return "missing"
        try:
            content = hook_path.read_text(encoding="utf-8")
        except OSError:
            return "missing"
        return "installed" if _HOOK_MARKER in content else "missing"

    def install_pre_commit_hook(self, project_root: Path) -> bool:
        """Install the ai-sync pre-commit hook, wrapping any existing hook."""
        hooks_dir = self.resolve_hooks_dir(project_root)
        if hooks_dir is None:
            return False
        hooks_dir.mkdir(parents=True, exist_ok=True)
        hook_path = hooks_dir / "pre-commit"
        chain_path = hooks_dir / "pre-commit.ai-sync-chain"

        if hook_path.exists():
            existing = hook_path.read_text(encoding="utf-8")
            if _HOOK_MARKER in existing:
                hook_path.write_text(_HOOK_SCRIPT, encoding="utf-8")
                self.make_executable(hook_path)
                return True
            if not chain_path.exists():
                hook_path.rename(chain_path)

        hook_path.write_text(_HOOK_SCRIPT, encoding="utf-8")
        self.make_executable(hook_path)
        return True

    def remove_pre_commit_hook(self, project_root: Path) -> bool:
        """Remove the ai-sync pre-commit hook and restore any chained original."""
        hooks_dir = self.resolve_hooks_dir(project_root)
        if hooks_dir is None:
            return False
        hook_path = hooks_dir / "pre-commit"
        chain_path = hooks_dir / "pre-commit.ai-sync-chain"

        if not hook_path.exists():
            return False
        try:
            content = hook_path.read_text(encoding="utf-8")
        except OSError:
            return False
        if _HOOK_MARKER not in content:
            return False

        hook_path.unlink()
        if chain_path.exists():
            chain_path.rename(hook_path)
        return True

    def make_executable(self, path: Path) -> None:
        current = path.stat().st_mode
        path.chmod(current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
