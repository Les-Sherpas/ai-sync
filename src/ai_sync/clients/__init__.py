"""Client adapters for Codex, Cursor, Gemini, Claude."""

from pathlib import Path

from .base import Client
from .claude import ClaudeClient
from .codex import CodexClient
from .cursor import CursorClient
from .gemini import GeminiClient


class ClientFactory:
    """Create all supported client adapters for a project root."""

    def create_clients(self, project_root: Path) -> list[Client]:
        return [
            CodexClient(project_root),
            CursorClient(project_root),
            GeminiClient(project_root),
            ClaudeClient(project_root),
        ]


__all__ = [
    "Client",
    "ClaudeClient",
    "CodexClient",
    "CursorClient",
    "GeminiClient",
    "ClientFactory",
]
