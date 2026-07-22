"""Mod slicing priority — where to spend Mod energy / slicing materials.

Slicing upgrades a mod's tier (E→D→C→B→A) and eventually its dots (5→6),
raising stat values (and often its speed). It's the main Mod-energy sink the
hygiene analyzer ignores. This ranks which equipped mods are worth slicing,
focused on **speed** (the prize stat) on units that serve your goals.

Candidate types (per equipped mod with headroom):
  - to_gold_6 : a 6-dot below gold -> slice up to 6A (cheap, big — do first)
  - to_6dot   : a maxed 5A mod     -> slice to 6-dot
  - to_gold_5 : a 5-dot below gold -> slice up toward 5A

Only mods that already carry real speed (or are a speed arrow, or are 6-dot) are
listed — slicing a speed-less common mod isn't worth the mats.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..models import Player
from ..names import display_name
from .goals import build_goal_index, goal_value

SPEED_FLOOR = 6.0
TYPE_MULT = {"to_gold_6": 1.5, "to_6dot": 1.2, "to_gold_5": 1.0}
TIER_LETTER = {1: "E", 2: "D", 3: "C", 4: "B", 5: "A"}
MAX_CANDIDATES = 25


@dataclass
class SliceCandidate:
    base_id: str
    unit_name: str
    slot: str
    set_name: str
    speed: float
    action: str        # human-readable slice step
    kind: str
    goals: list[str]
    priority: float


@dataclass
class SliceReport:
    player_name: str
    ally_code: str
    candidates: list[SliceCandidate] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.candidates)


def _classify(rarity: int, tier: int, level: int) -> tuple[str, str] | None:
    """Return (kind, action_label) for a sliceable mod, or None if maxed/not sliceable."""
    if rarity == 6 and tier < 5:
        return "to_gold_6", f"6{TIER_LETTER.get(tier, tier)} → 6A (gold)"
    if rarity == 5 and tier == 5 and level >= 15:
        return "to_6dot", "5A → 6-dot"
    if rarity == 5 and tier < 5:
        return "to_gold_5", f"5{TIER_LETTER.get(tier, tier)} → 5A (gold)"
    return None


def analyze_slicing(
    player: Player,
    squad_targets: list[dict[str, Any]] | None = None,
    fleet_targets: list[dict[str, Any]] | None = None,
    defense_targets: dict[str, Any] | None = None,
    priority_config: dict[str, dict[str, Any]] | None = None,
) -> SliceReport:
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

    goal_index, _ = build_goal_index(squad_targets, fleet_targets)
    wall_ids = set(_weights(defense_targets).keys())

    candidates: list[SliceCandidate] = []
    for u in player.units:
        value, goals = goal_value(u.base_id, goal_index)
        tracked = value > 0 or u.base_id in priority_config or u.base_id in wall_ids
        if not tracked:
            continue  # only slice mods on units you care about
        base = value if value > 0 else 1.0

        for m in u.mods:
            cls = _classify(m.rarity, m.tier, m.level)
            if cls is None:
                continue
            kind, action = cls
            # worth slicing only if it has real speed, is a speed arrow, or is 6-dot
            if not (m.speed >= SPEED_FLOOR or m.primary_name == "Speed" or m.rarity == 6):
                continue
            score = round(base * (0.5 + m.speed / 20.0) * TYPE_MULT[kind], 1)
            candidates.append(
                SliceCandidate(
                    base_id=u.base_id,
                    unit_name=display_name(u.base_id),
                    slot=m.slot_name,
                    set_name=m.set_name,
                    speed=m.speed,
                    action=action,
                    kind=kind,
                    goals=goals,
                    priority=score,
                )
            )

    candidates.sort(key=lambda c: c.priority, reverse=True)
    return SliceReport(
        player_name=player.name,
        ally_code=player.ally_code,
        candidates=candidates[:MAX_CANDIDATES],
    )
