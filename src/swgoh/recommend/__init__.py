"""Recommendation engines."""
from __future__ import annotations

from .fleet import FleetReport, analyze_fleet
from .mods import ModReport, UnitModReport, analyze_roster, load_priority_config
from .plan import TonightPlan, UnitPlan, build_tonight_plan
from .squads import SquadReport, analyze_squads

__all__ = [
    "ModReport",
    "UnitModReport",
    "analyze_roster",
    "load_priority_config",
    "FleetReport",
    "analyze_fleet",
    "SquadReport",
    "analyze_squads",
    "TonightPlan",
    "UnitPlan",
    "build_tonight_plan",
]
