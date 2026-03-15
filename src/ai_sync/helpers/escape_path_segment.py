"""Escape a path segment for structured path usage."""

from __future__ import annotations

from jsonpointer import JsonPointer


def escape_path_segment(segment: str) -> str:
    raw = JsonPointer.from_parts([str(segment)]).path
    return raw[1:] if raw.startswith("/") else raw
