"""Recommendation engines."""
from __future__ import annotations

from .defense import DefenseReport, DefenseTeam, WallUnit, analyze_defense
from .energy import EnergyReport, FarmTarget, analyze_energy
from .gear import GearReport, GearTarget, analyze_gear
from .fleet import FleetReport, analyze_fleet
from .mods import ModReport, UnitModReport, analyze_roster, load_priority_config
from .plan import Highlight, PlanCategory, PlanItem, TonightBoard, build_tonight_board
from .relics import RelicReport, RelicTarget, analyze_relics
from .slicing import SliceCandidate, SliceReport, analyze_slicing
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
    "GearReport",
    "GearTarget",
    "analyze_gear",
    "RelicReport",
    "RelicTarget",
    "analyze_relics",
    "SliceReport",
    "SliceCandidate",
    "analyze_slicing",
    "AbilityTarget",
    "ZetaReport",
    "analyze_zetas",
    "TonightBoard",
    "PlanCategory",
    "PlanItem",
    "Highlight",
    "build_tonight_board",
]
