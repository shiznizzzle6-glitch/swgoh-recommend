"""Guild contribution analyzer — your standing + raid-readiness.

Turns Comlink's `/guild` data into (a) where you stand among your guildmates and
(b) how to start contributing to the raids your guild *actually* runs. The raid
squads come from `raid_targets.yaml`, scored with the same readiness engine the
Squads tab uses, and only the raids your guild currently launches are shown.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

from ..factions import has_faction
from ..models import Guild, Player
from ..names import display_name
from ..ships import is_ship
from .squads import SquadPlan, _build_plan

# The four "classic" Territory Battles (Hoth + Geonosis). Unlike Rise of the
# Empire (t05D, relic-gated "any 7★"), their platoons demand SPECIFIC units,
# assigned per-event and only present in the live guild TB status. See
# data/tb_platoons.yaml for the stable per-TB facts we can bundle.
CLASSIC_TB_IDS = ("t01D", "t02D", "t03D", "t04D")

# Comlink raid ids -> display names.
RAID_NAMES = {
    "naboo": "Battle for Naboo",
    "order66": "Order 66",
    "krayt": "Krayt Dragon",
    "speederbike": "Speeder Bike (Challenge)",
    "aat": "Heroic AAT",
    "rancor": "Rancor",
    "sith": "Sith Triumvirate",
}

# Readiness boost (percentage points) for cheap "beginner" starter teams, so they
# stay near the top without outranking a team you're already well into.
BEGINNER_BOOST = 20

# Territory Battle recon-platoon requirements, derived from the TB definition in
# Comlink game data. Rise of the Empire (t05D, "mixed") platoons take ANY 7-star
# character meeting a relic bar that scales by phase — no specific units/faction.
# relic values are our relic-level scale (game relicTier - 2).
TB_PLATOON_REQS: dict[str, dict[str, Any]] = {
    "t05D": {
        "name": "Rise of the Empire",
        "phases": [
            {"phase": 1, "relic": 5},
            {"phase": 2, "relic": 6},
            {"phase": 3, "relic": 7},
            {"phase": 4, "relic": 8},
            {"phase": 5, "relic": 9},
            {"phase": 6, "relic": 9},
        ],
    },
}


@dataclass
class TbPhase:
    phase: int
    relic_req: int
    units: list[str] = field(default_factory=list)  # names of qualifying 7★ chars

    @property
    def count(self) -> int:
        return len(self.units)


@dataclass
class TbReport:
    tb_id: str
    tb_name: str
    total_7star: int
    phases: list[TbPhase] = field(default_factory=list)


def _analyze_tb(player: Player, tb_id: str) -> TbReport | None:
    reqs = TB_PLATOON_REQS.get(tb_id)
    if not reqs:
        return None
    chars = [u for u in player.units if u.stars == 7 and not is_ship(u.base_id)]
    phases = [
        TbPhase(
            phase=p["phase"],
            relic_req=p["relic"],
            units=sorted(u.name for u in chars if u.relic_level >= p["relic"]),
        )
        for p in reqs["phases"]
    ]
    return TbReport(tb_id=tb_id, tb_name=reqs["name"], total_7star=len(chars), phases=phases)


# --------------------------------------------------------------------------
# Classic TB platoon readiness (Hoth / Geonosis)
# --------------------------------------------------------------------------
# Two complementary views:
#   1. Faction-depth readiness (always available): how many distinct units of a
#      TB's driving faction you own, bucketed by star tier. A newer player's real
#      lever — platoons need MANY distinct faction units, and later phases gate
#      on 7★, so depth is what lets you fill slots whenever the guild runs one.
#   2. Live platoon fills (only while the guild is running that classic TB): the
#      exact per-slot unit + whether you own it at the required rarity, read from
#      the live guild TB status.


@dataclass
class TbFactionDepth:
    faction: str
    owned: int  # distinct owned characters in this faction
    r7: int     # owned at exactly 7★
    r6: int     # owned at 6★
    r5: int     # owned at 5★

    @property
    def fillable(self) -> int:
        """Owned at 5★+ — the pool that can donate to most platoon slots."""
        return self.r7 + self.r6 + self.r5


@dataclass
class LiveSlot:
    unit_name: str
    required_stars: int
    owned: bool       # you own this exact unit at the required rarity
    filled: bool      # a guildmate has already donated it


@dataclass
class LivePlatoon:
    zone: str
    slots: list[LiveSlot] = field(default_factory=list)

    @property
    def you_can_fill(self) -> int:
        return sum(1 for s in self.slots if s.owned and not s.filled)


@dataclass
class ClassicTb:
    tb_id: str
    name: str
    planet: str
    alignment: str
    phases: int
    factions: list[str]
    is_active: bool
    current_phase: int
    depth: list[TbFactionDepth] = field(default_factory=list)
    live_platoons: list[LivePlatoon] = field(default_factory=list)

    @property
    def has_live(self) -> bool:
        return bool(self.live_platoons)


@dataclass
class ClassicTbReport:
    active_tb_id: str | None  # the classic TB the guild is running now, if any
    tbs: list[ClassicTb] = field(default_factory=list)


def load_tb_platoons(path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    import yaml

    if path is not None:
        text = Path(path).read_text(encoding="utf-8")
    else:
        text = resources.files("swgoh.data").joinpath("tb_platoons.yaml").read_text("utf-8")
    data = yaml.safe_load(text) or {}
    return {str(k): dict(v or {}) for k, v in data.items()}


def _faction_depth(player: Player, factions: list[str]) -> list[TbFactionDepth]:
    chars = [u for u in player.units if not is_ship(u.base_id)]
    out: list[TbFactionDepth] = []
    for fac in factions:
        members = [u for u in chars if has_faction(u.base_id, fac)]
        out.append(
            TbFactionDepth(
                faction=fac,
                owned=len(members),
                r7=sum(1 for u in members if u.stars == 7),
                r6=sum(1 for u in members if u.stars == 6),
                r5=sum(1 for u in members if u.stars == 5),
            )
        )
    return out


def _parse_live_platoons(player: Player, guild: Guild) -> list[LivePlatoon]:
    """Best-effort read of the LIVE per-slot platoon fills for an active classic TB.

    The live guild TB status only exists while a battle is running, so this can't
    be validated between events. Field names below are provisional — derived from
    the static definition's shape (reconZone → platoon → squad slots) and Comlink
    conventions — and are read defensively: anything unrecognized yields an empty
    list (the UI then simply falls back to the faction-depth view). We finalize the
    mapping against a real payload the first time the guild runs Hoth/Geonosis.
    """
    raw = guild.tb_status_raw or {}
    if not raw:
        return []
    owned = {u.base_id: u for u in player.units}
    platoons: list[LivePlatoon] = []
    for conflict in raw.get("conflictStatus") or []:
        if not isinstance(conflict, dict):
            continue
        zone = conflict.get("zoneStatus") or conflict.get("reconZoneStatus") or conflict
        zone_id = str(zone.get("zoneId") or zone.get("id") or "")
        for pl in zone.get("platoon") or zone.get("platoons") or []:
            if not isinstance(pl, dict):
                continue
            slots: list[LiveSlot] = []
            for sq in pl.get("squad") or pl.get("squads") or []:
                if not isinstance(sq, dict):
                    continue
                unit_ref = str(
                    sq.get("unitDefId") or sq.get("defId") or sq.get("unitId") or ""
                ).split(":", 1)[0]
                if not unit_ref:
                    continue
                req_stars = int(sq.get("requiredRarity") or sq.get("rarity") or 0)
                have = owned.get(unit_ref)
                slots.append(
                    LiveSlot(
                        unit_name=display_name(unit_ref),
                        required_stars=req_stars,
                        owned=bool(have and (req_stars == 0 or have.stars >= req_stars)),
                        filled=bool(sq.get("playerId") or sq.get("filledBy") or sq.get("memberId")),
                    )
                )
            if slots:
                platoons.append(LivePlatoon(zone=zone_id or str(pl.get("id") or ""), slots=slots))
    return platoons


def _analyze_classic_tb(player: Player, guild: Guild) -> ClassicTbReport:
    meta = load_tb_platoons()
    active_id = guild.tb_id if (guild.tb_active and guild.tb_id in CLASSIC_TB_IDS) else None
    tbs: list[ClassicTb] = []
    for tb_id in CLASSIC_TB_IDS:
        m = meta.get(tb_id)
        if not m:
            continue
        is_active = tb_id == active_id
        tbs.append(
            ClassicTb(
                tb_id=tb_id,
                name=str(m.get("name") or tb_id),
                planet=str(m.get("planet") or ""),
                alignment=str(m.get("alignment") or ""),
                phases=int(m.get("phases") or 0),
                factions=list(m.get("factions") or []),
                is_active=is_active,
                current_phase=guild.tb_round if is_active else 0,
                depth=_faction_depth(player, list(m.get("factions") or [])),
                live_platoons=_parse_live_platoons(player, guild) if is_active else [],
            )
        )
    # Surface the active classic TB first.
    tbs.sort(key=lambda t: (not t.is_active, t.tb_id))
    return ClassicTbReport(active_tb_id=active_id, tbs=tbs)


def load_raid_targets(path: str | Path | None = None) -> dict[str, list[dict[str, Any]]]:
    import yaml

    if path is not None:
        text = Path(path).read_text(encoding="utf-8")
    else:
        text = resources.files("swgoh.data").joinpath("raid_targets.yaml").read_text("utf-8")
    data = yaml.safe_load(text) or {}
    return {str(k): list(v or []) for k, v in data.items()}


@dataclass
class GuildStanding:
    guild_name: str
    guild_gp: int
    member_count: int
    my_gp: int
    my_gp_rank: int            # 1 = biggest account in the guild
    gac_league: str
    gac_division: int
    gac_skill_rating: int
    # Skill-rating change since the previous logged snapshot (positive = gained).
    gac_skill_change: int | None = None

    @property
    def my_gp_percentile(self) -> int:
        if self.member_count <= 1:
            return 100
        # rank 1 (top) -> ~100th percentile, last -> low.
        return round(100 * (self.member_count - self.my_gp_rank) / (self.member_count - 1))


@dataclass
class RaidStanding:
    raid_id: str
    raid_name: str
    my_score: int | None
    guild_total: int | None
    top_score: int | None
    median_score: int | None
    squads: list[SquadPlan] = field(default_factory=list)  # readiness-sorted


@dataclass
class GuildReport:
    player_name: str
    ally_code: str
    standing: GuildStanding | None
    raids: list[RaidStanding] = field(default_factory=list)
    tb: TbReport | None = None
    classic_tb: ClassicTbReport | None = None


def _median(values: list[int]) -> int:
    if not values:
        return 0
    s = sorted(values)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) // 2


def analyze_guild(
    player: Player,
    guild: Guild,
    raid_targets: dict[str, list[dict[str, Any]]] | None = None,
    *,
    skill_change: int | None = None,
) -> GuildReport:
    if raid_targets is None:
        raid_targets = load_raid_targets()

    # --- Standing: rank by GP among members ---
    ordered = sorted(guild.members, key=lambda m: m.galactic_power, reverse=True)
    my_gp = 0
    my_rank = len(ordered)
    for i, m in enumerate(ordered, start=1):
        if m.player_id == player.player_id:
            my_gp = m.galactic_power
            my_rank = i
            break
    standing = GuildStanding(
        guild_name=guild.name or player.guild_name,
        guild_gp=guild.galactic_power,
        member_count=guild.member_count or len(guild.members),
        my_gp=my_gp,
        my_gp_rank=my_rank,
        gac_league=player.gac_league,
        gac_division=player.gac_division,
        gac_skill_rating=player.gac_skill_rating,
        gac_skill_change=skill_change,
    )

    # --- Raids: only the ones the guild actually runs ---
    raids: list[RaidStanding] = []
    for raid_id in guild.active_raids:
        my_score = guild_total = top = med = None
        if guild.recent_raid_id == raid_id and guild.recent_raid_scores:
            scores = list(guild.recent_raid_scores.values())
            my_score = guild.recent_raid_scores.get(player.player_id, 0)
            guild_total = guild.recent_raid_total or sum(scores)
            top = max(scores)
            med = _median(scores)

        squads = []
        for t in raid_targets.get(raid_id, []):
            t2 = dict(t)
            tags = list(t2.get("tags", []))
            if t2.get("beginner"):
                tags = ["beginner", *tags]
            t2["tags"] = tags
            squads.append(_build_plan(t2, player))
        # Closest-to-ready first, with cheap "beginner" starters boosted so they
        # stay visible without burying a team you're already most of the way to.
        squads.sort(
            key=lambda s: s.readiness + (BEGINNER_BOOST if "beginner" in s.tags else 0),
            reverse=True,
        )

        raids.append(
            RaidStanding(
                raid_id=raid_id,
                raid_name=RAID_NAMES.get(raid_id, raid_id.title()),
                my_score=my_score,
                guild_total=guild_total,
                top_score=top,
                median_score=med,
                squads=squads,
            )
        )

    return GuildReport(
        player_name=player.name,
        ally_code=player.ally_code,
        standing=standing,
        raids=raids,
        tb=_analyze_tb(player, guild.tb_id),
        classic_tb=_analyze_classic_tb(player, guild),
    )
