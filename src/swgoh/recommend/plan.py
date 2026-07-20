"""Unified "what to upgrade tonight" plan.

Merges the objectives from the Mods, Fleet, and Squad analyzers into one ranked
list keyed by unit. A unit wanted by several plans (e.g. Bossk — needed for both
Hound's Tooth in Fleet and the Bounty Hunters raid squad) rises to the top,
because one investment pays off in multiple places. That cross-feature leverage
is the whole point.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..names import display_name
from .fleet import FleetReport
from .mods import ModReport
from .squads import SquadReport


def _norm(priority: float, cap: float = 10.0) -> float:
    """Clamp differing analyzer priority scales into a common 0..cap range."""
    return max(0.0, min(cap, priority))


@dataclass
class Contribution:
    source: str   # short label, e.g. "Fleet (Executrix)", "Bounty Hunters squad", "Mods"
    kind: str     # gear / unlock / star / mod_pilot / mods ...
    detail: str
    weight: float


@dataclass
class UnitPlan:
    base_id: str
    name: str
    contributions: list[Contribution] = field(default_factory=list)

    @property
    def sources(self) -> list[str]:
        seen: list[str] = []
        for c in self.contributions:
            if c.source not in seen:
                seen.append(c.source)
        return seen

    @property
    def score(self) -> float:
        total = sum(c.weight for c in self.contributions)
        # Cross-feature boost: each extra distinct source adds 50%.
        return round(total * (1 + 0.5 * (len(self.sources) - 1)), 1)

    @property
    def _top(self) -> Contribution:
        return max(self.contributions, key=lambda c: c.weight)

    @property
    def headline(self) -> str:
        return self._top.detail

    @property
    def primary_kind(self) -> str:
        return self._top.kind

    @property
    def multi(self) -> bool:
        return len(self.sources) > 1


@dataclass
class TonightPlan:
    player_name: str
    ally_code: str
    units: list[UnitPlan] = field(default_factory=list)


def build_tonight_plan(
    mods: ModReport,
    fleet: FleetReport,
    squads: SquadReport,
    limit: int = 15,
) -> TonightPlan:
    buckets: dict[str, UnitPlan] = {}

    def add(base_id: str, contribution: Contribution) -> None:
        if not base_id:
            return
        plan = buckets.get(base_id)
        if plan is None:
            plan = UnitPlan(base_id=base_id, name=display_name(base_id))
            buckets[base_id] = plan
        plan.contributions.append(contribution)

    # Mods — units flagged with fixable mod work.
    for r in mods.flagged_units:
        if not r.issues:
            continue
        top = max(r.issues, key=lambda i: i.severity)
        add(
            r.unit.base_id,
            Contribution("Mods", "mods", f"{r.unit.name}: {top.detail}", _norm(r.raw_severity)),
        )

    # Fleet — the single recommended fleet's build path.
    if fleet.recommended:
        source = f"Fleet ({fleet.recommended.name})"
        for o in fleet.recommended.objectives:
            add(o.target_base_id, Contribution(source, o.kind, o.detail, _norm(o.priority)))

    # Squads — only near-fieldable ones (Ready/Close) are worth tonight's effort.
    for squad in squads.squads:
        if squad.status not in ("Ready", "Close"):
            continue
        source = f"{squad.name} squad"
        for o in squad.objectives:
            add(o.target_base_id, Contribution(source, o.kind, o.detail, _norm(o.priority)))

    units = sorted(buckets.values(), key=lambda u: u.score, reverse=True)
    return TonightPlan(
        player_name=mods.player_name,
        ally_code=mods.ally_code,
        units=units[:limit],
    )
