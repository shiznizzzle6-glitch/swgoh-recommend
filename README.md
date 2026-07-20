# SWGOH Recommendations

Pull your **Star Wars: Galaxy of Heroes** roster and generate custom
recommendations. First feature: a **mod analyzer + priority ranking** that flags
objectively-improvable mods (unleveled, sub-5-dot, empty slots, wrong arrow,
wrong sets) and ranks which characters most need work — weighted by how much you
care about them. Served as a web dashboard.

The whole stack (Comlink data service + this web app) is designed to run on a
small headless Linux VM; your laptop is just a browser pointed at it.

## Architecture

```
src/swgoh/
  models.py            # source-agnostic domain models (Player, Unit, Mod, ...)
  config.py            # settings from env / .env
  sources/
    base.py            # DataSource interface
    swgoh_gg.py        # swgoh.gg public API (currently Cloudflare-blocked)
    comlink.py         # swgoh-comlink adapter — the working data path
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

## Run the full stack on a VM (recommended)

On a headless Linux VM with Docker installed (see "VM setup" below), clone this
repo and bring up both services with one command:

```bash
git clone https://github.com/shiznizzzle6-glitch/swgoh-recommend.git
cd swgoh-recommend
docker compose up -d --build
```

This starts:

- **comlink** — the game-data service (internal only by default; also on `:3200`).
- **web** — the dashboard on **`:8000`**, talking to Comlink over the internal
  Docker network. Your ally code is baked in via `docker-compose.yml`.

Then from any browser on your LAN: **`http://<vm-ip>:8000`**. Update later with
`git pull && docker compose up -d --build`.

## Local development

To iterate on the code without Docker:

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # macOS / Linux
pip install -e ".[dev]"

cp .env.example .env              # set SWGOH_DATA_SOURCE + SWGOH_COMLINK_URL
swgoh-web                         # http://127.0.0.1:8000
```

Pass an ally code in the URL (`/?ally_code=123456789`) or type it into the box on
the dashboard. JSON is at `/api/mods?ally_code=123456789`. Bind to all interfaces
with `SWGOH_WEB_HOST=0.0.0.0`.

## Data sources

- **comlink** (recommended): richest data straight from the game servers, and
  **not affected by Cloudflare**. Requires running
  [swgoh-comlink](https://github.com/swgoh-utils/swgoh-comlink) locally (Docker).
  No game credentials needed — your ally code alone is enough.
- **swgoh_gg**: the free public API. **Currently gated by Cloudflare's JS
  challenge**, which returns a 403 to non-browser clients (curl, this app),
  regardless of User-Agent — so it can't be used programmatically right now. The
  adapter detects this and raises a clear error pointing you to Comlink. Kept in
  place in case swgoh.gg reopens programmatic access or you add a browser-based
  fetch. Note the old `api.swgoh.gg` host is dead; the API now lives at
  `https://swgoh.gg/api`.

The Comlink adapter's mod-level decoding (set/slot/rarity from `definitionId`)
is best-effort — validate it against your instance once data is flowing.

## VM setup (Alpine + Docker)

A minimal VM is plenty (1 GB RAM, 1–2 vCPU, 8 GB disk, **bridged** networking).
Alpine "Virtual" edition is the lightest headless option.

1. Install Alpine to disk: boot the ISO, log in as `root`, run `setup-alpine`
   (dhcp networking, enable openssh, disk mode `sys`), then `poweroff` and detach
   the ISO.
2. Install Docker + git + VMware guest tools:
   ```sh
   sed -i '/v3.[0-9]*\/community/s/^#//' /etc/apk/repositories
   apk update
   apk add docker docker-cli-compose git open-vm-tools
   rc-update add docker boot && rc-update add open-vm-tools boot
   service docker start && service open-vm-tools start
   ```
3. Clone this repo and `docker compose up -d --build` (see above).
4. `hostname -i` gives the VM's IP → browse to `http://<vm-ip>:8000`.

Cloning a private repo on the VM will prompt for a GitHub token, or copy the
files in via a VMware shared folder.

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
