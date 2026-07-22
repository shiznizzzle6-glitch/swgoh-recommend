"""Tests for the inline SVG rank-trend chart (offline)."""
from __future__ import annotations

from swgoh.history import RankSnapshot
from swgoh.web.charts import rank_trend_svg

DAY = 86400.0


def _hist():
    return [
        RankSnapshot(ts=1_000_000.0, squad_rank=2737, fleet_rank=240),
        RankSnapshot(ts=1_000_000.0 + DAY, squad_rank=2700, fleet_rank=250),
        RankSnapshot(ts=1_000_000.0 + 2 * DAY, squad_rank=2600, fleet_rank=248),
    ]


def test_empty_history_renders_nothing():
    assert rank_trend_svg([], "squad_rank") == ""


def test_missing_key_renders_nothing():
    hist = [RankSnapshot(ts=1_000_000.0, squad_rank=None, fleet_rank=200)]
    assert rank_trend_svg(hist, "squad_rank") == ""
    assert rank_trend_svg(hist, "fleet_rank") != ""


def test_single_point_renders_marker_no_line():
    hist = [RankSnapshot(ts=1_000_000.0, squad_rank=2737, fleet_rank=240)]
    svg = rank_trend_svg(hist, "squad_rank")
    assert "<svg" in svg and "</svg>" in svg
    assert "<circle" in svg
    assert "<path" not in svg          # no line for a lone point
    assert "#2737" in svg              # latest value labeled


def test_multi_point_has_line_and_latest_label():
    svg = rank_trend_svg(_hist(), "squad_rank")
    assert svg.count("<circle") == 3
    assert "<path" in svg              # trend line present
    assert "#2600" in svg             # latest (best) rank labeled
    assert "↑ better" in svg          # inversion is annotated


def test_y_axis_is_inverted_best_rank_on_top():
    # Best (smallest) rank must map to a smaller y (higher on screen) than worst.
    svg = rank_trend_svg(_hist(), "squad_rank", width=520, height=132)
    # Pull the circle y-coords in point order.
    import re

    ys = [float(m) for m in re.findall(r'<circle cx="[\d.]+" cy="([\d.]+)"', svg)]
    # ranks are 2737 (worst), 2700, 2600 (best) -> y should DECREASE (rise).
    assert ys[0] > ys[-1]
