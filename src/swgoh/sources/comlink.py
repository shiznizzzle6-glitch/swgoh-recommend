"""swgoh-comlink source (self-hosted / hosted game-data proxy).

Comlink returns the richest data straight from the game servers, but requires
running the container (https://github.com/swgoh-utils/swgoh-comlink). This
adapter is best-effort: it maps the documented Comlink player schema into our
models and degrades gracefully (rather than crashing) when a field is missing.
Validate it against your own instance before trusting mod-level detail.
"""
from __future__ import annotations

from typing import Any

import httpx

from ..models import Mod, Player, SecondaryStat, Unit
from .base import DataSource

# Comlink unitStatId -> (canonical name, is_percent).
COMLINK_STAT: dict[int, tuple[str, bool]] = {
    1: ("Health", False),
    5: ("Speed", False),
    16: ("Critical Damage", True),
    17: ("Potency", True),
    18: ("Tenacity", True),
    28: ("Protection", False),
    41: ("Offense", False),
    42: ("Defense", False),
    48: ("Offense", True),
    49: ("Defense", True),
    52: ("Accuracy", True),
    53: ("Critical Chance", True),
    54: ("Critical Avoidance", True),
    55: ("Health", True),
    56: ("Protection", True),
}

# Mod set enum used inside the mod definitionId prefix.
COMLINK_SET: dict[int, str] = {
    1: "Health",
    2: "Offense",
    3: "Defense",
    4: "Speed",
    5: "Critical Chance",
    6: "Critical Damage",
    7: "Potency",
    8: "Tenacity",
}


def _stat_human_value(inner: dict[str, Any], is_percent: bool) -> float:
    """Convert a Comlink stat's scaled integer into its human value.

    Comlink stores stat magnitudes as `unscaledDecimalValue` scaled by 1e8, e.g.
    a +30 speed arrow is "3000000000" (3000000000 / 1e8 == 30). For percent
    stats that quotient is a fraction (0.01936), so it's multiplied by 100 to
    get percent points (1.936%). `statValueDecimal` (scaled by 1e4) is the
    fallback if the unscaled value is absent.
    """
    raw = inner.get("unscaledDecimalValue")
    if raw is not None:
        base = _to_float(raw) / 1e8
    else:
        base = _to_float(inner.get("statValueDecimal")) / 1e4
    return base * 100 if is_percent else base


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _parse_stat(stat: dict[str, Any]) -> SecondaryStat | None:
    inner = stat.get("stat") if isinstance(stat.get("stat"), dict) else stat
    stat_id = int(inner.get("unitStatId") or inner.get("unitStat") or 0)
    if stat_id not in COMLINK_STAT:
        return None
    name, is_percent = COMLINK_STAT[stat_id]
    value = round(_stat_human_value(inner, is_percent), 2)
    rolls = int(stat.get("statRolls") or 1)
    return SecondaryStat(name=name, value=value, is_percent=is_percent, rolls=rolls)


def _parse_mod(raw: dict[str, Any]) -> Mod | None:
    def_id = str(raw.get("definitionId") or "")
    # definitionId digits encode set (1st), rarity (2nd), slot (3rd). Best-effort.
    set_id = int(def_id[0]) if len(def_id) >= 1 and def_id[0].isdigit() else 0
    rarity = int(def_id[1]) if len(def_id) >= 2 and def_id[1].isdigit() else 0
    slot = int(def_id[2]) if len(def_id) >= 3 and def_id[2].isdigit() else 0
    primary = _parse_stat(raw.get("primaryStat") or {})
    secondaries = [s for s in (_parse_stat(x) for x in (raw.get("secondaryStat") or [])) if s]
    return Mod(
        slot=slot,
        set_name=COMLINK_SET.get(set_id, f"Set{set_id}"),
        rarity=rarity,
        level=int(raw.get("level") or 0),
        tier=int(raw.get("tier") or 0),
        primary_name=primary.name if primary else "",
        primary_value=primary.value if primary else 0.0,
        secondaries=secondaries,
    )


def _parse_unit(raw: dict[str, Any]) -> Unit | None:
    def_id = str(raw.get("definitionId") or "")
    base_id = def_id.split(":", 1)[0] if def_id else ""
    if not base_id:
        return None
    relic = raw.get("relic") or {}
    relic_tier = int(relic.get("currentTier") or 0)
    mods = [m for m in (_parse_mod(m) for m in (raw.get("equippedStatMod") or [])) if m]
    return Unit(
        base_id=base_id,
        name=base_id,  # Comlink names require the localization bundle; base_id for now.
        stars=int(raw.get("currentRarity") or 0),
        level=int(raw.get("currentLevel") or 0),
        gear_level=int(raw.get("currentTier") or 0),
        relic_level=max(0, relic_tier - 2),
        power=0,
        mods=mods,
    )


class ComlinkSource(DataSource):
    name = "comlink"

    def __init__(self, base_url: str = "http://localhost:3000", timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def get_player(self, ally_code: str) -> Player:
        url = f"{self.base_url}/player"
        body = {"payload": {"allyCode": str(ally_code)}, "enums": False}
        resp = httpx.post(url, json=body, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        roster = data.get("rosterUnit") or data.get("roster") or []
        units = [u for u in (_parse_unit(r) for r in roster) if u]
        name = (data.get("name") or data.get("playerName") or "Unknown")
        return Player(name=str(name), ally_code=str(ally_code), units=units)
