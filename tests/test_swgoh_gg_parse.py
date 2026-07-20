"""Tests for swgoh.gg payload normalization (offline, no network)."""
from __future__ import annotations

from swgoh.sources.swgoh_gg import _parse_mod, _parse_unit

SAMPLE_UNIT = {
    "data": {
        "base_id": "DARTHVADER",
        "name": "Darth Vader",
        "rarity": 7,
        "level": 85,
        "gear_level": 13,
        "relic_tier": 9,  # -> relic level 7
        "power": 34000,
        "mods": [
            {
                "slot": 1,  # 0-indexed arrow in swgoh.gg -> becomes slot 2
                "set": 4,
                "rarity": 6,
                "level": 15,
                "tier": 5,
                "primary_stat": {"name": "Speed", "display_value": "30"},
                "secondary_stats": [
                    {"name": "Offense", "display_value": "1.5%", "roll": 3},
                    {"name": "Speed", "display_value": "11", "roll": 4},
                ],
            }
        ],
    }
}


def test_parse_unit_maps_core_fields():
    unit = _parse_unit(SAMPLE_UNIT)
    assert unit is not None
    assert unit.base_id == "DARTHVADER"
    assert unit.stars == 7
    assert unit.gear_level == 13
    assert unit.relic_level == 7  # relic_tier 9 - 2


def test_parse_mod_slot_reindex_and_set_name():
    mod = _parse_mod(SAMPLE_UNIT["data"]["mods"][0])
    assert mod is not None
    assert mod.slot == 2          # 0-indexed 1 -> 1-indexed 2 (Arrow)
    assert mod.slot_name == "Arrow"
    assert mod.set_name == "Speed"
    assert mod.primary_name == "Speed"
    assert mod.primary_value == 30.0


def test_parse_mod_secondary_speed_and_percent():
    mod = _parse_mod(SAMPLE_UNIT["data"]["mods"][0])
    names = {s.name: s for s in mod.secondaries}
    assert names["Speed"].value == 11.0
    assert names["Speed"].is_percent is False
    assert names["Offense"].is_percent is True
    # Mod speed = primary (30, it's the arrow) + secondary (11)
    assert mod.speed == 41.0
