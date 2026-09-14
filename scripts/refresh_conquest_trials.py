#!/usr/bin/env python3
"""Regenerate src/swgoh/data/conquest_trials.json (Proving Grounds briefings).

Each Conquest Proving Grounds trial carries a Global and/or Enemy Modifier whose
text *is* the puzzle — it tells you what the enemy team does and therefore what
beats it. The game ships that text in its localization bundle, so we pull it from
a running Comlink instance rather than transcribing it by hand.

Usage:
    python scripts/refresh_conquest_trials.py [comlink_url | Loc_ENG_US.txt]

Defaults to http://localhost:3200. The localization bundle is ~45 MB and Comlink
buffers it in memory, which can OOM a small VM — if the fetch keeps dropping,
save the bundle once and pass the extracted Loc_ENG_US.txt path instead.

Run it when a new Conquest volume adds trials.
"""
from __future__ import annotations

import base64
import io
import json
import re
import sys
import zipfile
from pathlib import Path

import httpx

ARG = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:3200"
BASE = ARG.rstrip("/")
OUT = Path(__file__).resolve().parents[1] / "src" / "swgoh" / "data" / "conquest_trials.json"

# Base-tier trials only. Keys are inconsistent in the game data: the Pass+ twin
# is spelled "01+_DESC" on early trials and "08_PLUS_DESC" later (with one
# "14_PLUS_DES" typo), and a revised trial gets a "_V2" suffix — so match the
# plain number plus an optional version, and keep the highest version seen.
KEY_RE = re.compile(r"^CONQUEST_UNIT_TRIALS_MISSION_(\d+)_DESC(?:_V(\d+))?$")
# The unit whose shards the trial awards, e.g. CONQUEST_UNIT_TRIALS_ENV_01|RAZOR CREST.
# Authoritative where present; older trials don't name the reward in their tips.
ENV_RE = re.compile(r"^CONQUEST_UNIT_TRIALS_ENV_(\d+)$")
# "Enemy Modifier (Pirate's Plunder): Whenever a Pirate ally ..."
MODIFIER_RE = re.compile(r"^(Global|Enemy) Modifier \(([^)]+)\):\s*(.+)$", re.S)
# Trailing stack/effect definitions: "Endless Ranks: When defeated, ..."
EFFECT_RE = re.compile(r"^([A-Z][A-Za-z' \-]{2,40}):\s*(.+)$", re.S)
REWARD_RE = re.compile(r"Earn (.+?) shards", re.I)
OPPONENT_RE = re.compile(
    r"(?:fighting against|[Ff]ace off against) (.+?)"
    r"(?:\s+(?:in this|in a|in the|on the|and a|deep within|within)\b|[.,;]|$)"
)


def strip_tags(text: str) -> str:
    """Drop the game's [c][FFFF33]...[-][/c] colour markup and unescape newlines."""
    return re.sub(r"\[[-/]?[a-zA-Z0-9#]*\]", "", text.replace("\\n", "\n"))


# Tokens that shouldn't be Capitalized when re-casing an ALL CAPS unit name.
LOWER_WORDS = {"of", "the", "and", "a"}
ACRONYMS = {"TIE", "SM", "AT", "BB", "R2", "C3PO", "K2"}


def smart_title(text: str) -> str:
    """Re-case an ALL CAPS unit name ("TIE INTERCEPTOR" -> "TIE Interceptor")."""
    words = []
    for i, word in enumerate(text.split()):
        head = word.split("-")[0].strip(",")
        if head.upper() in ACRONYMS:
            words.append(word.upper())
        elif i and word.lower() in LOWER_WORDS:
            words.append(word.lower())
        else:
            words.append(word.title())
    return " ".join(words)


