"""Unit stats: unmodded values from the export, the mod half computed live.

Countering has two axes. Abilities are one — see `swgoh.recommend.counters`.
Stats are the other: a speed race is won on Speed and Critical Chance, an
unresistable effect makes Tenacity worthless, and a plan built on Ability Block
or Stun needs Potency to land. Mods are the lever you can actually pull between
battles, so the app needs to know where a unit's stats come from.

Comlink computes no stats (`unitStat` is null, no /stats route), so unmodded
values come from a swgoh.gg roster export (scripts/refresh_base_stats.py) while
the mod contribution is read from equipped mods on every request. The split
matters: base stats only move when a unit gains levels, gear or relics, but mods
change whenever you rearrange them.

`base_stat` returns None for a unit the export doesn't cover, and callers are
expected to say so rather than quietly treating it as zero.
"""
from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources

from .models import Unit

# Stats a counter plan can actually ask for, in display order.
TRACKED_STATS = (
    "Speed",
    "Potency",
    "Tenacity",
    "Critical Chance",
    "Protection",
    "Health",
    "Armor",
)

# Mod stat names that mean the same thing as a tracked stat.
MOD_STAT_ALIASES = {
    "Critical Chance": "Critical Chance",
    "Potency": "Potency",
    "Tenacity": "Tenacity",
    "Speed": "Speed",
    "Health": "Health",
    "Protection": "Protection",
    "Defense": "Armor",
}


@lru_cache(maxsize=1)
def _data() -> dict:
    try:
        text = resources.files("swgoh.data").joinpath("base_stats.json").read_text("utf-8")
        return json.loads(text)
    except (FileNotFoundError, ValueError, ModuleNotFoundError):
        return {}


def base_stats(base_id: str) -> dict[str, float] | None:
    """Every unmodded stat for a unit, or None if the export doesn't cover it."""
    return (_data().get("stats") or {}).get(base_id)


def base_stat(base_id: str, stat: str) -> float | None:
    stats = base_stats(base_id)
    return None if stats is None else stats.get(stat)


def base_speed(base_id: str) -> float | None:
    return base_stat(base_id, "Speed")


def covered_units() -> int:
    return len(_data().get("stats") or {})


def mod_stat(unit: Unit, stat: str) -> float:
    """What equipped mods contribute to one stat — always live, never from the export.

    Percentage mod stats (a +5.88% Health primary, say) are deliberately not
    converted into flat values: doing that needs the unit's base, which is the
    half that goes stale. Flat contributions (Speed, and secondaries) are exact,
    and Speed — the stat that decides turn order — is always flat.
    """
    total = 0.0
    for mod in unit.mods:
        if MOD_STAT_ALIASES.get(mod.primary_name) == stat:
            total += mod.primary_value
        for sec in mod.secondaries:
            if MOD_STAT_ALIASES.get(sec.name) == stat:
                total += sec.value
    return round(total, 2)


def mod_speed(unit: Unit) -> float:
    return mod_stat(unit, "Speed")


def total_stat(unit: Unit, stat: str) -> float | None:
    """Base + mods, or None when the base half is unknown for this unit."""
    base = base_stat(unit.base_id, stat)
    if base is None:
        return None
    return round(base + mod_stat(unit, stat), 2)


def total_speed(unit: Unit) -> float | None:
    return total_stat(unit, "Speed")
