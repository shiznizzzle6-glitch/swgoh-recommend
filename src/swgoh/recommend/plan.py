"""Unified "what to upgrade tonight" board.

Rather than merging every analyzer into one flat list, this presents the **top
few things to work on in each area** — Fleet, Squads, Gear, Relics, Zetas,
Energy, Mods — so you can see your whole account at a glance and drill into any
tab. A small "multi-payoff" highlight surfaces units that show up in several
areas at once (e.g. Bossk — a fleet pilot who's also a gear/zeta/farm target),
because those are the highest-leverage single investments.

Defense is intentionally excluded: Squad Arena has no separate defense team to
set, so it isn't a "tonight" action.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from ..names import display_name
from .energy import EnergyReport
from .fleet import FleetReport
from .gear import GearReport
from .mods import ModReport
from .relics import RelicReport
from .squads import SquadReport
from .zetas import ZetaReport


@dataclass
class PlanItem:
    name: str        # the unit (or target) to work on
    detail: str      # short action phrase
    score: float     # in-category priority
    base_id: str = ""


@dataclass
class PlanCategory:
    key: str
    title: str
    link: str
    items: list[PlanItem] = field(default_factory=list)


@dataclass
class Highlight:
    base_id: str
    name: str
    areas: list[str]

    @property
    def count(self) -> int:
        return len(self.areas)


@dataclass
class TonightBoard:
    player_name: str
    ally_code: str
    categories: list[PlanCategory] = field(default_factory=list)
    highlights: list[Highlight] = field(default_factory=list)


def _label(base_id: str, fallback: str) -> str:
    return display_name(base_id) if base_id else fallback


def _fleet_items(fleet: FleetReport, limit: int) -> list[PlanItem]:
    if not fleet.recommended:
        return []
    return [
        PlanItem(_label(o.target_base_id, fleet.recommended.name), o.detail, round(o.priority, 1), o.target_base_id)
        for o in fleet.recommended.objectives[:limit]
    ]


def _squad_items(squads: SquadReport, limit: int) -> list[PlanItem]:
    pairs = []
    for s in squads.squads:
        if s.status not in ("Ready", "Close"):
            continue
        for o in s.objectives:
            pairs.append((o, s.name))
    pairs.sort(key=lambda x: x[0].priority, reverse=True)
    return [
        PlanItem(_label(o.target_base_id, name), f"{o.detail} · {name}", round(o.priority, 1), o.target_base_id)
        for o, name in pairs[:limit]
    ]


def _gear_items(gear: GearReport, limit: int) -> list[PlanItem]:
    out = []
    for t in gear.eligible[:limit]:
        piece = f" · next: {t.next_pieces[0]}" if t.next_pieces else ""
        out.append(PlanItem(t.name, f"{t.target_label}{piece}", t.priority, t.base_id))
    return out


def _relic_items(relics: RelicReport, limit: int) -> list[PlanItem]:
    return [
        PlanItem(t.name, t.target_label + (f" · {t.roles[0]}" if t.roles else ""), t.priority, t.base_id)
        for t in relics.eligible[:limit]
    ]


def _zeta_items(zetas: ZetaReport, limit: int) -> list[PlanItem]:
    combined = sorted(zetas.zetas + zetas.omicrons, key=lambda t: t.priority, reverse=True)
    return [
        PlanItem(t.unit_name, f"{t.kind}: {t.ability_name}", t.priority, t.base_id)
        for t in combined[:limit]
    ]


def _energy_items(energy: EnergyReport, limit: int) -> list[PlanItem]:
    farm = sorted(
        energy.cantina + energy.other + energy.unmapped,
        key=lambda t: t.priority,
        reverse=True,
    )
    out = []
    for t in farm[:limit]:
        pool = t.energy or "farm shards"
        out.append(PlanItem(t.name, f"{t.action_label} · {pool}", t.priority, t.base_id))
    return out


def _mod_items(mods: ModReport, limit: int) -> list[PlanItem]:
    out = []
    for r in mods.flagged_units[:limit]:
        detail = max(r.issues, key=lambda i: i.severity).detail if r.issues else ""
        out.append(PlanItem(r.unit.name, detail, round(r.score, 1), r.unit.base_id))
    return out


def build_tonight_board(
    mods: ModReport,
    fleet: FleetReport,
    squads: SquadReport,
    gear: GearReport,
    relics: RelicReport,
    zetas: ZetaReport,
    energy: EnergyReport,
    limit: int = 3,
) -> TonightBoard:
    categories = [
        PlanCategory("fleet", "Fleet", "/fleet", _fleet_items(fleet, limit)),
        PlanCategory("squads", "Squads", "/squads", _squad_items(squads, limit)),
        PlanCategory("gear", "Gear", "/gear", _gear_items(gear, limit)),
        PlanCategory("relics", "Relics", "/relics", _relic_items(relics, limit)),
        PlanCategory("zetas", "Zetas & Omicrons", "/zetas", _zeta_items(zetas, limit)),
        PlanCategory("energy", "Energy", "/energy", _energy_items(energy, limit)),
        PlanCategory("mods", "Mods", "/mods", _mod_items(mods, limit)),
    ]

    # Multi-payoff highlights: units appearing in 2+ areas.
    areas: dict[str, set[str]] = defaultdict(set)
    names: dict[str, str] = {}
    for cat in categories:
        for it in cat.items:
            if it.base_id:
                areas[it.base_id].add(cat.title)
                names.setdefault(it.base_id, it.name)
    highlights = [
        Highlight(base_id, names[base_id], sorted(cats))
        for base_id, cats in areas.items()
        if len(cats) >= 2
    ]
    highlights.sort(key=lambda h: h.count, reverse=True)

    return TonightBoard(
        player_name=mods.player_name,
        ally_code=mods.ally_code,
        categories=categories,
        highlights=highlights,
    )
