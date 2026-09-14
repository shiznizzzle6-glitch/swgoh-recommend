"""Conquest Proving Grounds trial briefings, backed by conquest_trials.json.

Each trial's Global/Enemy Modifier text is the puzzle the Counter page solves, so
we keep the game's own wording verbatim rather than paraphrasing it.

Regenerate with `python scripts/refresh_conquest_trials.py <comlink_url>`.
"""
from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources


@lru_cache(maxsize=1)
def trials() -> list[dict]:
    try:
        text = resources.files("swgoh.data").joinpath("conquest_trials.json").read_text("utf-8")
        return json.loads(text)
    except (FileNotFoundError, ValueError, ModuleNotFoundError):
        return []


def trial(number: int) -> dict | None:
    for t in trials():
        if t.get("number") == number:
            return t
    return None


def trial_label(t: dict) -> str:
    """"Trial 19 — SM-33 (vs Pirate King Hondo Ohnaka)" for menus and headings."""
    label = f"Trial {t['number']}"
    if t.get("reward_unit"):
        label += f" — {t['reward_unit']}"
    if t.get("opponent"):
        label += f" (vs {t['opponent']})"
    return label


def modifier_text(t: dict) -> str:
    """Every modifier and stack definition on a trial, as one searchable block."""
    parts = [f"{m['name']}: {m['text']}" for m in t.get("modifiers", [])]
    parts += [f"{e['name']}: {e['text']}" for e in t.get("effects", [])]
    return "\n\n".join(parts)


def modifier_entries(t: dict) -> list[dict]:
    """Modifiers with their scope kept intact.

    Scope changes the strategy: a *Global* modifier applies to your team as well,
    so its rule is something you can exploit rather than only endure. An *Enemy*
    modifier only ever helps them.
    """
    return [
        {
            "name": m.get("name", ""),
            "scope": m.get("scope", ""),
            "text": m.get("text", ""),
            "global": m.get("scope") == "Global",
        }
        for m in t.get("modifiers", [])
    ]
