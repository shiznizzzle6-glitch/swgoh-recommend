"""FastAPI app serving the SWGOH dashboard."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from ..config import get_settings
from ..service import SwgohService
from .charts import rank_trend_svg

_HERE = Path(__file__).parent
templates = Jinja2Templates(directory=str(_HERE / "templates"))

app = FastAPI(title="SWGOH Recommendations")


def _service() -> SwgohService:
    return SwgohService()


@app.get("/", response_class=HTMLResponse)
def tonight(request: Request, ally_code: str | None = Query(default=None)) -> HTMLResponse:
    settings = get_settings()
    code = ally_code or settings.ally_code
    if not code:
        return templates.TemplateResponse(
            request, "setup.html", {"data_source": settings.data_source}
        )
    try:
        plan, arena = _service().landing(code)
    except Exception as exc:
        return templates.TemplateResponse(
            request, "error.html", {"ally_code": code, "error": str(exc)}, status_code=502
        )
    return templates.TemplateResponse(
        request,
        "tonight.html",
        {
            "plan": plan,
            "arena": arena,
            "ally_code": code,
            "squad_chart": rank_trend_svg(arena.history, "squad_rank"),
            "fleet_chart": rank_trend_svg(arena.history, "fleet_rank"),
        },
    )


@app.get("/mods", response_class=HTMLResponse)
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


@app.get("/api/tonight")
def api_tonight(ally_code: str | None = Query(default=None)) -> JSONResponse:
    plan = _service().tonight_plan(ally_code)
    return JSONResponse(
        {
            "player": plan.player_name,
            "ally_code": plan.ally_code,
            "units": [
                {
                    "base_id": u.base_id,
                    "name": u.name,
                    "score": u.score,
                    "headline": u.headline,
                    "kind": u.primary_kind,
                    "sources": u.sources,
                }
                for u in plan.units
            ],
        }
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


@app.get("/squads", response_class=HTMLResponse)
def squads(request: Request, ally_code: str | None = Query(default=None)) -> HTMLResponse:
    settings = get_settings()
    code = ally_code or settings.ally_code
    if not code:
        return templates.TemplateResponse(
            request, "setup.html", {"data_source": settings.data_source}
        )
    try:
        report = _service().squad_report(code)
    except Exception as exc:
        return templates.TemplateResponse(
            request, "error.html", {"ally_code": code, "error": str(exc)}, status_code=502
        )
    return templates.TemplateResponse(
        request, "squads.html", {"report": report, "ally_code": code}
    )


@app.get("/defense", response_class=HTMLResponse)
def defense(request: Request, ally_code: str | None = Query(default=None)) -> HTMLResponse:
    settings = get_settings()
    code = ally_code or settings.ally_code
    if not code:
        return templates.TemplateResponse(
            request, "setup.html", {"data_source": settings.data_source}
        )
    try:
        report = _service().defense_report(code)
    except Exception as exc:
        return templates.TemplateResponse(
            request, "error.html", {"ally_code": code, "error": str(exc)}, status_code=502
        )
    return templates.TemplateResponse(
        request, "defense.html", {"report": report, "ally_code": code}
    )


@app.get("/zetas", response_class=HTMLResponse)
def zetas(request: Request, ally_code: str | None = Query(default=None)) -> HTMLResponse:
    settings = get_settings()
    code = ally_code or settings.ally_code
    if not code:
        return templates.TemplateResponse(
            request, "setup.html", {"data_source": settings.data_source}
        )
    try:
        report = _service().zeta_report(code)
    except Exception as exc:
        return templates.TemplateResponse(
            request, "error.html", {"ally_code": code, "error": str(exc)}, status_code=502
        )
    return templates.TemplateResponse(
        request, "zetas.html", {"report": report, "ally_code": code}
    )


@app.get("/api/zetas")
def api_zetas(ally_code: str | None = Query(default=None)) -> JSONResponse:
    report = _service().zeta_report(ally_code)

    def t_json(t):
        return {
            "base_id": t.base_id,
            "unit_name": t.unit_name,
            "ability_id": t.ability_id,
            "ability_name": t.ability_name,
            "kind": t.kind,
            "modes": t.modes,
            "goals": t.goals,
            "roles": t.roles,
            "priority": t.priority,
            "current_tier": t.current_tier,
            "max_tier": t.max_tier,
        }

    return JSONResponse(
        {
            "player": report.player_name,
            "ally_code": report.ally_code,
            "zetas": [t_json(t) for t in report.zetas],
            "omicrons": [t_json(t) for t in report.omicrons],
            "other_zetas": report.other_zetas,
            "other_omicrons": report.other_omicrons,
        }
    )


@app.get("/relics", response_class=HTMLResponse)
def relics(request: Request, ally_code: str | None = Query(default=None)) -> HTMLResponse:
    settings = get_settings()
    code = ally_code or settings.ally_code
    if not code:
        return templates.TemplateResponse(
            request, "setup.html", {"data_source": settings.data_source}
        )
    try:
        report = _service().relic_report(code)
    except Exception as exc:
        return templates.TemplateResponse(
            request, "error.html", {"ally_code": code, "error": str(exc)}, status_code=502
        )
    return templates.TemplateResponse(
        request, "relics.html", {"report": report, "ally_code": code}
    )


@app.get("/api/relics")
def api_relics(ally_code: str | None = Query(default=None)) -> JSONResponse:
    report = _service().relic_report(ally_code)

    def t_json(t):
        return {
            "base_id": t.base_id,
            "name": t.name,
            "relic_level": t.relic_level,
            "roles": t.roles,
            "goals": t.goals,
            "priority": t.priority,
            "note": t.note,
        }

    return JSONResponse(
        {
            "player": report.player_name,
            "ally_code": report.ally_code,
            "eligible_count": report.eligible_count,
            "eligible": [t_json(t) for t in report.eligible],
            "others": [t_json(t) for t in report.others],
        }
    )


@app.get("/energy", response_class=HTMLResponse)
def energy(request: Request, ally_code: str | None = Query(default=None)) -> HTMLResponse:
    settings = get_settings()
    code = ally_code or settings.ally_code
    if not code:
        return templates.TemplateResponse(
            request, "setup.html", {"data_source": settings.data_source}
        )
    try:
        report = _service().energy_report(code)
    except Exception as exc:
        return templates.TemplateResponse(
            request, "error.html", {"ally_code": code, "error": str(exc)}, status_code=502
        )
    return templates.TemplateResponse(
        request, "energy.html", {"report": report, "ally_code": code}
    )


@app.get("/api/energy")
def api_energy(ally_code: str | None = Query(default=None)) -> JSONResponse:
    report = _service().energy_report(ally_code)

    def t_json(t):
        return {
            "base_id": t.base_id,
            "name": t.name,
            "action": t.action,
            "action_label": t.action_label,
            "goals": t.goals,
            "priority": t.priority,
            "energy": t.energy,
            "node": t.node,
            "verify": t.verify,
        }

    return JSONResponse(
        {
            "player": report.player_name,
            "ally_code": report.ally_code,
            "cantina": [t_json(t) for t in report.cantina],
            "other": [t_json(t) for t in report.other],
            "unmapped": [t_json(t) for t in report.unmapped],
        }
    )


@app.get("/api/defense")
def api_defense(ally_code: str | None = Query(default=None)) -> JSONResponse:
    report = _service().defense_report(ally_code)

    def wall_json(w):
        return {
            "base_id": w.base_id,
            "name": w.name,
            "owned": w.owned,
            "wall_score": w.wall_score,
            "stars": w.stars,
            "gear_level": w.gear_level,
            "relic_level": w.relic_level,
        }

    def team_json(t):
        return {
            "name": t.name,
            "tier": t.tier,
            "tags": t.tags,
            "status": t.status,
            "rating": t.rating,
            "anchor": t.anchor,
            "members": [wall_json(m) for m in t.members],
            "objectives": [
                {"kind": o.kind, "detail": o.detail, "priority": round(o.priority, 1)}
                for o in t.objectives
            ],
        }

    return JSONResponse(
        {
            "player": report.player_name,
            "ally_code": report.ally_code,
            "current_defense": [wall_json(w) for w in report.current_defense],
            "current_rating": report.current_rating,
            "bench": [wall_json(w) for w in report.bench],
            "recommended": team_json(report.recommended) if report.recommended else None,
            "teams": [team_json(t) for t in report.teams],
        }
    )


@app.get("/api/arena")
def api_arena(ally_code: str | None = Query(default=None)) -> JSONResponse:
    status = _service().arena_status(ally_code)
    return JSONResponse(
        {
            "squad_rank": status.squad_rank,
            "fleet_rank": status.fleet_rank,
            "squad_change": status.squad_change,
            "fleet_change": status.fleet_change,
            "history": [
                {"ts": s.ts, "squad_rank": s.squad_rank, "fleet_rank": s.fleet_rank}
                for s in status.history
            ],
        }
    )


@app.get("/api/squads")
def api_squads(ally_code: str | None = Query(default=None)) -> JSONResponse:
    report = _service().squad_report(ally_code)
    return JSONResponse(
        {
            "player": report.player_name,
            "ally_code": report.ally_code,
            "squads": [
                {
                    "name": s.name,
                    "tier": s.tier,
                    "tags": s.tags,
                    "status": s.status,
                    "readiness": s.readiness,
                    "owned": s.owned_count,
                    "size": len(s.members),
                    "objectives": [
                        {"kind": o.kind, "detail": o.detail, "priority": round(o.priority, 1)}
                        for o in s.objectives
                    ],
                }
                for s in report.squads
            ],
        }
    )


@app.get("/api/fleet")
def api_fleet(ally_code: str | None = Query(default=None)) -> JSONResponse:
    report = _service().fleet_report(ally_code)

    def plan_json(p):
        return {
            "name": p.name,
            "tier": p.tier,
            "capital": p.capital.name,
            "readiness": p.readiness,
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
            "recommended": plan_json(report.recommended) if report.recommended else None,
            "other_targets": [plan_json(p) for p in report.other_targets],
            "current_best_ships": [s.name for s in report.current_best_ships],
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
                    "pilot_of": r.pilot_of,
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
