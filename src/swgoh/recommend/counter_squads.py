"""Build actual 5-unit squads to counter a threat, from your own roster.

The Counter page answers "which tools do I own"; this answers "so what do I
field". It takes the tools a threat calls for and assembles real squads under
the constraints that matter in game:

- **Entry requirements.** Conquest trials gate on relic level ("Relic 3+
  Characters"), so ineligible units are filtered out before anything else.
- **Leaders lead.** Only a unit with a leader ability can take the leader slot,
  and the squad is built around that leader's faction.
- **Families stick together.** Kits reference their own faction constantly
  ("all Pirate allies gain..."), so a squad sharing a faction gets synergy the
  parts don't have alone. Narrow families (Bad Batch) score higher than broad
  umbrellas (Rebel) because their kits interlock more tightly.
- **Investment decides ties.** Gear, relic, stars, mods and raw power — a
  perfect counter on an undergeared unit dies before it does anything.

Squads are also checked for *liabilities*: units whose kit actively feeds the
enemy modifier. Against something that heals off your debuffs, a debuff-heavy
attacker is worse than a neutral one, so it's flagged rather than quietly
recommended.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..ability_text import abilities_of
from ..factions import factions_of
from ..models import Player, Unit
from ..names import display_name
from ..ships import is_ship
from ..stats import base_speed, base_stat, mod_speed, mod_stat
from .counters import TOOLS_BY_KEY, Tool, _find, _sentences

SQUAD_SIZE = 5

# Category tags that aren't a "family" — roles, ship classes and event tags.
NON_FAMILY = {
    "Leader",
    "Capital Ship",
    "Cargo Ship",
    "Fleet Commander",
    "Order 66 Raid",
    "Galactic Legend",
}

# A faction this large is an umbrella ("Rebel"), not a kit-sharing family.
BROAD_FAMILY = 45

# Investment weights. Power already folds in gear/level/mods, but gear, relic,
# stars and mods are weighted explicitly too so the ranking reflects the things
# you actually farm.
#
# Comlink ships raw stats and no per-unit galactic power, so `power` is 0 on that
# source (swgoh.gg does provide it). Rather than let a dead term silently deflate
# every score, the weights are normalised over whichever components are actually
# populated — see `_investment`.
W_POWER, W_RELIC, W_GEAR, W_STARS, W_MODS = 0.40, 0.20, 0.15, 0.10, 0.15

# Squad score weights.
W_COVERAGE, W_INVESTMENT, W_SYNERGY = 0.45, 0.35, 0.20
LIABILITY_PENALTY = 4.0


@dataclass(frozen=True)
class Liability:
    """A kit trait that backfires against a particular threat."""

    threat_key: str
    label: str
    patterns: tuple[str, ...]
    min_hits: int  # how many mentions before a kit really "leans on" this


LIABILITIES: tuple[Liability, ...] = (
    Liability(
        "debuff_feeding",
        "debuff-heavy kit — feeds their sustain",
        (r"\binflict\b", r"Damage Over Time"),
        3,
    ),
    Liability(
        "debuff_reflect",
        "debuff-heavy kit — those debuffs come back at you",
        (r"\binflict\b", r"Damage Over Time"),
        3,
    ),
    Liability(
        "damage_reflect",
        "calls assists / multi-hits — every hit reflects",
        (r"to assist", r"assist[s]?\b"),
        2,
    ),
)


@dataclass
class SquadMember:
    base_id: str
    unit_name: str
    is_leader: bool
    stars: int
    gear_level: int
    relic_level: int
    power: int
    investment: float
    base_speed: int | None = None  # None when the stats export doesn't cover it
    mod_speed: float = 0.0
    # {stat: {'base': x|None, 'mods': y, 'total': z|None}} for the stats this fight wants
    stat_values: dict = field(default_factory=dict)
    tools: list[str] = field(default_factory=list)  # tool labels this unit brings
    liabilities: list[str] = field(default_factory=list)

    @property
    def gear_label(self) -> str:
        return f"R{self.relic_level}" if self.relic_level else f"G{self.gear_level}"

    @property
    def total_speed(self) -> float | None:
        return None if self.base_speed is None else self.base_speed + self.mod_speed

    @property
    def speed_label(self) -> str:
        """"265 (143 base + 91 mods)" — the why behind the number."""
        if self.base_speed is None:
            return f"+{self.mod_speed:g} from mods (base unknown)"
        return f"{self.total_speed:g} ({self.base_speed} base + {self.mod_speed:g} mods)"


@dataclass
class CounterSquad:
    members: list[SquadMember]  # leader first
    family: str
    family_count: int
    covered: list[str] = field(default_factory=list)  # tool labels answered
    missing: list[str] = field(default_factory=list)  # tools nobody covers
    score: float = 0.0
    coverage: float = 0.0

    @property
    def leader(self) -> SquadMember | None:
        return self.members[0] if self.members else None

    @property
    def power(self) -> int:
        return sum(m.power for m in self.members)

    @property
    def warnings(self) -> list[str]:
        seen: dict[str, None] = {}
        for m in self.members:
            for line in m.liabilities:
                seen.setdefault(f"{m.unit_name}: {line}", None)
        return list(seen)

    @property
    def synergy_label(self) -> str:
        if self.family_count >= SQUAD_SIZE:
            return f"Full {self.family} squad"
        if self.family_count >= 3:
            return f"{self.family_count}/{SQUAD_SIZE} {self.family}"
        return "Mixed"


def _mod_score(unit: Unit) -> float:
    """Rough mod quality: how many slots are maxed, and how much speed they add."""
    if not unit.mods:
        return 0.0
    maxed = sum(1 for m in unit.mods if m.is_maxed and m.rarity >= 5)
    speed = sum(m.speed for m in unit.mods)
    return 0.6 * min(1.0, maxed / 6) + 0.4 * min(1.0, speed / 120)


def _investment(unit: Unit, max_power: int) -> float:
    """0–1 score for how fieldable a unit is.

    Weights are renormalised over the components the data source populates, so a
    source without per-unit power still produces a full-range score instead of
    one capped at 60%.
    """
    parts = [
        (W_RELIC, min(1.0, unit.relic_level / 9)),
        (W_GEAR, min(1.0, unit.gear_level / 13)),
        (W_STARS, min(1.0, unit.stars / 7)),
        (W_MODS, _mod_score(unit)),
    ]
    if max_power:
        parts.append((W_POWER, unit.power / max_power))
    total = sum(w for w, _ in parts)
    return sum(w * v for w, v in parts) / total if total else 0.0


def _matches(patterns: tuple[str, ...], text: str) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def _tool_index(units: list[Unit], tools: list[Tool]) -> dict[str, set[str]]:
    """base_id -> tool keys that unit's kit provides.

    Matches sentence-by-sentence through the same finder the Counter page uses,
    so a tool's direction-disqualifying `excludes` apply here too — otherwise a
    squad takes credit for a mechanic that's pointed at its own allies.
    """
    index: dict[str, set[str]] = {}
    for unit in units:
        sentences: list[str] = []
        for ability in abilities_of(unit.base_id):
            sentences.extend(_sentences(ability["d"]))
        if not sentences:
            continue
        found = {t.key for t in tools if _find(t.patterns, sentences, t.excludes)}
        if found:
            index[unit.base_id] = found
    return index


def _liability_index(units: list[Unit], threat_keys: set[str]) -> dict[str, list[str]]:
    """base_id -> liability labels, for the threats actually in play."""
    active = [l for l in LIABILITIES if l.threat_key in threat_keys]
    if not active:
        return {}
    index: dict[str, list[str]] = {}
    for unit in units:
        blob = "\n".join(a["d"] for a in abilities_of(unit.base_id))
        if not blob:
            continue
        labels: list[str] = []
        for liability in active:
            hits = sum(len(re.findall(p, blob, re.IGNORECASE)) for p in liability.patterns)
            if hits >= liability.min_hits and liability.label not in labels:
                labels.append(liability.label)
        if labels:
            index[unit.base_id] = labels
    return index


def _families(base_id: str) -> list[str]:
    return [f for f in factions_of(base_id) if f not in NON_FAMILY]


def _family_weight(family: str, roster_size: dict[str, int]) -> float:
    """Narrow families interlock more than umbrellas, so they're worth more."""
    size = roster_size.get(family, 0)
    return 1.0 if size and size < BROAD_FAMILY else 0.6


