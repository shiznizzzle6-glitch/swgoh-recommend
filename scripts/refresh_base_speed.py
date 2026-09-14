#!/usr/bin/env python3
"""Regenerate src/swgoh/data/base_speed.json (unmodded Speed per unit).

Speed decides turn order, and turn order decides fights — but Comlink ships raw
roster data and computes no stats (`unitStat` is null, and this build has no
/stats route), so base Speed has to come from elsewhere.

swgoh.gg's roster export does compute it: `stats["5"]` is total Speed and
`stat_diffs["5"]` is the part contributed by mods, so the difference is the
unmodded value. swgoh.gg blocks servers behind Cloudflare, so download the export
in a browser as download.json and point this script at the folder:

    python scripts/refresh_base_speed.py [dir_with_download_json]   # default: repo root

Base Speed only moves when a unit gains levels, gear or relics, so a slightly old
export stays accurate for far longer than the mod half — which the app reads live
from Comlink on every request and never takes from here.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else ROOT
OUT = ROOT / "src" / "swgoh" / "data" / "base_speed.json"

SPEED_STAT_ID = "5"


def main() -> None:
    path = SRC / "download.json"
    payload = json.loads(path.read_text("utf-8"))
    rows = [u.get("data") or {} for u in payload.get("units", [])]

    speeds: dict[str, int] = {}
    for row in rows:
        base_id = row.get("base_id")
        total = (row.get("stats") or {}).get(SPEED_STAT_ID)
        if not base_id or total is None:
            continue
        from_mods = (row.get("stat_diffs") or {}).get(SPEED_STAT_ID) or 0
        base = round(float(total) - float(from_mods))
        if base > 0:
            speeds[str(base_id)] = int(base)

    out = {
        # Provenance, so the app can say how much of the roster this covers.
        "_meta": {"source": "swgoh.gg roster export", "units": len(speeds)},
        "speeds": dict(sorted(speeds.items())),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"wrote base Speed for {len(speeds)} units to {OUT}")


if __name__ == "__main__":
    main()
