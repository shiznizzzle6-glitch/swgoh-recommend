#!/usr/bin/env python3
"""Regenerate src/swgoh/data/ship_data.json (structural ship reference).

For every ship (combatType 2) records whether it's a capital ship, its faction
tags, alignment, and crew (pilot base_ids). Display names come from
unit_names.json via swgoh.names, so they're not duplicated here.

Usage:
    python scripts/refresh_ship_data.py [comlink_url]   # default http://localhost:3200
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:3200").rstrip("/")
OUT = Path(__file__).resolve().parents[1] / "src" / "swgoh" / "data" / "ship_data.json"


def main() -> None:
    gamedata_version = httpx.post(
        f"{BASE}/metadata", json={"payload": {}}, timeout=60
    ).json()["latestGamedataVersion"]

    print("fetching unit definitions (segment 3)...")
    data = httpx.post(
        f"{BASE}/data",
        json={
            "payload": {
                "version": gamedata_version,
                "includePveUnits": False,
                "requestSegment": 3,
            },
            "enums": False,
        },
        timeout=300,
    ).json()

    ships: dict[str, dict] = {}
    for unit in data.get("units", []):
        if unit.get("combatType") != 2:
            continue
        base_id = unit.get("baseId")
        if not base_id or base_id in ships:
            continue
        cats = unit.get("categoryId") or []
        factions = sorted(
            c[len("affiliation_"):] for c in cats if c.startswith("affiliation_")
        )
        alignment = next(
            (c[len("alignment_"):] for c in cats if c.startswith("alignment_")), ""
        )
        pilots = [c.get("unitId") for c in (unit.get("crew") or []) if c.get("unitId")]
        ships[base_id] = {
            "capital": "shipclass_capitalship" in cats,
            "factions": factions,
            "alignment": alignment,
            "pilots": pilots,
        }

    ships = dict(sorted(ships.items()))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(ships, indent=1), encoding="utf-8")
    caps = sum(1 for s in ships.values() if s["capital"])
    print(f"wrote {len(ships)} ships ({caps} capital) to {OUT}")


if __name__ == "__main__":
    main()
