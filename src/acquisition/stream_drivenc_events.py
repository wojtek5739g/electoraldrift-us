"""DriveNC (NCDOT) - live road events in North Carolina: closures, incidents, road work.

API:    https://www.drivenc.gov/api/v2/get/event?key=<key>&format=json
        A free developer key is REQUIRED (env var DRIVENC_API_KEY; request it on drivenc.gov
        after creating an account). Throttling: 10 calls per 60 s, so one call for the
        whole state every 60 s is well within the limit.
Same API: other state 511 sites use the same /api/v2/get/event interface (e.g. 511wi.gov,
        az511.com). Use --base-url and that site's key to collect another state.
Output: data/bronze/drivenc_events/events_<YYYYmmdd_HHMMSS>.jsonl - one line = one event in one
        poll, with selected fields and county_fips (NC county name -> FIPS).
The live feature for Model 2 is the same as the historical Helene feature: number of road
closures active in a county on a given day (see batch_ncdot_helene.py).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import time
from datetime import datetime, timezone

import pandas as pd

from common import BRONZE, REFERENCE, get_json, get_logger, make_session, now_utc, write_manifest

SOURCE = "drivenc_events"
BASE_URL = "https://www.drivenc.gov"
KEEP = ["ID", "RoadwayName", "DirectionOfTravel", "EventType", "EventSubType", "IsFullClosure",
        "Severity", "County", "Latitude", "Longitude", "StartDate", "PlannedEndDate", "LastUpdated"]
log = get_logger(SOURCE)


class _RedactKey(logging.Filter):
    """Removes the API key from log messages (it is part of the request URL in error messages)."""

    def __init__(self, key: str):
        super().__init__()
        self.key = key

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if self.key and self.key in msg:
            record.msg, record.args = msg.replace(self.key, "<KEY>"), ()
        return True


def county_lookup(state: str = "NC") -> dict[str, str]:
    ref = pd.read_csv(REFERENCE / "county_centroids.csv", dtype={"county_fips": str})
    ref = ref[ref["state"] == state]
    names = ref["name"].str.replace(r" County$", "", regex=True).str.lower()
    return dict(zip(names, ref["county_fips"]))


def unix_to_iso(v) -> str | None:
    try:
        return datetime.fromtimestamp(int(v), tz=timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError, OSError):
        return None


def to_record(ev: dict, polled: str, lookup: dict[str, str]) -> dict:
    rec = {"polled_at": polled, **{k: ev.get(k) for k in KEEP}}
    for k in ("StartDate", "PlannedEndDate", "LastUpdated"):
        rec[k] = unix_to_iso(rec[k])
    county = (ev.get("County") or "").replace(" County", "").strip().lower()
    rec["county_fips"] = lookup.get(county)
    return rec


def run(polls: int = 3, interval: int = 60, base_url: str = BASE_URL, state: str = "NC") -> str | None:
    key = os.environ.get("DRIVENC_API_KEY")
    url = f"{base_url.rstrip('/')}/api/v2/get/event"
    if not key:
        log.error("A developer key is required. Request one on %s and set it, in PowerShell: "
                  '$env:DRIVENC_API_KEY="<key>"   (cmd: set DRIVENC_API_KEY=<key>)', base_url)
        write_manifest(SOURCE, url, None, "missing_key")
        return None
    log.addFilter(_RedactKey(key))
    if interval < 6:
        raise ValueError("The API allows 10 calls per 60 s; use an interval of at least 6 s")
    s = make_session()
    lookup = county_lookup(state)
    out = BRONZE / SOURCE / f"events_{datetime.now():%Y%m%d_%H%M%S}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with open(out, "w", encoding="utf-8") as f:
        for i in range(polls):
            events = get_json(url, SOURCE, s, params={"key": key, "format": "json"}) or []
            polled = now_utc()
            for ev in events:
                f.write(json.dumps(to_record(ev, polled, lookup), ensure_ascii=False) + "\n")
            closures = sum(1 for ev in events if ev.get("IsFullClosure"))
            total += len(events)
            log.info("Poll %d/%d: %d events (%d full closures)", i + 1, polls, len(events), closures)
            if i < polls - 1:
                time.sleep(interval)
    write_manifest(SOURCE, url, out, "ok", polls=polls, records=total)
    return str(out)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--polls", type=int, default=3)
    p.add_argument("--interval", type=int, default=60)
    p.add_argument("--base-url", default=BASE_URL, help="another 511 site, e.g. https://511wi.gov")
    p.add_argument("--state", default="NC", help="state code for the county lookup, e.g. WI")
    a = p.parse_args()
    run(a.polls, a.interval, a.base_url, a.state)
