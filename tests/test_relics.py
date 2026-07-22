"""Tests for the relic upgrade priority analyzer (offline)."""
from __future__ import annotations

from swgoh.recommend.relics import analyze_relics
from swgoh.models import Player, Unit

SQUADS = [
    {"name": "Nightsisters", "tier": "A", "members": ["TALIA"]},
]
# Fleet target whose ship pilots include a relic-eligible unit.
FLEET = [
    {"name": "Executrix", "tier": "S", "capital": "CAPITALSTARDESTROYER", "core": ["IG2000"], "support": []},
]
DEFENSE = {"wall_units": [{"base_id": "CALKESTIS", "weight": 1.0}], "teams": []}
PRIORITY: dict = {}


def _u(base_id, gear=13, level=85, relic=0):
    return Unit(base_id=base_id, name=base_id, gear_level=gear, level=level, relic_level=relic)


def _player():
    return Player(
        name="P", ally_code="1",
        units=[
            _u("CALKESTIS", relic=5),   # defense wall
            _u("TALIA", relic=1),       # nightsister squad
            _u("JABBATHEHUTT", relic=2),  # eligible but no goal
            _u("BOSSK", gear=8, relic=0),  # NOT eligible (g8)
            _u("MACEWINDU", gear=13, level=80, relic=0),  # NOT eligible (L80)
        ],
    )


def test_only_g13_l85_units_are_eligible():
    rep = analyze_relics(_player(), SQUADS, FLEET, DEFENSE, PRIORITY)
    ids = {t.base_id for t in rep.eligible} | {t.base_id for t in rep.others}
    assert "BOSSK" not in ids       # gear 8
    assert "MACEWINDU" not in ids   # level 80
    assert rep.eligible_count == 3


def test_goal_units_separate_from_ungoaled():
    rep = analyze_relics(_player(), SQUADS, FLEET, DEFENSE, PRIORITY)
    goal_ids = {t.base_id for t in rep.eligible}
    assert "CALKESTIS" in goal_ids   # defense wall
    assert "TALIA" in goal_ids       # squad
    assert {t.base_id for t in rep.others} == {"JABBATHEHUTT"}


def test_defense_wall_role_and_target_label():
    rep = analyze_relics(_player(), SQUADS, FLEET, DEFENSE, PRIORITY)
    cal = next(t for t in rep.eligible if t.base_id == "CALKESTIS")
    assert "Defense wall" in cal.roles
    # Cal at R5 (== target) -> next milestone is R6.
    assert cal.target_label == "R5 → R6"
    talia = next(t for t in rep.eligible if t.base_id == "TALIA")
    assert talia.target_label == "R1 → R5"   # below target -> aim for baseline


def test_low_relic_goal_unit_outranks_maxed_ungoaled():
    rep = analyze_relics(_player(), SQUADS, FLEET, DEFENSE, PRIORITY)
    # Every goal-tied target should outrank the un-goaled bench.
    assert rep.eligible
    assert min(t.priority for t in rep.eligible) >= 0
    talia = next(t for t in rep.eligible if t.base_id == "TALIA")
    # R1 nightsister gets an urgency boost over its flat goal value.
    assert talia.priority > 2.0
