"""Tests for the unified 'tonight' plan aggregation (offline)."""
from __future__ import annotations

from swgoh.recommend.fleet import FleetReport, FleetTargetPlan, Objective as FObj, ShipStatus
from swgoh.recommend.mods import Issue, ModReport, UnitModReport
from swgoh.recommend.plan import build_tonight_plan
from swgoh.recommend.squads import Objective as SObj, SquadPlan, SquadReport, MemberStatus
from swgoh.models import Unit


def _mods_report():
    r = UnitModReport(
        unit=Unit("CALKESTIS", "Cal Kestis", gear_level=13),
        is_priority=False, weight=0.5, recommended_sets=[], recommended_arrow="Speed", note="",
        fully_modded=True, issues=[Issue("arrow_primary", "Arrow is Health", 2)],
    )
    return ModReport("ShizzNizzle", "474168985", [r], total_mods=1, unleveled_mods=0, low_rarity_mods=0)


def _fleet_report():
    cap = ShipStatus("CAP", "Executrix", owned=True, stars=7, is_capital=True, pilots=[])
    plan = FleetTargetPlan(
        name="Executrix (offense)", tier="S", note="", capital=cap, core=[], support=[],
        objectives=[FObj("gear_pilot", "Gear Bossk to g12+ to strengthen Hound's Tooth", 9.0, "BOSSK")],
    )
    return FleetReport("ShizzNizzle", "474168985", recommended=plan)


def _squad_report():
    bh = SquadPlan(
        name="Bounty Hunters", tier="S", tags=["raid_krayt"], note="",
        members=[MemberStatus("BOSSK", "Bossk", True, True, stars=7, gear_level=8)],
        objectives=[SObj("gear", "Gear Bossk to g12+ (now g8)", 8.0, "BOSSK")],
    )
    # Force the "Ready" status path by giving it a high-readiness single member.
    bh.members = [MemberStatus("BOSSK", "Bossk", True, True, stars=7, gear_level=13, relic_level=5)]
    bh.objectives = [SObj("gear", "Gear Bossk to g12+ (now g8)", 8.0, "BOSSK")]
    return SquadReport("ShizzNizzle", "474168985", [bh])


def test_multi_source_unit_ranks_first():
    plan = build_tonight_plan(_mods_report(), _fleet_report(), _squad_report())
    assert plan.units
    top = plan.units[0]
    assert top.base_id == "BOSSK"      # wanted by Fleet AND a squad
    assert top.multi
    assert len(top.sources) == 2


def test_cross_feature_boost_beats_single_source():
    plan = build_tonight_plan(_mods_report(), _fleet_report(), _squad_report())
    bossk = next(u for u in plan.units if u.base_id == "BOSSK")
    cal = next(u for u in plan.units if u.base_id == "CALKESTIS")
    # Bossk: (9+8) * 1.5 = 25.5 ; Cal: 2 * 1.0 = 2
    assert bossk.score > cal.score
    assert bossk.score == 25.5


def test_only_ready_close_squads_contribute():
    # A "Build" squad (few owned) should not feed the tonight plan.
    build_squad = SquadPlan(
        name="Inquisitorius", tier="A", tags=["gac"], note="",
        members=[MemberStatus("GRANDINQUISITOR", "Grand Inquisitor", True, False)],
        objectives=[SObj("unlock", "Unlock Grand Inquisitor", 10.0, "GRANDINQUISITOR")],
    )
    report = SquadReport("p", "1", [build_squad])
    plan = build_tonight_plan(_mods_report(), _fleet_report(), report)
    assert all(u.base_id != "GRANDINQUISITOR" for u in plan.units)


def test_headline_uses_highest_weight_contribution():
    plan = build_tonight_plan(_mods_report(), _fleet_report(), _squad_report())
    bossk = next(u for u in plan.units if u.base_id == "BOSSK")
    assert "Hound's Tooth" in bossk.headline   # fleet weight 9 > squad weight 8
