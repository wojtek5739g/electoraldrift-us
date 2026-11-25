"""Per-user prediction timeline - MOCK implementation.

Each browser gets its own random session id (UUID, kept in localStorage) and sends it
with every call. That id is the key; the client IP and User-Agent are only recorded
next to it, because one IP can hide many users (campus NAT, proxies) and one user's IP
can change mid-session.

On "Start Simulation" we pre-compute a baseline (seq 0 = certified 2024 results) plus
POINTS further predictions, one every INTERVAL_S seconds of simulated time. A point is
released to the client once its time has come; `speed` (1x/10x/60x) compresses
real time for demos. Timestamps always sit on the 60 s grid of simulated time.

LATER: replace `_mock_points` with reads of real model output (PostgreSQL), keeping the
response shape, and drop the in-memory store.
"""
from __future__ import annotations

import math
import random
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

POINTS = 30          # predictions after the baseline
INTERVAL_S = 60      # simulated seconds between predictions
SPEEDS = (1, 10, 60)
MAX_SESSIONS = 500
SESSION_TTL_S = 6 * 3600

# Mock random-walk tuning (pp = percentage points of two-party margin).
SWING_PHI, SWING_SIGMA = 0.97, 1.5     # persistence / step noise of statewide swing (pp)
COUNTY_PHI, COUNTY_SIGMA = 0.9, 2.0    # same, per county
MOMENTUM = 0.5                         # share of last step's swing change carried forward
SHOCK_P, SHOCK_PP = 0.12, 6.0          # chance per step of a big statewide event, and its size
POLAR_SIGMA = 1.0                      # urban/rural divergence: safe seats get safer (or converge)
TURNOUT_SIGMA, TURNOUT_MAX = 0.008, 0.08

_lock = threading.Lock()
_sessions: dict[str, dict] = {}


def valid_session_id(sid: str) -> bool:
    try:
        return str(uuid.UUID(sid)) == sid.lower()
    except (ValueError, AttributeError):
        return False


def _county_row(dem: int, rep: int, other: int) -> dict:
    two = dem + rep
    return {"dem": dem, "rep": rep, "other": other, "total": dem + rep + other,
            "margin_pp": round((rep - dem) / two * 100, 2) if two else None}


def _summary(counties: dict) -> dict:
    dem = sum(c["dem"] for c in counties.values())
    rep = sum(c["rep"] for c in counties.values())
    other = sum(c["other"] for c in counties.values())
    return _county_row(dem, rep, other)


def _mock_points(base_features: list[dict], seed: str, t0: datetime) -> list[dict]:
    """Random walk around the certified results: statewide swing with momentum and shocks,
    county noise, polarization (lean-correlated) and turnout drift."""
    rng = random.Random(seed)
    base = {f["properties"]["fips"]: f["properties"] for f in base_features}
    swing = 0.0
    last_d_swing = 0.0
    county_drift = {k: 0.0 for k in base}
    turnout = {k: 0.0 for k in base}

    points = []
    for seq in range(POINTS + 1):
        if seq > 0:
            shock = rng.choice((-1, 1)) * rng.uniform(0.5, 1) * SHOCK_PP if rng.random() < SHOCK_P else 0.0
            d_swing = MOMENTUM * last_d_swing + rng.gauss(0, SWING_SIGMA) + shock
            swing = SWING_PHI * swing + d_swing
            last_d_swing = d_swing
            polar = rng.gauss(0, POLAR_SIGMA)  # >0: R counties get redder and D counties bluer
            for k, p in base.items():
                lean = max(-1, min(1, (p["margin_pp"] or 0) / 40))
                county_drift[k] = COUNTY_PHI * county_drift[k] + rng.gauss(0, COUNTY_SIGMA) + polar * lean
                turnout[k] = max(-TURNOUT_MAX, min(TURNOUT_MAX, turnout[k] + rng.gauss(0, TURNOUT_SIGMA)))
        counties = {}
        for k, p in base.items():
            if seq == 0:  # baseline = exact certified counts
                counties[k] = _county_row(p["dem"] or 0, p["rep"] or 0, p["other"] or 0)
                continue
            other_share = (p["other"] or 0) / p["total"] if p["total"] else 0
            total = round(p["total"] * (1 + turnout[k]))
            other = round(total * other_share)
            two = total - other
            m = max(-98.0, min(98.0, (p["margin_pp"] or 0) + swing + county_drift[k]))
            rep = round(two * (1 + m / 100) / 2)
            counties[k] = _county_row(two - rep, rep, other)
        points.append({
            "seq": seq,
            "ts": (t0 + timedelta(seconds=seq * INTERVAL_S)).isoformat().replace("+00:00", "Z"),
            "kind": "baseline" if seq == 0 else "prediction",
            "summary": _summary(counties),
            "counties": counties,
        })
    return points


def _progress(s: dict, now: float) -> float:
    """How many intervals of simulated time have elapsed (frozen once stopped)."""
    if s["stopped"]:
        return s["anchor_progress"]
    return s["anchor_progress"] + (now - s["anchor_real"]) * s["speed"] / INTERVAL_S


def _prune(now: float) -> None:
    for sid in [k for k, s in _sessions.items() if now - s["created_real"] > SESSION_TTL_S]:
        del _sessions[sid]
    while len(_sessions) >= MAX_SESSIONS:
        del _sessions[min(_sessions, key=lambda k: _sessions[k]["created_real"])]


def start(sid: str, speed: int, base_features: list[dict], client: dict) -> dict:
    now = time.time()
    t0 = datetime.now(timezone.utc).replace(microsecond=0)
    with _lock:
        _prune(now)
        _sessions[sid] = {
            "created_real": now, "anchor_real": now, "anchor_progress": 0.0, "speed": speed, "stopped": False,
            "started_at": t0.isoformat().replace("+00:00", "Z"), "client": client,
            "points": _mock_points(base_features, f"{sid}:{now}", t0),
        }
        return _state(sid, since=-1, now=now)


def set_speed(sid: str, speed: int) -> dict | None:
    now = time.time()
    with _lock:
        s = _sessions.get(sid)
        if s is None:
            return None
        s["anchor_progress"], s["anchor_real"], s["speed"] = _progress(s, now), now, speed
        return _state(sid, since=10**9, now=now)


def stop(sid: str) -> dict | None:
    """Freeze the timeline at the points already released; Start creates a new one."""
    now = time.time()
    with _lock:
        s = _sessions.get(sid)
        if s is None:
            return None
        if not s["stopped"]:
            s["anchor_progress"], s["anchor_real"], s["stopped"] = math.floor(_progress(s, now)), now, True
        return _state(sid, since=10**9, now=now)


def state(sid: str, since: int) -> dict | None:
    with _lock:
        return _state(sid, since, time.time()) if sid in _sessions else None


def _state(sid: str, since: int, now: float) -> dict:
    s = _sessions[sid]
    prog = _progress(s, now)
    released = min(POINTS + 1, 1 + math.floor(prog))
    done = released >= POINTS + 1 or s["stopped"]
    next_in = None if done else (math.floor(prog) + 1 - prog) * INTERVAL_S / s["speed"]
    return {
        "session_id": sid, "started_at": s["started_at"], "interval_s": INTERVAL_S,
        "speed": s["speed"], "speeds": list(SPEEDS), "total_points": POINTS + 1,
        "released": released, "done": done, "stopped": s["stopped"],
        "next_in_s": None if next_in is None else round(next_in, 3),
        "points": [p for p in s["points"][:released] if p["seq"] > since],
    }
