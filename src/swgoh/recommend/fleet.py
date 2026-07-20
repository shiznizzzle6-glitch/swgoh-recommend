"""Meta-target-driven Fleet build-priority engine.

Rather than grouping ships by faction (Fleet arena has no same-faction bonus and
mixing is fine), this matches your roster against a curated set of
known-effective meta fleets (`fleet_targets.yaml`) and ranks the build path to
the one you're closest to fielding well.

Key mechanic baked in: a ship's power comes from its *pilot's* character stats
(gear, relic, stars, and mods — though notably NOT mod speed, which doesn't
affect ships). So objectives center on gearing the right pilots and building the
keystone ships, capital pilot first.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

from ..models import Player
from ..names import display_name
from ..ships import ship_data

PILOT_GEAR_TARGET = 12
CAPITAL_GEAR_TARGET = 12
MOD_LEVELED_LEVEL = 12       # a mod at this level+ contributes its stats to the ship
MOD_COVERAGE_TARGET = 0.8    # fraction of 6 mods leveled to count a pilot "modded"

TIER_WEIGHT = {"S": 3.0, "A": 2.0, "B": 1.0}

# Objective base priorities (higher = do sooner).
PRIO_CAPITAL_PILOT = 12
PRIO_CORE_TOP = 10          # first/most-important core ship
PRIO_SUPPORT = 3


def _pilot_score(gear: int, relic: int) -> float:
    return gear + relic * 1.5


def load_fleet_targets(path: str | Path | None = None) -> list[dict[str, Any]]:
    import yaml

    if path is not None:
        text = Path(path).read_text(encoding="utf-8")
    else:
        text = resources.files("swgoh.data").joinpath("fleet_targets.yaml").read_text("utf-8")
    return list(yaml.safe_load(text) or [])


@dataclass
class PilotStatus:
    base_id: str
    name: str
    owned: bool
    stars: int = 0
    gear_level: int = 0
    relic_level: int = 0
    mods_leveled: int = 0  # count of this pilot's mods at MOD_LEVELED_LEVEL+

    @property
    def score(self) -> float:
        return _pilot_score(self.gear_level, self.relic_level) if self.owned else 0.0

    @property
    def mod_coverage(self) -> float:
        """0..1 — how much of a full 6-mod set is leveled (contributes to the ship)."""
        return min(1.0, self.mods_leveled / 6) if self.owned else 0.0

    @property
    def geared(self) -> bool:
        return self.owned and self.gear_level >= PILOT_GEAR_TARGET


@dataclass
class ShipStatus:
    base_id: str
    name: str
    owned: bool
    stars: int
    is_capital: bool
    pilots: list[PilotStatus]

    @property
    def best_pilot(self) -> PilotStatus | None:
        owned = [p for p in self.pilots if p.owned]
        if owned:
            return max(owned, key=lambda p: p.score)
        return self.pilots[0] if self.pilots else None

    @property
    def power_frac(self) -> float:
        """0..1 estimate of how built this ship is.

        Ship power comes from the pilot's character stats — gear/relic AND mods
        (mods contribute everything except Speed, which doesn't affect ships) —
        plus the ship's own stars.
        """
        if not self.owned:
            return 0.0
        pilot = self.best_pilot
        if not pilot or not pilot.owned:
            return 0.15  # ship owned but pilot missing -> barely usable
        gear = min(1.0, _pilot_score(pilot.gear_level, pilot.relic_level) / 18.0)
        star = self.stars / 7
        return 0.3 * star + 0.5 * gear + 0.2 * pilot.mod_coverage


@dataclass
class Objective:
    kind: str
    detail: str
    priority: float
    target_base_id: str = ""


@dataclass
class FleetTargetPlan:
    name: str
    tier: str
    note: str
    capital: ShipStatus
    core: list[ShipStatus]
    support: list[ShipStatus]
    readiness: float = 0.0  # 0..100
    objectives: list[Objective] = field(default_factory=list)

    @property
    def value(self) -> float:
        return self.readiness * TIER_WEIGHT.get(self.tier, 1.0)


@dataclass
class FleetReport:
    player_name: str
    ally_code: str
    recommended: FleetTargetPlan | None
    other_targets: list[FleetTargetPlan] = field(default_factory=list)
    current_best_ships: list[ShipStatus] = field(default_factory=list)
    owned_ships: int = 0
    owned_capitals: int = 0


def _ship_status(base_id: str, player: Player) -> ShipStatus:
    info = ship_data().get(base_id, {})
    ship_unit = player.unit(base_id)
    pilots = []
    for pilot_id in info.get("pilots", []):
        pu = player.unit(pilot_id)
        mods_leveled = (
            sum(1 for m in pu.mods if m.level >= MOD_LEVELED_LEVEL) if pu else 0
        )
        pilots.append(
            PilotStatus(
                base_id=pilot_id,
                name=display_name(pilot_id),
                owned=pu is not None,
                stars=pu.stars if pu else 0,
                gear_level=pu.gear_level if pu else 0,
                relic_level=pu.relic_level if pu else 0,
                mods_leveled=mods_leveled,
            )
        )
    return ShipStatus(
        base_id=base_id,
        name=display_name(base_id),
        owned=ship_unit is not None,
        stars=ship_unit.stars if ship_unit else 0,
        is_capital=bool(info.get("capital")),
        pilots=pilots,
    )


def _ship_objectives(ship: ShipStatus, base_priority: float, role: str) -> list[Objective]:
    objs: list[Objective] = []
    pilot = ship.best_pilot
    if not ship.owned:
        who = f" (pilot {pilot.name})" if pilot else ""
        objs.append(
            Objective(
                "unlock_ship",
                f"Unlock {ship.name}{who} — {role} of this fleet",
                base_priority,
                ship.base_id,
            )
        )
        return objs
    if pilot and not pilot.owned:
        objs.append(
            Objective(
                "unlock_pilot",
                f"Unlock {pilot.name} to field {ship.name}",
                base_priority,
                pilot.base_id,
            )
        )
    elif pilot and pilot.gear_level < PILOT_GEAR_TARGET:
        objs.append(
            Objective(
                "gear_pilot",
                f"Gear {pilot.name} to g{PILOT_GEAR_TARGET}+ (now g{pilot.gear_level}) "
                f"to strengthen {ship.name}",
                base_priority - 1 + (PILOT_GEAR_TARGET - pilot.gear_level) * 0.3,
                pilot.base_id,
            )
        )
    elif pilot and pilot.geared and pilot.mod_coverage < MOD_COVERAGE_TARGET:
        # Geared but under-modded: the ship is leaving pilot stats on the table.
        objs.append(
            Objective(
                "mod_pilot",
                f"Mod {pilot.name} for offense/survivability "
                f"({pilot.mods_leveled}/6 mods leveled) to boost {ship.name} — "
                f"Speed mods don't help ships",
                base_priority - 2,
                pilot.base_id,
            )
        )
    if ship.owned and ship.stars and ship.stars < 7:
        objs.append(
            Objective(
                "star_ship",
                f"Star up {ship.name} ({ship.stars}★ → 7★)",
                base_priority - 3 + (7 - ship.stars) * 0.2,
                ship.base_id,
            )
        )
    return objs


def _build_plan(target: dict[str, Any], player: Player) -> FleetTargetPlan:
    capital = _ship_status(target["capital"], player)
    core = [_ship_status(b, player) for b in target.get("core", [])]
    support = [_ship_status(b, player) for b in target.get("support", [])]

    core_frac = sum(s.power_frac for s in core) / len(core) if core else 0.0
    support_frac = sum(s.power_frac for s in support) / len(support) if support else 0.0
    readiness = 100 * (0.35 * capital.power_frac + 0.45 * core_frac + 0.20 * support_frac)

    plan = FleetTargetPlan(
        name=target.get("name", target["capital"]),
        tier=str(target.get("tier", "B")),
        note=str(target.get("note") or "").strip(),
        capital=capital,
        core=core,
        support=support,
        readiness=round(readiness, 1),
    )

    objectives: list[Objective] = []
    cap_pilot = capital.best_pilot
    if not capital.owned:
        objectives.append(
            Objective("unlock_ship", f"Unlock capital ship {capital.name}", PRIO_CAPITAL_PILOT, capital.base_id)
        )
    elif cap_pilot and not cap_pilot.owned:
        objectives.append(
            Objective("unlock_pilot", f"Unlock {cap_pilot.name} to pilot {capital.name}", PRIO_CAPITAL_PILOT, cap_pilot.base_id)
        )
    elif cap_pilot and cap_pilot.gear_level < CAPITAL_GEAR_TARGET:
        objectives.append(
            Objective(
                "gear_capital_pilot",
                f"Gear {cap_pilot.name} to g{CAPITAL_GEAR_TARGET}+ (now g{cap_pilot.gear_level}) "
                f"— capital pilot, biggest single boost",
                PRIO_CAPITAL_PILOT + (CAPITAL_GEAR_TARGET - cap_pilot.gear_level) * 0.3,
                cap_pilot.base_id,
            )
        )

    for i, ship in enumerate(core):
        objectives += _ship_objectives(ship, PRIO_CORE_TOP - i, "core")
    for ship in support:
        objectives += _ship_objectives(ship, PRIO_SUPPORT, "support")

    objectives.sort(key=lambda o: o.priority, reverse=True)
    plan.objectives = objectives
    return plan


def analyze_fleet(player: Player, targets: list[dict[str, Any]] | None = None) -> FleetReport:
    if targets is None:
        targets = load_fleet_targets()

    data = ship_data()
    owned_ship_ids = [u.base_id for u in player.units if u.base_id in data]
    owned_capitals = [b for b in owned_ship_ids if data[b].get("capital")]

    plans = [_build_plan(t, player) for t in targets]
    plans.sort(key=lambda p: p.value, reverse=True)

    # "What can I field right now" — strongest owned ships regardless of faction.
    owned_regular = [
        _ship_status(b, player) for b in owned_ship_ids if not data[b].get("capital")
    ]
    owned_regular.sort(key=lambda s: s.power_frac, reverse=True)

    return FleetReport(
        player_name=player.name,
        ally_code=player.ally_code,
        recommended=plans[0] if plans else None,
        other_targets=plans[1:],
        current_best_ships=owned_regular[:7],
        owned_ships=len(owned_regular),
        owned_capitals=len(owned_capitals),
    )
