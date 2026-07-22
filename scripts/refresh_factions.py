#!/usr/bin/env python3
"""Regenerate src/swgoh/data/unit_factions.json (base_id -> [categories]).

Source: swgoh.gg's `/api/characters/` and `/api/ships/` endpoints. swgoh.gg is
behind Cloudflare (it blocks servers/scripts), so you can't fetch it from the
VM — download those two URLs in a *browser* and save them as characters.json and
ships.json, then point this script at the folder holding them:

    python scripts/refresh_factions.py [dir_with_json]   # default: repo root

`categories` is swgoh.gg's tag list per unit — factions (Empire, Nightsister,
Bounty Hunter), traits (Scoundrel, Unaligned Force User) and role tags (Leader).
We keep them all; consumers filter as needed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else ROOT
OUT = ROOT / "src" / "swgoh" / "data" / "unit_factions.json"


def _load(name: str) -> list[dict]:
    path = SRC / name
    if not path.exists():
        print(f"  (skipped {name} — not found in {SRC})")
        return []
    return json.loads(path.read_text("utf-8"))


def main() -> None:
    factions: dict[str, list[str]] = {}
    for fname in ("characters.json", "ships.json"):
        rows = _load(fname)
        for unit in rows:
            base_id = unit.get("base_id")
            cats = unit.get("categories") or []
            if base_id and cats:
                factions[str(base_id)] = sorted({str(c) for c in cats})
        print(f"  {fname}: {len(rows)} units")

    factions = dict(sorted(factions.items()))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(factions, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {len(factions)} unit->factions to {OUT}")


if __name__ == "__main__":
    main()
