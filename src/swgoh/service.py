"""High-level service: fetch a player and produce recommendations."""
from __future__ import annotations

from .config import Settings, get_settings
from .history import ArenaStatus, load_status, record_rank
from .models import Player
from .recommend import (
    DefenseReport,
    EnergyReport,
    FleetReport,
    ModReport,
    SquadReport,
    TonightPlan,
    analyze_defense,
    analyze_energy,
    analyze_fleet,
    analyze_roster,
    analyze_squads,
    build_tonight_plan,
    load_priority_config,
)
from .sources import build_source
from .sources.cache import FileCache


class SwgohService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.source = build_source(self.settings)
        # Wire the file cache into the swgoh.gg source if it supports it.
        if hasattr(self.source, "cache"):
            self.source.cache = FileCache(
                self.settings.cache_dir, self.settings.cache_ttl_seconds
            )
        self._priority_config = load_priority_config()

    def get_player(self, ally_code: str | None = None) -> Player:
        code = ally_code or self.settings.ally_code
        if not code:
            raise ValueError("No ally code provided or configured (set SWGOH_ALLY_CODE).")
        player = self.source.get_player(code)
        # Snapshot arena rank on every fetch (de-duplicated to ~1/day); never
        # let logging break a request.
        record_rank(player, self.settings.rank_history_path)
        return player

    def mod_report(self, ally_code: str | None = None) -> ModReport:
        player = self.get_player(ally_code)
        return analyze_roster(player, self._priority_config)

    def fleet_report(self, ally_code: str | None = None) -> FleetReport:
        player = self.get_player(ally_code)
        return analyze_fleet(player)

    def squad_report(self, ally_code: str | None = None) -> SquadReport:
        player = self.get_player(ally_code)
        return analyze_squads(player)

    def defense_report(self, ally_code: str | None = None) -> DefenseReport:
        player = self.get_player(ally_code)
        return analyze_defense(player)

    def energy_report(self, ally_code: str | None = None) -> EnergyReport:
        player = self.get_player(ally_code)
        return analyze_energy(player)

    def arena_status(self, ally_code: str | None = None) -> ArenaStatus:
        player = self.get_player(ally_code)
        return load_status(player, self.settings.rank_history_path)

    def tonight_plan(self, ally_code: str | None = None) -> TonightPlan:
        """Fetch the roster once and merge all analyzers into one ranked plan."""
        player = self.get_player(ally_code)
        mods = analyze_roster(player, self._priority_config)
        fleet = analyze_fleet(player)
        squads = analyze_squads(player)
        return build_tonight_plan(mods, fleet, squads)

    def landing(self, ally_code: str | None = None) -> tuple[TonightPlan, ArenaStatus]:
        """One fetch → the tonight plan plus the arena-rank trend for the header."""
        player = self.get_player(ally_code)
        mods = analyze_roster(player, self._priority_config)
        fleet = analyze_fleet(player)
        squads = analyze_squads(player)
        plan = build_tonight_plan(mods, fleet, squads)
        status = load_status(player, self.settings.rank_history_path)
        return plan, status
