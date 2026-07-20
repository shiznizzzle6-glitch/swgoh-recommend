"""Tests for the mod analyzer."""
from __future__ import annotations

from swgoh.models import Unit
from swgoh.recommend.mods import analyze_roster, load_priority_config


def _cfg():
    return {
        "DARTHVADER": {"weight": 2.0, "arrow": "Speed", "sets": ["Speed", "Critical Chance"]},
        "GRANDADMIRALTHRAWN": {"weight": 2.0, "arrow": "Speed", "sets": ["Speed", "Potency"]},
    }


def test_bundled_priority_config_loads():
    cfg = load_priority_config()
    assert "DARTHVADER" in cfg
    assert cfg["DARTHVADER"]["arrow"] == "Speed"


def test_well_modded_unit_has_no_issues(well_modded_vader):
    from swgoh.models import Player

    report = analyze_roster(Player("c", "1", [well_modded_vader]), _cfg())
    vader = report.unit_reports[0]
    assert vader.is_priority
    assert vader.issues == []
    assert vader.total_speed == 57.0  # 30 + 12 + 9 + 6


def test_badly_modded_unit_flags_expected_issues(badly_modded_thrawn):
    from swgoh.models import Player

    report = analyze_roster(Player("c", "1", [badly_modded_thrawn]), _cfg())
    thrawn = report.unit_reports[0]
    kinds = {i.kind for i in thrawn.issues}
    assert "missing_mod" in kinds       # only 5/6 mods
    assert "unleveled" in kinds         # a level-9 mod
    assert "low_rarity" in kinds        # a 4-dot mod
    assert "arrow_primary" in kinds     # Protection arrow, not Speed
    assert "set_mismatch" in kinds      # no Speed/Potency sets completed


def test_low_gear_non_priority_units_are_ignored(player):
    report = analyze_roster(player, _cfg())
    base_ids = {r.unit.base_id for r in report.unit_reports}
    assert "JAWA" not in base_ids
    assert {"DARTHVADER", "GRANDADMIRALTHRAWN"} <= base_ids


def test_ranking_puts_worse_priority_unit_first(player):
    report = analyze_roster(player, _cfg())
    # Thrawn is badly modded; Vader is clean. Thrawn should rank first.
    assert report.unit_reports[0].unit.base_id == "GRANDADMIRALTHRAWN"
    assert report.flagged_units[0].unit.base_id == "GRANDADMIRALTHRAWN"


def test_report_totals(player):
    report = analyze_roster(player, _cfg())
    assert report.total_mods == 11  # 6 (vader) + 5 (thrawn)
    assert report.unleveled_mods == 1
    assert report.low_rarity_mods == 1


def test_completed_sets_math():
    from tests.conftest import full_speed_arrow_mods

    u = Unit(base_id="X", name="X", mods=full_speed_arrow_mods())
    completed = u.completed_sets()
    assert "Speed" in completed          # 4 speed mods -> speed set
    assert "Critical Chance" in completed  # 2 crit mods -> crit set
