"""Defense / arena-hold analyzer.

Most of this tool scores units by *offensive* build value. This one scores the
opposite property: how well a unit or team **survives**. In Squad Arena and GAC,
a team that can't be fully killed before the timer forces a DRAW — and a draw is
a win for the defender (the attacker fails and you hold your rank). Self-sustain
kits (self-heal, protection recovery, revive, damage immunity) do this, and they
scale hardest with RELIC, so the readiness math here weights relic above gear.

The report (a) rates your currently-set Squad Arena defense, (b) ranks your best
owned "wall" units, and (c) scores curated synergy-wall teams, with the ordered
relic/unlock steps to strengthen the best one.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

from ..models import Player
from ..names import display_name

# Any unit not in wall_units still has *some* survivability once geared.
BASELINE_WEIGHT = 0.25
# Relic level we push anchors toward; sustain payoff is steep up to here.
RELIC_TARGET = 5

PRIO_ANCHOR = 10.0
PRIO_MEMBER = 7.0


def load_defense_targets(path: str | Path | None = None) -> dict[str, Any]:
    import yaml

    if path is not None:
        text = Path(path).read_text(encoding="utf-8")
    else:
        text = resources.files("swgoh.data").joinpath("defense_targets.yaml").read_text("utf-8")
    data = yaml.safe_load(text) or {}
    return {
        "wall_units": list(data.get("wall_units") or []),
        "teams": list(data.get("teams") or []),
    }


def _weights(targets: dict[str, Any]) -> dict[str, tuple[float, str]]:
    out: dict[str, tuple[float, str]] = {}
    for w in targets.get("wall_units", []):
        bid = str(w.get("base_id") or "").strip()
        if bid:
            out[bid] = (float(w.get("weight", BASELINE_WEIGHT)), str(w.get("note") or "").strip())
    return out


def _wall_frac(stars: int, gear: int, relic: int) -> float:
    """Survivability completeness (0-1), weighted toward relic then gear."""
    return (
        0.15 * (min(stars, 7) / 7)
        + 0.30 * (min(gear, 13) / 13)
        + 0.55 * min(1.0, relic / 8)
    )


@dataclass
class WallUnit:
    base_id: str
    name: str
    owned: bool
    weight: float
    note: str = ""
    stars: int = 0
    gear_level: int = 0
    relic_level: int = 0

    @property
    def wall_score(self) -> float:
        """0-100: how much of a wall this unit is *right now*."""
        if not self.owned:
            return 0.0
        return round(self.weight * _wall_frac(self.stars, self.gear_level, self.relic_level) * 100, 1)


@dataclass
class Objective:
    kind: str
    detail: str
    priority: float
    target_base_id: str = ""


@dataclass
class DefenseTeam:
    name: str
    tier: str
    tags: list[str]
    anchor: str
    note: str
    members: list[WallUnit]
    objectives: list[Objective] = field(default_factory=list)

    @property
    def owned_count(self) -> int:
        return sum(1 for m in self.members if m.owned)

    @property
    def rating(self) -> float:
        if not self.members:
            return 0.0
        return round(sum(m.wall_score for m in self.members) / len(self.members), 1)

    @property
    def status(self) -> str:
        if self.owned_count == len(self.members) and self.rating >= 55:
            return "Ready"
        if self.owned_count >= len(self.members) - 1 and self.rating >= 30:
            return "Close"
        return "Build"


@dataclass
class DefenseReport:
    player_name: str
    ally_code: str
    current_defense: list[WallUnit] = field(default_factory=list)
    current_rating: float = 0.0
    bench: list[WallUnit] = field(default_factory=list)  # owned walls, strongest first
    recommended: DefenseTeam | None = None
    teams: list[DefenseTeam] = field(default_factory=list)
    objectives: list[Objective] = field(default_factory=list)


def _wall_unit(base_id: str, player: Player, weights: dict[str, tuple[float, str]]) -> WallUnit:
    weight, note = weights.get(base_id, (BASELINE_WEIGHT, ""))
    u = player.unit(base_id)
    return WallUnit(
        base_id=base_id,
        name=display_name(base_id),
        owned=u is not None,
        weight=weight,
        note=note,
        stars=u.stars if u else 0,
        gear_level=u.gear_level if u else 0,
        relic_level=u.relic_level if u else 0,
    )


def _team_objectives(team: DefenseTeam) -> list[Objective]:
    objs: list[Objective] = []
    for m in team.members:
        is_anchor = m.base_id == team.anchor
        base = PRIO_ANCHOR if is_anchor else PRIO_MEMBER
        tag = " (anchor)" if is_anchor else ""
        if not m.owned:
            objs.append(Objective("unlock", f"Unlock {m.name}{tag}", base, m.base_id))
        elif m.relic_level < RELIC_TARGET:
            gap = RELIC_TARGET - m.relic_level
            objs.append(
                Objective(
                    "relic",
                    f"Relic {m.name} to R{RELIC_TARGET}+ (now R{m.relic_level}) — "
                    f"sustain scales hardest with relic{tag}",
                    base - 1 + m.weight * gap,
                    m.base_id,
                )
            )
    objs.sort(key=lambda o: o.priority, reverse=True)
    return objs


def _best_owned_wall(bench: list[WallUnit]) -> DefenseTeam | None:
    """A synthetic 'field this now' team: your 5 stickiest OWNED units.

    Grounded in the actual roster rather than an aspirational template — it's the
    strongest wall you can literally set today, with relic steps to harden it.
    """
    members = bench[:5]
    if not members:
        return None
    team = DefenseTeam(
        name="Your best available wall",
        tier="",
        tags=[],
        anchor=members[0].base_id,
        note=(
            "Your five stickiest owned units — the strongest wall you can set right "
            "now. Relic the sustain units (they scale hardest with relic) to turn "
            "draws into reliable holds."
        ),
        members=members,
    )
    team.objectives = _team_objectives(team)
    return team


def analyze_defense(player: Player, targets: dict[str, Any] | None = None) -> DefenseReport:
    if targets is None:
        targets = load_defense_targets()
    weights = _weights(targets)

    # (a) Rate the live, currently-set defense team.
    current = [_wall_unit(b, player, weights) for b in player.arena_defense_squad]
    current_rating = round(sum(m.wall_score for m in current) / len(current), 1) if current else 0.0

    # (b) Bench: every owned wall unit, strongest first.
    bench = [_wall_unit(b, player, weights) for b in weights]
    bench = [w for w in bench if w.owned]
    bench.sort(key=lambda w: w.wall_score, reverse=True)

    # (c) Recommendation = the best wall you can field from owned units today.
    recommended = _best_owned_wall(bench)

    # (d) Curated synergy walls to work toward, strongest first (a coherent lead
    #     out-walls five unrelated tanks, so these are the aspirational targets).
    teams: list[DefenseTeam] = []
    for t in targets.get("teams", []):
        ids = [str(x) for x in t.get("members", [])]
        team = DefenseTeam(
            name=str(t.get("name", "Wall")),
            tier=str(t.get("tier", "B")),
            tags=[str(x) for x in t.get("tags", [])],
            anchor=str(t.get("anchor") or (ids[0] if ids else "")),
            note=str(t.get("note") or "").strip(),
            members=[_wall_unit(b, player, weights) for b in ids],
        )
        team.objectives = _team_objectives(team)
        teams.append(team)
    teams.sort(key=lambda t: t.rating, reverse=True)

    return DefenseReport(
        player_name=player.name,
        ally_code=player.ally_code,
        current_defense=current,
        current_rating=current_rating,
        bench=bench,
        recommended=recommended,
        teams=teams,
        objectives=recommended.objectives if recommended else [],
    )
