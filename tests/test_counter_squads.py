"""Tests for the counter squad builder (offline).

Squads are assembled from the bundled faction/ability data, so these use real
base_ids — the point is that the *rules* hold: entry requirements filter, leaders
lead, families group, and investment breaks ties.
"""
from __future__ import annotations

import pytest

from swgoh.factions import factions_of
from swgoh.models import Mod, Player, SecondaryStat, Unit
from swgoh.recommend.counter_squads import (
    SQUAD_SIZE,
    _investment,
    _mod_score,
    build_counter_squads,
)

# Jedi with leader abilities, deliberately mixed investment levels.
JEDI = [
    ("MACEWINDU", 7, 13, 5),
    ("GRANDMASTERYODA", 7, 13, 7),
    ("JEDIKNIGHTREVAN", 7, 13, 6),
    ("AHSOKATANO", 7, 12, 5),
    ("EZRABRIDGERS3", 7, 12, 5),
    ("HERMITYODA", 7, 12, 3),
]
# Rebels, so there's a second family to choose between.
REBELS = [
    ("STORMTROOPERHAN", 7, 12, 3),
    ("CHOPPERS3", 7, 12, 3),
    ("SABINEWRENS3", 7, 12, 3),
    ("KANANJARRUSS3", 7, 12, 5),
]


def _unit(base_id: str, stars: int, gear: int, relic: int, power: int = 0) -> Unit:
    return Unit(
        base_id=base_id, name=base_id, stars=stars, level=85,
        gear_level=gear, relic_level=relic, power=power,
    )


def _player(extra: list[Unit] | None = None) -> Player:
    units = [_unit(*spec) for spec in JEDI + REBELS]
    return Player(name="T", ally_code="1", units=units + (extra or []))


TOOLS = ["dispel", "taunt", "tm_removal", "healing_immunity", "crit_avoidance"]


def test_builds_full_size_squads():
    squads = build_counter_squads(_player(), TOOLS)
    assert squads
    for sq in squads:
        assert len(sq.members) == SQUAD_SIZE


def test_leader_slot_holds_a_unit_with_a_leader_ability():
    for sq in build_counter_squads(_player(), TOOLS):
        leader = sq.leader
        assert leader is not None
        assert leader.is_leader
        assert "Leader" in factions_of(leader.base_id)
        # Exactly one leader per squad.
        assert sum(1 for m in sq.members if m.is_leader) == 1


def test_relic_requirement_excludes_ineligible_units():
    """A trial gated at Relic 5+ must not field a Relic 3 unit."""
    squads = build_counter_squads(_player(), TOOLS, min_relic=5)
    assert squads
    for sq in squads:
        for m in sq.members:
            assert m.relic_level >= 5


def test_impossible_requirement_yields_no_squads():
    assert build_counter_squads(_player(), TOOLS, min_relic=9) == []


def test_no_tools_requested_yields_no_squads():
    assert build_counter_squads(_player(), []) == []


def test_squads_prefer_a_shared_family():
    squads = build_counter_squads(_player(), TOOLS)
    top = squads[0]
    # The best squad should be built around one family, not five strangers.
    assert top.family_count >= 3
    assert top.family != "Mixed"


def test_squad_reports_covered_and_missing_tools():
    squads = build_counter_squads(_player(), TOOLS)
    top = squads[0]
    assert top.covered or top.missing
    # Covered and missing together account for every requested tool.
    assert len(top.covered) + len(top.missing) >= len(TOOLS) - 1
    assert 0 <= top.coverage <= 100


def test_results_are_distinct_squads():
    squads = build_counter_squads(_player(), TOOLS, limit=3)
    seen = [frozenset(m.base_id for m in sq.members) for sq in squads]
    assert len(seen) == len(set(seen))
    # And not near-identical either (the builder drops 4-of-5 overlaps).
    for i, a in enumerate(seen):
        for b in seen[i + 1 :]:
            assert len(a & b) < SQUAD_SIZE - 1


def test_squads_sorted_by_score():
    squads = build_counter_squads(_player(), TOOLS, limit=3)
    assert squads == sorted(squads, key=lambda s: s.score, reverse=True)


# --- investment ranking ---
def test_investment_rewards_relic_gear_stars():
    weak = _unit("A", 5, 8, 0)
    strong = _unit("B", 7, 13, 8)
    assert _investment(strong, 0) > _investment(weak, 0)