def fetch_localization(retries: int = 3) -> bytes:
    """Read the English localization file from a local path, or download it.

    The bundle is ~45 MB and Comlink buffers the whole thing, which can OOM a
    small VM mid-transfer — so retry, and let the caller supply a saved copy.
    """
    local = Path(ARG).expanduser()
    if local.is_file():
        print(f"reading {local}")
        return local.read_bytes()

    for attempt in range(1, retries + 1):
        print(f"fetching localization bundle (attempt {attempt}/{retries})...")
        try:
            meta = httpx.post(f"{BASE}/metadata", json={"payload": {}}, timeout=60).json()
            loc_version = meta["latestLocalizationBundleVersion"]
            bundle = httpx.post(
                f"{BASE}/localization",
                json={"payload": {"id": loc_version}, "unzip": False},
                timeout=300,
            ).json()
        except httpx.HTTPError as exc:
            if attempt == retries:
                raise
            print(f"  {type(exc).__name__}: {exc} — retrying")
            continue
        zf = zipfile.ZipFile(io.BytesIO(base64.b64decode(bundle["localizationBundle"])))
        eng_file = next(n for n in zf.namelist() if "ENG" in n.upper())
        return zf.read(eng_file)
    raise RuntimeError("unreachable")


def tidy_opponent(name: str) -> str:
    """Trim the prose around an opponent so it reads as a name in a menu."""
    name = " ".join(name.split()).strip()
    name = re.sub(r"^(?:the|a|an)\s+", "", name, flags=re.I)
    return name


def parse_trial(number: int, raw: str) -> dict:
    text = strip_tags(raw)
    blocks = [b.strip() for b in text.split("\n\n") if b.strip()]

    tips: list[str] = []
    modifiers: list[dict] = []
    effects: list[dict] = []
    for block in blocks:
        if block.startswith("Strategy Tips:"):
            tips = [
                line.lstrip("- ").strip()
                for line in block.splitlines()[1:]
                if line.strip().lstrip("- ")
            ]
            continue
        m = MODIFIER_RE.match(block)
        if m:
            modifiers.append(
                {"scope": m.group(1), "name": m.group(2).strip(), "text": " ".join(m.group(3).split())}
            )
            continue
        # Anything else shaped "Name: text" after the modifiers defines a stack
        # or status the modifier refers to.
        if modifiers:
            e = EFFECT_RE.match(block)
            if e:
                effects.append({"name": e.group(1).strip(), "text": " ".join(e.group(2).split())})

    # Match within a single tip: tips run together into unrelated sentences
    # ("...Phoenix Squadron" + "Phoenix Squadron enemies are immune to Fear").
    reward = next((m for m in (REWARD_RE.search(t) for t in tips) if m), None)
    opponent = next((m for m in (OPPONENT_RE.search(t) for t in tips) if m), None)
    return {
        "number": number,
        "reward_unit": reward.group(1).strip() if reward else "",
        "opponent": tidy_opponent(opponent.group(1)) if opponent else "",
        "tips": tips,
        "modifiers": modifiers,
        "effects": effects,
    }


def main() -> None:
    best: dict[int, tuple[int, str]] = {}
    envs: dict[int, str] = {}
    for line in fetch_localization().decode("utf-8", "replace").split("\n"):
        key, _, value = line.partition("|")
        key = key.strip()
        m = KEY_RE.match(key)
        if m:
            number, version = int(m.group(1)), int(m.group(2) or 1)
            if version >= best.get(number, (0, ""))[0]:
                best[number] = (version, value)
            continue
        e = ENV_RE.match(key)
        if e:
            envs[int(e.group(1))] = smart_title(value.strip())

    trials = [parse_trial(n, raw) for n, (_, raw) in sorted(best.items())]
    for t in trials:
        # Prefer the name as written in the tips ("SM-33") — the ENV string is
        # ALL CAPS, so its re-casing is a guess. ENV covers the older trials
        # whose tips don't name the reward at all.
        t["reward_unit"] = t["reward_unit"] or envs.get(t["number"], "")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(trials, indent=1, ensure_ascii=False), encoding="utf-8")
    mods = sum(len(t["modifiers"]) for t in trials)
    print(f"wrote {len(trials)} trials ({mods} modifiers) to {OUT}")


if __name__ == "__main__":
    main()
