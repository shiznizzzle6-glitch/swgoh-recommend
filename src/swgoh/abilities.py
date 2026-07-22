"""Zeta/Omicron/Ultimate ability definitions, backed by ability_data.json.

Static game data (which abilities carry a zeta/omicron/ultimate, their max tier,
and which game modes an omicron applies to). Learned status is NOT stored here —
it's computed live from Comlink skill tiers via `is_learned`.

Regenerate with `python scripts/refresh_abilities.py <dir_with_swgoh_gg_json>`.
"""
from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources


@lru_cache(maxsize=1)
def ability_defs() -> dict[str, dict]:
    try:
        text = resources.files("swgoh.data").joinpath("ability_data.json").read_text("utf-8")
        return json.loads(text)
    except (FileNotFoundError, ValueError, ModuleNotFoundError):
        return {}


@lru_cache(maxsize=1)
def _by_char() -> dict[str, list[dict]]:
    index: dict[str, list[dict]] = {}
    for base_id, d in ability_defs().items():
        entry = {"id": base_id, **d}
        index.setdefault(d["char"], []).append(entry)
    return index


def abilities_for(char_base_id: str) -> list[dict]:
    """Zeta/omicron/ultimate ability defs belonging to a character."""
    return list(_by_char().get(char_base_id, []))


def zeta_tier(defn: dict) -> int:
    """Tier at which the zeta is learned (one below max if the ability also omicrons)."""
    return defn["max"] - 1 if defn.get("o") else defn["max"]


def is_zeta_learned(defn: dict, current_tier: int) -> bool:
    return bool(defn.get("z")) and current_tier >= zeta_tier(defn)


def is_omicron_learned(defn: dict, current_tier: int) -> bool:
    return bool(defn.get("o")) and current_tier >= defn["max"]
