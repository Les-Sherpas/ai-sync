"""Read a value from structured data at a path."""

from __future__ import annotations

from ai_sync.helpers.split_path import split_path


def get_at_path(data: object, path: str) -> object:
    if path == "/":
        return data
    parts = split_path(path)
    cur: object = data
    for part in parts:
        if isinstance(cur, dict):
            if part not in cur:
                raise KeyError(path)
            cur = cur[part]
        elif isinstance(cur, list):
            idx = int(part)
            if idx >= len(cur):
                raise KeyError(path)
            cur = cur[idx]
        else:
            raise KeyError(path)
    return cur
