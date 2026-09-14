"""Full ability descriptions per character, backed by ability_text.json.

The Counter page reasons at the *mechanic* level — "who can dispel", "who
inflicts Buff Immunity" — which means searching the text of every ability rather
than looking up character names. This is the index that makes that possible.

Descriptions are swgoh.gg's max-tier text, so an ability whose counter-effect
only appears at a zeta tier reads here as though it's always active. Callers that
care should check learned status via `swgoh.abilities` (see `needs_zeta` in the
counter engine).

Regenerate with `python scripts/refresh_ability_text.py`.
"""
from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources


@lru_cache(maxsize=1)
def ability_text() -> dict[str, list[dict]]:
    """char base_id -> [{i: ability_id, n: name, k: kind, z/o: zeta/omicron, d: description}]"""
    try:
        text = resources.files("swgoh.data").joinpath("ability_text.json").read_text("utf-8")
        return json.loads(text)
    except (FileNotFoundError, ValueError, ModuleNotFoundError):
        return {}


def abilities_of(char_base_id: str) -> list[dict]:
    return ability_text().get(char_base_id, [])
