#!/usr/bin/env python3
"""Regenerate src/swgoh/data/unit_names.json (base_id -> display name).

Pulls the unit definitions and the English localization bundle from a running
Comlink instance and builds a static base_id -> name map. Run it whenever new
units are released.

Usage:
    python scripts/refresh_unit_names.py [comlink_url]   # default http://localhost:3200
"""
from __future__ import annotations

import base64
import io
import json
import sys
import zipfile
from pathlib import Path

import httpx

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:3200").rstrip("/")
OUT = Path(__file__).resolve().parents[1] / "src" / "swgoh" / "data" / "unit_names.json"


def main() -> None:
    meta = httpx.post(f"{BASE}/metadata", json={"payload": {}}, timeout=60).json()
    gamedata_version = meta["latestGamedataVersion"]
    loc_version = meta["latestLocalizationBundleVersion"]

    print("fetching localization bundle...")
    bundle = httpx.post(
        f"{BASE}/localization",
        json={"payload": {"id": loc_version}, "unzip": False},
        timeout=300,
    ).json()
    zf = zipfile.ZipFile(io.BytesIO(base64.b64decode(bundle["localizationBundle"])))
    eng_file = next(n for n in zf.namelist() if "ENG" in n.upper())
    loc: dict[str, str] = {}
    for line in zf.read(eng_file).decode("utf-8", "replace").split("\n"):
        if "|" in line:
            key, value = line.split("|", 1)
            loc[key.strip()] = value.strip()
    print(f"  {len(loc)} localization entries")

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

    names: dict[str, str] = {}
    for unit in data.get("units", []):
        base_id = unit.get("baseId")
        name_key = unit.get("nameKey")
        if not base_id or base_id in names:
            continue
        name = loc.get(name_key, "").strip()
        if name:
            names[base_id] = name

    names = dict(sorted(names.items()))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(names, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {len(names)} names to {OUT.relative_to(Path.cwd()) if OUT.is_relative_to(Path.cwd()) else OUT}")


if __name__ == "__main__":
    main()
