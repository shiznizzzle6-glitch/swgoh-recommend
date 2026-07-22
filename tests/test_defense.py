"""Tests for the defense / arena-hold analyzer (offline)."""
from __future__ import annotations

import json
from importlib import resources

from swgoh.recommend.defense import analyze_defense, load_defense_targets
from swgoh.models import Player, Unit


TARGETS = {
    "wall_units": [
        {"base_id": "CALKESTIS", "weight": 1.0, "note": "self-heal wall"},
        {"base_id": "FIFTHBROTHER", "weight": 0.9, "note": "inquisitor sustain"},
        {"base_id": "SEVENTHSISTER", "weight": 0.85, "note": "inquisitor sustain"},
    ],
    "teams": [
        {
            "name": "Inquisitorius",
            "tier": "S",
            "tags": ["squad_arena"],
            "anchor": "GRANDINQUISITOR",
            "note": "lead sustain",
            "members": ["GRANDINQUISITOR", "FIFTHBROTHER", "SEVENTHSISTER"],
        }
    ],
}


def _player():
    return Player(
        name="P",
        ally_code="1",
        units=[
            Unit(base_id="CALKESTIS", name="Cal Kestis", stars=6, level=85, gear_level=13, relic_level=5),
            Unit(base_id="FIFTHBROTHER", name="Fifth Brother", stars=7, level=85, gear_level=13, relic_level=1),
            Unit(base_id="SEVENTHSISTER", name="Seventh Sister", stars=7, level=85, gear_level=13, relic_level=1),
        ],
        arena_defense_squad=["CALKESTIS", "FIFTHBROTHER"],
    )


def test_relic_dominates_wall_score():
    rep = analyze_defense(_player(), TARGETS)
    scores = {w.base_id: w.wall_score for w in rep.current_defense}
    # Cal (r5) is a much bigger wall than Fifth Brother (r1) despite same gear.
    assert scores["CALKESTIS"] > scores["FIFTHBROTHER"]
    assert rep.current_rating > 0


def test_bench_lists_owned_walls_strongest_first():
    rep = analyze_defense(_player(), TARGETS)
    ids = [w.base_id for w in rep.bench]
    assert ids[0] == "CALKESTIS"          # highest wall score
    assert "SEVENTHSISTER" in ids         # owned but not on defense still benched
    assert all(w.owned for w in rep.bench)


def test_recommended_is_best_owned_wall_with_relic_steps():
    rep = analyze_defense(_player(), TARGETS)
    assert rep.recommended is not None
    # Field-now recommendation is built from OWNED units only (no unlock asks).
    assert all(m.owned for m in rep.recommended.members)
    assert rep.recommended.anchor == "CALKESTIS"  # stickiest owned unit
    kinds = {o.kind for o in rep.recommended.objectives}
    assert kinds == {"relic"}
    # Cal (r5) is already at target, so relic steps target the r1 Inquisitors.
    targets = {o.target_base_id for o in rep.recommended.objectives}
    assert "FIFTHBROTHER" in targets and "SEVENTHSISTER" in targets
    assert "CALKESTIS" not in targets


def test_curated_teams_surface_unlock_targets():
    rep = analyze_defense(_player(), TARGETS)
    # The aspirational curated team still flags the missing lead to unlock.
    inq = next(t for t in rep.teams if t.name == "Inquisitorius")
    unlocks = {o.target_base_id for o in inq.objectives if o.kind == "unlock"}
    assert "GRANDINQUISITOR" in unlocks


def test_bundled_defense_targets_base_ids_valid():
    targets = load_defense_targets()
    names = json.loads(
        resources.files("swgoh.data").joinpath("unit_names.json").read_text("utf-8")
    )
    ids = {w["base_id"] for w in targets["wall_units"]}
    for t in targets["teams"]:
        ids.update(t["members"])
        ids.add(t["anchor"])
    missing = sorted(i for i in ids if i not in names)
    assert not missing, f"unknown base_ids in defense_targets.yaml: {missing}"
