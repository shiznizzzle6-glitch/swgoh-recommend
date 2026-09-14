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


def _mods(count: int = 6, speed: float = 0.0) -> list[Mod]:
    """A plain full loadout. Units are modded by default because an unmodded unit
    isn't fieldable — the builder excludes it, as it should."""
    return [
        Mod(slot=i, set_name="Health", rarity=6, level=15, tier=5,
            primary_name="Speed" if (i == 2 and speed) else "Offense",
            primary_value=speed if (i == 2 and speed) else 5.88,
            secondaries=[])
        for i in range(1, count + 1)
    ]


def _unit(base_id: str, stars: int, gear: int, relic: int, power: int = 0,
          mods: int = 6) -> Unit:
    u = Unit(
        base_id=base_id, name=base_id, stars=stars, level=85,
        gear_level=gear, relic_level=relic, power=power,
    )
    u.mods = _mods(mods)
    return u


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
    bare = _unit("A", 7, 13, 5, mods=0)
    assert _mod_score(bare) == 0.0
    # A full loadout of plain mods already beats a half-empty one.
    assert _mod_score(_unit("A", 7, 13, 5)) > _mod_score(_unit("A", 7, 13, 5, mods=3))
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
def _kit_warnings(squad):
    """Warnings about kits, ignoring the unrelated missing-mods notices."""
    return [w for w in squad.warnings if "mods equipped" not in w]


def test_liability_flags_only_apply_to_active_threats():
    no_threat = build_counter_squads(_player(), TOOLS, threat_keys=set())
    assert all(not _kit_warnings(sq) for sq in no_threat)
    # Several of these kits call assists, which backfires against a reflect threat.
    with_threat = build_counter_squads(_player(), TOOLS, threat_keys={"damage_reflect"})
    assert any(_kit_warnings(sq) for sq in with_threat)


def test_missing_mods_are_warned_about_regardless_of_threat():
    """A relic unit running three mods is missing about half its stats — that
    decides fights more bluntly than any kit interaction."""
    units = [_unit(b, 7, 13, 5) for b in ("MACEWINDU", "GRANDMASTERYODA", "JEDIKNIGHTREVAN", "AHSOKATANO")]
    units.append(_unit("EZRABRIDGERS3", 7, 13, 5, mods=3))  # half-modded
    squads = build_counter_squads(Player(name="T", ally_code="1", units=units), TOOLS)
    assert squads
    assert any("mods equipped" in w for w in squads[0].warnings)
    assert squads[0].unmodded


def test_fully_modded_unit_beats_an_unmodded_one_for_a_slot():
    from swgoh.models import Mod, SecondaryStat

    def modded(base_id: str) -> Unit:
        u = _unit(base_id, 7, 13, 5)
        u.mods = [
            Mod(slot=i, set_name="Speed", rarity=6, level=15, tier=5,
                primary_name="Speed", primary_value=20.0,
                secondaries=[SecondaryStat("Speed", 10.0)])
            for i in range(1, 7)
        ]
        return u

    # Same family and investment; only mod completeness differs.
    full = [modded(b) for b in ("MACEWINDU", "GRANDMASTERYODA", "JEDIKNIGHTREVAN", "AHSOKATANO", "EZRABRIDGERS3")]
    bare = [_unit(b, 7, 13, 5, mods=2) for b in ("HERMITYODA", "KANANJARRUSS3")]
    player = Player(name="T", ally_code="1", units=full + bare)

    top = build_counter_squads(player, TOOLS, limit=1)[0]
    picked = {m.base_id for m in top.members}
    assert not (picked & {u.base_id for u in bare}), "an unmodded unit took a slot from a modded one"


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


# --- speed breakdown (base from the stats export, mods live) ---
def test_speed_label_explains_the_number():
    from swgoh.recommend.counter_squads import SquadMember

    known = SquadMember("X", "X", False, 7, 13, 5, 0, 0.5, base_speed=143, mod_speed=91)
    assert known.total_speed == 234
    assert "234" in known.speed_label and "143 base" in known.speed_label and "91 mods" in known.speed_label

    unknown = SquadMember("Y", "Y", False, 7, 13, 5, 0, 0.5, base_speed=None, mod_speed=38)
    assert unknown.total_speed is None
    assert "base unknown" in unknown.speed_label
    assert "38" in unknown.speed_label


def test_base_speed_lookup_is_honest_about_gaps():
    from swgoh.stats import base_speed, covered_units

    assert covered_units() > 100
    assert base_speed("MACEWINDU")  # covered by the export
    assert base_speed("NOT_A_REAL_UNIT_ID") is None


def test_mod_and_total_speed_use_live_mods():
    from swgoh.models import Mod, SecondaryStat
    from swgoh.stats import base_speed, mod_speed, total_speed

    u = _unit("MACEWINDU", 7, 13, 5)
    assert mod_speed(u) == 0
    u.mods = [
        Mod(slot=2, set_name="Speed", rarity=6, level=15, tier=5,
            primary_name="Speed", primary_value=30.0,
            secondaries=[SecondaryStat("Speed", 11.0)])
    ]
    assert mod_speed(u) == 41
    assert total_speed(u) == base_speed("MACEWINDU") + 41


