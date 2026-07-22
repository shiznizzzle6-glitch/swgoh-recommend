"""Recommendation engines."""
from __future__ import annotations

from .defense import DefenseReport, DefenseTeam, WallUnit, analyze_defense
from .energy import EnergyReport, FarmTarget, analyze_energy
from .fleet import FleetReport, analyze_fleet
from .mods import ModReport, UnitModReport, analyze_roster, load_priority_config
from .plan import TonightPlan, UnitPlan, build_tonight_plan
from .relics import RelicReport, RelicTarget, analyze_relics
from .squads import SquadReport, analyze_squads
from .zetas import AbilityTarget, ZetaReport, analyze_zetas

__all__ = [
    "ModReport",
    "UnitModReport",
    "analyze_roster",
    "load_priority_config",
    "FleetReport",
    "analyze_fleet",
    "SquadReport",
    "analyze_squads",
    "DefenseReport",
    "DefenseTeam",
    "WallUnit",
    "analyze_defense",
    "EnergyReport",
    "FarmTarget",
    "analyze_energy",
    "RelicReport",
    "RelicTarget",
    "analyze_relics",
    "AbilityTarget",
    "ZetaReport",
    "analyze_zetas",
    "TonightPlan",
    "UnitPlan",
    "build_tonight_plan",
]