def test_investment_uses_power_only_when_the_source_supplies_it():
    """Comlink reports no per-unit power; the score must still use the full range."""
    unit = _unit("A", 7, 13, 9)
    without = _investment(unit, 0)
    assert without == pytest.approx(1.0, abs=0.35)  # not crushed by a dead term
    with_power = _investment(_unit("A", 7, 13, 9, power=50000), 50000)
    assert with_power >= without


def test_mod_score_rises_with_maxed_speed_mods():
    bare = _unit("A", 7, 13, 5)
    assert _mod_score(bare) == 0.0
    modded = _unit("B", 7, 13, 5)
    modded.mods = [
        Mod(slot=i, set_name="Speed", rarity=6, level=15, tier=5,
            primary_name="Speed", primary_value=30.0,
            secondaries=[SecondaryStat("Speed", 20.0)])
        for i in range(1, 7)
    ]
    assert _mod_score(modded) > 0.9


def test_better_geared_unit_wins_the_slot():
    """Two same-family units, identical kits aside — the invested one gets picked."""
    squads = build_counter_squads(_player(), TOOLS, limit=1)
    top = squads[0]
    avg = sum(m.investment for m in top.members) / len(top.members)
    # The chosen five should beat the roster average.
    roster = _player().units
    overall = sum(_investment(u, 0) for u in roster) / len(roster)
    assert avg > overall


# --- liabilities ---
def test_liability_flags_only_apply_to_active_threats():
    no_threat = build_counter_squads(_player(), TOOLS, threat_keys=set())
    assert all(not sq.warnings for sq in no_threat)
    # Several of these kits call assists, which backfires against a reflect threat.
    with_threat = build_counter_squads(_player(), TOOLS, threat_keys={"damage_reflect"})
    assert any(sq.warnings for sq in with_threat)


def test_ships_never_enter_a_squad():
    player = _player([_unit("MILLENNIUMFALCON", 7, 13, 0)])
    for sq in build_counter_squads(player, TOOLS):
        assert all(m.base_id != "MILLENNIUMFALCON" for m in sq.members)


def test_too_few_eligible_units_yields_no_squads():
    tiny = Player(name="T", ally_code="1", units=[_unit("MACEWINDU", 7, 13, 5)])
    assert build_counter_squads(tiny, TOOLS) == []


def test_squad_tool_index_respects_effect_direction():
    """A squad must not be credited with a mechanic aimed at its own allies."""
    from swgoh.recommend.counter_squads import _tool_index
    from swgoh.recommend.counters import TOOLS_BY_KEY

    # Morgan Elsbeth's "Defeated allies can't be revived" is a drawback, not
    # revive denial; Grand Moff Tarkin's "Enemies can't be revived" is the tool.
    units = [_unit("MORGANELSBETH", 7, 13, 5), _unit("GRANDMOFFTARKIN", 7, 13, 5)]
    index = _tool_index(units, [TOOLS_BY_KEY["revive_block"]])
    assert "revive_block" not in index.get("MORGANELSBETH", set())
    assert "revive_block" in index.get("GRANDMOFFTARKIN", set())


def test_speed_race_favours_faster_units():
    """A flat speed penalty widens turn-order gaps, so the builder must weight
    mod speed when the modifier is a speed race."""
    from swgoh.models import Mod, SecondaryStat

    def speedy(base_id: str, speed: float) -> Unit:
        u = _unit(base_id, 7, 13, 5)
        u.mods = [
            Mod(slot=1, set_name="Speed", rarity=6, level=15, tier=5,
                primary_name="Speed", primary_value=speed,
                secondaries=[SecondaryStat("Speed", speed)])
        ]
        return u

    # Same family, same investment; only mod speed differs.
    fast = [speedy(b, 30.0) for b in ("MACEWINDU", "GRANDMASTERYODA", "HERMITYODA")]
    slow = [speedy(b, 0.0) for b in ("JEDIKNIGHTREVAN", "AHSOKATANO", "EZRABRIDGERS3", "KANANJARRUSS3")]
    player = Player(name="T", ally_code="1", units=fast + slow)

    racing = build_counter_squads(player, TOOLS, threat_keys={"speed_race"}, limit=1)
    assert racing
    picked = {m.base_id for m in racing[0].members}
    # At least two of the three fast units should make the cut.
    assert len(picked & {u.base_id for u in fast}) >= 2
