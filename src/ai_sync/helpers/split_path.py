"""Split a structured path into component segments."""

from __future__ import annotations

from jsonpointer import JsonPointer, JsonPointerException


def split_path(path: str) -> list[str]:
    if path == "" or path == "/":
        return []
    if not path.startswith("/"):
        raise ValueError(f"Invalid path: {path}")
    try:
        return list(JsonPointer(path).get_parts())
    except JsonPointerException as exc:
        raise ValueError(f"Invalid path: {path}") from exc
