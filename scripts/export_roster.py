#!/usr/bin/env python3
"""Export a roster to a multi-sheet spreadsheet: characters, abilities, mods.

Everything the app reasons about, flattened so you can sort and filter it
yourself — which is often faster than any page for questions like "who has a
speed arrow" or "which relic-5 units still have a level-1 mod".

    python scripts/export_roster.py                          # uses SWGOH_* env / .env
    python scripts/export_roster.py --ally-code 474168985 --out roster.xlsx
    python scripts/export_roster.py --comlink http://192.168.2.87:3200

Needs the export extra:  pip install -e ".[export]"

Sheets
------
Characters  one row per character: family, stars, gear, relic, mod count, and
            each tracked stat split into base / mods / total.
Abilities   one row per ability: kind, current tier on the in-game scale, max
            tier, whether a zeta or omicron is learned, and the full text.
Mods        one row per equipped mod: slot, set, dots, level, tier, primary and
            every secondary with its value and roll count.
Summary     roster totals, computed with formulas so they follow your edits.

Base stats come from the bundled stats export (scripts/refresh_base_stats.py)
and are blank for units it doesn't cover; the mod half is always live, so the
"mods" columns are exact even when "base" is empty.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from swgoh.ability_text import abilities_of  # noqa: E402
from swgoh.abilities import ability_defs, is_omicron_learned, is_zeta_learned  # noqa: E402
from swgoh.factions import factions_of  # noqa: E402
from swgoh.models import Player, Unit  # noqa: E402
from swgoh.names import display_name  # noqa: E402
from swgoh.recommend.counter_squads import NON_FAMILY  # noqa: E402
from swgoh.recommend.counters import COMLINK_TIER_OFFSET  # noqa: E402
from swgoh.ships import is_ship  # noqa: E402
from swgoh.stats import TRACKED_STATS, base_stat, mod_stat  # noqa: E402

try:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
except ModuleNotFoundError:  # pragma: no cover - dependency guard
    sys.exit('openpyxl is required: pip install -e ".[export]"')

FONT = "Arial"
HEADER_FILL = PatternFill("solid", fgColor="1F3864")
HEADER_FONT = Font(name=FONT, bold=True, color="FFFFFF", size=10)
BODY_FONT = Font(name=FONT, size=10)
TITLE_FONT = Font(name=FONT, bold=True, size=12)
# Marks a value the bundled stats export couldn't supply.
MISSING_FILL = PatternFill("solid", fgColor="FFF2CC")

MAX_SECONDARIES = 4


def families_of(base_id: str) -> str:
    """The unit's factions, minus role and event tags."""
    return ", ".join(f for f in factions_of(base_id) if f not in NON_FAMILY)


def write_sheet(ws, headers: list[str], rows: list[list], freeze: str = "A2") -> None:
    ws.append(headers)
    for cell in ws[1]:
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    for row in rows:
        ws.append(row)
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.font = BODY_FONT
    ws.freeze_panes = freeze
    ws.auto_filter.ref = ws.dimensions
    # Width from the longest value, capped so a description column stays sane.
    for i, header in enumerate(headers, start=1):
        longest = max(
            [len(str(header))] + [len(str(r[i - 1])) for r in rows if r[i - 1] is not None] or [10]
        )
        ws.column_dimensions[get_column_letter(i)].width = min(max(longest + 2, 9), 46)


def character_rows(units: list[Unit]) -> tuple[list[str], list[list]]:
    headers = [
        "Unit", "Base ID", "Family", "Stars", "Level", "Gear", "Relic",
        "Power", "Mods equipped",
    ]
    for stat in TRACKED_STATS:
        headers += [f"{stat} (base)", f"{stat} (mods)", f"{stat} (total)"]

    rows: list[list] = []
    for u in units:
        row: list = [
            display_name(u.base_id), u.base_id, families_of(u.base_id),
            u.stars, u.level, u.gear_level, u.relic_level, u.power, len(u.mods),
        ]
        for stat in TRACKED_STATS:
            base = base_stat(u.base_id, stat)
            mods = mod_stat(u, stat)
            row += [base, mods, None if base is None else round(base + mods, 2)]
        rows.append(row)
    rows.sort(key=lambda r: (-r[6], -r[5], r[0]))  # relic, then gear, then name
    return headers, rows


def ability_rows(units: list[Unit]) -> tuple[list[str], list[list]]:
    headers = [
        "Unit", "Ability", "Type", "Tier", "Max tier", "Zeta", "Omicron",
        "Zeta learned", "Omicron learned", "Description",
    ]
    defs = ability_defs()
    rows: list[list] = []
    for u in units:
        for a in abilities_of(u.base_id):
            raw = u.skills.get(a.get("i", ""))
            if raw is None:
                continue  # not on this unit's kit / not unlocked
            # Comlink reports tiers below the in-game scale the rules use.
            tier = raw + COMLINK_TIER_OFFSET
            defn = defs.get(a.get("i", ""))
            zeta = bool(a.get("z"))
            omicron = bool(a.get("o"))
            rows.append([
                display_name(u.base_id),
                a.get("n", ""),
                a.get("k", ""),
                tier,
                a.get("m") or (defn or {}).get("max"),
                "Yes" if zeta else "",
                "Yes" if omicron else "",
                ("Yes" if is_zeta_learned(defn, tier) else "No") if (defn and zeta) else "",
                ("Yes" if is_omicron_learned(defn, tier) else "No") if (defn and omicron) else "",
                a.get("d", ""),
            ])
    rows.sort(key=lambda r: (r[0], r[2], r[1]))
    return headers, rows


