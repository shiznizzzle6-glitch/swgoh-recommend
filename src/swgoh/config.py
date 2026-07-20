"""Runtime configuration, loaded from environment / .env."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # dotenv is optional at runtime
    pass


def _clean_ally_code(raw: str | None) -> str | None:
    if not raw:
        return None
    digits = "".join(ch for ch in raw if ch.isdigit())
    return digits or None


@dataclass(frozen=True)
class Settings:
    ally_code: str | None
    data_source: str  # "swgoh_gg" | "comlink"
    swgoh_gg_base_url: str
    comlink_url: str
    cache_dir: Path
    cache_ttl_seconds: int

    @property
    def has_ally_code(self) -> bool:
        return bool(self.ally_code)


def get_settings() -> Settings:
    cache_dir = Path(os.getenv("SWGOH_CACHE_DIR", ".cache")).expanduser()
    return Settings(
        ally_code=_clean_ally_code(os.getenv("SWGOH_ALLY_CODE")),
        data_source=os.getenv("SWGOH_DATA_SOURCE", "swgoh_gg").strip().lower(),
        swgoh_gg_base_url=os.getenv("SWGOH_GG_BASE_URL", "https://api.swgoh.gg").rstrip("/"),
        comlink_url=os.getenv("SWGOH_COMLINK_URL", "http://localhost:3000").rstrip("/"),
        cache_dir=cache_dir,
        cache_ttl_seconds=int(os.getenv("SWGOH_CACHE_TTL", "3600")),
    )
