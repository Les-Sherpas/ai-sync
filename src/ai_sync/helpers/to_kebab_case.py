"""Convert names to kebab-case."""

from __future__ import annotations

import re


def to_kebab_case(name: str) -> str:
    return re.sub(r"[_ ]+", "-", name).lower()
