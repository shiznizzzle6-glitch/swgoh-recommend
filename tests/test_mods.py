"""Tests for the mod analyzer."""
from __future__ import annotations

from swgoh.models import Player, Unit
from swgoh.recommend.mods import analyze_roster, load_priority_config


def _cfg():
    return {
        "DARTHVADER": {"weight": 2.0, "arrow": "Speed", "sets": ["Speed", "Critical Chance"]},
        "GRANDADMIRALTHRAWN": {"weight": 2.0, "arrow": "Speed", "sets": ["Speed", "Potency"]},
        "GENERALSKYWALKER": {"weight": 2.0, "arrow": "Speed", "sets": ["Speed", "Health"]},
    }


def test_bundled_priority_config_loads():
    cfg = load_priority_config()
    assert "VADER" in cfg
    assert cfg["VADER"]["arrow"] == "Speed"


def test_well_modded_priority_unit_has_no_issues(well_modded_vader):
    report = analyze_roster(Player("c", "1", [well_modded_vader]), _cfg())
    vader = report.unit_reports[0]
    assert vader.is_priority
    assert vader.fully_modded
    assert vader.issues == []
    assert vader.total_speed == 57.0  # 30 + 12 + 9 + 6


def test_fully_modded_wrong_unit_flags_tuning_issues(wrong_modded_thrawn):
    report = analyze_roster(Player("c", "1", [wrong_modded_thrawn]), _cfg())
    thrawn = report.unit_reports[0]
    kinds = {i.kind for i in thrawn.issues}
    assert thrawn.fully_modded
    assert "arrow_primary" in kinds     # Protection arrow, not Speed
    assert "set_mismatch" in kinds      # no Speed/Potency sets completed
    assert "low_speed" in kinds         # zero speed from mods
    assert "undermodded" not in kinds   # it IS modded, just badly


def test_undermodded_unit_collapses_to_single_flag(undermodded_gas):
    report = analyze_roster(Player("c", "1", [undermodded_gas]), _cfg())
    gas = report.unit_reports[0]
    assert not gas.fully_modded
    assert len(gas.issues) == 1
    assert gas.issues[0].kind == "undermodded"


def test_nonpriority_undermodded_unit_excluded(nonprio_undermodded):
    report = analyze_roster(Player("c", "1", [nonprio_undermodded]), _cfg())
    assert report.unit_reports == []


def test_nonpriority_modded_with_issue_included(nonprio_modded_hermit):
    report = analyze_roster(Player("c", "1", [nonprio_modded_hermit]), _cfg())
    assert len(report.unit_reports) == 1
    hermit = report.unit_reports[0]
    assert not hermit.is_priority
    assert {i.kind for i in hermit.issues} == {"low_rarity"}


def test_ranking_and_flagging(player):
    report = analyze_roster(player, _cfg())
    # Badly-modded priority Thrawn (many high-severity issues x2 weight) tops it.
    assert report.unit_reports[0].unit.base_id == "GRANDADMIRALTHRAWN"
    flagged = [r.unit.base_id for r in report.flagged_units]
    assert flagged[0] == "GRANDADMIRALTHRAWN"
    # Clean Vader is analyzed (priority) but not flagged.
    assert "DARTHVADER" not in flagged
    # Non-priority undermodded unit never appears; Jawa (no mods) never appears.
    assert "UGNAUGHT" not in {r.unit.base_id for r in report.unit_reports}
    assert "JAWA" not in {r.unit.base_id for r in report.unit_reports}


def test_report_totals(player):
    report = analyze_roster(player, _cfg())
    # 6 (vader) + 6 (thrawn) + 3 (gas) + 6 (hermit) + 2 (ugnaught) = 23
    assert report.total_mods == 23
    assert report.unleveled_mods == 3   # gas's three level-1 mods
    assert report.low_rarity_mods == 1  # hermit's one 4-dot


def test_friendly_names_from_bundled_map():
    from swgoh.names import display_name

    assert display_name("EMPERORPALPATINE") == "Emperor Palpatine"
    assert display_name("GRANDADMIRALTHRAWN") == "Grand Admiral Thrawn"
    # Unknown ids fall back to a prettified form, never crash.
    assert display_name("TOTALLYFAKEUNIT")


def test_generic_heuristics_on_nonpriority_fully_modded_unit():
    # A fielded unit not in the config still gets universal tuning advice:
    # non-Speed arrow + low mod speed, even with no per-unit recommendation.
    from tests.conftest import make_mod

    mods = [make_mod(i, "Health", primary=("Health", 5.88)) for i in range(1, 7)]
    mods[1] = make_mod(2, "Health", primary=("Protection", 24.0))  # arrow, non-speed
    unit = Unit(base_id="SOMEFIELDEDUNIT", name="Fielded", gear_level=13, mods=mods)
    report = analyze_roster(Player("c", "1", [unit]), _cfg())
    assert len(report.unit_reports) == 1
    kinds = {i.kind for i in report.unit_reports[0].issues}
    assert "arrow_primary" in kinds  # generic Speed-arrow advice
    assert "low_speed" in kinds      # zero mod speed
    assert "set_mismatch" not in kinds  # no config -> no set advice


def test_fully_modded_ranks_above_undermodded(player):
    report = analyze_roster(player, _cfg())
    fm = [r.fully_modded for r in report.unit_reports]
    # All fully-modded units come before any undermodded ones.
    assert fm == sorted(fm, reverse=True)


def test_pure_pilot_unit_suppresses_speed_advice_and_notes_ship():
    # BOSSK crews Hound's Tooth. As a non-priority pilot with a non-Speed arrow,
    # the misleading Speed advice is suppressed and a pilot note is attached.
    from tests.conftest import make_mod

    mods = [make_mod(i, "Offense", primary=("Health", 5.88)) for i in range(1, 7)]
    mods[1] = make_mod(2, "Offense", primary=("Protection", 24.0))  # non-Speed arrow
    mods[0] = make_mod(1, "Offense", rarity=4, primary=("Offense", 5.88))  # keeps it flagged
    bossk = Unit(base_id="BOSSK", name="Bossk", gear_level=13, mods=mods)
    report = analyze_roster(Player("c", "1", [bossk]), _cfg())
    assert len(report.unit_reports) == 1
    r = report.unit_reports[0]
    kinds = {i.kind for i in r.issues}
    assert "arrow_primary" not in kinds   # suppressed for a pure pilot
    assert "low_speed" not in kinds       # suppressed for a pure pilot
    assert "low_rarity" in kinds          # real issue still flagged
    assert r.pilot_of                      # notes that Bossk pilots a ship


def test_completed_sets_math():
    from tests.conftest import full_speed_arrow_mods

    u = Unit(base_id="X", name="X", mods=full_speed_arrow_mods())
    completed = u.completed_sets()
    assert "Speed" in completed
    assert "Critical Chance" in completed
