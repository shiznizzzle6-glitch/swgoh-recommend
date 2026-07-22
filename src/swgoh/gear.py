"""Gear reference lookup, backed by gear_names.json + gear_requirements.json.

Static game data: human names for gear pieces, and the 6 pieces each character
needs at every gear tier (1-12; swgoh.gg doesn't list the G12->G13 step).

Regenerate with `python scripts/refresh_gear.py <dir_with_swgoh_gg_json>`.
"""
from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources

MAX_TIER_WITH_PIECES = 12  # swgoh.gg gear_levels stops here


def _load(name: str) -> dict:
    try:
        text = resources.files("swgoh.data").joinpath(name).read_text("utf-8")
        return json.loads(text)
    except (FileNotFoundError, ValueError, ModuleNotFoundError):
        return {}


@lru_cache(maxsize=1)
def gear_names() -> dict[str, str]:
    return _load("gear_names.json")


@lru_cache(maxsize=1)
def gear_requirements() -> dict[str, dict[str, list[str]]]:
    return _load("gear_requirements.json")


def gear_name(base_id: str) -> str:
    return gear_names().get(base_id, base_id)


def gear_for_tier(char_base_id: str, tier: int) -> list[str]:
    """Gear piece base_ids required at `tier` for a character (empty if unknown)."""
    return list(gear_requirements().get(char_base_id, {}).get(str(tier), []))


def next_tier_pieces(char_base_id: str, current_gear_level: int) -> list[str]:
    """Named gear pieces needed to reach the next tier (empty past tier 12)."""
    return [gear_name(g) for g in gear_for_tier(char_base_id, current_gear_level + 1)]
