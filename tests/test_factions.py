"""Tests for the bundled faction/category lookup (offline)."""
from __future__ import annotations

from swgoh.factions import (
    all_factions,
    faction_map,
    factions_of,
    has_faction,
    units_with_faction,
)


def test_known_unit_factions():
    bossk = factions_of("BOSSK")
    assert "Bounty Hunter" in bossk
    assert "Scoundrel" in bossk


def test_has_faction():
    assert has_faction("EMPERORPALPATINE", "Sith")
    assert has_faction("EMPERORPALPATINE", "Empire")
    assert not has_faction("EMPERORPALPATINE", "Nightsister")


def test_unknown_unit_is_empty():
    assert factions_of("NOT_A_REAL_UNIT") == []


def test_reverse_index():
    ns = units_with_faction("Nightsister")
    assert "MOTHERTALZIN" in ns
    empire = units_with_faction("Empire")
    assert "EMPERORPALPATINE" in empire and "FIFTHBROTHER" in empire


def test_bundle_shape_and_coverage():
    fm = faction_map()
    assert len(fm) > 300  # characters + ships
    # values are lists of strings
    assert all(isinstance(v, list) for v in list(fm.values())[:20])
    facs = all_factions()
    for expected in ("Empire", "Rebel", "Jedi", "Sith", "Bounty Hunter", "Nightsister"):
        assert expected in facs
