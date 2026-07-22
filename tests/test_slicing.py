"""Tests for the mod slicing priority analyzer (offline)."""
from __future__ import annotations

from swgoh.recommend.slicing import analyze_slicing
from swgoh.models import Mod, Player, SecondaryStat, Unit

SQUADS = [{"name": "Bounty Hunters", "tier": "S", "members": ["BOSSK"]}]
FLEET: list = []
DEFENSE = {"wall_units": [], "teams": []}
PRIORITY: dict = {}


def _mod(rarity, tier, level, speed=0.0, primary="Offense"):
    secs = [SecondaryStat("Speed", speed)] if speed else []
    return Mod(slot=1, set_name="Speed", rarity=rarity, level=level, tier=tier,
               primary_name=primary, primary_value=0.0, secondaries=secs)


def _player():
    return Player(
        name="P", ally_code="1",
        units=[
            Unit(base_id="BOSSK", name="Bossk", mods=[
                _mod(6, 2, 15, speed=22),   # 6-dot below gold, speedy -> to_gold_6
                _mod(5, 5, 15, speed=10),   # 5A maxed, speedy -> to_6dot
                _mod(5, 3, 12, speed=8),    # 5C, speedy -> to_gold_5
                _mod(5, 3, 9, speed=0),     # slow, low -> filtered out
                _mod(6, 5, 15, speed=15),   # 6A gold already -> not sliceable
            ]),
            # Ungoaled unit -> ignored entirely.
            Unit(base_id="JAWA", name="Jawa", mods=[_mod(6, 1, 12, speed=20)]),
        ],
    )


def test_only_goal_units_and_sliceable_speedy_mods():
    rep = analyze_slicing(_player(), SQUADS, FLEET, DEFENSE, PRIORITY)
    assert all(c.base_id == "BOSSK" for c in rep.candidates)   # Jawa excluded
    kinds = sorted(c.kind for c in rep.candidates)
    assert kinds == ["to_6dot", "to_gold_5", "to_gold_6"]      # the 3 valid ones
    # the slow 5C and the finished 6A gold are excluded
    assert rep.count == 3


def test_six_dot_to_gold_ranks_first():
    rep = analyze_slicing(_player(), SQUADS, FLEET, DEFENSE, PRIORITY)
    top = rep.candidates[0]
    assert top.kind == "to_gold_6"          # cheapest/biggest multiplier + high speed
    assert top.action == "6D → 6A (gold)"   # tier 2 == D


def test_speed_arrow_included_even_without_secondary_speed():
    player = Player(name="P", ally_code="1", units=[
        Unit(base_id="BOSSK", name="Bossk", mods=[
            Mod(slot=2, set_name="Speed", rarity=5, level=15, tier=3,
                primary_name="Speed", primary_value=25.0, secondaries=[]),
        ]),
    ])
    rep = analyze_slicing(player, SQUADS, FLEET, DEFENSE, PRIORITY)
    assert rep.count == 1
    assert rep.candidates[0].kind == "to_gold_5"
