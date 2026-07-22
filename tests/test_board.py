"""Tests for the categorized 'tonight' board (offline)."""
from __future__ import annotations

from swgoh.recommend.energy import EnergyReport, FarmTarget
from swgoh.recommend.fleet import FleetReport, FleetTargetPlan, Objective as FObj, ShipStatus
from swgoh.recommend.gear import GearReport, GearTarget
from swgoh.recommend.mods import Issue, ModReport, UnitModReport
from swgoh.recommend.plan import build_tonight_board
from swgoh.recommend.relics import RelicReport, RelicTarget
from swgoh.recommend.squads import MemberStatus, Objective as SObj, SquadPlan, SquadReport
from swgoh.recommend.zetas import AbilityTarget, ZetaReport
from swgoh.models import Unit


def _mods():
    r = UnitModReport(
        unit=Unit("CALKESTIS", "Cal Kestis", gear_level=13), is_priority=False, weight=0.5,
        recommended_sets=[], recommended_arrow="Speed", note="", fully_modded=True,
        issues=[Issue("arrow_primary", "Arrow is Health", 2)],
    )
    return ModReport("ShizzNizzle", "474168985", [r], total_mods=1)


def _fleet():
    cap = ShipStatus("CAP", "Executrix", owned=True, stars=7, is_capital=True, pilots=[])
    plan = FleetTargetPlan(
        name="Executrix", tier="S", note="", capital=cap, core=[], support=[],
        objectives=[FObj("gear_pilot", "Gear Bossk to g12+", 9.0, "BOSSK")],
    )
    return FleetReport("ShizzNizzle", "474168985", recommended=plan)


def _squads():
    bh = SquadPlan(
        name="Bounty Hunters", tier="S", tags=[], note="",
        members=[MemberStatus("BOSSK", "Bossk", True, True, stars=7, gear_level=11, relic_level=0)],
        objectives=[SObj("gear", "Gear Bossk to g12+", 8.0, "BOSSK")],
    )
    return SquadReport("ShizzNizzle", "474168985", [bh])


def _gear():
    t = GearTarget("BOSSK", "Bossk", 11, 12, ["Mk 12 X"], 2, ["Fleet pilot"], ["Bounty Hunters"], 22.0)
    return GearReport("ShizzNizzle", "474168985", eligible=[t], eligible_count=1)


def _relics():
    t = RelicTarget("IG88", "IG-88", 1, ["Fleet pilot"], ["Executrix fleet"], 6.2)
    return RelicReport("ShizzNizzle", "474168985", eligible=[t])


def _zetas():
    z = AbilityTarget("BOSSK", "Bossk", "leaderskill_BOSSK", "On The Hunt", "zeta", [], ["Bounty Hunters"], ["Fleet pilot"], 21.1, 6, 8)
    return ZetaReport("ShizzNizzle", "474168985", zetas=[z], omicrons=[])


def _energy():
    t = FarmTarget("DENGAR", "Dengar", "star", "6★ → 7★", ["Bounty Hunters"], 3.0, energy="cantina")
    return EnergyReport("ShizzNizzle", "474168985", cantina=[t])


def _board():
    return build_tonight_board(_mods(), _fleet(), _squads(), _gear(), _relics(), _zetas(), _energy())


def test_board_has_all_categories_in_order():
    board = _board()
    keys = [c.key for c in board.categories]
    assert keys == ["fleet", "squads", "gear", "relics", "zetas", "energy", "mods"]
    # Defense is intentionally not a category.
    assert "defense" not in keys


def test_categories_carry_top_items():
    board = _board()
    by_key = {c.key: c for c in board.categories}
    assert by_key["gear"].items[0].name == "Bossk"
    assert by_key["relics"].items[0].name == "IG-88"
    assert by_key["zetas"].items[0].detail == "zeta: On The Hunt"
    assert by_key["energy"].items[0].name == "Dengar"


def test_multi_payoff_highlight_surfaces_bossk():
    board = _board()
    bossk = next((h for h in board.highlights if h.base_id == "BOSSK"), None)
    assert bossk is not None
    # Bossk shows up under Fleet, Squads, Gear, Zetas.
    assert set(bossk.areas) >= {"Fleet", "Squads", "Gear", "Zetas & Omicrons"}
    assert bossk.count >= 4
    # highlights are sorted by breadth
    assert board.highlights[0].count >= board.highlights[-1].count


def test_item_limit_respected():
    board = _board()
    for c in board.categories:
        assert len(c.items) <= 3
