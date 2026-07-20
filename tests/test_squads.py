"""Tests for the squad builder (offline)."""
from __future__ import annotations

from swgoh.models import Player, Unit
from swgoh.recommend.squads import analyze_squads, load_squad_targets

TARGETS = [
    {"name": "Ready Squad", "tier": "S", "tags": ["gac"],
     "members": ["L", "M2", "M3", "M4", "M5"]},
    {"name": "Build Squad", "tier": "A", "tags": ["tw"],
     "members": ["X1", "X2", "X3", "X4", "X5"]},
]


def _ready_player():
    return Player(
        name="Cmdr", ally_code="1",
        units=[
            Unit("L", "Leader", stars=7, gear_level=13, relic_level=5),
            Unit("M2", "M2", stars=7, gear_level=13, relic_level=3),
            Unit("M3", "M3", stars=7, gear_level=12),
            Unit("M4", "M4", stars=7, gear_level=12),
            Unit("M5", "M5", stars=7, gear_level=12),
            # Build Squad: only one member owned, undergeared.
            Unit("X1", "X1", stars=5, gear_level=8),
        ],
    )


def test_fully_built_squad_is_ready_with_no_objectives():
    report = analyze_squads(_ready_player(), TARGETS)
    ready = report.squads[0]
    assert ready.name == "Ready Squad"
    assert ready.status == "Ready"
    assert ready.owned_count == 5
    assert ready.objectives == []


def test_missing_members_produce_unlock_objectives_and_build_status():
    report = analyze_squads(_ready_player(), TARGETS)
    build = [s for s in report.squads if s.name == "Build Squad"][0]
    assert build.status == "Build"
    kinds = {o.kind for o in build.objectives}
    assert "unlock" in kinds          # X2..X5 not owned
    # The owned leader (X1, g8) is the highest-priority step here.
    assert build.objectives[0].target_base_id == "X1"


def test_ready_squad_sorts_before_build_squad():
    report = analyze_squads(_ready_player(), TARGETS)
    assert [s.name for s in report.squads] == ["Ready Squad", "Build Squad"]


def test_undergeared_owned_member_gets_gear_objective():
    player = Player("c", "1", units=[
        Unit("L", "Leader", stars=7, gear_level=9),
        Unit("M2", "M2", stars=7, gear_level=13),
        Unit("M3", "M3", stars=7, gear_level=13),
        Unit("M4", "M4", stars=7, gear_level=13),
        Unit("M5", "M5", stars=7, gear_level=13),
    ])
    report = analyze_squads(player, [TARGETS[0]])
    gear = [o for o in report.squads[0].objectives if o.kind == "gear"]
    assert any(o.target_base_id == "L" for o in gear)


def test_bundled_squad_targets_load_and_reference_real_ids():
    import json
    from importlib import resources

    targets = load_squad_targets()
    assert targets
    names = json.loads(resources.files("swgoh.data").joinpath("unit_names.json").read_text("utf-8"))
    for t in targets:
        assert 2 <= len(t["members"]) <= 5
        for b in t["members"]:
            assert b in names, f"{b} not a known base_id"
