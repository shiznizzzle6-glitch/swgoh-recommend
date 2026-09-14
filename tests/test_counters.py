"""Tests for the counter engine (offline).

The worked example throughout is Pirate's Plunder, the enemy modifier on the
SM-33 / Maz Kanata Proving Grounds trials — quoted verbatim from the game's
localization bundle, so the detection rules are exercised against real wording
rather than text invented to fit them.
"""
from __future__ import annotations

from swgoh.models import Player, Unit
from swgoh.recommend.counters import (
    THREATS,
    TOOLS,
    analyze_counters,
    detect_threats,
    find_tool_bearers,
    search_abilities,
)
from swgoh.trials import modifier_text, trial, trial_label, trials

PIRATES_PLUNDER = (
    "Whenever a Pirate ally scores a critical hit, the enemy loses 10% Protection. "
    "While a Pirate ally has Profit, they recover 10% Health whenever they gain a buff "
    "and 10% Protection whenever they are inflicted with a debuff. Whenever a Pirate "
    "ally's Health falls below 75%, they dispel all debuffs on themselves and inflict "
    "those debuffs on the weakest enemy. If the Pirate ally does not have any debuffs, "
    "instead inflict Armor Shred on the strongest enemy until the end of the encounter "
    "which can't be resisted."
)


def _keys(text: str) -> set[str]:
    return {t.key for t, _ in detect_threats(text)}


# --- threat detection ---
def test_pirates_plunder_detects_its_core_mechanics():
    keys = _keys(PIRATES_PLUNDER)
    # The three that decide how you build for this fight.
    assert "debuff_feeding" in keys      # debuffs heal them
    assert "debuff_reflect" in keys      # and then bounce back at you
    assert "crit_engine" in keys         # crits drive the Protection loss


def test_pirates_plunder_flags_unresistable_and_shred():
    keys = _keys(PIRATES_PLUNDER)
    assert "unresistable" in keys
    assert "armor_shred" in keys


def test_debuff_feeding_warns_against_debuff_stacking():
    """The counter-intuitive advice is the whole point — assert it's actually given."""
    threats = dict((t.key, t) for t, _ in detect_threats(PIRATES_PLUNDER))
    avoid = " ".join(threats["debuff_feeding"].avoid).lower()
    assert "debuff" in avoid
    assert "don't" in avoid


def test_detection_quotes_the_triggering_sentence():
    for threat, quote in detect_threats(PIRATES_PLUNDER):
        assert quote in PIRATES_PLUNDER, threat.key


def test_unrelated_text_detects_nothing():
    assert detect_threats("The battle takes place on Takodana at sunset.") == []


def test_retribution_warns_against_assist_teams():
    """Trial 18's Steadfast Retribution: every hit you land comes back at you."""
    text = (
        "Whenever a Galactic Republic ally receives damage from an enemy, they deal true "
        "damage to that enemy equal to 100% of the damage received."
    )
    threats = {t.key: t for t, _ in detect_threats(text)}
    assert "damage_reflect" in threats
    assert "true_damage" in threats
    assert any("assist" in line.lower() for line in threats["damage_reflect"].avoid)


def test_every_bundled_trial_yields_a_reading():
    """A trial the engine says nothing about is a coverage gap, not a clean bill."""
    for t in trials():
        assert detect_threats(modifier_text(t)), f"no threats detected for trial {t['number']}"


def test_instant_defeat_tool_ignores_passive_wording():
    """"they are instantly defeated" describes a unit dying, not a tool you bring."""
    from swgoh.recommend.counters import _find

    passive = ["otherwise, they are instantly defeated"]
    active = ["This ability instantly defeats target enemy"]
    tool = next(t for t in TOOLS if t.key == "instant_defeat")
    assert _find(tool.patterns, passive) is None
    assert _find(tool.patterns, active) is not None


def test_revive_threat_recommends_revive_prevention():
    threats = {t.key: t for t, _ in detect_threats("When defeated, revive with 30% Health.")}
    assert "revive" in threats
    assert "revive_block" in threats["revive"].use


# --- catalogue sanity ---
def test_every_threat_points_at_real_tools():
    tool_keys = {t.key for t in TOOLS}
    for threat in THREATS:
        assert threat.use, f"{threat.key} recommends no tools"
        for key in threat.use:
            assert key in tool_keys, f"{threat.key} -> unknown tool {key}"


def test_threat_and_tool_keys_are_unique():
    assert len({t.key for t in THREATS}) == len(THREATS)
    assert len({t.key for t in TOOLS}) == len(TOOLS)


