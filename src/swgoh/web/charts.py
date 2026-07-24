"""Tiny dependency-free SVG charts for the dashboard.

Server-rendered inline SVG (no JS libraries, no external requests) so it works
inside the same self-contained page as everything else. Currently: the arena
rank trend.

Rank is a *position* — a LOWER number is better — so the y-axis is inverted:
the best (smallest) rank sits at the TOP and the line rising means you're
climbing. Squad and Fleet ranks live on very different scales, so each gets its
own separately-scaled chart (never a shared/dual axis).
"""
from __future__ import annotations

from datetime import datetime, timezone
from html import escape

from ..history import RankSnapshot

# Single data series -> the app's brand accent (gold). No categorical palette to
# validate; identity comes from each chart's own title, not color.
LINE = "var(--accent)"
INK = "var(--text)"
MUTED = "var(--muted)"
GRID = "var(--line)"
SURFACE = "var(--panel)"


def _fmt_day(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%b %-d") if ts else ""


def _fmt_day_safe(ts: float) -> str:
    # %-d is POSIX-only; fall back for Windows/other platforms.
    try:
        return _fmt_day(ts)
    except ValueError:
        d = datetime.fromtimestamp(ts, tz=timezone.utc)
        return d.strftime("%b ") + str(d.day)


def rank_trend_svg(
    history: list[RankSnapshot],
    key: str,
    *,
    width: int = 520,
    height: int = 132,
) -> str:
    """Render one inverted-y rank line for `key` ('squad_rank' | 'fleet_rank').

    Returns "" if there's no data for that key. A single data point renders as a
    lone marker (the trend fills in as more days are logged).
    """
    pts = [(s.ts, getattr(s, key)) for s in history if getattr(s, key) is not None]
    if not pts:
        return ""

    pad_l, pad_r, pad_t, pad_b = 10, 52, 16, 22
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b

    ranks = [r for _, r in pts]
    best, worst = min(ranks), max(ranks)  # best == smallest number
    span = worst - best or max(1, round(best * 0.02))  # avoid /0 on a flat line

    times = [t for t, _ in pts]
    t0, t1 = min(times), max(times)
    t_span = t1 - t0

    def x_of(i: int, t: float) -> float:
        if len(pts) == 1:
            return pad_l + plot_w / 2
        if t_span > 0:
            return pad_l + plot_w * (t - t0) / t_span
        return pad_l + plot_w * i / (len(pts) - 1)  # same-day points: space evenly

    def y_of(rank: int) -> float:
        # Inverted: best rank (smallest) -> top (small y).
        frac = (rank - best) / span
        return pad_t + plot_h * frac

    coords = [(x_of(i, t), y_of(r), r, t) for i, (t, r) in enumerate(pts)]

    parts: list[str] = []
    parts.append(
        f'<svg viewBox="0 0 {width} {height}" role="img" '
        f'style="width:100%;height:auto;display:block" '
        f'aria-label="{escape(key.replace("_", " "))} over time">'
    )

    # Recessive guide lines at best and worst, with rank labels.
    for rank in ({best, worst} if span else {best}):
        y = y_of(rank)
        parts.append(
            f'<line x1="{pad_l}" y1="{y:.1f}" x2="{pad_l + plot_w}" y2="{y:.1f}" '
            f'stroke="{GRID}" stroke-width="1" />'
        )
        parts.append(
            f'<text x="{pad_l + plot_w + 6}" y="{y + 3:.1f}" fill="{MUTED}" '
            f'font-size="11" font-variant-numeric="tabular-nums">#{rank}</text>'
        )

    # "better" hint (the axis is inverted, which surprises people).
    parts.append(
        f'<text x="{pad_l}" y="{pad_t - 5:.1f}" fill="{MUTED}" font-size="10">↑ better (climbing)</text>'
    )

    # The trend line.
    if len(coords) > 1:
        d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y, _, _ in coords)
        parts.append(
            f'<path d="{d}" fill="none" stroke="{LINE}" stroke-width="2" '
            f'stroke-linejoin="round" stroke-linecap="round" />'
        )

    # Markers with native hover tooltips.
    last_i = len(coords) - 1
    for i, (x, y, r, t) in enumerate(coords):
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{LINE}" '
            f'stroke="{SURFACE}" stroke-width="2">'
            f"<title>{escape(_fmt_day_safe(t))}: #{r}</title></circle>"
        )
        if i == last_i:  # direct-label the latest point
            parts.append(
                f'<text x="{x + 8:.1f}" y="{y + 4:.1f}" fill="{INK}" font-size="12" '
                f'font-weight="700" font-variant-numeric="tabular-nums">#{r}</text>'
            )

    # X-axis end dates.
    parts.append(
        f'<text x="{pad_l}" y="{height - 6}" fill="{MUTED}" font-size="10">{escape(_fmt_day_safe(t0))}</text>'
    )
    if len(coords) > 1:
        parts.append(
            f'<text x="{pad_l + plot_w}" y="{height - 6}" fill="{MUTED}" font-size="10" '
            f'text-anchor="end">{escape(_fmt_day_safe(t1))}</text>'
        )

    parts.append("</svg>")
    return "".join(parts)


