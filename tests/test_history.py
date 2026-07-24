"""Tests for arena-rank history recording + trend (offline, temp files)."""
from __future__ import annotations

from swgoh.history import load_status, record_rank
from swgoh.models import Player


def _p(squad, fleet):
    return Player(name="P", ally_code="123456789", squad_arena_rank=squad, fleet_arena_rank=fleet)


def test_record_and_dedupe_same_day(tmp_path):
    path = tmp_path / "rank.jsonl"
    # First write for the day succeeds.
    assert record_rank(_p(2737, 234), path, now=1_000_000.0) is True
    # Same ranks, same UTC day -> skipped.
    assert record_rank(_p(2737, 234), path, now=1_000_100.0) is False
    # A rank change on the same day IS recorded (intra-day movement).
    assert record_rank(_p(2700, 234), path, now=1_000_200.0) is True
    lines = [l for l in path.read_text().splitlines() if l.strip()]
    assert len(lines) == 2


def test_record_skips_when_no_ranks(tmp_path):
    path = tmp_path / "rank.jsonl"
    assert record_rank(_p(None, None), path, now=1_000_000.0) is False
    assert not path.exists()


def test_status_delta_climb_and_drop(tmp_path):
    path = tmp_path / "rank.jsonl"
    record_rank(_p(2737, 240), path, now=1_000_000.0)
    # Next day: squad improved (lower number), fleet worsened.
    record_rank(_p(2700, 250), path, now=1_100_000.0)
    status = load_status(_p(2700, 250), path)
    assert status.squad_rank == 2700
    assert status.squad_change == -37   # climbed
    assert status.fleet_change == 10    # dropped
    assert status.has_history is True


def test_status_no_history_is_none(tmp_path):
    path = tmp_path / "rank.jsonl"
    record_rank(_p(2737, 234), path, now=1_000_000.0)
    status = load_status(_p(2737, 234), path)
    assert status.squad_change is None
    assert status.has_history is False


def _pg(squad, fleet, skill):
    return Player(
        name="P", ally_code="123456789",
        squad_arena_rank=squad, fleet_arena_rank=fleet, gac_skill_rating=skill,
    )


def test_records_when_only_skill_rating_present(tmp_path):
    path = tmp_path / "rank.jsonl"
    # No arena ranks but a GAC rating -> still worth logging.
    assert record_rank(_pg(None, None, 1350), path, now=1_000_000.0) is True
    status = load_status(_pg(None, None, 1350), path)
    assert status.skill_rating == 1350


def test_skill_change_positive_is_improvement(tmp_path):
    path = tmp_path / "rank.jsonl"
    record_rank(_pg(2737, 240, 1350), path, now=1_000_000.0)
    # Next day: same ranks but skill rating climbed -> a new row is written.
    assert record_rank(_pg(2737, 240, 1400), path, now=1_100_000.0) is True
    status = load_status(_pg(2737, 240, 1400), path)
    assert status.skill_change == 50          # gained rating
    assert status.has_skill_history is True


def test_skill_change_skips_snapshots_without_rating(tmp_path):
    path = tmp_path / "rank.jsonl"
    # Day 1 had a rating; day 2 a rank-only change (no GAC yet in that fetch).
    record_rank(_pg(2737, 240, 1350), path, now=1_000_000.0)
    record_rank(_pg(2700, 240, 0), path, now=1_100_000.0)  # skill 0 -> None
    status = load_status(_pg(2700, 240, 1375), path)
    # Compares to the last snapshot that actually had a rating (1350), not the None row.
    assert status.skill_change == 25


def _pgp(squad, fleet, gp):
    return Player(
        name="P", ally_code="123456789",
        squad_arena_rank=squad, fleet_arena_rank=fleet, galactic_power=gp,
    )


def test_records_when_only_gp_present(tmp_path):
    path = tmp_path / "rank.jsonl"
    # No ranks or GAC rating, but GP alone is worth logging a first row.
    assert record_rank(_pgp(None, None, 2_000_000), path, now=1_000_000.0) is True
    status = load_status(_pgp(None, None, 2_000_000), path)
    assert status.galactic_power == 2_000_000


def test_gp_change_positive_is_growth(tmp_path):
    path = tmp_path / "rank.jsonl"
    record_rank(_pgp(2737, 240, 2_100_000), path, now=1_000_000.0)
    # Next day: GP grew (and a new day forces a fresh row that captures it).
    record_rank(_pgp(2737, 240, 2_191_413), path, now=1_100_000.0)
    status = load_status(_pgp(2737, 240, 2_191_413), path)
    assert status.gp_change == 91_413        # grew
    assert status.has_gp_history is True


def test_gp_alone_does_not_write_intraday_row(tmp_path):
    path = tmp_path / "rank.jsonl"
    assert record_rank(_pgp(2737, 240, 2_100_000), path, now=1_000_000.0) is True
    # Same day, ranks unchanged, only GP moved -> deliberately NOT a new row.
    assert record_rank(_pgp(2737, 240, 2_150_000), path, now=1_000_100.0) is False
    lines = [l for l in path.read_text().splitlines() if l.strip()]
    assert len(lines) == 1


def _pall(squad, fleet, skill, gp):
    return Player(
        name="P", ally_code="123456789", squad_arena_rank=squad, fleet_arena_rank=fleet,
        gac_skill_rating=skill, galactic_power=gp,
    )


def test_gp_backfills_once_when_newly_available_same_day(tmp_path):
    path = tmp_path / "rank.jsonl"
    # A pre-feature row today: ranks + skill, but no GP.
    assert record_rank(_pall(2737, 240, 1350, 0), path, now=1_000_000.0) is True
    # Same day, identical ranks/skill, but now a GP arrives -> write once to start the trend.
    assert record_rank(_pall(2737, 240, 1350, 2_100_000), path, now=1_000_100.0) is True
    # A further same-day fetch (GP now on record) is deduped, even as GP drifts.
    assert record_rank(_pall(2737, 240, 1350, 2_150_000), path, now=1_000_200.0) is False
    lines = [l for l in path.read_text().splitlines() if l.strip()]
    assert len(lines) == 2


def test_gp_change_skips_snapshots_without_gp(tmp_path):
    path = tmp_path / "rank.jsonl"
    record_rank(_pgp(2737, 240, 2_100_000), path, now=1_000_000.0)
    record_rank(_pgp(2700, 240, 0), path, now=1_100_000.0)  # gp 0 -> None row
    status = load_status(_pgp(2680, 240, 2_150_000), path)
    # Compares to the last snapshot that actually had a GP (2.1M), not the None row.
    assert status.gp_change == 50_000


def test_history_filters_by_ally_code(tmp_path):
    path = tmp_path / "rank.jsonl"
    record_rank(_p(2737, 234), path, now=1_000_000.0)
    other = Player(name="Q", ally_code="999999999", squad_arena_rank=5, fleet_arena_rank=5)
    record_rank(other, path, now=1_000_050.0)
    status = load_status(_p(2737, 234), path)
    assert len(status.history) == 1
    assert status.history[0].squad_rank == 2737
