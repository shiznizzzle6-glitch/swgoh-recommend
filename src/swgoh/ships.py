"""Ship reference data (capital flag, factions, alignment, pilots).

Backed by the bundled ship_data.json. Regenerate with
`python scripts/refresh_ship_data.py <comlink_url>`. Display names come from
swgoh.names (unit_names.json), so they aren't duplicated here.
"""
from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources


@lru_cache(maxsize=1)
def ship_data() -> dict[str, dict]:
    try:
        text = resources.files("swgoh.data").joinpath("ship_data.json").read_text("utf-8")
        return json.loads(text)
    except (FileNotFoundError, ValueError, ModuleNotFoundError):
        return {}


def is_ship(base_id: str) -> bool:
    return base_id in ship_data()


def is_capital_ship(base_id: str) -> bool:
    return bool(ship_data().get(base_id, {}).get("capital"))


def pilots_of(base_id: str) -> list[str]:
    return list(ship_data().get(base_id, {}).get("pilots", []))


def factions_of(base_id: str) -> list[str]:
    return list(ship_data().get(base_id, {}).get("factions", []))
