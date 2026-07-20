"""FastAPI app serving the SWGOH dashboard."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from ..config import get_settings
from ..service import SwgohService

_HERE = Path(__file__).parent
templates = Jinja2Templates(directory=str(_HERE / "templates"))

app = FastAPI(title="SWGOH Recommendations")


def _service() -> SwgohService:
    return SwgohService()


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, ally_code: str | None = Query(default=None)) -> HTMLResponse:
    settings = get_settings()
    code = ally_code or settings.ally_code
    if not code:
        return templates.TemplateResponse(
            request, "setup.html", {"data_source": settings.data_source}
        )
    try:
        report = _service().mod_report(code)
    except Exception as exc:  # surface fetch/parse errors in the UI
        return templates.TemplateResponse(
            request,
            "error.html",
            {"ally_code": code, "error": str(exc)},
            status_code=502,
        )
    return templates.TemplateResponse(
        request, "dashboard.html", {"report": report, "ally_code": code}
    )


@app.get("/fleet", response_class=HTMLResponse)
def fleet(request: Request, ally_code: str | None = Query(default=None)) -> HTMLResponse:
    settings = get_settings()
    code = ally_code or settings.ally_code
    if not code:
        return templates.TemplateResponse(
            request, "setup.html", {"data_source": settings.data_source}
        )
    try:
        report = _service().fleet_report(code)
    except Exception as exc:
        return templates.TemplateResponse(
            request, "error.html", {"ally_code": code, "error": str(exc)}, status_code=502
        )
    return templates.TemplateResponse(
        request, "fleet.html", {"report": report, "ally_code": code}
    )


@app.get("/api/fleet")
def api_fleet(ally_code: str | None = Query(default=None)) -> JSONResponse:
    report = _service().fleet_report(ally_code)

    def plan_json(p):
        return {
            "faction": p.faction,
            "capital": p.capital.name,
            "score": round(p.score, 1),
            "ships": [s.name for s in p.ships],
            "objectives": [
                {"kind": o.kind, "detail": o.detail, "priority": round(o.priority, 1)}
                for o in p.objectives
            ],
        }

    return JSONResponse(
        {
            "player": report.player_name,
            "ally_code": report.ally_code,
            "owned_ships": report.owned_ships,
            "owned_capitals": report.owned_capitals,
            "best": plan_json(report.best) if report.best else None,
            "alternatives": [plan_json(p) for p in report.alternatives],
        }
    )


@app.get("/api/mods")
def api_mods(ally_code: str | None = Query(default=None)) -> JSONResponse:
    report = _service().mod_report(ally_code)
    return JSONResponse(
        {
            "player": report.player_name,
            "ally_code": report.ally_code,
            "totals": {
                "mods": report.total_mods,
                "unleveled": report.unleveled_mods,
                "low_rarity": report.low_rarity_mods,
            },
            "units": [
                {
                    "base_id": r.unit.base_id,
                    "name": r.unit.name,
                    "is_priority": r.is_priority,
                    "score": round(r.score, 1),
                    "total_speed": r.total_speed,
                    "issues": [
                        {"kind": i.kind, "detail": i.detail, "severity": i.severity}
                        for i in r.issues
                    ],
                }
                for r in report.unit_reports
            ],
        }
    )


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


def main() -> None:
    import os

    import uvicorn

    settings = get_settings()
    host = os.getenv("SWGOH_WEB_HOST", "127.0.0.1")
    port = int(os.getenv("SWGOH_WEB_PORT", "8000"))
    print(f"SWGOH dashboard starting (source={settings.data_source}).")
    print(f"Open http://{host}:{port}")
    uvicorn.run("swgoh.web.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
