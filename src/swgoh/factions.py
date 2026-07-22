"""Character/ship faction & category lookup, backed by unit_factions.json.

swgoh.gg calls these `categories`: a mix of factions (Empire, Nightsister,
Bounty Hunter), traits (Scoundrel, Droid) and role tags (Leader). We keep them
all under one lookup — consumers filter to what they need.

Regenerate with `python scripts/refresh_factions.py <dir_with_swgoh_gg_json>`.
"""
from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources


@lru_cache(maxsize=1)
def faction_map() -> dict[str, list[str]]:
    try:
        text = resources.files("swgoh.data").joinpath("unit_factions.json").read_text("utf-8")
        return json.loads(text)
    except (FileNotFoundError, ValueError, ModuleNotFoundError):
        return {}


def factions_of(base_id: str) -> list[str]:
    """All category tags for a unit (empty list if unknown)."""
    return list(faction_map().get(base_id, []))


def has_faction(base_id: str, faction: str) -> bool:
    return faction in faction_map().get(base_id, [])


@lru_cache(maxsize=1)
def _reverse_index() -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for base_id, cats in faction_map().items():
        for cat in cats:
            index.setdefault(cat, []).append(base_id)
    return index


def units_with_faction(faction: str) -> list[str]:
    """All unit base_ids tagged with `faction`."""
    return list(_reverse_index().get(faction, []))


def all_factions() -> set[str]:
    return set(_reverse_index().keys())
