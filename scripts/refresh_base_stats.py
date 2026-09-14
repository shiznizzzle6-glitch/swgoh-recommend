#!/usr/bin/env python3
"""Regenerate src/swgoh/data/base_stats.json (unmodded stats per unit).

Modifiers don't only demand abilities — they demand stats. A speed race wants
Speed and Critical Chance; an unresistable effect makes Tenacity worthless; a
debuff-based plan needs Potency to land. Comlink computes no stats at all
(`unitStat` is null, and this build has no /stats route), so the unmodded half
has to come from elsewhere.

swgoh.gg's roster export does compute them: `stats` holds totals by stat id and
`stat_diffs` holds the part contributed by mods, so the difference is the unmodded
value. swgoh.gg blocks servers behind Cloudflare, so download the export in a
browser as download.json and point this script at the folder:

    python scripts/refresh_base_stats.py [dir_with_download_json]   # default: repo root

Base stats only move when a unit gains levels, gear or relics, so a slightly old
export stays accurate for far longer than the mod half — which the app reads live
from Comlink on every request and never takes from here.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else ROOT
OUT = ROOT / "src" / "swgoh" / "data" / "base_stats.json"

# swgoh.gg stat ids -> the names used throughout the app. Identified from value
# ranges across the export: Potency/Tenacity arrive as fractions (0.71 = 71%),
# everything else is already in its display unit.
STAT_IDS = {
    "1": "Health",
    "5": "Speed",
    "8": "Armor",
    "14": "Critical Chance",
    "17": "Potency",
    "18": "Tenacity",
    "28": "Protection",
}
# Stats the export stores as a 0-1 fraction but the game shows as a percentage.
FRACTIONAL = {"Potency", "Tenacity"}


def main() -> None:
    path = SRC / "download.json"
    payload = json.loads(path.read_text("utf-8"))
    rows = [u.get("data") or {} for u in payload.get("units", [])]

    stats: dict[str, dict[str, float]] = {}
    for row in rows:
        base_id = row.get("base_id")
        if not base_id or row.get("combat_type") != 1:
            continue  # characters only; ships don't enter squads
        totals = row.get("stats") or {}
        diffs = row.get("stat_diffs") or {}
        unit: dict[str, float] = {}
        for stat_id, name in STAT_IDS.items():
            total = totals.get(stat_id)
            if total is None:
                continue
            base = float(total) - float(diffs.get(stat_id) or 0)
            if name in FRACTIONAL:
                base *= 100
            unit[name] = round(base, 2)
        if unit:
            stats[str(base_id)] = unit

    out = {
        # Provenance, so the app can say how much of the roster this covers.
        "_meta": {"source": "swgoh.gg roster export", "units": len(stats)},
        "stats": dict(sorted(stats.items())),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"wrote base stats for {len(stats)} units to {OUT}")


if __name__ == "__main__":
    main()
