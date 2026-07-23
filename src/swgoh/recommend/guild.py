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

from ..models import Guild, Player
from ..ships import is_ship
from .squads import SquadPlan, _build_plan

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
    )
