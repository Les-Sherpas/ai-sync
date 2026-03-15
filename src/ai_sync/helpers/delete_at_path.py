"""Delete a value from structured data at a path."""

from __future__ import annotations

from ai_sync.helpers.split_path import split_path


def delete_at_path(data: object, path: str) -> object:
    if path == "/":
        return {}
    parts = split_path(path)
    if not parts:
        return data
    cur: object = data
    for idx, part in enumerate(parts[:-1]):
        if isinstance(cur, list):
            list_idx = int(part)
            while len(cur) <= list_idx:
                cur.append({})
            if not isinstance(cur[list_idx], (dict, list)):
                cur[list_idx] = {}
            cur = cur[list_idx]
            continue
        if not isinstance(cur, dict):
            return data
        if part not in cur or not isinstance(cur[part], (dict, list)):
            next_part = parts[idx + 1]
            if next_part.isdigit():
                raise ValueError(
                    f"Ambiguous path {path!r}: list container is not explicitly defined at {part!r}"
                )
            cur[part] = {}
        cur = cur[part]
    last = parts[-1]
    if isinstance(cur, list):
        list_idx = int(last)
        if list_idx < len(cur):
            cur[list_idx] = None
    elif isinstance(cur, dict):
        cur.pop(last, None)
    return data
