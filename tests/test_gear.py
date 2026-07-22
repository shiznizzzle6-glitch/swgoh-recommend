"""Tests for the gear upgrade priority analyzer + loader (offline)."""
from __future__ import annotations

from swgoh.gear import gear_for_tier, gear_name, next_tier_pieces
from swgoh.recommend.gear import analyze_gear
from swgoh.models import Player, Unit


SQUADS = [{"name": "Bad Batch", "tier": "S", "members": ["BADBATCHTECH"]}]
FLEET = [
    {"name": "Executrix", "tier": "S", "capital": "CAPITALSTARDESTROYER", "core": ["IG2000"], "support": []},
]
PRIORITY: dict = {}


def _player():
    return Player(
        name="P", ally_code="1",
        units=[
            Unit(base_id="BADBATCHTECH", name="Tech", gear_level=1),   # goal, very low gear
            Unit(base_id="IG88", name="IG-88", gear_level=12),         # fleet pilot (IG2000 crew)
            Unit(base_id="JAWA", name="Jawa", gear_level=3),           # no goal
            Unit(base_id="CALKESTIS", name="Cal", gear_level=13),      # maxed -> excluded
        ],
    )


def test_bundled_gear_data_resolves():
    # Bossk's tier-11 pieces resolve to real names.
    pieces = gear_for_tier("BOSSK", 11)
    assert len(pieces) == 6
    assert all(gear_name(p) != p for p in pieces)  # every id has a name
    named = next_tier_pieces("BOSSK", 10)          # next tier == 11
    assert "Mk 11 BlasTech Weapon Mod" in named


def test_excludes_maxed_and_ungoaled():
    rep = analyze_gear(_player(), SQUADS, FLEET, PRIORITY)
    ids = {t.base_id for t in rep.eligible}
    assert "CALKESTIS" not in ids       # already G13
    assert "JAWA" not in ids            # no tracked goal
    assert rep.others_count == 1        # Jawa counted here
    assert ids == {"BADBATCHTECH", "IG88"}


def test_target_label_and_pieces():
    rep = analyze_gear(_player(), SQUADS, FLEET, PRIORITY)
    tech = next(t for t in rep.eligible if t.base_id == "BADBATCHTECH")
    assert tech.target_label == "G1 → G2"
    assert tech.tiers_to_target == 12
    # G12 -> G13 has no piece list in the dataset.
    ig = next(t for t in rep.eligible if t.base_id == "IG88")
    assert ig.target_label == "G12 → G13"
    assert ig.next_pieces == []


def test_fleet_pilot_priority_weighting():
    rep = analyze_gear(_player(), SQUADS, FLEET, PRIORITY)
    ig = next(t for t in rep.eligible if t.base_id == "IG88")
    assert "Fleet pilot" in ig.roles
    assert ig.priority > 0
