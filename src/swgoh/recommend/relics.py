"""Relic upgrade priority.

Relics (Gear 13 + level 85 required) are one of the biggest power jumps in the
game, and their materials come from scavenging surplus gear — so a deep gear
inventory is relic fuel waiting to be spent. This analyzer answers *which* units
to spend it on, ranked by real payoff:

- **Fleet pilots** — a pilot's relic raises the CHARACTER stats their ship
  inherits, so it's a direct fleet-arena power boost (your top focus).
- **Defense-wall units** — sustain scales hardest with relic, so relics turn
  arena draws into holds (the Cal/Inquisitor insight).
- **Squad members / priority units** — general goal progress.

Early relic levels are cheap (basic scavenged mats) and high-value, so a
goal-relevant unit sitting at R1-R2 is usually a better spend than pushing an
already-high relic higher. The tool can't see your actual material inventory
(the API doesn't expose it) — this is a priority ranking, not a budget.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..models import Player
from ..names import display_name
from ..ships import ships_piloted_by

TARGET_RELIC = 5            # a strong baseline; beyond this is diminishing returns
TIER_WEIGHT = {"S": 3.0, "A": 2.0, "B": 1.0}
FLEET_PILOT_MULT = 1.3     # relics on pilots boost ships — fleet arena is the focus
WALL_MULT = 1.2            # sustain scales hardest with relic
PRIORITY_MULT = 1.1
BASE_NO_GOAL = 0.6         # eligible but not tied to any tracked goal


@dataclass
class RelicTarget:
    base_id: str
    name: str
    relic_level: int
    roles: list[str]        # e.g. ["Fleet pilot", "Defense wall"]
    goals: list[str]        # distinct goal labels
    priority: float
    note: str = ""

    @property
    def below_target(self) -> bool:
        return self.relic_level < TARGET_RELIC

    @property
    def target_label(self) -> str:
        nxt = TARGET_RELIC if self.below_target else self.relic_level + 1
        return f"R{self.relic_level} → R{nxt}"


@dataclass
class RelicReport:
    player_name: str
    ally_code: str
    eligible: list[RelicTarget] = field(default_factory=list)  # goal-tied, ranked
    others: list[RelicTarget] = field(default_factory=list)    # eligible, no goal
    eligible_count: int = 0


def _goal_context(
    squad_targets: list[dict[str, Any]],
    fleet_targets: list[dict[str, Any]],
) -> tuple[dict[str, list[tuple[str, str]]], set[str]]:
    """base_id -> [(goal, tier)], plus the set of base_ids that are fleet pilots."""
    from ..ships import pilots_of

    goals: dict[str, list[tuple[str, str]]] = {}
    fleet_pilots: set[str] = set()

    def add(base_id: str, name: str, tier: str) -> None:
        if base_id:
            goals.setdefault(base_id, []).append((name, tier))

    for t in squad_targets:
        tier = str(t.get("tier", "B"))
        for b in t.get("members", []):
            add(str(b), str(t.get("name", "Squad")), tier)

    for t in fleet_targets:
        tier = str(t.get("tier", "B"))
        name = str(t.get("name", "Fleet"))
        ships = [t.get("capital")] + list(t.get("core", [])) + list(t.get("support", []))
        for ship in ships:
            for pilot in pilots_of(str(ship or "")):
                add(pilot, f"{name} fleet", tier)
                fleet_pilots.add(pilot)

    return goals, fleet_pilots


def _note(roles: list[str], goals: list[str], base_id: str, is_fleet_pilot: bool) -> str:
    bits: list[str] = []
    if is_fleet_pilot:
        ships = [display_name(s) for s in ships_piloted_by(base_id)]
        if ships:
            bits.append(f"Boosts {', '.join(ships[:2])} in fleet arena (pilot relics raise ship stats).")
    if "Defense wall" in roles:
        bits.append("Sustain scales hardest with relic — hardens your arena defense.")
    if not bits and goals:
        bits.append(f"Progresses {', '.join(goals[:2])}.")
    return " ".join(bits)


def analyze_relics(
    player: Player,
    squad_targets: list[dict[str, Any]] | None = None,
    fleet_targets: list[dict[str, Any]] | None = None,
    defense_targets: dict[str, Any] | None = None,
    priority_config: dict[str, dict[str, Any]] | None = None,
) -> RelicReport:
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

    goal_index, fleet_pilots = _goal_context(squad_targets, fleet_targets)
    wall_ids = set(_weights(defense_targets).keys())

    eligible: list[RelicTarget] = []
    others: list[RelicTarget] = []

    for u in player.units:
        if u.gear_level < 13 or u.level < 85:
            continue  # relics need Gear 13 + level 85

        goal_list = goal_index.get(u.base_id, [])
        distinct = sorted({g for g, _ in goal_list})
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

        value = sum(TIER_WEIGHT.get(tier, 1.0) for _, tier in goal_list)
        value *= 1 + 0.2 * (len(distinct) - 1)  # cross-goal leverage
        if value <= 0 and (is_wall or is_priority):
            value = 1.0  # tracked for defense/mods even without a squad/fleet goal
        has_goal = value > 0

        mult = 1.0
        if is_fleet_pilot:
            mult *= FLEET_PILOT_MULT
        if is_wall:
            mult *= WALL_MULT
        if is_priority:
            mult *= PRIORITY_MULT

        base = value if has_goal else BASE_NO_GOAL
        urgency = 1 + 0.15 * max(0, TARGET_RELIC - u.relic_level)
        score = round(base * mult * urgency, 1)

        target = RelicTarget(
            base_id=u.base_id,
            name=display_name(u.base_id),
            relic_level=u.relic_level,
            roles=roles,
            goals=distinct,
            priority=score,
            note=_note(roles, distinct, u.base_id, is_fleet_pilot),
        )
        (eligible if (has_goal or roles) else others).append(target)

    eligible.sort(key=lambda t: t.priority, reverse=True)
    others.sort(key=lambda t: (t.relic_level < TARGET_RELIC, -t.relic_level), reverse=True)
    return RelicReport(
        player_name=player.name,
        ally_code=player.ally_code,
        eligible=eligible,
        others=others,
        eligible_count=len(eligible) + len(others),
    )
