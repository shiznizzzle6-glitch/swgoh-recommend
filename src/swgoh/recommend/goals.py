"""Shared goal index: which of your target squads/fleets each unit serves.

Several analyzers (relics, zetas, energy) rank units by how many of your tracked
goals they contribute to. This centralizes that: a unit's value is the tier-
weighted sum of the goals it's in, boosted for serving several at once.
"""
from __future__ import annotations

from typing import Any

from ..ships import pilots_of

TIER_WEIGHT = {"S": 3.0, "A": 2.0, "B": 1.0}


def build_goal_index(
    squad_targets: list[dict[str, Any]],
    fleet_targets: list[dict[str, Any]],
) -> tuple[dict[str, list[tuple[str, str]]], set[str]]:
    """base_id -> [(goal_label, tier)], plus the set of base_ids that are fleet pilots."""
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
        name = f"{t.get('name', 'Fleet')} fleet"
        ships = [t.get("capital")] + list(t.get("core", [])) + list(t.get("support", []))
        for ship in ships:
            for pilot in pilots_of(str(ship or "")):
                add(pilot, name, tier)
                fleet_pilots.add(pilot)

    return goals, fleet_pilots


def goal_value(base_id: str, goal_index: dict[str, list[tuple[str, str]]]) -> tuple[float, list[str]]:
    """Tier-weighted value + distinct goal labels for a unit (0.0 / [] if none)."""
    goal_list = goal_index.get(base_id, [])
    if not goal_list:
        return 0.0, []
    distinct = sorted({g for g, _ in goal_list})
    value = sum(TIER_WEIGHT.get(tier, 1.0) for _, tier in goal_list)
    value *= 1 + 0.2 * (len(distinct) - 1)
    return value, distinct
