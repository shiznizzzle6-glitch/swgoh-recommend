# SWGOH Recommendations

Pull your **Star Wars: Galaxy of Heroes** roster and generate custom
recommendations. First feature: a **mod analyzer + priority ranking** that flags
objectively-improvable mods (unleveled, sub-5-dot, empty slots, wrong arrow,
wrong sets) and ranks which characters most need work — weighted by how much you
care about them. Served as a local web dashboard.

## Architecture

```
src/swgoh/
  models.py            # source-agnostic domain models (Player, Unit, Mod, ...)
  config.py            # settings from env / .env
  sources/
    base.py            # DataSource interface
    swgoh_gg.py        # swgoh.gg public API (no auth) — the default
    comlink.py         # swgoh-comlink adapter (self-hosted, best-effort)
    cache.py           # TTL file cache
  recommend/
    mods.py            # the mod analyzer + ranking
  data/
    priority_characters.yaml   # your editable per-character mod guidance
  service.py           # fetch + analyze
  web/app.py           # FastAPI dashboard
```

The **hybrid data layer**: both sources normalize into `swgoh.models`, so the
analyzer and UI never see raw API payloads. Switch sources with one env var.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # macOS / Linux
pip install -e ".[dev]"

cp .env.example .env              # then edit SWGOH_ALLY_CODE
```

## Run

```bash
swgoh-web
# open http://127.0.0.1:8000
```

Or pass an ally code in the URL: `http://127.0.0.1:8000/?ally_code=123456789`.
JSON is at `/api/mods?ally_code=123456789`.

You can also drive it without setting `.env`; just type your ally code into the
box on the dashboard.

## Data sources

- **swgoh_gg** (default): free public API, no auth. Uses your public swgoh.gg
  profile. Fastest to start.
- **comlink**: richest data straight from game servers, but you must run
  [swgoh-comlink](https://github.com/swgoh-utils/swgoh-comlink). Set
  `SWGOH_DATA_SOURCE=comlink` and `SWGOH_COMLINK_URL`. The adapter is
  best-effort — validate mod-level detail against your instance.

## Customize the recommendations

Edit `src/swgoh/data/priority_characters.yaml` to add characters, adjust weights,
preferred arrow primary, and recommended sets. `base_id` values come from
swgoh.gg. The analyzer's severity weights and thresholds live at the top of
`src/swgoh/recommend/mods.py`.

## Tests

```bash
pytest
```

All tests run offline (no network).

## Roadmap

- Gear & relic priority recommendations
- Squad / counter suggestions (GAC, TW)
- Ship recommendations
- Richer mod scoring (speed rolls, offense-heavy secondaries, slicing advice)
