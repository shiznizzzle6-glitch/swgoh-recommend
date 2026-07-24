"""Persist and summarize arena-rank history over time.

The game API exposes your *current* Squad/Fleet arena rank but no battle log, so
the only way to see whether a defense is holding is to snapshot rank over time
and watch the trend. Snapshots are appended to a JSONL file (one object per
line) and de-duplicated to at most one row per UTC day unless a rank actually
changed — so ordinary page views don't flood it.

Rank is a *position*: a LOWER number is better, so an improvement is a negative
delta. `ArenaStatus` exposes deltas already normalized to "climbed / dropped".
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .models import Player


@dataclass
class RankSnapshot:
    ts: float  # unix seconds
    squad_rank: int | None
    fleet_rank: int | None
    # GAC skill rating (Elo-like: HIGHER is better, unlike the arena ranks above).
    skill_rating: int | None = None
    # Total account galactic power (HIGHER is better, like skill rating).
    galactic_power: int | None = None

    @property
    def day(self) -> str:
        return datetime.fromtimestamp(self.ts, tz=timezone.utc).strftime("%Y-%m-%d")


@dataclass
class ArenaStatus:
    squad_rank: int | None
    fleet_rank: int | None
    skill_rating: int | None = None
    galactic_power: int | None = None
    # Change vs the previous snapshot. Negative == climbed (rank number fell).
    # For skill_rating / galactic_power the sign is flipped in meaning: POSITIVE == improved.
    squad_change: int | None = None
    fleet_change: int | None = None
    skill_change: int | None = None
    gp_change: int | None = None
    history: list[RankSnapshot] = field(default_factory=list)

    @property
    def has_history(self) -> bool:
        return len(self.history) > 1

    @property
    def has_skill_history(self) -> bool:
        return sum(1 for s in self.history if s.skill_rating is not None) > 1

    @property
    def has_gp_history(self) -> bool:
        return sum(1 for s in self.history if s.galactic_power is not None) > 1


def _read(path: Path, ally_code: str) -> list[RankSnapshot]:
    if not path.exists():
        return []
    out: list[RankSnapshot] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if str(row.get("ally_code")) != str(ally_code):
            continue
        out.append(
            RankSnapshot(
                ts=float(row.get("ts") or 0),
                squad_rank=row.get("squad_rank"),
                fleet_rank=row.get("fleet_rank"),
                skill_rating=row.get("skill_rating"),
                galactic_power=row.get("galactic_power"),
            )
        )
    out.sort(key=lambda s: s.ts)
    return out


def record_rank(player: Player, path: str | Path, now: float | None = None) -> bool:
    """Append today's rank snapshot for `player`, unless it's redundant.

    Skips the write when the newest existing snapshot is from the same UTC day
    *and* carries identical ranks and skill rating — keeping the log to roughly
    one row per day while still capturing intra-day movement. Returns True if a
    row was written. Never raises on I/O problems: rank logging must not break a
    page request.
    """
    # GAC skill rating / GP default to 0 on the model; treat that as "no data".
    skill = player.gac_skill_rating or None
    gp = player.galactic_power or None
    if (
        player.squad_arena_rank is None
        and player.fleet_arena_rank is None
        and skill is None
        and gp is None
    ):
        return False
    ts = time.time() if now is None else now
    path = Path(path)
    try:
        existing = _read(path, player.ally_code)
        if existing:
            last = existing[-1]
            # GP is deliberately excluded from the change check: it drifts with
            # every level/gear tick, so keying on it would write many rows a day.
            # A fresh row (new day, or a rank/skill move) still captures current GP,
            # giving a clean ~daily GP trend without the noise.
            unchanged = (
                last.squad_rank == player.squad_arena_rank
                and last.fleet_rank == player.fleet_arena_rank
                and last.skill_rating == skill
            )
            snap = RankSnapshot(ts, player.squad_arena_rank, player.fleet_arena_rank, skill)
            if unchanged and last.day == snap.day:
                return False
        row = {
            "ts": round(ts, 3),
            "ally_code": str(player.ally_code),
            "squad_rank": player.squad_arena_rank,
            "fleet_rank": player.fleet_arena_rank,
            "skill_rating": skill,
            "galactic_power": gp,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
        return True
    except OSError:
        return False


def _delta(current: int | None, previous: int | None) -> int | None:
    if current is None or previous is None:
        return None
    return current - previous


def load_status(player: Player, path: str | Path) -> ArenaStatus:
    """Build the current-rank + trend view, using the just-recorded history."""
    history = _read(Path(path), player.ally_code)
    squad_change = fleet_change = skill_change = None
    if len(history) >= 2:
        prev = history[-2]
        squad_change = _delta(player.squad_arena_rank, prev.squad_rank)
        fleet_change = _delta(player.fleet_arena_rank, prev.fleet_rank)
    # Skill rating can be flat for days, so compare to the most recent PRIOR
    # snapshot that actually carried a rating (skipping the current row).
    skill = player.gac_skill_rating or None
    if skill is not None:
        for prev in reversed(history[:-1]):
            if prev.skill_rating is not None:
                skill_change = skill - prev.skill_rating
                break
    # GP moves the same way — compare to the most recent PRIOR snapshot with a GP.
    gp = player.galactic_power or None
    gp_change = None
    if gp is not None:
        for prev in reversed(history[:-1]):
            if prev.galactic_power is not None:
                gp_change = gp - prev.galactic_power
                break
    return ArenaStatus(
        squad_rank=player.squad_arena_rank,
        fleet_rank=player.fleet_arena_rank,
        skill_rating=skill,
        galactic_power=gp,
        squad_change=squad_change,
        fleet_change=fleet_change,
        skill_change=skill_change,
        gp_change=gp_change,
        history=history,
    )
