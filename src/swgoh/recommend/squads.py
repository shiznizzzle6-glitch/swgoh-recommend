"""Squad-builder for guild contribution.

Matches your roster against a curated set of useful squads (`squad_targets.yaml`,
tagged by where they help — raids, TW, TB, GAC) and, for each, computes how
close you are to fielding it and the ordered steps to get there. Sorted so the
squads you can field (or nearly) surface first — that's your fastest way to
contribute.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

from ..models import Player
from ..names import display_name

GEAR_TARGET = 12
TIER_WEIGHT = {"S": 3.0, "A": 2.0, "B": 1.0}

PRIO_LEADER = 10
PRIO_MEMBER = 7


def _member_frac(owned: bool, stars: int, gear: int, relic: int) -> float:
    if not owned:
        return 0.0
    invest = min(1.0, (gear + relic * 1.5) / 18.0)
    return 0.3 * (stars / 7) + 0.7 * invest


def load_squad_targets(path: str | Path | None = None) -> list[dict[str, Any]]:
    import yaml

    if path is not None:
        text = Path(path).read_text(encoding="utf-8")
    else:
        text = resources.files("swgoh.data").joinpath("squad_targets.yaml").read_text("utf-8")
    return list(yaml.safe_load(text) or [])


@dataclass
class MemberStatus:
    base_id: str
    name: str
    is_leader: bool
    owned: bool
    stars: int = 0
    gear_level: int = 0
    relic_level: int = 0

    @property
    def frac(self) -> float:
        return _member_frac(self.owned, self.stars, self.gear_level, self.relic_level)


@dataclass
class Objective:
    kind: str
    detail: str
    priority: float
    target_base_id: str = ""


@dataclass
class SquadPlan:
    name: str
    tier: str
    tags: list[str]
    note: str
    members: list[MemberStatus]  # leader first
    objectives: list[Objective] = field(default_factory=list)

    @property
    def owned_count(self) -> int:
        return sum(1 for m in self.members if m.owned)

    @property
    def readiness(self) -> float:
        if not self.members:
            return 0.0
        return round(100 * sum(m.frac for m in self.members) / len(self.members), 1)

    @property
    def status(self) -> str:
        if self.owned_count == len(self.members) and self.readiness >= 65:
            return "Ready"
        if self.owned_count >= len(self.members) - 1 and self.readiness >= 35:
            return "Close"
        return "Build"

    @property
    def value(self) -> float:
        return self.readiness * TIER_WEIGHT.get(self.tier, 1.0)


@dataclass
class SquadReport:
    player_name: str
    ally_code: str
    squads: list[SquadPlan] = field(default_factory=list)


def _member_status(base_id: str, is_leader: bool, player: Player) -> MemberStatus:
    u = player.unit(base_id)
    return MemberStatus(
        base_id=base_id,
        name=display_name(base_id),
        is_leader=is_leader,
        owned=u is not None,
        stars=u.stars if u else 0,
        gear_level=u.gear_level if u else 0,
        relic_level=u.relic_level if u else 0,
    )


def _build_plan(target: dict[str, Any], player: Player) -> SquadPlan:
    ids = list(target.get("members", []))
    members = [_member_status(b, i == 0, player) for i, b in enumerate(ids)]
    plan = SquadPlan(
        name=target.get("name", ids[0] if ids else "Squad"),
        tier=str(target.get("tier", "B")),
        tags=[str(t) for t in target.get("tags", [])],
        note=str(target.get("note") or "").strip(),
        members=members,
    )

    objectives: list[Objective] = []
    for m in members:
        base = PRIO_LEADER if m.is_leader else PRIO_MEMBER
        role = "leader" if m.is_leader else "member"
        if not m.owned:
            objectives.append(
                Objective("unlock", f"Unlock {m.name} ({role})", base, m.base_id)
            )
        elif m.gear_level < GEAR_TARGET:
            objectives.append(
                Objective(
                    "gear",
                    f"Gear {m.name} to g{GEAR_TARGET}+ (now g{m.gear_level})",
                    base - 2 + (GEAR_TARGET - m.gear_level) * 0.2,
                    m.base_id,
                )
            )
        if m.owned and m.stars and m.stars < 7:
            objectives.append(
                Objective("star", f"Star up {m.name} ({m.stars}★ → 7★)", base - 5, m.base_id)
            )
    objectives.sort(key=lambda o: o.priority, reverse=True)
    plan.objectives = objectives
    return plan


def analyze_squads(player: Player, targets: list[dict[str, Any]] | None = None) -> SquadReport:
    if targets is None:
        targets = load_squad_targets()
    plans = [_build_plan(t, player) for t in targets]
    # Closest-to-fieldable first, with stronger squads breaking ties.
    plans.sort(key=lambda p: (p.readiness, p.value), reverse=True)
    return SquadReport(player_name=player.name, ally_code=player.ally_code, squads=plans)
