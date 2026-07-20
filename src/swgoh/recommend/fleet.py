"""Data-driven Fleet build-priority engine.

Given a roster, it finds your strongest *coherent* fleet (an owned capital ship
plus owned ships of the same faction) and ranks concrete build objectives. The
guiding insight: a ship's combat power scales with its **pilot's** gear/relic,
so gearing the right pilots — not starring ships — is the real lever. Objectives
are ranked by leverage, capital pilot first.

Everything here is derived from your roster + the bundled ship reference; no
hand-picked "meta" is assumed, so it reflects what *you* own and have invested.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..models import Player
from ..names import display_name
from ..ships import ship_data

# A fleet pilot is "ready" at this gear level; capitals are held a notch higher.
PILOT_GEAR_TARGET = 12
CAPITAL_GEAR_TARGET = 12
# A full arena fleet is a capital plus this many ships (starters + reinforcements).
FLEET_SIZE = 6

# Objective priorities (higher = do sooner).
PRIO_CAPITAL_PILOT = 10
PRIO_UNLOCK_PILOT = 7
PRIO_INCOMPLETE_FLEET = 5
PRIO_STAR_SHIP = 1


def _pilot_score(gear: int, relic: int) -> float:
    """Rough investment proxy for how much a pilot boosts its ship."""
    return gear + relic * 1.5


@dataclass
class PilotStatus:
    base_id: str
    name: str
    owned: bool
    stars: int = 0
    gear_level: int = 0
    relic_level: int = 0

    @property
    def score(self) -> float:
        return _pilot_score(self.gear_level, self.relic_level) if self.owned else 0.0


@dataclass
class ShipStatus:
    base_id: str
    name: str
    stars: int
    is_capital: bool
    factions: list[str]
    pilots: list[PilotStatus]

    @property
    def best_pilot(self) -> PilotStatus | None:
        owned = [p for p in self.pilots if p.owned]
        return max(owned, key=lambda p: p.score) if owned else (self.pilots[0] if self.pilots else None)

    @property
    def strength(self) -> float:
        best = self.best_pilot
        pilot = best.score if best else 0.0
        return pilot + self.stars * 0.5


@dataclass
class Objective:
    kind: str
    detail: str
    priority: float
    target_base_id: str = ""


@dataclass
class FleetPlan:
    faction: str
    capital: ShipStatus
    ships: list[ShipStatus]
    objectives: list[Objective] = field(default_factory=list)

    @property
    def score(self) -> float:
        cap = self.capital.strength * 2 if self.capital else 0.0
        return cap + sum(s.strength for s in self.ships)


@dataclass
class FleetReport:
    player_name: str
    ally_code: str
    best: FleetPlan | None
    alternatives: list[FleetPlan] = field(default_factory=list)
    owned_ships: int = 0
    owned_capitals: int = 0


def _ship_status(base_id: str, player: Player) -> ShipStatus:
    info = ship_data().get(base_id, {})
    ship_unit = player.unit(base_id)
    pilots = []
    for pilot_id in info.get("pilots", []):
        pu = player.unit(pilot_id)
        pilots.append(
            PilotStatus(
                base_id=pilot_id,
                name=display_name(pilot_id),
                owned=pu is not None,
                stars=pu.stars if pu else 0,
                gear_level=pu.gear_level if pu else 0,
                relic_level=pu.relic_level if pu else 0,
            )
        )
    return ShipStatus(
        base_id=base_id,
        name=display_name(base_id),
        stars=ship_unit.stars if ship_unit else 0,
        is_capital=bool(info.get("capital")),
        factions=list(info.get("factions", [])),
        pilots=pilots,
    )


def _objectives_for(plan: FleetPlan) -> list[Objective]:
    objectives: list[Objective] = []

    # 1. Capital pilot is the linchpin of the fleet.
    cap_pilot = plan.capital.best_pilot if plan.capital else None
    if cap_pilot:
        if not cap_pilot.owned:
            objectives.append(
                Objective(
                    "unlock_pilot",
                    f"Unlock {cap_pilot.name} to pilot your capital ship {plan.capital.name}",
                    PRIO_CAPITAL_PILOT,
                    cap_pilot.base_id,
                )
            )
        elif cap_pilot.gear_level < CAPITAL_GEAR_TARGET:
            objectives.append(
                Objective(
                    "gear_capital_pilot",
                    f"Gear {cap_pilot.name} (capital pilot) to g{CAPITAL_GEAR_TARGET}+ "
                    f"(currently g{cap_pilot.gear_level}) — biggest single boost to {plan.capital.name}",
                    PRIO_CAPITAL_PILOT + (CAPITAL_GEAR_TARGET - cap_pilot.gear_level),
                    cap_pilot.base_id,
                )
            )

    # 2. Fleet ships: missing pilots block the ship; under-geared pilots weaken it.
    for ship in plan.ships:
        best = ship.best_pilot
        if best is None:
            continue
        if not best.owned:
            objectives.append(
                Objective(
                    "unlock_pilot",
                    f"Unlock {best.name} to field {ship.name}",
                    PRIO_UNLOCK_PILOT,
                    best.base_id,
                )
            )
        elif best.gear_level < PILOT_GEAR_TARGET:
            objectives.append(
                Objective(
                    "gear_pilot",
                    f"Gear {best.name} to g{PILOT_GEAR_TARGET}+ (currently g{best.gear_level}) "
                    f"to strengthen {ship.name}",
                    3 + (PILOT_GEAR_TARGET - best.gear_level),
                    best.base_id,
                )
            )

    # 3. Fleet too small to fill reinforcements.
    if len(plan.ships) < FLEET_SIZE:
        objectives.append(
            Objective(
                "incomplete_fleet",
                f"You own only {len(plan.ships)} {plan.faction} ship(s) besides the capital; "
                f"unlock more to fill a full {FLEET_SIZE}-ship fleet",
                PRIO_INCOMPLETE_FLEET,
            )
        )

    # 4. Low-star ships (minor).
    for ship in plan.ships:
        if ship.stars and ship.stars < 5:
            objectives.append(
                Objective(
                    "star_ship",
                    f"Star up {ship.name} ({ship.stars}★)",
                    PRIO_STAR_SHIP + (5 - ship.stars) * 0.5,
                    ship.base_id,
                )
            )

    objectives.sort(key=lambda o: o.priority, reverse=True)
    return objectives


def analyze_fleet(player: Player) -> FleetReport:
    data = ship_data()
    owned_ship_ids = [u.base_id for u in player.units if u.base_id in data]
    owned_capitals = [b for b in owned_ship_ids if data[b].get("capital")]
    owned_regular = [b for b in owned_ship_ids if not data[b].get("capital")]

    # Best capital per faction (by pilot investment).
    capital_by_faction: dict[str, ShipStatus] = {}
    for cap_id in owned_capitals:
        cs = _ship_status(cap_id, player)
        for fac in cs.factions or ["unaligned"]:
            cur = capital_by_faction.get(fac)
            if cur is None or cs.strength > cur.strength:
                capital_by_faction[fac] = cs

    plans: list[FleetPlan] = []
    for fac, capital in capital_by_faction.items():
        fac_ships = [
            _ship_status(b, player) for b in owned_regular if fac in data[b].get("factions", [])
        ]
        fac_ships.sort(key=lambda s: s.strength, reverse=True)
        plan = FleetPlan(faction=fac, capital=capital, ships=fac_ships[:FLEET_SIZE])
        plan.objectives = _objectives_for(plan)
        plans.append(plan)

    plans.sort(key=lambda p: p.score, reverse=True)

    return FleetReport(
        player_name=player.name,
        ally_code=player.ally_code,
        best=plans[0] if plans else None,
        alternatives=plans[1:3],
        owned_ships=len(owned_regular),
        owned_capitals=len(owned_capitals),
    )
