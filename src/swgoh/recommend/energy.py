"""Energy Focus — point idle energy pools at goal-relevant farming.

The Tonight plan is built from *gear/build* objectives, which spend Light/Dark
(gear) and Fleet (ship) energy. That leaves **Cantina** and **Mod** energy idle.
This analyzer closes the Cantina gap: it takes the characters your squad/fleet
goals actually need (still unowned, or under 7★ so they want shards), ranks them
by how many goals they serve, and — via the curated `farm_locations.yaml` —
tells you which to farm with Cantina energy.

The ranking is fully data-driven from your roster + existing target configs; the
farm map only annotates *where* each is farmed (and is easy to correct).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

from ..models import Player
from ..names import display_name
from ..ships import pilots_of

GOAL_TIER_WEIGHT = {"S": 3.0, "A": 2.0, "B": 1.0}
UNLOCK_MULTIPLIER = 1.4  # unlocking a missing member is worth more than a star-up


def load_farm_locations(path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    import yaml

    if path is not None:
        text = Path(path).read_text(encoding="utf-8")
    else:
        text = resources.files("swgoh.data").joinpath("farm_locations.yaml").read_text("utf-8")
    data = yaml.safe_load(text) or {}
    return {str(k): (v or {}) for k, v in data.items()}


@dataclass
class FarmTarget:
    base_id: str
    name: str
    action: str          # "unlock" | "star"
    action_label: str    # "Unlock" | "5★ → 7★"
    goals: list[str]     # distinct goal names this character serves
    priority: float
    energy: str | None = None
    node: str = ""
    verify: bool = False

    @property
    def detail(self) -> str:
        return f"{self.action_label} {self.name} — serves {', '.join(self.goals)}"


@dataclass
class EnergyReport:
    player_name: str
    ally_code: str
    cantina: list[FarmTarget] = field(default_factory=list)   # the focus pool
    other: list[FarmTarget] = field(default_factory=list)     # mapped to other pools
    unmapped: list[FarmTarget] = field(default_factory=list)  # no farm location yet


def _goal_index(
    squad_targets: list[dict[str, Any]],
    fleet_targets: list[dict[str, Any]],
) -> dict[str, list[tuple[str, str]]]:
    """base_id -> list of (goal_name, tier). Fleet contributes ship PILOTS."""
    goals: dict[str, list[tuple[str, str]]] = {}

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

    return goals


def analyze_energy(
    player: Player,
    farm_map: dict[str, dict[str, Any]] | None = None,
    squad_targets: list[dict[str, Any]] | None = None,
    fleet_targets: list[dict[str, Any]] | None = None,
) -> EnergyReport:
    if farm_map is None:
        farm_map = load_farm_locations()
    if squad_targets is None:
        from .squads import load_squad_targets

        squad_targets = load_squad_targets()
    if fleet_targets is None:
        from .fleet import load_fleet_targets

        fleet_targets = load_fleet_targets()

    goals = _goal_index(squad_targets, fleet_targets)

    targets: list[FarmTarget] = []
    for base_id, goal_list in goals.items():
        u = player.unit(base_id)
        if u is None:
            action, label = "unlock", "Unlock"
        elif u.stars < 7:
            action, label = "star", f"{u.stars}★ → 7★"
        else:
            continue  # already 7★ and owned — no shards needed

        distinct = sorted({g for g, _ in goal_list})
        value = sum(GOAL_TIER_WEIGHT.get(tier, 1.0) for _, tier in goal_list)
        value *= 1 + 0.25 * (len(distinct) - 1)  # cross-goal leverage
        if action == "unlock":
            value *= UNLOCK_MULTIPLIER

        farm = farm_map.get(base_id) or {}
        targets.append(
            FarmTarget(
                base_id=base_id,
                name=display_name(base_id),
                action=action,
                action_label=label,
                goals=distinct,
                priority=round(value, 1),
                energy=(str(farm["energy"]).lower() if farm.get("energy") else None),
                node=str(farm.get("node") or ""),
                verify=bool(farm.get("verify", False)),
            )
        )

    targets.sort(key=lambda t: t.priority, reverse=True)
    return EnergyReport(
        player_name=player.name,
        ally_code=player.ally_code,
        cantina=[t for t in targets if t.energy == "cantina"],
        other=[t for t in targets if t.energy and t.energy != "cantina"],
        unmapped=[t for t in targets if not t.energy],
    )
