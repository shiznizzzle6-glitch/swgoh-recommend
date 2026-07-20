"""Shared fixtures. All offline — no network calls in tests."""
from __future__ import annotations

import pytest

from swgoh.models import Mod, Player, SecondaryStat, Unit


def make_mod(slot, set_name, rarity=6, level=15, primary=("Speed", 30.0), secs=None):
    return Mod(
        slot=slot,
        set_name=set_name,
        rarity=rarity,
        level=level,
        tier=5,
        primary_name=primary[0],
        primary_value=primary[1],
        secondaries=[SecondaryStat(n, v) for n, v in (secs or [])],
    )


def full_speed_arrow_mods():
    """Six clean mods: 4 speed + 2 crit chance, speed arrow, all maxed 6-dot."""
    return [
        make_mod(1, "Speed", primary=("Offense", 5.88)),
        make_mod(2, "Speed", primary=("Speed", 30.0)),
        make_mod(3, "Speed", primary=("Defense", 11.7)),
        make_mod(4, "Speed", primary=("Critical Damage", 36.0), secs=[("Speed", 12.0)]),
        make_mod(5, "Critical Chance", primary=("Health", 5.88), secs=[("Speed", 9.0)]),
        make_mod(6, "Critical Chance", primary=("Potency", 24.0), secs=[("Speed", 6.0)]),
    ]


@pytest.fixture
def well_modded_vader():
    return Unit(
        base_id="DARTHVADER", name="Darth Vader", stars=7, level=85,
        gear_level=13, relic_level=7, power=34000, mods=full_speed_arrow_mods(),
    )


@pytest.fixture
def badly_modded_thrawn():
    # Non-speed arrow, unleveled + low-rarity mods, missing set, only 5 mods.
    mods = [
        make_mod(1, "Health", primary=("Offense", 5.88)),
        make_mod(2, "Health", rarity=4, level=9, primary=("Protection", 24.0)),  # bad arrow
        make_mod(3, "Health", primary=("Defense", 11.7)),
        make_mod(4, "Health", primary=("Health", 5.88)),
        make_mod(6, "Tenacity", primary=("Tenacity", 24.0)),
    ]
    return Unit(
        base_id="GRANDADMIRALTHRAWN", name="Grand Admiral Thrawn", stars=7,
        level=85, gear_level=13, relic_level=5, power=30000, mods=mods,
    )


@pytest.fixture
def player(well_modded_vader, badly_modded_thrawn):
    # A non-priority, low-gear unit that should be ignored by default.
    filler = Unit(base_id="JAWA", name="Jawa", gear_level=3, mods=[])
    return Player(
        name="Test Commander", ally_code="123456789",
        units=[well_modded_vader, badly_modded_thrawn, filler],
    )
