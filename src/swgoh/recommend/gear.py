"""Gear upgrade priority.

Ranks goal-relevant units that aren't yet Gear 13, and — using swgoh.gg's gear
data — lists the actual named pieces needed for their next tier (a shopping
list). Gearing fleet pilots boosts their ships, and reaching G13 is the gate for
relics, so those weigh in. Mirrors the relic page but for gear.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..gear import MAX_TIER_WITH_PIECES, next_tier_pieces
from ..models import Player
from ..names import display_name
from .goals import build_goal_index, goal_value

TARGET_GEAR = 13
FLEET_PILOT_MULT = 1.25   # gearing pilots is the fleet-arena bottleneck
PRIORITY_MULT = 1.1


@dataclass
class GearTarget:
    base_id: str
    name: str
    gear_level: int
    next_tier: int
    next_pieces: list[str]     # named pieces for the next tier ([] past tier 12)
    tiers_to_target: int
    roles: list[str]
    goals: list[str]
    priority: float

    @property
    def target_label(self) -> str:
        return f"G{self.gear_level} → G{self.next_tier}"


@dataclass
class GearReport:
    player_name: str
    ally_code: str
    eligible: list[GearTarget] = field(default_factory=list)
    others_count: int = 0       # goal-less owned units below target gear
    eligible_count: int = 0


def analyze_gear(
    player: Player,
    squad_targets: list[dict[str, Any]] | None = None,
    fleet_targets: list[dict[str, Any]] | None = None,
    priority_config: dict[str, dict[str, Any]] | None = None,
) -> GearReport:
    if squad_targets is None:
        from .squads import load_squad_targets

        squad_targets = load_squad_targets()
    if fleet_targets is None:
        from .fleet import load_fleet_targets

        fleet_targets = load_fleet_targets()
    if priority_config is None:
        from .mods import load_priority_config

        priority_config = load_priority_config()

    goal_index, fleet_pilots = build_goal_index(squad_targets, fleet_targets)

    eligible: list[GearTarget] = []
    others = 0

    for u in player.units:
        if u.gear_level >= TARGET_GEAR:
            continue

        value, goals = goal_value(u.base_id, goal_index)
        is_fleet_pilot = u.base_id in fleet_pilots
        is_priority = u.base_id in priority_config
        roles: list[str] = []
        if is_fleet_pilot:
            roles.append("Fleet pilot")
        if is_priority:
            roles.append("Priority")

        if value <= 0 and not roles:
            others += 1
            continue

        mult = 1.0
        if is_fleet_pilot:
            mult *= FLEET_PILOT_MULT
        if is_priority:
            mult *= PRIORITY_MULT
        base = value if value > 0 else 1.0

        next_tier = u.gear_level + 1
        pieces = next_tier_pieces(u.base_id, u.gear_level) if next_tier <= MAX_TIER_WITH_PIECES else []
        eligible.append(
            GearTarget(
                base_id=u.base_id,
                name=display_name(u.base_id),
                gear_level=u.gear_level,
                next_tier=next_tier,
                next_pieces=pieces,
                tiers_to_target=TARGET_GEAR - u.gear_level,
                roles=roles,
                goals=goals,
                priority=round(base * mult, 1),
            )
        )

    eligible.sort(key=lambda t: t.priority, reverse=True)
    return GearReport(
        player_name=player.name,
        ally_code=player.ally_code,
        eligible=eligible,
        others_count=others,
        eligible_count=len(eligible),
    )
