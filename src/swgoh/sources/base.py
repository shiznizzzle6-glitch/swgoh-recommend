"""The interface all data sources implement."""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import Player


class DataSource(ABC):
    """A source of SWGOH player data, normalized into swgoh.models.Player."""

    name: str = "base"

    @abstractmethod
    def get_player(self, ally_code: str) -> Player:
        """Fetch and normalize a player's full roster by ally code."""
        raise NotImplementedError