def _member(
    unit: Unit,
    is_leader: bool,
    max_power: int,
    tools: dict[str, set[str]],
    liabilities: dict[str, list[str]],
    stat_names: tuple[str, ...] = (),
) -> SquadMember:
    keys = tools.get(unit.base_id, set())
    return SquadMember(
        base_id=unit.base_id,
        unit_name=display_name(unit.base_id),
        is_leader=is_leader,
        stars=unit.stars,
        gear_level=unit.gear_level,
        relic_level=unit.relic_level,
        power=unit.power,
        investment=round(_investment(unit, max_power), 3),
        base_speed=base_speed(unit.base_id),
        mod_speed=mod_speed(unit),
        stat_values={
            name: {
                "base": base_stat(unit.base_id, name),
                "mods": mod_stat(unit, name),
                "total": (
                    None
                    if base_stat(unit.base_id, name) is None
                    else round(base_stat(unit.base_id, name) + mod_stat(unit, name), 2)
                ),
            }
            for name in stat_names
        },
        tools=sorted(TOOLS_BY_KEY[k].label for k in keys if k in TOOLS_BY_KEY),
        liabilities=list(liabilities.get(unit.base_id, [])),
    )


def build_counter_squads(
    player: Player,
    tool_keys: list[str],
    threat_keys: set[str] | None = None,
    min_relic: int = 0,
    limit: int = 3,
    leader_candidates: int = 12,
    stat_names: tuple[str, ...] = (),
) -> list[CounterSquad]:
    """Assemble the best squads your roster can field against a set of threats."""
    needed = [TOOLS_BY_KEY[k] for k in dict.fromkeys(tool_keys) if k in TOOLS_BY_KEY]
    if not needed:
        return []

    eligible = [
        u
        for u in player.units
        if not is_ship(u.base_id) and u.stars > 0 and u.relic_level >= min_relic
    ]
    if len(eligible) < SQUAD_SIZE:
        return []

    max_power = max((u.power for u in eligible), default=0)
    tools = _tool_index(eligible, needed)
    liabilities = _liability_index(eligible, threat_keys or set())

    roster_size: dict[str, int] = {}
    for u in eligible:
        for f in _families(u.base_id):
            roster_size[f] = roster_size.get(f, 0) + 1

    invest = {u.base_id: _investment(u, max_power) for u in eligible}
    by_id = {u.base_id: u for u in eligible}

    # Under a speed-race modifier, turn order decides the fight before kits do —
    # a flat speed penalty widens the gap between fast and slow rather than
    # closing it, so mod speed is worth weighting explicitly.
    racing = "speed_race" in (threat_keys or set())
    # Base Speed comes from the stats export and doesn't cover newer units. Rather
    # than score those as zero — which would bury exactly the recent, fast kits —
    # stand in the roster median so only the live mod half distinguishes them.
    known = [b for b in (base_speed(u.base_id) for u in eligible) if b is not None]
    median_base = sorted(known)[len(known) // 2] if known else 0
    speed = {
        u.base_id: (base_speed(u.base_id) or median_base) + mod_speed(u) for u in eligible
    }
    fastest = max(speed.values(), default=0)

    def unit_value(base_id: str) -> float:
        """Standalone worth: how fieldable, plus how many needed tools it brings."""
        value = invest[base_id] + 0.12 * len(tools.get(base_id, set()))
        if racing and fastest:
            value += 0.20 * (speed.get(base_id, 0) / fastest)
        return value

    leaders = sorted(
        (u for u in eligible if "Leader" in factions_of(u.base_id)),
        key=lambda u: unit_value(u.base_id),
        reverse=True,
    )[:leader_candidates]

    squads: list[CounterSquad] = []
    seen: set[frozenset[str]] = set()

    for leader in leaders:
        # Try each of the leader's families, plus an unrestricted build.
        for family in [*_families(leader.base_id), ""]:
            pool = [
                u
                for u in eligible
                if u.base_id != leader.base_id
                and (not family or family in factions_of(u.base_id))
            ]
            if len(pool) < SQUAD_SIZE - 1:
                continue

            picked = [leader]
            covered: set[str] = set(tools.get(leader.base_id, set()))
            while len(picked) < SQUAD_SIZE:
                best, best_score = None, float("-inf")
                for cand in pool:
                    if cand in picked:
                        continue
                    new_tools = tools.get(cand.base_id, set()) - covered
                    # Marginal coverage first, investment to break ties.
                    score = 0.5 * len(new_tools) + unit_value(cand.base_id)
                    score -= LIABILITY_PENALTY * 0.05 * len(liabilities.get(cand.base_id, []))
                    if score > best_score:
                        best, best_score = cand, score
                if best is None:
                    break
                picked.append(best)
                covered |= tools.get(best.base_id, set())

            if len(picked) < SQUAD_SIZE:
                continue
            key = frozenset(u.base_id for u in picked)
            if key in seen:
                continue
            seen.add(key)

            members = [
                _member(u, i == 0, max_power, tools, liabilities, stat_names)
                for i, u in enumerate(picked)
            ]
            shared = ""
            shared_count = 0
            for fam in _families(leader.base_id):
                count = sum(1 for u in picked if fam in factions_of(u.base_id))
                if count > shared_count:
                    shared, shared_count = fam, count

            coverage = len(covered & {t.key for t in needed}) / len(needed)
            avg_invest = sum(m.investment for m in members) / len(members)
            synergy = (shared_count / SQUAD_SIZE) * _family_weight(shared, roster_size)
            penalty = LIABILITY_PENALTY * sum(len(m.liabilities) for m in members)
            score = (
                100 * (W_COVERAGE * coverage + W_INVESTMENT * avg_invest + W_SYNERGY * synergy)
                - penalty
            )

            squads.append(
                CounterSquad(
                    members=members,
                    family=shared or "Mixed",
                    family_count=shared_count,
                    covered=sorted(TOOLS_BY_KEY[k].label for k in covered if k in TOOLS_BY_KEY),
                    missing=sorted(t.label for t in needed if t.key not in covered),
                    coverage=round(100 * coverage, 1),
                    score=round(score, 1),
                )
            )

    squads.sort(key=lambda s: s.score, reverse=True)
    # Don't show five variations on the same five units.
    final: list[CounterSquad] = []
    for squad in squads:
        ids = {m.base_id for m in squad.members}
        if any(len(ids & {m.base_id for m in kept.members}) >= SQUAD_SIZE - 1 for kept in final):
            continue
        final.append(squad)
        if len(final) >= limit:
            break
    return final


@dataclass
class ModDonor:
    """A mod sitting on a unit you aren't fielding, carrying a stat you need."""

    owner_base_id: str
    owner_name: str
    owner_relic: int
    slot_name: str
    set_name: str
    stat: str
    amount: float
    is_primary: bool  # the stat is the mod's primary, not a secondary

    @property
    def speed(self) -> float:  # kept for callers that only care about Speed
        return self.amount if self.stat == "Speed" else 0.0

    @property
    def is_speed_arrow(self) -> bool:
        return self.stat == "Speed" and self.is_primary and self.slot_name == "Arrow"

    @property
    def label(self) -> str:
        primary = f" ({self.stat} primary)" if self.is_primary else ""
        return f"{self.slot_name}{primary} · +{self.amount:g} {self.stat}"


# Below this, a mod isn't worth the swap for a given stat.
MIN_DONOR = {"Speed": 10.0, "Potency": 8.0, "Tenacity": 8.0, "Critical Chance": 5.0}
DEFAULT_MIN_DONOR = 100.0  # flat stats (Health/Protection) come in big numbers


def _mod_contribution(mod, stat: str) -> tuple[float, bool]:
    """How much of `stat` one mod carries, and whether it's the primary."""
    from ..stats import MOD_STAT_ALIASES

    amount = 0.0
    is_primary = False
    if MOD_STAT_ALIASES.get(mod.primary_name) == stat:
        amount += mod.primary_value
        is_primary = True
    for sec in mod.secondaries:
        if MOD_STAT_ALIASES.get(sec.name) == stat:
            amount += sec.value
    return amount, is_primary


def find_mod_donors(
    player: Player,
    squad_ids: set[str],
    stat: str = "Speed",
    limit: int = 8,
    min_amount: float | None = None,
) -> list[ModDonor]:
    """Mods carrying `stat`, equipped on units outside the squad, best first.

    When a modifier attacks or rewards a stat, the fastest fix usually isn't
    farming — it's moving mods you already own off units that aren't in this
    fight. Units already in the squad are excluded, since moving a mod within the
    squad gains nothing.
    """
    threshold = MIN_DONOR.get(stat, DEFAULT_MIN_DONOR) if min_amount is None else min_amount
    donors: list[ModDonor] = []
    for unit in player.units:
        if unit.base_id in squad_ids or is_ship(unit.base_id):
            continue
        for mod in unit.mods:
            amount, is_primary = _mod_contribution(mod, stat)
            if amount < threshold:
                continue
            donors.append(
                ModDonor(
                    owner_base_id=unit.base_id,
                    owner_name=display_name(unit.base_id),
                    owner_relic=unit.relic_level,
                    slot_name=mod.slot_name,
                    set_name=mod.set_name,
                    stat=stat,
                    amount=round(amount, 2),
                    is_primary=is_primary,
                )
            )
    # Biggest contribution first; prefer taking from less-invested owners on ties.
    donors.sort(key=lambda d: (d.amount, -d.owner_relic), reverse=True)
    return donors[:limit]


@dataclass
class SquadVerdict:
    """What a squad you named would actually do in this fight."""

    typed: list[str]
    squad: CounterSquad | None
    unresolved: list[str] = field(default_factory=list)  # names that matched nothing
    not_owned: list[str] = field(default_factory=list)
    ineligible: list[str] = field(default_factory=list)  # owned, but below the relic gate

    @property
    def fieldable(self) -> bool:
        return self.squad is not None and not self.not_owned and not self.ineligible


def evaluate_squad(
    player: Player,
    names: list[str],
    tool_keys: list[str],
    threat_keys: set[str] | None = None,
    min_relic: int = 0,
    stat_names: tuple[str, ...] = (),
) -> SquadVerdict:
    """Score a squad someone else recommended against your roster and this fight.

    Community team lists are written for an average roster, not yours — so the
    useful questions are whether you own it, whether it clears the entry
    requirement, and what it actually covers. Units you don't own are reported
    rather than silently dropped, because a squad missing two members isn't a
    squad.
    """
    from ..aliases import resolve_squad

    owned = {u.base_id: u for u in player.units}
    resolved = resolve_squad(names, set(owned))

    verdict = SquadVerdict(typed=list(names), squad=None)
    units: list[Unit] = []
    for typed, base_id in resolved:
        if base_id is None:
            verdict.unresolved.append(typed)
            continue
        unit = owned.get(base_id)
        if unit is None:
            verdict.not_owned.append(display_name(base_id))
            continue
        if unit.relic_level < min_relic:
            verdict.ineligible.append(f"{display_name(base_id)} (R{unit.relic_level})")
        units.append(unit)

    if not units:
        return verdict

    needed = [TOOLS_BY_KEY[k] for k in dict.fromkeys(tool_keys) if k in TOOLS_BY_KEY]
    tools = _tool_index(units, needed)
    liabilities = _liability_index(units, threat_keys or set())
    max_power = max((u.power for u in units), default=0)

    # The first name given is the leader, as written.
    members = [
        _member(u, i == 0, max_power, tools, liabilities, stat_names)
        for i, u in enumerate(units)
    ]
    covered: set[str] = set()
    for u in units:
        covered |= tools.get(u.base_id, set())

    shared, shared_count = "", 0
    for fam in _families(units[0].base_id):
        count = sum(1 for u in units if fam in factions_of(u.base_id))
        if count > shared_count:
            shared, shared_count = fam, count

    coverage = len(covered) / len(needed) if needed else 0.0
    verdict.squad = CounterSquad(
        members=members,
        family=shared or "Mixed",
        family_count=shared_count,
        covered=sorted(TOOLS_BY_KEY[k].label for k in covered if k in TOOLS_BY_KEY),
        missing=sorted(t.label for t in needed if t.key not in covered),
        coverage=round(100 * coverage, 1),
        score=round(100 * coverage, 1),
    )
    return verdict
