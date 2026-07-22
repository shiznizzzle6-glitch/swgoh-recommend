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


def test_history_filters_by_ally_code(tmp_path):
    path = tmp_path / "rank.jsonl"
    record_rank(_p(2737, 234), path, now=1_000_000.0)
    other = Player(name="Q", ally_code="999999999", squad_arena_rank=5, fleet_arena_rank=5)
    record_rank(other, path, now=1_000_050.0)
    status = load_status(_p(2737, 234), path)
    assert len(status.history) == 1
    assert status.history[0].squad_rank == 2737
