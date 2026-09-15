#!/usr/bin/env python3
"""Regenerate src/swgoh/data/ability_text.json (searchable ability descriptions).

The Counter page works at the *mechanic* level — "who can dispel", "who inflicts
Buff Immunity" — so it needs the full text of every character ability, not just
the zeta/omicron defs that ability_data.json keeps.

Source: swgoh.gg's `/api/abilities/` endpoint. swgoh.gg blocks servers, so
download it in a browser as abilities.json and point this script at the folder:

    python scripts/refresh_ability_text.py [dir_with_abilities_json]   # default: repo root

Ship abilities are skipped (no character_base_id) — the counter engine reasons
about character squads.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else ROOT
OUT = ROOT / "src" / "swgoh" / "data" / "ability_text.json"

# swgoh.gg ability base_id prefixes -> the kind of slot the ability sits in.
KIND_PREFIXES = (
    ("basicskill", "Basic"),
    ("specialskill", "Special"),
    ("leaderskill", "Leader"),
    ("uniqueskill", "Unique"),
    ("contractskill", "Unique"),
)


def clean(desc: str) -> str:
    r"""swgoh.gg ships line breaks as a literal backslash-n, so an ability reads as
    one unbroken run of text. Turn them into real newlines — the counter engine
    splits on those to quote the single line that matched."""
    desc = desc.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", " ")
    lines = [" ".join(line.split()) for line in desc.split("\n")]
    return "\n".join(line for line in lines if line).strip()


def kind_of(base_id: str) -> str:
    low = base_id.lower()
    for prefix, label in KIND_PREFIXES:
        if low.startswith(prefix):
            return label
    return "Other"


def main() -> None:
    rows = json.loads((SRC / "abilities.json").read_text("utf-8"))
    out: dict[str, list[dict]] = {}
    for a in rows:
        char = a.get("character_base_id")
        desc = clean(a.get("description") or "")
        if not char or not desc:
            continue  # ship crew / unattributed, or no text to search
        out.setdefault(str(char), []).append(
            {
                # Ability base_id, so learned status can be cross-referenced
                # against the player's live skill tiers (see swgoh.abilities).
                "i": str(a.get("base_id", "")),
                "n": a.get("name", ""),
                "k": kind_of(str(a.get("base_id", ""))),
                # Max tier, so a roster export can show "level 6 of 8".
                "m": int(a.get("tier_max") or 0),
                "z": bool(a.get("is_zeta")),
                "o": bool(a.get("is_omicron")),
                "d": desc,
            }
        )
    # Stable ordering: Basic, Special, Leader, Unique, then by name.
    order = {"Basic": 0, "Special": 1, "Leader": 2, "Unique": 3, "Other": 4}
    out = {
        char: sorted(abils, key=lambda x: (order.get(x["k"], 9), x["n"]))
        for char, abils in sorted(out.items())
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    total = sum(len(v) for v in out.values())
    print(f"wrote {total} abilities across {len(out)} characters to {OUT}")


if __name__ == "__main__":
    main()
