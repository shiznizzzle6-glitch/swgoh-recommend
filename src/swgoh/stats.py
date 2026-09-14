"""Unmodded Speed per unit, backed by base_speed.json.

Comlink computes no stats, so the unmodded half of a unit's Speed comes from a
swgoh.gg roster export (see scripts/refresh_base_speed.py). The modded half is
always read live from the player's equipped mods, so the total is only as stale
as the unit's gear/relic level — not as stale as its mods.

`base_speed` returns None for a unit the export didn't cover, and callers are
expected to say so rather than quietly treating it as zero.
"""
from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources

from .models import Unit


@lru_cache(maxsize=1)
def _data() -> dict:
    try:
        text = resources.files("swgoh.data").joinpath("base_speed.json").read_text("utf-8")
        return json.loads(text)
    except (FileNotFoundError, ValueError, ModuleNotFoundError):
        return {}


def base_speed(base_id: str) -> int | None:
    """Unmodded Speed, or None if this unit isn't in the export."""
    return (_data().get("speeds") or {}).get(base_id)


def covered_units() -> int:
    return len((_data().get("speeds") or {}))


def mod_speed(unit: Unit) -> float:
    """Speed contributed by equipped mods — always live, never from the export."""
    return sum(m.speed for m in unit.mods)


def total_speed(unit: Unit) -> float | None:
    """Base + mods, or None when base Speed is unknown for this unit."""
    base = base_speed(unit.base_id)
    if base is None:
        return None
    return base + mod_speed(unit)
