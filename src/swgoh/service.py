"""High-level service: fetch a player and produce recommendations."""
from __future__ import annotations

from .config import Settings, get_settings
from .history import ArenaStatus, load_status, record_rank
from .models import Player
from .recommend import (
    DefenseReport,
    EnergyReport,
    FleetReport,
    GearReport,
    ModReport,
    RelicReport,
    SliceReport,
    SquadReport,
    TonightBoard,
    ZetaReport,
    analyze_defense,
    analyze_energy,
    analyze_fleet,
    analyze_gear,
    analyze_relics,
    analyze_roster,
    analyze_slicing,
    analyze_squads,
    analyze_zetas,
    build_tonight_board,
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

    def mods_page(self, ally_code: str | None = None) -> tuple[ModReport, SliceReport]:
        """Mod hygiene + slicing priority from a single fetch (for the Mods tab)."""
        player = self.get_player(ally_code)
        return analyze_roster(player, self._priority_config), analyze_slicing(player)

    def slice_report(self, ally_code: str | None = None) -> SliceReport:
        player = self.get_player(ally_code)
        return analyze_slicing(player)

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

    def relic_report(self, ally_code: str | None = None) -> RelicReport:
        player = self.get_player(ally_code)
        return analyze_relics(player)

    def zeta_report(self, ally_code: str | None = None) -> ZetaReport:
        player = self.get_player(ally_code)
        return analyze_zetas(player)

    def gear_report(self, ally_code: str | None = None) -> GearReport:
        player = self.get_player(ally_code)
        return analyze_gear(player)

    def arena_status(self, ally_code: str | None = None) -> ArenaStatus:
        player = self.get_player(ally_code)
        return load_status(player, self.settings.rank_history_path)

    def _board(self, player: Player) -> TonightBoard:
        """Run every 'tonight' analyzer over one already-fetched player."""
        return build_tonight_board(
            mods=analyze_roster(player, self._priority_config),
            fleet=analyze_fleet(player),
            squads=analyze_squads(player),
            gear=analyze_gear(player),
            relics=analyze_relics(player),
            zetas=analyze_zetas(player),
            energy=analyze_energy(player),
        )

    def tonight_board(self, ally_code: str | None = None) -> TonightBoard:
        return self._board(self.get_player(ally_code))

    def landing(self, ally_code: str | None = None) -> tuple[TonightBoard, ArenaStatus]:
        """One fetch → the categorized board plus the arena-rank trend for the header."""
        player = self.get_player(ally_code)
        board = self._board(player)
        status = load_status(player, self.settings.rank_history_path)
        return board, status
