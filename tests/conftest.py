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
    # Priority, fully modded, matches recommended -> no issues.
    return Unit(
        base_id="DARTHVADER", name="Darth Vader", stars=7, level=85,
        gear_level=13, relic_level=7, power=34000, mods=full_speed_arrow_mods(),
    )


@pytest.fixture
def wrong_modded_thrawn():
    # Priority, fully modded (6x level 15) but wrong: Health sets, Protection
    # arrow, no speed -> arrow_primary + set_mismatch + low_speed.
    mods = [
        make_mod(1, "Health", primary=("Offense", 5.88)),
        make_mod(2, "Health", primary=("Protection", 24.0)),
        make_mod(3, "Health", primary=("Defense", 11.7)),
        make_mod(4, "Health", primary=("Health", 5.88)),
        make_mod(5, "Health", primary=("Health", 5.88)),
        make_mod(6, "Health", primary=("Potency", 24.0)),
    ]
    return Unit(
        base_id="GRANDADMIRALTHRAWN", name="Grand Admiral Thrawn", stars=7,
        level=85, gear_level=13, relic_level=5, power=30000, mods=mods,
    )


@pytest.fixture
def undermodded_gas():
    # Priority, only 3 level-1 mods -> single "undermodded" flag.
    mods = [
        make_mod(1, "Speed", level=1, primary=("Offense", 1.0)),
        make_mod(2, "Speed", level=1, primary=("Speed", 5.0)),
        make_mod(3, "Speed", level=1, primary=("Defense", 2.0)),
    ]
    return Unit(
        base_id="GENERALSKYWALKER", name="General Skywalker", stars=7,
        level=85, gear_level=13, relic_level=0, power=28000, mods=mods,
    )


@pytest.fixture
def nonprio_modded_hermit():
    # Non-priority, fully modded but one 4-dot mod -> low_rarity -> surfaced.
    mods = full_speed_arrow_mods()
    mods[0] = make_mod(1, "Speed", rarity=4, primary=("Offense", 5.88))
    return Unit(base_id="HERMITYODA", name="Hermit Yoda", gear_level=13, mods=mods)


@pytest.fixture
def nonprio_undermodded():
    # Non-priority, only 2 mods -> excluded entirely.
    mods = [make_mod(1, "Health"), make_mod(2, "Health")]
    return Unit(base_id="UGNAUGHT", name="Ugnaught", gear_level=12, mods=mods)


@pytest.fixture
def player(
    well_modded_vader, wrong_modded_thrawn, undermodded_gas,
    nonprio_modded_hermit, nonprio_undermodded,
):
    filler = Unit(base_id="JAWA", name="Jawa", gear_level=3, mods=[])
    return Player(
        name="Test Commander", ally_code="123456789",
        units=[
            well_modded_vader, wrong_modded_thrawn, undermodded_gas,
            nonprio_modded_hermit, nonprio_undermodded, filler,
        ],
    )
