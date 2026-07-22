"""Tests for zeta/omicron learned-status rule + priority analyzer (offline)."""
from __future__ import annotations

from swgoh.abilities import ability_defs, is_omicron_learned, is_zeta_learned, zeta_tier
from swgoh.recommend.zetas import analyze_zetas
from swgoh.models import Player, Unit


# --- learned-status rule (validated 100% against a real snapshot) ---
def test_zeta_learned_rule_plain():
    d = {"z": True, "o": False, "max": 8}
    assert zeta_tier(d) == 8
    assert not is_zeta_learned(d, 7)
    assert is_zeta_learned(d, 8)


def test_zeta_tier_is_one_below_max_when_also_omicron():
    d = {"z": True, "o": True, "max": 9}
    assert zeta_tier(d) == 8
    assert is_zeta_learned(d, 8)       # zeta at tier 8
    assert not is_omicron_learned(d, 8)  # omicron only at max (9)
    assert is_omicron_learned(d, 9)


def test_bundled_ability_defs_present():
    defs = ability_defs()
    assert len(defs) > 200
    assert any(v["z"] for v in defs.values())
    assert any(v["o"] for v in defs.values())


# --- analyzer, with an injected ability set (no dependency on bundled data) ---
SQUADS = [{"name": "Nightsisters", "tier": "A", "members": ["TALIA"]}]
FLEET: list = []
DEFENSE = {"wall_units": [{"base_id": "CALKESTIS", "weight": 1.0}], "teams": []}
PRIORITY: dict = {}


def _player():
    return Player(
        name="P", ally_code="1",
        units=[
            # Talia: leader zeta not learned (tier 7 < max 8), special zeta learned.
            Unit(base_id="TALIA", name="Talia", skills={
                "leaderskill_TALIA": 7, "specialskill_TALIA01": 8,
            }),
            # An un-goaled unit with an unlearned zeta -> counted in "other".
            Unit(base_id="JAWA", name="Jawa", skills={"leaderskill_JAWA": 6}),
        ],
    )


def _abilities(monkeypatch):
    import swgoh.recommend.zetas as z

    defs = {
        "TALIA": [
            {"id": "leaderskill_TALIA", "name": "Rise Again", "z": True, "o": False, "u": False, "max": 8, "modes": []},
            {"id": "specialskill_TALIA01", "name": "Frenzy", "z": True, "o": True, "u": False, "max": 9, "modes": ["GAC"]},
        ],
        "JAWA": [
            {"id": "leaderskill_JAWA", "name": "Scavenge", "z": True, "o": False, "u": False, "max": 8, "modes": []},
        ],
    }
    monkeypatch.setattr(z, "abilities_for", lambda bid: defs.get(bid, []))


def test_goal_unit_zeta_ranked_ungoaled_counted(monkeypatch):
    _abilities(monkeypatch)
    # tiers below are already in-game scale, so disable the Comlink offset.
    rep = analyze_zetas(_player(), SQUADS, FLEET, DEFENSE, PRIORITY, comlink_tier_offset=0)
    zeta_ids = {(t.base_id, t.ability_id) for t in rep.zetas}
    assert ("TALIA", "leaderskill_TALIA") in zeta_ids   # unlearned zeta on goal unit
    # specialskill_TALIA01 zeta IS learned (tier 8 == zeta_tier for max9 omicron)
    assert ("TALIA", "specialskill_TALIA01") not in zeta_ids
    assert rep.other_zetas == 1                          # Jawa's zeta, no goal


def test_omicron_surfaces_only_when_zeta_ready(monkeypatch):
    _abilities(monkeypatch)
    rep = analyze_zetas(_player(), SQUADS, FLEET, DEFENSE, PRIORITY, comlink_tier_offset=0)
    # Talia's Frenzy: tier 8 == zeta learned, omicron (max 9) not yet -> applicable.
    omi = [t for t in rep.omicrons if t.ability_id == "specialskill_TALIA01"]
    assert len(omi) == 1
    assert omi[0].modes == ["GAC"]
