"""swgoh.gg public API source (no auth required).

Docs: https://api.swgoh.gg/  — the player endpoint returns the full roster
including equipped mods. We normalize into swgoh.models here so the rest of the
app never has to know swgoh.gg's field names.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from ..models import Mod, Player, SecondaryStat, Unit
from .base import DataSource
from .cache import FileCache

# swgoh.gg numeric mod-set ids -> canonical set names used by our models.
# If set names ever look wrong in the UI, this map is the one-line fix.
SET_ID_TO_NAME: dict[int, str] = {
    1: "Health",
    2: "Offense",
    3: "Defense",
    4: "Speed",
    5: "Critical Chance",
    6: "Critical Damage",
    7: "Potency",
    8: "Tenacity",
}

# Stat names swgoh.gg reports as percentages (secondaries).
_PERCENT_STATS = {
    "Offense",
    "Defense",
    "Health",
    "Protection",
    "Critical Chance",
    "Potency",
    "Tenacity",
}


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("%", "").replace(",", "")
    try:
        return float(text)
    except ValueError:
        return 0.0


def _parse_stat_name(stat: dict[str, Any]) -> str:
    return str(stat.get("name") or stat.get("stat") or "").strip()


def _parse_secondary(stat: dict[str, Any]) -> SecondaryStat:
    name = _parse_stat_name(stat)
    display = stat.get("display_value")
    is_percent = (isinstance(display, str) and "%" in display) or name in _PERCENT_STATS and name != "Speed"
    # Prefer the human display value; fall back to the raw numeric value.
    value = _to_float(display if display is not None else stat.get("value"))
    return SecondaryStat(
        name=name,
        value=value,
        is_percent=bool(is_percent) and name != "Speed",
        rolls=int(stat.get("roll") or stat.get("rolls") or 1),
    )


def _parse_mod(raw: dict[str, Any]) -> Mod | None:
    if not isinstance(raw, dict):
        return None
    slot = int(raw.get("slot", 0) or 0)
    # swgoh.gg slots are sometimes 0-indexed; normalize to 1-6.
    if 0 <= slot <= 5:
        slot += 1
    set_id = int(raw.get("set", 0) or 0)
    primary = raw.get("primary_stat") or {}
    secondaries = [
        _parse_secondary(s) for s in (raw.get("secondary_stats") or []) if isinstance(s, dict)
    ]
    return Mod(
        slot=slot,
        set_name=SET_ID_TO_NAME.get(set_id, f"Set{set_id}"),
        rarity=int(raw.get("rarity") or raw.get("pips") or 0),
        level=int(raw.get("level") or 0),
        tier=int(raw.get("tier") or 0),
        primary_name=_parse_stat_name(primary),
        primary_value=_to_float(primary.get("display_value") or primary.get("value")),
        secondaries=secondaries,
    )


def _parse_unit(entry: dict[str, Any]) -> Unit | None:
    data = entry.get("data") if isinstance(entry.get("data"), dict) else entry
    if not isinstance(data, dict) or not data.get("base_id"):
        return None
    relic_tier = int(data.get("relic_tier") or 0)
    # swgoh.gg encodes relic as tier where 1 == locked; actual relic == tier - 2.
    relic_level = max(0, relic_tier - 2)
    mods = [m for m in (_parse_mod(m) for m in (data.get("mods") or [])) if m]
    return Unit(
        base_id=str(data.get("base_id")),
        name=str(data.get("name") or data.get("base_id")),
        stars=int(data.get("rarity") or 0),
        level=int(data.get("level") or 0),
        gear_level=int(data.get("gear_level") or 0),
        relic_level=relic_level,
        power=int(data.get("power") or 0),
        mods=mods,
    )


class SwgohGgSource(DataSource):
    name = "swgoh_gg"

    def __init__(
        self,
        base_url: str = "https://api.swgoh.gg",
        cache: FileCache | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.cache = cache
        self.timeout = timeout

    def _fetch_player_json(self, ally_code: str) -> dict[str, Any]:
        key = f"swgoh_gg:player:{ally_code}"
        if self.cache:
            cached = self.cache.get(key)
            if cached is not None:
                return cached
        url = f"{self.base_url}/player/{ally_code}/"
        headers = {
            "Accept": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            ),
        }
        resp = httpx.get(url, timeout=self.timeout, headers=headers)

        # swgoh.gg now sits behind Cloudflare's JS challenge, which returns an
        # HTML interstitial (often HTTP 403) that plain HTTP clients can't solve.
        content_type = resp.headers.get("content-type", "")
        looks_like_html = "text/html" in content_type or resp.text.lstrip().startswith("<")
        if resp.status_code == 403 or looks_like_html:
            raise RuntimeError(
                "swgoh.gg blocked this request with a Cloudflare challenge "
                f"(HTTP {resp.status_code}). Its public API is no longer reachable "
                "from non-browser clients. Use the Comlink data source instead "
                "(set SWGOH_DATA_SOURCE=comlink). See the README."
            )
        resp.raise_for_status()
        payload = resp.json()
        if self.cache:
            self.cache.set(key, payload)
        return payload

    def get_player(self, ally_code: str) -> Player:
        payload = self._fetch_player_json(ally_code)
        data = payload.get("data") or {}
        raw_units = payload.get("units") or data.get("units") or []
        units = [u for u in (_parse_unit(e) for e in raw_units) if u]
        return Player(
            name=str(data.get("name") or "Unknown"),
            ally_code=str(data.get("ally_code") or ally_code),
            units=units,
        )
