#!/usr/bin/env python3
"""Regenerate the gear reference bundles from swgoh.gg JSON.

Produces two files from browser-downloaded swgoh.gg data (Cloudflare blocks
servers, so download these in a browser first):
  - gear_names.json         : gear base_id -> human name        (from gear.json)
  - gear_requirements.json  : char base_id -> {tier: [gear ids]} (from characters.json)

    python scripts/refresh_gear.py [dir_with_json]   # default: repo root

Note: swgoh.gg's `gear_levels` only covers tiers 1-12, so the G12->G13 step has
no piece list here (that's expected).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else ROOT
DATA = ROOT / "src" / "swgoh" / "data"


def main() -> None:
    gear = json.loads((SRC / "gear.json").read_text("utf-8"))
    names = {str(g["base_id"]): g.get("name", "") for g in gear if g.get("base_id")}
    names = dict(sorted(names.items()))
    (DATA / "gear_names.json").write_text(
        json.dumps(names, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    print(f"wrote {len(names)} gear names")

    chars = json.loads((SRC / "characters.json").read_text("utf-8"))
    reqs: dict[str, dict[str, list[str]]] = {}
    for c in chars:
        base_id = c.get("base_id")
        levels = c.get("gear_levels") or []
        if not base_id or not levels:
            continue
        reqs[str(base_id)] = {
            str(lvl["tier"]): [str(g) for g in (lvl.get("gear") or [])]
            for lvl in levels
            if lvl.get("tier")
        }
    reqs = dict(sorted(reqs.items()))
    (DATA / "gear_requirements.json").write_text(
        json.dumps(reqs, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    print(f"wrote gear requirements for {len(reqs)} characters")


if __name__ == "__main__":
    main()
