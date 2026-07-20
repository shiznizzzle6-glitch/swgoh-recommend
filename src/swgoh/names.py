"""base_id -> display name lookup, backed by the bundled unit_names.json.

Regenerate the data with `python scripts/refresh_unit_names.py <comlink_url>`.
"""
from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources


@lru_cache(maxsize=1)
def name_map() -> dict[str, str]:
    try:
        text = resources.files("swgoh.data").joinpath("unit_names.json").read_text("utf-8")
        return json.loads(text)
    except (FileNotFoundError, ValueError, ModuleNotFoundError):
        return {}


def display_name(base_id: str) -> str:
    """Friendly name for a base_id, falling back to a prettified id."""
    mapped = name_map().get(base_id)
    if mapped:
        return mapped
    return base_id.replace("_", " ").title()