def _fmt_gp(value: int) -> str:
    """Compact GP label: 2,191,413 -> '2.19M' (keeps the right margin narrow)."""
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"{value / 1_000:.0f}K"
    return str(value)


def _up_trend_svg(
    pts: list[tuple[float, int]],
    *,
    aria: str,
    hint: str,
    fmt,
    width: int,
    height: int,
) -> str:
    """Render a 'higher is better' value trend (normal y-axis) from (ts, value) points.

    Shared by the skill-rating and galactic-power charts: unlike arena rank, these
    are scores where bigger is better, so the largest value sits at the TOP and a
    rising line means growth. `fmt` renders the value labels. Returns "" if empty.
    """
    if not pts:
        return ""

    pad_l, pad_r, pad_t, pad_b = 10, 60, 16, 22
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b

    values = [v for _, v in pts]
    hi, lo = max(values), min(values)
    span = hi - lo or max(1, round(hi * 0.02))  # avoid /0 on a flat line

    times = [t for t, _ in pts]
    t0, t1 = min(times), max(times)
    t_span = t1 - t0

    def x_of(i: int, t: float) -> float:
        if len(pts) == 1:
            return pad_l + plot_w / 2
        if t_span > 0:
            return pad_l + plot_w * (t - t0) / t_span
        return pad_l + plot_w * i / (len(pts) - 1)

    def y_of(value: int) -> float:
        # Highest value -> top (small y).
        return pad_t + plot_h * (hi - value) / span

    coords = [(x_of(i, t), y_of(v), v, t) for i, (t, v) in enumerate(pts)]

    parts: list[str] = []
    parts.append(
        f'<svg viewBox="0 0 {width} {height}" role="img" '
        f'style="width:100%;height:auto;display:block" '
        f'aria-label="{escape(aria)}">'
    )

    for value in ({hi, lo} if span else {hi}):
        y = y_of(value)
        parts.append(
            f'<line x1="{pad_l}" y1="{y:.1f}" x2="{pad_l + plot_w}" y2="{y:.1f}" '
            f'stroke="{GRID}" stroke-width="1" />'
        )
        parts.append(
            f'<text x="{pad_l + plot_w + 6}" y="{y + 3:.1f}" fill="{MUTED}" '
            f'font-size="11" font-variant-numeric="tabular-nums">{escape(fmt(value))}</text>'
        )

    parts.append(
        f'<text x="{pad_l}" y="{pad_t - 5:.1f}" fill="{MUTED}" font-size="10">{escape(hint)}</text>'
    )

    if len(coords) > 1:
        d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y, _, _ in coords)
        parts.append(
            f'<path d="{d}" fill="none" stroke="{LINE}" stroke-width="2" '
            f'stroke-linejoin="round" stroke-linecap="round" />'
        )

    last_i = len(coords) - 1
    for i, (x, y, v, t) in enumerate(coords):
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{LINE}" '
            f'stroke="{SURFACE}" stroke-width="2">'
            f"<title>{escape(_fmt_day_safe(t))}: {escape(fmt(v))}</title></circle>"
        )
        if i == last_i:
            parts.append(
                f'<text x="{x + 8:.1f}" y="{y + 4:.1f}" fill="{INK}" font-size="12" '
                f'font-weight="700" font-variant-numeric="tabular-nums">{escape(fmt(v))}</text>'
            )

    parts.append(
        f'<text x="{pad_l}" y="{height - 6}" fill="{MUTED}" font-size="10">{escape(_fmt_day_safe(t0))}</text>'
    )
    if len(coords) > 1:
        parts.append(
            f'<text x="{pad_l + plot_w}" y="{height - 6}" fill="{MUTED}" font-size="10" '
            f'text-anchor="end">{escape(_fmt_day_safe(t1))}</text>'
        )

    parts.append("</svg>")
    return "".join(parts)


def skill_trend_svg(
    history: list[RankSnapshot],
    *,
    width: int = 520,
    height: int = 132,
) -> str:
    """Render the GAC skill-rating trend (HIGHER is better -> normal y-axis)."""
    pts = [(s.ts, s.skill_rating) for s in history if s.skill_rating is not None]
    return _up_trend_svg(
        pts,
        aria="GAC skill rating over time",
        hint="↑ better (gaining)",
        fmt=lambda v: f"{v:,}",
        width=width,
        height=height,
    )


def gp_trend_svg(
    history: list[RankSnapshot],
    *,
    width: int = 520,
    height: int = 132,
) -> str:
    """Render the galactic-power trend (HIGHER is better -> normal y-axis)."""
    pts = [(s.ts, s.galactic_power) for s in history if s.galactic_power is not None]
    return _up_trend_svg(
        pts,
        aria="Galactic power over time",
        hint="↑ better (growing)",
        fmt=_fmt_gp,
        width=width,
        height=height,
    )
