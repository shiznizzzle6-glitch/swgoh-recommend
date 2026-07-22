"""Rules-based mod analysis.

This is a "mod hygiene + priority" engine, not scraped meta advice. It ranks
which characters most need mod *work you'd actually do*, weighted by how much
you care about them (your `priority_characters.yaml`).

The key design choice: a unit is either **undermodded** (few mods, or mostly
low-level ones — you clearly haven't invested, so it collapses to a single
low-urgency flag) or **fully modded** (6 mods, mostly maxed — now the granular
tuning analysis is worth doing: wrong set, non-Speed arrow, low speed, a stray
unleveled/low-rarity mod). Non-priority units only surface if they're both
invested in and improvable, so parked Galactic-Legend-requirement units with
junk mods don't drown out your real squads.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

from ..factions import factions_of
from ..models import Player, Unit
from ..names import display_name
from ..ships import ships_piloted_by

# Severity weights per issue kind. Tune freely.
SEV_UNDERMODDED = 3
SEV_UNLEVELED = 2
SEV_LOW_RARITY = 2
SEV_ARROW_PRIMARY = 3          # against a unit's configured recommended arrow
SEV_ARROW_PRIMARY_GENERIC = 2  # non-Speed arrow with no config (advisory)
SEV_SET_MISMATCH = 3
SEV_LOW_SPEED = 3

# Weight applied to units not in your priority config (priority units use their
# configured weight, typically 1.0-2.0), so your chosen characters rank above
# incidental ones.
NONPRIORITY_WEIGHT = 0.5

# "Fully modded" == 6 mods with at least this many at MAXED_MOD_LEVEL+.
MAXED_MOD_LEVEL = 12
MIN_MAXED_FOR_MODDED = 4

# Total mod speed below which a fully-modded unit is flagged. Configured
# (priority) units are held to a higher bar than incidental fully-modded ones.
LOW_SPEED_THRESHOLD = 40.0
GENERIC_LOW_SPEED_THRESHOLD = 15.0


@dataclass
class Issue:
    kind: str
    detail: str
    severity: int


@dataclass
class UnitModReport:
    unit: Unit
    is_priority: bool
    weight: float
    recommended_sets: list[str]
    recommended_arrow: str
    note: str
    fully_modded: bool = False
    pilot_of: list[str] = field(default_factory=list)
    factions: list[str] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)

    @property
    def total_speed(self) -> float:
        return round(sum(m.speed for m in self.unit.mods), 1)

    @property
    def raw_severity(self) -> int:
        return sum(i.severity for i in self.issues)

    @property
    def score(self) -> float:
        """Ranking score: worse mods on characters you care about float to top."""
        return self.raw_severity * self.weight


@dataclass
class ModReport:
    player_name: str
    ally_code: str
    unit_reports: list[UnitModReport]
    total_mods: int = 0
    unleveled_mods: int = 0
    low_rarity_mods: int = 0

    @property
    def flagged_units(self) -> list[UnitModReport]:
        return [r for r in self.unit_reports if r.issues]


def load_priority_config(path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    """Load per-character mod guidance. Defaults to the bundled YAML."""
    import yaml

    if path is not None:
        text = Path(path).read_text(encoding="utf-8")
    else:
        text = resources.files("swgoh.data").joinpath("priority_characters.yaml").read_text(
            encoding="utf-8"
        )
    data = yaml.safe_load(text) or {}
    return {str(k): (v or {}) for k, v in data.items()}


def _analyze_unit(unit: Unit, cfg: dict[str, Any] | None) -> UnitModReport:
    is_priority = cfg is not None
    cfg = cfg or {}
    recommended_sets = [str(s) for s in (cfg.get("sets") or [])]
    recommended_arrow = str(cfg.get("arrow") or "Speed")
    weight = float(cfg.get("weight", 1.0)) if is_priority else NONPRIORITY_WEIGHT

    mods = unit.mods
    maxed = sum(1 for m in mods if m.level >= MAXED_MOD_LEVEL)
    fully_modded = len(mods) == 6 and maxed >= MIN_MAXED_FOR_MODDED
    pilot_of = [display_name(s) for s in ships_piloted_by(unit.base_id)]

    report = UnitModReport(
        unit=unit,
        is_priority=is_priority,
        weight=weight,
        recommended_sets=recommended_sets,
        recommended_arrow=recommended_arrow,
        note=str(cfg.get("note") or ""),
        fully_modded=fully_modded,
        pilot_of=pilot_of,
        factions=factions_of(unit.base_id),
    )

    if not fully_modded:
        # Not invested yet: one low-urgency flag rather than a pile of noise.
        report.issues.append(
            Issue(
                "undermodded",
                f"Not fully modded ({len(mods)}/6 mods, {maxed} at level {MAXED_MOD_LEVEL}+)",
                SEV_UNDERMODDED,
            )
        )
        return report

    # Fully modded: the granular, actionable tuning analysis. Per-mod checks
    # apply to every fully-modded unit; a level-12+ mod counts as done (that's
    # the "modded" bar), so only genuinely-behind mods are flagged.
    for m in mods:
        if m.level < MAXED_MOD_LEVEL:
            report.issues.append(
                Issue("unleveled", f"{m.slot_name} mod at level {m.level}/15", SEV_UNLEVELED)
            )
        if m.rarity and m.rarity < 5:
            report.issues.append(
                Issue("low_rarity", f"{m.slot_name} mod is {m.rarity}-dot (aim for 5-6)", SEV_LOW_RARITY)
            )

    # For a non-priority unit that's purely a ship pilot, Speed-focused advice is
    # misleading — Speed doesn't help its ship, and it isn't a configured ground
    # unit. Skip the generic Speed flags (the pilot note explains why).
    skip_speed_advice = (not is_priority) and bool(pilot_of)

    # Arrow primary: Speed is best for the vast majority of units. Configured
    # units can override the target (and are flagged more firmly).
    arrow = unit.mod_in_slot(2)
    want_arrow = recommended_arrow if is_priority else "Speed"
    if arrow and want_arrow and arrow.primary_name != want_arrow and not skip_speed_advice:
        qualifier = "recommended" if is_priority else "usually best"
        report.issues.append(
            Issue(
                "arrow_primary",
                f"Arrow primary is {arrow.primary_name}; {want_arrow} {qualifier}",
                SEV_ARROW_PRIMARY if is_priority else SEV_ARROW_PRIMARY_GENERIC,
            )
        )

    # Set mismatch only applies where we have a curated recommendation.
    if is_priority and recommended_sets:
        have: dict[str, int] = {}
        for s in unit.completed_sets():
            have[s] = have.get(s, 0) + 1
        want: dict[str, int] = {}
        for s in recommended_sets:
            want[s] = want.get(s, 0) + 1
        missing = [s for s, n in want.items() if have.get(s, 0) < n]
        if missing:
            report.issues.append(
                Issue(
                    "set_mismatch",
                    f"Missing recommended set(s): {', '.join(missing)}",
                    SEV_SET_MISMATCH,
                )
            )

    speed_threshold = LOW_SPEED_THRESHOLD if is_priority else GENERIC_LOW_SPEED_THRESHOLD
    if report.total_speed < speed_threshold and not skip_speed_advice:
        report.issues.append(
            Issue(
                "low_speed",
                f"Only {report.total_speed:g} speed from mods (under {speed_threshold:g})",
                SEV_LOW_SPEED,
            )
        )

    return report


def analyze_roster(
    player: Player,
    priority_config: dict[str, dict[str, Any]] | None = None,
) -> ModReport:
    """Analyze the roster and return a ranked ModReport.

    Priority units are always considered. Non-priority units are only surfaced
    when they're fully modded *and* have a real improvement to make.
    """
    if priority_config is None:
        priority_config = load_priority_config()

    modded_units = [u for u in player.units if u.mods]

    # Roster-wide hygiene totals (over every modded unit, for the summary cards).
    total_mods = sum(len(u.mods) for u in modded_units)
    unleveled = sum(1 for u in modded_units for m in u.mods if not m.is_maxed)
    low_rarity = sum(1 for u in modded_units for m in u.mods if m.rarity and m.rarity < 5)

    reports: list[UnitModReport] = []
    for unit in modded_units:
        cfg = priority_config.get(unit.base_id)
        report = _analyze_unit(unit, cfg)
        if report.is_priority:
            reports.append(report)
        elif report.fully_modded and report.issues:
            reports.append(report)

    # Fully-modded units (where advice is actionable) rank above undermodded
    # ones; within each group, higher score first.
    reports.sort(key=lambda r: (r.fully_modded, r.score, r.is_priority), reverse=True)
    return ModReport(
        player_name=player.name,
        ally_code=player.ally_code,
        unit_reports=reports,
        total_mods=total_mods,
        unleveled_mods=unleveled,
        low_rarity_mods=low_rarity,
    )
