"""Zeta / Omicron upgrade priority.

Zetas and omicrons are big, materials-gated ability upgrades. This ranks the ones
you haven't learned yet on units that matter to your goals, computing learned
status live from Comlink skill tiers (see swgoh.abilities). Zetas and omicrons
use different materials, so they're ranked in separate lists. Omicrons also carry
the game modes they work in (GAC/TW/TB), shown as tags.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..abilities import abilities_for, is_omicron_learned, is_zeta_learned, zeta_tier
from ..models import Player
from ..names import display_name
from .goals import build_goal_index, goal_value

FLEET_PILOT_MULT = 1.2
WALL_MULT = 1.15
PRIORITY_MULT = 1.1

# Comlink reports skill tiers exactly 2 below swgoh.gg's ability_tier / tier_max
# scale — validated 665/665 abilities with zero variance against a live snapshot.
# The learned-status rule is defined on the swgoh (in-game) scale, so we lift
# Comlink tiers by this before applying it.
COMLINK_TIER_OFFSET = 2


@dataclass
class AbilityTarget:
    base_id: str
    unit_name: str
    ability_id: str
    ability_name: str
    kind: str            # "zeta" | "omicron"
    modes: list[str]     # game modes (omicron only)
    goals: list[str]
    roles: list[str]
    priority: float
    current_tier: int
    max_tier: int


@dataclass
class ZetaReport:
    player_name: str
    ally_code: str
    zetas: list[AbilityTarget] = field(default_factory=list)
    omicrons: list[AbilityTarget] = field(default_factory=list)
    other_zetas: int = 0      # unlearned zetas on units with no tracked goal
    other_omicrons: int = 0


def analyze_zetas(
    player: Player,
    squad_targets: list[dict[str, Any]] | None = None,
    fleet_targets: list[dict[str, Any]] | None = None,
    defense_targets: dict[str, Any] | None = None,
    priority_config: dict[str, dict[str, Any]] | None = None,
    comlink_tier_offset: int = COMLINK_TIER_OFFSET,
) -> ZetaReport:
    if squad_targets is None:
        from .squads import load_squad_targets

        squad_targets = load_squad_targets()
    if fleet_targets is None:
        from .fleet import load_fleet_targets

        fleet_targets = load_fleet_targets()
    if defense_targets is None:
        from .defense import load_defense_targets

        defense_targets = load_defense_targets()
    if priority_config is None:
        from .mods import load_priority_config

        priority_config = load_priority_config()

    from .defense import _weights

    goal_index, fleet_pilots = build_goal_index(squad_targets, fleet_targets)
    wall_ids = set(_weights(defense_targets).keys())

    zetas: list[AbilityTarget] = []
    omicrons: list[AbilityTarget] = []
    other_zetas = other_omicrons = 0

    for u in player.units:
        defs = abilities_for(u.base_id)
        if not defs or not u.skills:
            continue

        value, goals = goal_value(u.base_id, goal_index)
        is_fleet_pilot = u.base_id in fleet_pilots
        is_wall = u.base_id in wall_ids
        is_priority = u.base_id in priority_config
        roles: list[str] = []
        if is_fleet_pilot:
            roles.append("Fleet pilot")
        if is_wall:
            roles.append("Defense wall")
        if is_priority:
            roles.append("Priority")

        has_goal = value > 0 or bool(roles)
        base = value if value > 0 else (1.0 if roles else 0.0)
        mult = 1.0
        if is_fleet_pilot:
            mult *= FLEET_PILOT_MULT
        if is_wall:
            mult *= WALL_MULT
        if is_priority:
            mult *= PRIORITY_MULT
        score = round(base * mult, 1)

        for d in defs:
            raw = u.skills.get(d["id"])
            if raw is None:
                continue  # ability not on this unit's kit / not unlocked
            tier = raw + comlink_tier_offset  # lift Comlink -> swgoh (in-game) scale

            def make(kind: str) -> AbilityTarget:
                return AbilityTarget(
                    base_id=u.base_id,
                    unit_name=display_name(u.base_id),
                    ability_id=d["id"],
                    ability_name=d.get("name", d["id"]),
                    kind=kind,
                    modes=list(d.get("modes", [])),
                    goals=goals,
                    roles=roles,
                    priority=score,
                    current_tier=tier,
                    max_tier=d["max"],
                )

            if d.get("z") and not is_zeta_learned(d, tier):
                if has_goal:
                    zetas.append(make("zeta"))
                else:
                    other_zetas += 1
            # Only surface an omicron once it's actually applicable (zeta, if any,
            # already learned) — you can't omicron an ability you haven't zeta'd.
            if d.get("o") and not is_omicron_learned(d, tier):
                zeta_ready = (not d.get("z")) or tier >= zeta_tier(d)
                if zeta_ready:
                    if has_goal:
                        omicrons.append(make("omicron"))
                    else:
                        other_omicrons += 1

    zetas.sort(key=lambda t: t.priority, reverse=True)
    omicrons.sort(key=lambda t: t.priority, reverse=True)
    return ZetaReport(
        player_name=player.name,
        ally_code=player.ally_code,
        zetas=zetas,
        omicrons=omicrons,
        other_zetas=other_zetas,
        other_omicrons=other_omicrons,
    )
