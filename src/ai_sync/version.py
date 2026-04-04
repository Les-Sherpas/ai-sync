"""Runtime version discovery for ai-sync."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version


def get_ai_sync_version() -> str:
    """Return the installed ai-sync version, or '0.0.0' if not installed."""
    try:
        return version("ai-sync")
    except PackageNotFoundError:
        return "0.0.0"