def mod_rows(units: list[Unit]) -> tuple[list[str], list[list]]:
    headers = [
        "Unit", "Slot", "Set", "Dots", "Level", "Tier",
        "Primary", "Primary value", "Speed from mod",
    ]
    for i in range(1, MAX_SECONDARIES + 1):
        headers += [f"Secondary {i}", f"Value {i}", f"Rolls {i}"]

    rows: list[list] = []
    for u in units:
        for m in u.mods:
            row: list = [
                display_name(u.base_id), m.slot_name, m.set_name, m.rarity,
                m.level, m.tier, m.primary_name, m.primary_value, m.speed,
            ]
            for i in range(MAX_SECONDARIES):
                if i < len(m.secondaries):
                    sec = m.secondaries[i]
                    row += [sec.name, sec.value, sec.rolls]
                else:
                    row += [None, None, None]
            rows.append(row)
    rows.sort(key=lambda r: (r[0], r[1]))
    return headers, rows


def write_summary(ws, headers: list[str], char_count: int) -> None:
    """Totals as formulas, so they follow any edit or filter on Characters.

    Column letters are derived from the headers rather than written by hand — a
    stat added to TRACKED_STATS shifts every column after it, and a formula
    pointing one column off still recalculates cleanly while reporting the wrong
    number.
    """
    last = char_count + 1  # header occupies row 1

    def col(name: str) -> str:
        return get_column_letter(headers.index(name) + 1)

    base_id, stars, gear, relic = col("Base ID"), col("Stars"), col("Gear"), col("Relic")
    mods, spd_mods, spd_total = col("Mods equipped"), col("Speed (mods)"), col("Speed (total)")

    ws["A1"] = "Roster summary"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = "Every figure below is a formula over the Characters sheet."
    ws["A2"].font = Font(name=FONT, italic=True, size=9)

    entries = [
        ("Characters", f"=COUNTA(Characters!{base_id}2:{base_id}{last})"),
        ("Relic 5+", f'=COUNTIF(Characters!{relic}2:{relic}{last},">=5")'),
        ("Relic 3+ (Conquest trial entry)", f'=COUNTIF(Characters!{relic}2:{relic}{last},">=3")'),
        ("7-star", f"=COUNTIF(Characters!{stars}2:{stars}{last},7)"),
        ("Gear 13", f"=COUNTIF(Characters!{gear}2:{gear}{last},13)"),
        ("Average relic", f"=ROUND(AVERAGE(Characters!{relic}2:{relic}{last}),2)"),
        ("Units missing mods", f'=COUNTIF(Characters!{mods}2:{mods}{last},"<6")'),
        ("Units with no mods at all", f"=COUNTIF(Characters!{mods}2:{mods}{last},0)"),
        ("Total mods equipped", f"=SUM(Characters!{mods}2:{mods}{last})"),
        ("Best Speed total", f"=MAX(Characters!{spd_total}2:{spd_total}{last})"),
        (
            "Average Speed from mods",
            f"=ROUND(AVERAGE(Characters!{spd_mods}2:{spd_mods}{last}),1)",
        ),
    ]
    for i, (label, formula) in enumerate(entries, start=4):
        ws[f"A{i}"] = label
        ws[f"A{i}"].font = BODY_FONT
        ws[f"B{i}"] = formula
        ws[f"B{i}"].font = BODY_FONT
    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["B"].width = 14


def flag_missing_base_stats(ws, headers: list[str], rows: list[list]) -> None:
    """Shade base-stat cells the export couldn't fill, so blanks read as
    'not covered' rather than 'zero'."""
    for col, header in enumerate(headers, start=1):
        if not header.endswith("(base)"):
            continue
        for r, row in enumerate(rows, start=2):
            if row[col - 1] is None:
                ws.cell(row=r, column=col).fill = MISSING_FILL


def build(player: Player, out: Path) -> None:
    units = sorted(
        (u for u in player.units if not is_ship(u.base_id)),
        key=lambda u: display_name(u.base_id),
    )

    wb = Workbook()
    summary = wb.active
    summary.title = "Summary"

    ch_headers, ch_rows = character_rows(units)
    ws = wb.create_sheet("Characters")
    write_sheet(ws, ch_headers, ch_rows)
    flag_missing_base_stats(ws, ch_headers, ch_rows)

    ab_headers, ab_rows = ability_rows(units)
    write_sheet(wb.create_sheet("Abilities"), ab_headers, ab_rows)

    md_headers, md_rows = mod_rows(units)
    write_sheet(wb.create_sheet("Mods"), md_headers, md_rows)

    write_summary(summary, ch_headers, len(ch_rows))

    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    print(f"wrote {out}")
    print(f"  Characters {len(ch_rows)}   Abilities {len(ab_rows)}   Mods {len(md_rows)}")
    uncovered = sum(1 for r in ch_rows if r[9] is None)
    if uncovered:
        print(
            f"  note: {uncovered} characters have no base stats (shaded) — refresh them with "
            "scripts/refresh_base_stats.py"
        )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ally-code", default=None, help="defaults to SWGOH_ALLY_CODE")
    ap.add_argument("--comlink", default=None, help="Comlink URL (overrides SWGOH_COMLINK_URL)")
    ap.add_argument("--out", default="roster.xlsx", type=Path)
    args = ap.parse_args()

    if args.comlink:
        os.environ["SWGOH_COMLINK_URL"] = args.comlink
        os.environ.setdefault("SWGOH_DATA_SOURCE", "comlink")

    from swgoh.service import SwgohService

    player = SwgohService().get_player(args.ally_code)
    print(f"{player.name} ({player.ally_code}): {len(player.units)} roster entries")
    build(player, args.out)


if __name__ == "__main__":
    main()
