"""Rules-based mod analysis.

This is a "mod hygiene + priority" engine, not scraped meta advice. It flags
objectively-improvable mod situations (unleveled mods, sub-5-dot mods, empty
slots, non-Speed arrows, wrong sets vs your curated config) and ranks which
characters most need attention, weighted by how much you care about them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

from ..models import Player, Unit

# Severity weights per issue kind. Tune freely.
SEV_MISSING_MOD = 4
SEV_UNLEVELED = 3
SEV_LOW_RARITY = 2
SEV_ARROW_PRIMARY = 3
SEV_SET_MISMATCH = 2
SEV_LOW_SPEED = 3

# A priority unit with less than this much total mod speed is under-modded.
LOW_SPEED_THRESHOLD = 40.0

# Only analyze units at or above this gear level unless they're in the config.
DEFAULT_MIN_GEAR = 11


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

    @property
    def total_mods(self) -> int:
        return sum(len(r.unit.mods) for r in self.unit_reports)

    @property
    def unleveled_mods(self) -> int:
        return sum(
            1 for r in self.unit_reports for m in r.unit.mods if not m.is_maxed
        )

    @property
    def low_rarity_mods(self) -> int:
        return sum(
            1 for r in self.unit_reports for m in r.unit.mods if m.rarity < 5
        )

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
    weight = float(cfg.get("weight", 1.0))
    report = UnitModReport(
        unit=unit,
        is_priority=is_priority,
        weight=weight,
        recommended_sets=recommended_sets,
        recommended_arrow=recommended_arrow,
        note=str(cfg.get("note") or ""),
    )

    mods = unit.mods
    if len(mods) < 6:
        report.issues.append(
            Issue("missing_mod", f"Only {len(mods)}/6 mods equipped", SEV_MISSING_MOD * (6 - len(mods)))
        )

    for m in mods:
        if not m.is_maxed:
            report.issues.append(
                Issue("unleveled", f"{m.slot_name} mod at level {m.level}/15", SEV_UNLEVELED)
            )
        if m.rarity and m.rarity < 5:
            report.issues.append(
                Issue("low_rarity", f"{m.slot_name} mod is {m.rarity}-dot (aim for 5-6)", SEV_LOW_RARITY)
            )

    if is_priority:
        arrow = unit.mod_in_slot(2)
        if arrow and recommended_arrow and arrow.primary_name != recommended_arrow:
            report.issues.append(
                Issue(
                    "arrow_primary",
                    f"Arrow primary is {arrow.primary_name}; {recommended_arrow} recommended",
                    SEV_ARROW_PRIMARY,
                )
            )

        if recommended_sets:
            completed = unit.completed_sets()
            have = dict()
            for s in completed:
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

        if mods and report.total_speed < LOW_SPEED_THRESHOLD:
            report.issues.append(
                Issue(
                    "low_speed",
                    f"Only {report.total_speed:g} speed from mods (under {LOW_SPEED_THRESHOLD:g})",
                    SEV_LOW_SPEED,
                )
            )

    return report


def analyze_roster(
    player: Player,
    priority_config: dict[str, dict[str, Any]] | None = None,
    min_gear: int = DEFAULT_MIN_GEAR,
) -> ModReport:
    """Analyze every relevant unit and return a ranked ModReport."""
    if priority_config is None:
        priority_config = load_priority_config()

    reports: list[UnitModReport] = []
    for unit in player.units:
        cfg = priority_config.get(unit.base_id)
        relevant = cfg is not None or unit.gear_level >= min_gear or unit.relic_level > 0
        if not relevant or not unit.mods:
            continue
        reports.append(_analyze_unit(unit, cfg))

    reports.sort(key=lambda r: (r.score, r.is_priority, r.total_speed), reverse=True)
    return ModReport(player_name=player.name, ally_code=player.ally_code, unit_reports=reports)
