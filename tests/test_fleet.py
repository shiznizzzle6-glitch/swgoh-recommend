"""Tests for the Fleet build-priority engine (offline, injected ship data)."""
from __future__ import annotations

import pytest

from swgoh.models import Player, Unit
from swgoh.recommend import fleet as fleet_mod
from swgoh.recommend.fleet import analyze_fleet

FAKE_SHIPS = {
    "CAP_EMP": {"capital": True, "factions": ["empire"], "pilots": ["TARKIN"]},
    "SHIP_A": {"capital": False, "factions": ["empire"], "pilots": ["VADERPILOT"]},
    "SHIP_B": {"capital": False, "factions": ["empire"], "pilots": ["TIEPILOT"]},
    "CAP_REB": {"capital": True, "factions": ["rebels"], "pilots": ["ACKBAR"]},
    "SHIP_R": {"capital": False, "factions": ["rebels"], "pilots": ["WEDGE"]},
}


@pytest.fixture(autouse=True)
def _inject_ship_data(monkeypatch):
    monkeypatch.setattr(fleet_mod, "ship_data", lambda: FAKE_SHIPS)


@pytest.fixture
def fleet_player():
    return Player(
        name="Admiral", ally_code="1",
        units=[
            Unit("CAP_EMP", "Executrix", stars=5),
            Unit("SHIP_A", "TIE Advanced", stars=5),
            Unit("SHIP_B", "TIE Fighter", stars=4),
            Unit("CAP_REB", "Home One", stars=5),
            Unit("SHIP_R", "X-wing", stars=3),
            Unit("TARKIN", "Tarkin", gear_level=10),
            Unit("VADERPILOT", "Vader", gear_level=12),
            Unit("TIEPILOT", "TIE Pilot", gear_level=8),
            Unit("ACKBAR", "Ackbar", gear_level=9),
            Unit("WEDGE", "Wedge", gear_level=8),
        ],
    )


def test_best_fleet_is_most_invested_faction(fleet_player):
    report = analyze_fleet(fleet_player)
    assert report.best is not None
    assert report.best.faction == "empire"
    assert report.best.capital.base_id == "CAP_EMP"
    assert report.owned_ships == 3   # SHIP_A, SHIP_B, SHIP_R
    assert report.owned_capitals == 2


def test_capital_pilot_gear_is_top_objective(fleet_player):
    report = analyze_fleet(fleet_player)
    top = report.best.objectives[0]
    assert top.kind == "gear_capital_pilot"   # Tarkin g10 < target
    assert "Tarkin" in top.detail


def test_objectives_cover_undergeared_pilot_and_small_fleet(fleet_player):
    report = analyze_fleet(fleet_player)
    kinds = {o.kind for o in report.best.objectives}
    assert "gear_pilot" in kinds          # TIE Pilot g8
    assert "incomplete_fleet" in kinds    # only 2 empire ships < 6


def test_alternatives_include_other_capitals(fleet_player):
    report = analyze_fleet(fleet_player)
    alt_factions = {p.faction for p in report.alternatives}
    assert "rebels" in alt_factions


def test_missing_pilot_becomes_unlock_objective(fleet_player):
    # Drop a ship's pilot (keeps Empire the best fleet) -> unlock objective.
    fleet_player.units = [u for u in fleet_player.units if u.base_id != "TIEPILOT"]
    report = analyze_fleet(fleet_player)
    assert report.best.faction == "empire"
    unlock = [o for o in report.best.objectives if o.kind == "unlock_pilot"]
    assert any(o.target_base_id == "TIEPILOT" for o in unlock)
