"""Tests for the meta-target-driven Fleet engine (offline, injected data)."""
from __future__ import annotations

import pytest

from swgoh.models import Player, Unit
from swgoh.recommend import fleet as fleet_mod
from swgoh.recommend.fleet import analyze_fleet

FAKE_SHIPS = {
    "CAP_S": {"capital": True, "pilots": ["PILOT_S"]},
    "CAP_A": {"capital": True, "pilots": ["PILOT_A"]},
    "KEY1": {"capital": False, "pilots": ["P1"]},
    "KEY2": {"capital": False, "pilots": ["P2"]},
    "SUP1": {"capital": False, "pilots": ["P3"]},
}

TARGETS = [
    {"name": "S Fleet", "capital": "CAP_S", "tier": "S", "core": ["KEY1", "KEY2"], "support": ["SUP1"]},
    {"name": "A Fleet", "capital": "CAP_A", "tier": "A", "core": ["KEY1"], "support": []},
]


@pytest.fixture(autouse=True)
def _inject_ship_data(monkeypatch):
    monkeypatch.setattr(fleet_mod, "ship_data", lambda: FAKE_SHIPS)


@pytest.fixture
def fleet_player():
    return Player(
        name="Admiral", ally_code="1",
        units=[
            Unit("CAP_S", "Cap S", stars=6),
            Unit("CAP_A", "Cap A", stars=6),
            Unit("KEY1", "Key One", stars=5),
            Unit("SUP1", "Support One", stars=5),
            Unit("PILOT_S", "Pilot S", gear_level=8),
            Unit("PILOT_A", "Pilot A", gear_level=13, relic_level=3),
            Unit("P1", "Pilot One", gear_level=10),
            Unit("P3", "Pilot Three", gear_level=8),
            # P2 (KEY2's pilot) and KEY2 itself are NOT owned.
        ],
    )


def test_higher_tier_target_is_recommended(fleet_player):
    report = analyze_fleet(fleet_player, TARGETS)
    assert report.recommended is not None
    assert report.recommended.name == "S Fleet"
    assert report.recommended.tier == "S"


def test_capital_pilot_gear_is_top_objective(fleet_player):
    report = analyze_fleet(fleet_player, TARGETS)
    assert report.recommended.objectives[0].kind == "gear_capital_pilot"


def test_missing_core_ship_becomes_unlock_objective(fleet_player):
    report = analyze_fleet(fleet_player, TARGETS)
    kinds = {o.kind for o in report.recommended.objectives}
    unlock_targets = {o.target_base_id for o in report.recommended.objectives if o.kind == "unlock_ship"}
    assert "unlock_ship" in kinds
    assert "KEY2" in unlock_targets   # unowned core ship
    assert "gear_pilot" in kinds      # P1/P3 under gear target


def test_readiness_reflects_investment(fleet_player):
    report = analyze_fleet(fleet_player, TARGETS)
    # Both targets have some readiness; the recommended one is a real 0<r<100.
    assert 0 < report.recommended.readiness < 100


def test_current_best_ships_lists_owned_noncapitals(fleet_player):
    report = analyze_fleet(fleet_player, TARGETS)
    base_ids = [s.base_id for s in report.current_best_ships]
    assert "KEY1" in base_ids          # owned, geared pilot -> strongest
    assert "CAP_S" not in base_ids     # capitals excluded from this list
    assert report.owned_capitals == 2


def test_bundled_targets_load_and_reference_real_ids():
    from swgoh.recommend.fleet import load_fleet_targets
    from swgoh.ships import ship_data

    targets = load_fleet_targets()
    assert targets
    ships = ship_data()
    for t in targets:
        assert t["capital"] in ships and ships[t["capital"]]["capital"]
        for b in t.get("core", []) + t.get("support", []):
            assert b in ships, f"{b} not a known ship base_id"
