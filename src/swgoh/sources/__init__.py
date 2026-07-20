"""Data sources. Every source normalizes into swgoh.models."""
from __future__ import annotations

from ..config import Settings
from .base import DataSource
from .comlink import ComlinkSource
from .swgoh_gg import SwgohGgSource


def build_source(settings: Settings) -> DataSource:
    """Return the DataSource selected by settings.data_source."""
    name = settings.data_source
    if name in ("swgoh_gg", "swgoh.gg", "gg"):
        return SwgohGgSource(base_url=settings.swgoh_gg_base_url)
    if name in ("comlink", "swgoh_comlink"):
        return ComlinkSource(base_url=settings.comlink_url)
    raise ValueError(f"Unknown data source: {name!r}")


__all__ = ["DataSource", "SwgohGgSource", "ComlinkSource", "build_source"]
