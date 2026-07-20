"""Tests for Comlink payload normalization (offline).

Sample values mirror the real Comlink schema: stat magnitudes are integers
scaled by 1e8 in `unscaledDecimalValue`; mod `definitionId` encodes
set/rarity/slot in its first three digits.
"""
from __future__ import annotations

from swgoh.sources.comlink import _parse_mod, _parse_unit

SQUARE = {
    "definitionId": "451",  # set=4 (Speed), rarity=5, slot=1 (Square)
    "level": 15,
    "tier": 5,
    "primaryStat": {"stat": {"unitStatId": 48, "unscaledDecimalValue": "630000"}},
    "secondaryStat": [
        {"statRolls": 1, "stat": {"unitStatId": 5, "unscaledDecimalValue": "400000000"}},
        {"statRolls": 1, "stat": {"unitStatId": 53, "unscaledDecimalValue": "1936000"}},
    ],
}

ARROW = {
    "definitionId": "452",  # set=4 (Speed), rarity=5, slot=2 (Arrow)
    "level": 15,
    "tier": 5,
    "primaryStat": {"stat": {"unitStatId": 5, "unscaledDecimalValue": "3000000000"}},
    "secondaryStat": [],
}


def test_mod_definition_id_decode():
    m = _parse_mod(SQUARE)
    assert m.set_name == "Speed"
    assert m.rarity == 5
    assert m.slot == 1
    assert m.slot_name == "Square"
    assert m.level == 15


def test_flat_and_percent_secondary_scaling():
    m = _parse_mod(SQUARE)
    by_name = {s.name: s for s in m.secondaries}
    # Flat speed: 400000000 / 1e8 == 4.0, not a percent.
    assert by_name["Speed"].value == 4.0
    assert by_name["Speed"].is_percent is False
    # Percent crit chance: 1936000 / 1e8 * 100 == 1.94%.
    assert by_name["Critical Chance"].value == 1.94
    assert by_name["Critical Chance"].is_percent is True


def test_percent_primary_scaling():
    m = _parse_mod(SQUARE)
    assert m.primary_name == "Offense"
    assert m.primary_value == 0.63  # 630000 / 1e8 * 100


def test_speed_arrow_primary_and_mod_speed():
    m = _parse_mod(ARROW)
    assert m.slot_name == "Arrow"
    assert m.primary_name == "Speed"
    assert m.primary_value == 30.0  # 3000000000 / 1e8
    assert m.speed == 30.0


def test_parse_unit_relic_offset_and_base_id():
    unit = _parse_unit(
        {
            "definitionId": "MACEWINDU:SEVEN_STAR",
            "currentRarity": 7,
            "currentLevel": 85,
            "currentTier": 13,
            "relic": {"currentTier": 4},  # relic level == 4 - 2 == 2
            "equippedStatMod": [ARROW],
        }
    )
    assert unit.base_id == "MACEWINDU"
    assert unit.gear_level == 13
    assert unit.relic_level == 2
    assert len(unit.mods) == 1
