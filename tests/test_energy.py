"""Tests for the Cantina energy-focus analyzer (offline)."""
from __future__ import annotations

import json
from importlib import resources

from swgoh.recommend.energy import analyze_energy, load_farm_locations
from swgoh.models import Player, Unit

SQUADS = [
    {"name": "Bounty Hunters", "tier": "S", "members": ["BOSSK", "DENGAR", "JANGOFETT"]},
    {"name": "Nightsisters", "tier": "A", "members": ["TALIA"]},
]
# No fleet targets in the unit test (keeps it independent of ship data).
FLEET: list = []
FARM = {
    "BOSSK": {"energy": "cantina", "node": "Cantina Battles", "verify": True},
    "DENGAR": {"energy": "cantina"},
    "TALIA": {"energy": "normal"},
    # JANGOFETT intentionally unmapped.
}


def _player():
    return Player(
        name="P",
        ally_code="1",
        units=[
            Unit(base_id="BOSSK", name="Bossk", stars=6),      # needs shards
            Unit(base_id="DENGAR", name="Dengar", stars=7),    # maxed -> excluded
            Unit(base_id="TALIA", name="Talia", stars=5),      # needs shards, non-cantina
            # JANGOFETT not owned -> unlock
        ],
    )


def test_cantina_list_ranks_and_excludes_maxed():
    rep = analyze_energy(_player(), FARM, SQUADS, FLEET)
    ids = [t.base_id for t in rep.cantina]
    assert "BOSSK" in ids           # 6★, cantina -> included
    assert "DENGAR" not in ids      # already 7★ -> no shards needed
    # Bossk serves 1 goal here but is 6★; still the top cantina target.
    assert rep.cantina[0].base_id == "BOSSK"
    assert rep.cantina[0].action == "star"
    assert rep.cantina[0].verify is True


def test_non_cantina_and_unmapped_split():
    rep = analyze_energy(_player(), FARM, SQUADS, FLEET)
    assert any(t.base_id == "TALIA" for t in rep.other)      # normal pool
    assert any(t.base_id == "JANGOFETT" for t in rep.unmapped)  # no location
    jango = next(t for t in rep.unmapped if t.base_id == "JANGOFETT")
    assert jango.action == "unlock"


def test_cross_goal_leverage_raises_priority():
    # A character serving two S-tier goals should outrank one serving a single.
    squads = [
        {"name": "A", "tier": "S", "members": ["BOSSK"]},
        {"name": "B", "tier": "S", "members": ["BOSSK"]},
        {"name": "C", "tier": "S", "members": ["DENGAR"]},
    ]
    player = Player(
        name="P", ally_code="1",
        units=[Unit("BOSSK", "Bossk", stars=6), Unit("DENGAR", "Dengar", stars=6)],
    )
    farm = {"BOSSK": {"energy": "cantina"}, "DENGAR": {"energy": "cantina"}}
    rep = analyze_energy(player, farm, squads, [])
    top = rep.cantina[0]
    assert top.base_id == "BOSSK"
    assert top.goals == ["A", "B"]


def test_bundled_farm_locations_base_ids_valid():
    farm = load_farm_locations()
    names = json.loads(
        resources.files("swgoh.data").joinpath("unit_names.json").read_text("utf-8")
    )
    missing = sorted(b for b in farm if b not in names)
    assert not missing, f"unknown base_ids in farm_locations.yaml: {missing}"
    # Every entry declares an energy pool.
    for b, v in farm.items():
        assert v.get("energy"), f"{b} missing energy"
