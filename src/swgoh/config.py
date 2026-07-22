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
    rank_history_path: Path

    @property
    def has_ally_code(self) -> bool:
        return bool(self.ally_code)


def get_settings() -> Settings:
    cache_dir = Path(os.getenv("SWGOH_CACHE_DIR", ".cache")).expanduser()
    # Persist arena-rank history under a writable data dir (mount this in Docker
    # so the trend survives container rebuilds).
    data_dir = Path(os.getenv("SWGOH_DATA_DIR", ".data")).expanduser()
    rank_history_path = Path(
        os.getenv("SWGOH_RANK_HISTORY", str(data_dir / "rank_history.jsonl"))
    ).expanduser()
    # Hardcoded default ally code; override anytime with SWGOH_ALLY_CODE.
    return Settings(
        ally_code=_clean_ally_code(os.getenv("SWGOH_ALLY_CODE", "474168985")),
        data_source=os.getenv("SWGOH_DATA_SOURCE", "swgoh_gg").strip().lower(),
        swgoh_gg_base_url=os.getenv("SWGOH_GG_BASE_URL", "https://swgoh.gg/api").rstrip("/"),
        comlink_url=os.getenv("SWGOH_COMLINK_URL", "http://localhost:3200").rstrip("/"),
        cache_dir=cache_dir,
        cache_ttl_seconds=int(os.getenv("SWGOH_CACHE_TTL", "3600")),
        rank_history_path=rank_history_path,
    )