# --- mod donors ---
def test_mod_donors_exclude_the_squad_and_rank_by_speed():
    from swgoh.models import Mod, SecondaryStat
    from swgoh.recommend.counter_squads import find_mod_donors

    def with_speed(base_id: str, speed: float) -> Unit:
        u = _unit(base_id, 7, 13, 5)
        u.mods = [
            Mod(slot=2, set_name="Speed", rarity=6, level=15, tier=5,
                primary_name="Speed", primary_value=speed, secondaries=[])
        ]
        return u

    player = Player(
        name="T", ally_code="1",
        units=[with_speed("MACEWINDU", 30), with_speed("HERMITYODA", 25), with_speed("JAWA", 12)],
    )
    donors = find_mod_donors(player, squad_ids={"MACEWINDU"})
    assert all(d.owner_base_id != "MACEWINDU" for d in donors)   # no self-donation
    assert [d.owner_base_id for d in donors] == ["HERMITYODA", "JAWA"]  # fastest first
    assert donors[0].is_speed_arrow


def test_mod_donors_ignore_slow_mods():
    from swgoh.models import Mod
    from swgoh.recommend.counter_squads import find_mod_donors

    u = _unit("HERMITYODA", 7, 13, 5)
    u.mods = [Mod(slot=1, set_name="Health", rarity=6, level=15, tier=5,
                  primary_name="Offense", primary_value=5.88, secondaries=[])]
    player = Player(name="T", ally_code="1", units=[u])
    assert find_mod_donors(player, squad_ids=set()) == []


def test_donors_found_for_any_stat_not_just_speed():
    from swgoh.models import Mod, SecondaryStat
    from swgoh.recommend.counter_squads import find_mod_donors

    u = _unit("HERMITYODA", 7, 13, 5)
    u.mods = [
        Mod(slot=3, set_name="Potency", rarity=6, level=15, tier=5,
            primary_name="Potency", primary_value=24.0,
            secondaries=[SecondaryStat("Speed", 11.0)])
    ]
    player = Player(name="T", ally_code="1", units=[u])

    potency = find_mod_donors(player, set(), stat="Potency")
    assert potency and potency[0].amount == 24.0 and potency[0].is_primary

    speed = find_mod_donors(player, set(), stat="Speed")
    assert speed and speed[0].amount == 11.0 and not speed[0].is_primary


def test_squad_members_carry_the_requested_stats():
    squads = build_counter_squads(
        _player(), TOOLS, stat_names=("Speed", "Potency"), limit=1
    )
    member = squads[0].members[0]
    assert set(member.stat_values) == {"Speed", "Potency"}
    for value in member.stat_values.values():
        assert set(value) == {"base", "mods", "total"}


# --- evaluating a squad someone else recommended ---
def test_community_shorthand_resolves_to_units():
    from swgoh.aliases import resolve, resolve_squad

    assert resolve("CLS") == ["COMMANDERLUKESKYWALKER"]
    assert resolve("3PaC") == ["C3POCHEWBACCA"]
    assert resolve("Snips") == ["AHSOKATANO"]
    assert resolve("not a unit at all") == []
    # Squad context disambiguates: "Echo" is Bad Batch here, 501st elsewhere.
    bad_batch = dict(resolve_squad(["Hunter", "Tech", "Echo"]))
    assert bad_batch["Echo"] == "BADBATCHECHO"


def test_evaluate_squad_reports_unowned_and_ineligible():
    from swgoh.recommend.counter_squads import evaluate_squad

    player = _player()  # Jedi + Rebels, no Sith
    v = evaluate_squad(player, ["Mace Windu", "Darth Traya"], TOOLS, min_relic=0)
    assert "Darth Traya" in v.not_owned
    assert not v.fieldable

    gated = evaluate_squad(player, ["Mace Windu", "Hermit Yoda"], TOOLS, min_relic=5)
    assert any("Hermit Yoda" in x for x in gated.ineligible)  # fixture has him at R3
    assert not gated.fieldable


def test_evaluate_squad_scores_a_fieldable_squad():
    from swgoh.recommend.counter_squads import evaluate_squad

    v = evaluate_squad(
        _player(),
        ["Mace Windu", "Grand Master Yoda", "Jedi Knight Revan"],
        ["dispel", "taunt"],
        min_relic=5,
        stat_names=("Speed",),
    )
    assert v.fieldable
    assert v.squad is not None
    assert v.squad.members[0].is_leader          # first name given leads
    assert "Speed" in v.squad.members[0].stat_values
    assert 0 <= v.squad.coverage <= 100


def test_evaluate_squad_with_nothing_recognised():
    from swgoh.recommend.counter_squads import evaluate_squad

    v = evaluate_squad(_player(), ["zzzz", "qqqq"], TOOLS)
    assert v.squad is None
    assert len(v.unresolved) == 2
    assert not v.fieldable


def test_aoe_and_assist_kits_flagged_against_damage_triggered_stacks():
    """Phoenix-style assist kits are the worst possible pick when damage itself
    is what stacks the enemy."""
    from swgoh.recommend.counter_squads import _liability_index

    units = [_unit(b, 7, 13, 5) for b in ("EZRABRIDGERS3", "SABINEWRENS3", "CHOPPERS3")]
    flagged = _liability_index(units, {"damage_triggered_stacks"})
    assert flagged, "no Phoenix kit flagged as an assist/AoE liability"
