"""Tests for guild parsing + contribution analyzer (offline)."""
from __future__ import annotations

import json
from importlib import resources

from swgoh.recommend.guild import analyze_guild, load_raid_targets
from swgoh.models import Guild, GuildMember, Player, Unit
from swgoh.sources.comlink import _parse_guild


def test_parse_guild_members_raids_and_scores():
    payload = {
        "guild": {
            "profile": {
                "id": "g1", "name": "Test Guild", "guildGalacticPower": "400000000",
                "memberCount": 2,
                "singleLaunchConfig": {"raidId": "naboo"},
                "autoLaunchConfig": {"raidId": "order66"},
            },
            "member": [
                {"playerId": "A", "playerName": "Alice", "galacticPower": "5000000", "playerLevel": 85},
                {"playerId": "B", "playerName": "Bob", "galacticPower": "2000000", "playerLevel": 85},
            ],
            "recentRaidResult": [{
                "raidId": "order66",
                "raidMember": [
                    {"playerId": "A", "memberProgress": "4500000"},
                    {"playerId": "B", "memberProgress": "0"},
                ],
            }],
            "lastRaidPointsSummary": {"totalPoints": "4500000"},
        }
    }
    g = _parse_guild(payload)
    assert g.name == "Test Guild"
    assert g.active_raids == ["naboo", "order66"]
    assert len(g.members) == 2
    assert g.recent_raid_id == "order66"
    assert g.recent_raid_scores == {"A": 4500000, "B": 0}
    assert g.recent_raid_total == 4500000


def _player():
    return Player(
        name="Bob", ally_code="1", player_id="B", guild_name="Test Guild",
        gac_league="carbonite", gac_division=5, gac_skill_rating=1390,
        units=[Unit("ENFYSNEST", "Enfys Nest", stars=5, gear_level=8)],
    )


def _guild():
    return Guild(
        id="g1", name="Test Guild", galactic_power=400_000_000, member_count=2,
        members=[
            GuildMember("A", "Alice", galactic_power=5_000_000),
            GuildMember("B", "Bob", galactic_power=2_000_000),
        ],
        active_raids=["order66"],
        recent_raid_id="order66", recent_raid_total=4_500_000,
        recent_raid_scores={"A": 4_500_000, "B": 0},
    )


RAIDS = {
    "order66": [
        {"name": "Enfys Nest (solo)", "tier": "A", "beginner": True, "members": ["ENFYSNEST"]},
        {"name": "Dark Clones", "tier": "S", "members": ["GRANDMOFFTARKIN", "SCORCH"]},
    ]
}


def test_standing_rank_and_percentile():
    rep = analyze_guild(_player(), _guild(), RAIDS)
    s = rep.standing
    assert s.my_gp == 2_000_000
    assert s.my_gp_rank == 2          # Bob is 2nd of 2 by GP
    assert s.my_gp_percentile == 0    # last place -> 0th percentile
    assert s.gac_skill_rating == 1390


def test_raid_shows_my_score_vs_guild():
    rep = analyze_guild(_player(), _guild(), RAIDS)
    r = rep.raids[0]
    assert r.raid_name == "Order 66"
    assert r.my_score == 0            # Bob scored nothing
    assert r.top_score == 4_500_000
    # beginner team (Enfys, which Bob owns) ranks ahead of the unowned dark clones
    assert r.squads[0].name == "Enfys Nest (solo)"
    assert "beginner" in r.squads[0].tags


def test_only_active_raids_shown():
    rep = analyze_guild(_player(), _guild(), RAIDS)
    assert [r.raid_id for r in rep.raids] == ["order66"]  # naboo not active in this guild


def test_bundled_raid_targets_base_ids_valid():
    targets = load_raid_targets()
    names = json.loads(
        resources.files("swgoh.data").joinpath("unit_names.json").read_text("utf-8")
    )
    ids = {b for squads in targets.values() for t in squads for b in t["members"]}
    missing = sorted(i for i in ids if i not in names)
    assert not missing, f"unknown base_ids in raid_targets.yaml: {missing}"