# --- roster matching ---
def _roster() -> Player:
    """Two units with hand-written ability text isn't possible (text is bundled),
    so use real base_ids whose bundled abilities carry known mechanics."""
    return Player(
        name="Test Commander",
        ally_code="123456789",
        units=[
            Unit(base_id="TARFFUL", name="Tarfful", stars=7, gear_level=12, relic_level=5),
            Unit(base_id="JAWA", name="Jawa", stars=5, gear_level=8, relic_level=0),
        ],
    )


def test_find_tool_bearers_matches_bundled_ability_text():
    dispel = next(t for t in TOOLS if t.key == "dispel")
    bearers = find_tool_bearers(_roster(), dispel)
    # Tarfful's basic dispels all buffs on the target.
    assert any(b.base_id == "TARFFUL" for b in bearers)
    hit = next(b for b in bearers if b.base_id == "TARFFUL")
    assert "dispel" in hit.quote.lower()
    assert hit.ability_name


def test_bearers_sorted_with_best_geared_first():
    tool = next(t for t in TOOLS if t.key == "protection_up")
    bearers = find_tool_bearers(_roster(), tool)
    if len(bearers) > 1:
        assert bearers[0].readiness >= bearers[-1].readiness


def test_ships_are_excluded_from_roster_search():
    player = Player(
        name="T", ally_code="1",
        units=[Unit(base_id="MILLENNIUMFALCON", name="Falcon", stars=7, gear_level=1)],
    )
    for tool in TOOLS:
        assert find_tool_bearers(player, tool) == []


def test_search_abilities_finds_keyword_and_quotes_it():
    results = search_abilities(_roster(), "Protection Up")
    assert results
    assert all("protection up" in r.quote.lower() for r in results)


def test_search_abilities_empty_query_returns_nothing():
    assert search_abilities(_roster(), "   ") == []


def test_quotes_are_single_lines_not_whole_kits():
    """Ability text uses escaped newlines; if they aren't unescaped at build time
    a whole multi-line kit collapses into one 'sentence' and the quote is useless."""
    from swgoh.ability_text import ability_text

    for abilities in ability_text().values():
        for ability in abilities:
            assert "\\n" not in ability["d"]


def test_long_quotes_are_trimmed_without_clipping_words():
    from swgoh.recommend.counters import MAX_QUOTE, _trim

    sentence = "padding " * 40 + "the keyword here " + "tail " * 40
    out = _trim(sentence, "keyword")
    assert len(out) <= MAX_QUOTE + 2  # plus the ellipsis characters
    assert "keyword" in out
    assert not out.strip("…").startswith(" ")


# --- bundled trial data ---
def test_trials_bundle_loaded_and_covers_sm33():
    all_trials = trials()
    assert len(all_trials) >= 18
    t19 = trial(19)
    assert t19 is not None
    assert t19["reward_unit"] == "SM-33"
    assert "Pirate's Plunder" in modifier_text(t19)
    assert "SM-33" in trial_label(t19)


def test_unknown_trial_is_none():
    assert trial(999) is None


# --- end-to-end report ---
def test_analyze_counters_from_trial_number():
    report = analyze_counters(_roster(), trial_number=19)
    assert report.analysed
    assert report.trial_number == 19
    assert "SM-33" in report.source_label
    assert report.steps
    assert report.avoid_all  # the "what not to bring" panel has content


def test_analyze_counters_from_pasted_text():
    report = analyze_counters(_roster(), threat_text=PIRATES_PLUNDER)
    assert report.source_label == "Pasted enemy text"
    assert {s.key for s in report.steps} >= {"debuff_feeding", "crit_engine"}


def test_analyze_counters_with_no_input_is_empty_but_valid():
    report = analyze_counters(_roster())
    assert not report.analysed
    assert report.steps == []
    assert report.avoid_all == []


def test_analyze_counters_unknown_trial_raises():
    import pytest

    with pytest.raises(ValueError):
        analyze_counters(_roster(), trial_number=999)


def test_report_carries_search_results_alongside_a_threat():
    report = analyze_counters(_roster(), trial_number=19, query="dispel")
    assert report.steps
    assert report.query == "dispel"
    assert report.matches


def test_avoid_all_deduplicates_across_threats():
    report = analyze_counters(_roster(), threat_text=PIRATES_PLUNDER)
    assert len(report.avoid_all) == len(set(report.avoid_all))
