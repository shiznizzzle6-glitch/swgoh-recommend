"""High-level service: fetch a player and produce recommendations."""
from __future__ import annotations

from .config import Settings, get_settings
from .models import Player
from .recommend import ModReport, analyze_roster, load_priority_config
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
        return self.source.get_player(code)

    def mod_report(self, ally_code: str | None = None) -> ModReport:
        player = self.get_player(ally_code)
        return analyze_roster(player, self._priority_config)
