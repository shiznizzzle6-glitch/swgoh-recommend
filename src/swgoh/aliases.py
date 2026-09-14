"""Resolve the names people actually type into unit base_ids.

Community team lists are written in shorthand — "CLS/Han/Chewy/3PaC/3PO" — and
none of that matches the display names in unit_names.json. This maps the common
abbreviations, then falls back to normalised and partial matching so a squad
pasted from a guide or a Discord message resolves without hand-editing.

Ambiguity is real and left visible: "Echo" is a Bad Batch member *and* a 501st
clone, so `resolve` returns every candidate and the caller decides (see
`resolve_squad`, which uses the rest of the squad as context).
"""
from __future__ import annotations

import re
from functools import lru_cache

from .names import name_map

# Community shorthand -> base_id. Only unambiguous ones belong here.
ALIASES = {
    "cls": "COMMANDERLUKESKYWALKER",
    "gas": "GENERALSKYWALKER",
    "jka": "ANAKINKNIGHT",
    "gk": "GENERALKENOBI",
    "snips": "AHSOKATANO",
    "cat": "COMMANDERAHSOKA",
    "3po": "C3POLEGENDARY",
    "c3po": "C3POLEGENDARY",
    "3pac": "C3POCHEWBACCA",
    "chewy": "CHEWBACCALEGENDARY",
    "chewie": "CHEWBACCALEGENDARY",
    "jkr": "JEDIKNIGHTREVAN",
    "jkl": "JEDIKNIGHTLUKE",
    "jml": "GRANDMASTERLUKE",
    "gmy": "GRANDMASTERYODA",
    "hoda": "HERMITYODA",
    "basti": "BASTILASHAN",
    "bastila": "BASTILASHAN",
    "jolee": "JOLEEBINDO",
    "dr": "DARTHREVAN",
    "malak": "DARTHMALAK",
    "traya": "DARTHTRAYA",
    "nihilus": "DARTHNIHILUS",
    "sion": "DARTHSION",
    "nest": "ENFYSNEST",
    "padme": "PADMEAMIDALA",
    "shaak": "SHAAKTI",
    "ep": "EMPERORPALPATINE",
    "vader": "VADER",
    "thrawn": "GRANDADMIRALTHRAWN",
    "piett": "ADMIRALPIETT",
    "wat": "WATTAMBOR",
    "bam": "BESKARMANDALORIAN",
    "adrad": "ADMIRALRADDUS",
    "cholo": "CAPTAINHANSOLO",
    "arc": "ARCTROOPER501ST",
    "fives": "CT5555",
    "rex": "CT7567",
    "sith assassin": "SITHASSASSIN",
    "sith trooper": "FOSITHTROOPER",
    "han": "HANSOLO",
    "hunter": "BADBATCHHUNTER",
    "tech": "BADBATCHTECH",
    "wrecker": "BADBATCHWRECKER",
}

# Names that legitimately mean different units depending on the squad around them.
AMBIGUOUS = {
    "echo": ("BADBATCHECHO", "CT210408"),
    "rex": ("CT7567", "CAPTAINREX"),
    "wrecker": ("BADBATCHWRECKER", "WRECKERS3"),
    "hunter": ("BADBATCHHUNTER", "HUNTERS3"),
}


def _norm(text: str) -> str:
    """Lowercase, strip punctuation and accents-ish noise for loose matching."""
    text = text.strip().lower().replace("’", "'")
    return re.sub(r"[^a-z0-9]+", "", text)


@lru_cache(maxsize=1)
def _by_normalised_name() -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for base_id, name in name_map().items():
        # Skip the event/inherit duplicates — they're the same character.
        if any(base_id.endswith(sfx) for sfx in ("_EVENT", "_GLE", "_INHERIT")) or "_" in base_id[1:]:
            continue
        index.setdefault(_norm(name), []).append(base_id)
    return index


def resolve(name: str) -> list[str]:
    """Candidate base_ids for a typed name, best guess first ([] if unknown)."""
    raw = name.strip()
    if not raw:
        return []
    key = raw.lower().strip()
    norm = _norm(raw)

    if key in AMBIGUOUS:
        return list(AMBIGUOUS[key])
    if key in ALIASES:
        return [ALIASES[key]]
    if norm in {_norm(k) for k in ALIASES} :
        for k, v in ALIASES.items():
            if _norm(k) == norm:
                return [v]

    exact = _by_normalised_name().get(norm)
    if exact:
        return list(exact)

    # Partial match: "kenobi" -> General Kenobi, Obi-Wan Kenobi (Old Ben), ...
    hits = [
        base_id
        for key_norm, ids in _by_normalised_name().items()
        if norm and norm in key_norm
        for base_id in ids
    ]
    return hits[:5]


def resolve_squad(names: list[str], owned: set[str] | None = None) -> list[tuple[str, str | None]]:
    """Resolve a whole squad, using ownership and squad-mates to break ties.

    Returns (typed_name, base_id or None) pairs, preserving order — the leader is
    whatever the caller listed first.
    """
    from .factions import factions_of

    resolved: list[tuple[str, str | None]] = []
    picks: list[str] = []
    for name in names:
        candidates = resolve(name)
        if not candidates:
            resolved.append((name, None))
            continue
        # Prefer a unit you actually own.
        if owned:
            owned_hits = [c for c in candidates if c in owned]
            if owned_hits:
                candidates = owned_hits
        # Then prefer one sharing a faction with the rest of the squad —
        # "Echo" in a Bad Batch squad is the Bad Batch one.
        if len(candidates) > 1 and picks:
            context = {f for p in picks for f in factions_of(p)}
            shared = [c for c in candidates if context & set(factions_of(c))]
            if shared:
                candidates = shared
        resolved.append((name, candidates[0]))
        picks.append(candidates[0])
    return resolved
