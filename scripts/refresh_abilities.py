#!/usr/bin/env python3
"""Regenerate src/swgoh/data/ability_data.json (zeta/omicron/ultimate defs).

Source: swgoh.gg's `/api/abilities/` endpoint. swgoh.gg blocks servers, so
download it in a browser as abilities.json and point this script at the folder:

    python scripts/refresh_abilities.py [dir_with_abilities_json]   # default: repo root

We keep only abilities that carry a zeta, omicron, or ultimate upgrade (the ones
worth prioritizing) and only the fields the analyzer needs. Learned status is
computed live from Comlink skill tiers, so we don't store any player state here.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else ROOT
OUT = ROOT / "src" / "swgoh" / "data" / "ability_data.json"

# swgoh.gg omicron battle-type enum -> friendly game-mode label.
MODE_LABELS = {
    "TERRITORY_WAR_BATTLE": "TW",
    "TERRITORY_TOURNAMENT_BATTLE": "GAC",
    "TERRITORY_STRIKE_BATTLE": "TB",
    "TERRITORY_COVERT_BATTLE": "TB",
    "GRAND_ARENA": "GAC",
    "CONQUEST_BATTLE": "Conquest",
    "RAID": "Raid",
}


def main() -> None:
    path = SRC / "abilities.json"
    rows = json.loads(path.read_text("utf-8"))
    out: dict[str, dict] = {}
    for a in rows:
        if not (a.get("is_zeta") or a.get("is_omicron") or a.get("is_ultimate")):
            continue
        char = a.get("character_base_id")
        if not char:
            continue  # skip ship-crew / unattributed abilities
        modes = sorted({MODE_LABELS.get(m, m) for m in (a.get("omicron_battle_types") or [])})
        out[str(a["base_id"])] = {
            "name": a.get("name", ""),
            "char": str(char),
            "z": bool(a.get("is_zeta")),
            "o": bool(a.get("is_omicron")),
            "u": bool(a.get("is_ultimate")),
            "max": int(a.get("tier_max") or 8),
            "modes": modes,
        }
    out = dict(sorted(out.items()))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    z = sum(1 for v in out.values() if v["z"])
    o = sum(1 for v in out.values() if v["o"])
    print(f"wrote {len(out)} abilities ({z} zeta, {o} omicron) to {OUT}")


if __name__ == "__main__":
    main()
