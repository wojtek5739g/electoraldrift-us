"""ElectoralDrift US - serving API (Milestone 3, step 1).

Currently serves only the certified 2024 presidential results for North Carolina,
read from a prepared GeoJSON file. Later steps will read from PostgreSQL/PostGIS
(live predictions, scenarios, overlays); those endpoints are declared in /api/features
so the UI can show them as "coming soon".
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import simulation as sim

ASSETS = Path(os.getenv("EDUS_ASSETS", Path(__file__).parent / "assets"))
AVAILABLE = {("NC", 2024): "nc_2024_counties.geojson"}

app = FastAPI(title="ElectoralDrift US API", version="0.3.0", root_path=os.getenv("ROOT_PATH", ""))
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@lru_cache(maxsize=8)
def _load(filename: str) -> dict:
    path = ASSETS / filename
    if not path.exists():
        raise HTTPException(503, f"Data file {filename} not deployed")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "datasets": [f"{s}-{y}" for s, y in AVAILABLE]}


@app.get("/api/results/{year}/{state}/counties")
def county_results(year: int, state: str) -> dict:
    """County polygons with 2024 presidential results as GeoJSON properties."""
    key = (state.upper(), year)
    if key not in AVAILABLE:
        raise HTTPException(404, f"No results for {state.upper()} {year} yet")
    return _load(AVAILABLE[key])


@app.get("/api/results/{year}/{state}/summary")
def state_summary(year: int, state: str) -> dict:
    data = county_results(year, state)
    tot = {"dem": 0, "rep": 0, "other": 0, "total": 0}
    for f in data["features"]:
        for k in tot:
            tot[k] += f["properties"].get(k) or 0
    two = tot["dem"] + tot["rep"]
    return {**tot, "state": state.upper(), "year": year,
            "margin_pp": round((tot["rep"] - tot["dem"]) / two * 100, 2) if two else None,
            "counties": len(data["features"])}


class SimStart(BaseModel):
    session_id: str
    speed: int = 1


class SimSpeed(BaseModel):
    speed: int


def _check_session(sid: str) -> str:
    if not sim.valid_session_id(sid):
        raise HTTPException(400, "session_id must be a UUID")
    return sid.lower()


def _check_speed(speed: int) -> int:
    if speed not in sim.SPEEDS:
        raise HTTPException(400, f"speed must be one of {list(sim.SPEEDS)}")
    return speed


@app.post("/api/sim/start")
def sim_start(body: SimStart, request: Request) -> dict:
    """(Re)start this user's prediction timeline. MOCK: predictions are a random walk."""
    sid = _check_session(body.session_id)
    fwd = request.headers.get("x-forwarded-for", "")
    client = {"ip": fwd.split(",")[0].strip() or (request.client.host if request.client else None),
              "user_agent": request.headers.get("user-agent")}
    return sim.start(sid, _check_speed(body.speed), county_results(2024, "NC")["features"], client)


@app.post("/api/sim/{session_id}/speed")
def sim_speed(session_id: str, body: SimSpeed) -> dict:
    res = sim.set_speed(_check_session(session_id), _check_speed(body.speed))
    if res is None:
        raise HTTPException(404, "No simulation for this session")
    return res


@app.post("/api/sim/{session_id}/stop")
def sim_stop(session_id: str) -> dict:
    res = sim.stop(_check_session(session_id))
    if res is None:
        raise HTTPException(404, "No simulation for this session")
    return res


@app.get("/api/sim/{session_id}")
def sim_state(session_id: str, since: int = -1) -> dict:
    """Timeline points released so far with seq > since, plus timing of the next one."""
    res = sim.state(_check_session(session_id), since)
    if res is None:
        raise HTTPException(404, "No simulation for this session")
    return res


@app.get("/api/features")
def features() -> list[dict]:
    """Feature flags shown in the UI. Only enabled ones are clickable."""
    return [
        {"id": "results_2024", "label": "2024 results by county", "enabled": True},
        {"id": "live_predictions", "label": "Live model predictions (every 60 s) - mock data", "enabled": True},
        {"id": "scenario_sliders", "label": "Scenario sliders (weather, unemployment)", "enabled": False},
        {"id": "nws_alerts", "label": "NWS weather alerts overlay", "enabled": False},
        {"id": "faa_status", "label": "FAA airport status overlay", "enabled": False},
        {"id": "nc_absentee", "label": "NC early & mail ballot model", "enabled": False},
        {"id": "history", "label": "Historical elections 2000-2020", "enabled": False},
        {"id": "all_states", "label": "All states + 270 EV bar", "enabled": False},
        {"id": "disinfo", "label": "Disinformation signals", "enabled": False},
    ]
