"""Clean domain models that every data source normalizes into.

Keeping a source-agnostic model here is what makes the hybrid data layer work:
the analyzer and web layers never see swgoh.gg or Comlink payloads directly.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Canonical mod slot names, keyed by slot number (1-based).
MOD_SLOT_NAMES: dict[int, str] = {
    1: "Square",
    2: "Arrow",
    3: "Diamond",
    4: "Triangle",
    5: "Circle",
    6: "Cross",
}

# Number of mods required to complete each set bonus.
MOD_SET_SIZE: dict[str, int] = {
    "Health": 2,
    "Defense": 2,
    "Critical Chance": 2,
    "Potency": 2,
    "Tenacity": 2,
    "Offense": 4,
    "Critical Damage": 4,
    "Speed": 4,
}


@dataclass
class SecondaryStat:
    name: str
    value: float
    is_percent: bool = False
    rolls: int = 1


@dataclass
class Mod:
    slot: int
    set_name: str
    rarity: int  # dots / pips, 1-6
    level: int  # 1-15
    tier: int  # 1-5 (grey..gold)
    primary_name: str
    primary_value: float
    secondaries: list[SecondaryStat] = field(default_factory=list)

    @property
    def slot_name(self) -> str:
        return MOD_SLOT_NAMES.get(self.slot, f"Slot{self.slot}")

    @property
    def speed(self) -> float:
        """Total speed this mod contributes (primary if the arrow, plus secondary)."""
        total = 0.0
        if self.primary_name == "Speed":
            total += self.primary_value
        for s in self.secondaries:
            if s.name == "Speed":
                total += s.value
        return total

    @property
    def is_maxed(self) -> bool:
        return self.level >= 15


@dataclass
class Unit:
    base_id: str
    name: str
    stars: int = 0
    level: int = 0
    gear_level: int = 0  # 1-13
    relic_level: int = 0  # 0-9 (0 == no relic)
    power: int = 0
    mods: list[Mod] = field(default_factory=list)
    skills: dict[str, int] = field(default_factory=dict)  # ability base_id -> current tier

    def mod_in_slot(self, slot: int) -> Mod | None:
        for m in self.mods:
            if m.slot == slot:
                return m
        return None

    def completed_sets(self) -> list[str]:
        """Set bonuses this unit currently has completed, honoring multiples."""
        counts: dict[str, int] = {}
        for m in self.mods:
            counts[m.set_name] = counts.get(m.set_name, 0) + 1
        completed: list[str] = []
        for set_name, count in counts.items():
            size = MOD_SET_SIZE.get(set_name)
            if size:
                completed.extend([set_name] * (count // size))
        return completed


@dataclass
class Player:
    name: str
    ally_code: str
    units: list[Unit] = field(default_factory=list)
    # Current PvP standings (lower rank number is better). None if unavailable.
    squad_arena_rank: int | None = None
    fleet_arena_rank: int | None = None
    # base_ids of the currently-set Squad Arena defense team, in slot order.
    arena_defense_squad: list[str] = field(default_factory=list)
    # Identity + guild membership (for guild features).
    player_id: str = ""
    guild_id: str = ""
    guild_name: str = ""
    # Grand Arena (GAC) standing.
    gac_league: str = ""
    gac_division: int = 0
    gac_skill_rating: int = 0

    def unit(self, base_id: str) -> Unit | None:
        for u in self.units:
            if u.base_id == base_id:
                return u
        return None


@dataclass
class GuildMember:
    player_id: str
    name: str
    galactic_power: int = 0
    char_gp: int = 0
    ship_gp: int = 0
    level: int = 0
    last_active_ms: int = 0
    league_id: str = ""


@dataclass
class Guild:
    id: str
    name: str
    galactic_power: int = 0
    member_count: int = 0
    members: list[GuildMember] = field(default_factory=list)
    # Raids the guild currently runs (e.g. ["naboo", "order66"]).
    active_raids: list[str] = field(default_factory=list)
    # Most recent completed raid: id, guild total, and per-player scores.
    recent_raid_id: str = ""
    recent_raid_total: int = 0
    recent_raid_scores: dict[str, int] = field(default_factory=dict)
