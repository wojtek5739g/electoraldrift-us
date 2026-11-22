"""NOAA NWS - active weather alerts, live (REST, GeoJSON), polled every 60 s.

API: https://api.weather.gov/alerts/active  (no key, but a User-Agent header with contact
info is REQUIRED - set env var EDUS_CONTACT to your e-mail).
Counties: properties.geocode.SAME = '0' + 5-digit FIPS (e.g. 037183 -> 37183).
Output: data/bronze/nws_alerts/alerts_<YYYYmmdd_HHMMSS>.jsonl - one line = one alert in one poll
        (with a list of county_fips).
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime

from common import BRONZE, get_json, get_logger, make_session, now_utc, write_manifest

SOURCE = "nws_alerts"
URL = "https://api.weather.gov/alerts/active"
log = get_logger(SOURCE)


def same_to_fips(codes) -> list[str]:
    return sorted({c[-5:] for c in (codes or []) if len(c) == 6 and c.isdigit()})


def run(polls: int = 3, interval: int = 60, area: str | None = None) -> str:
    s = make_session()
    out = BRONZE / SOURCE / f"alerts_{datetime.now():%Y%m%d_%H%M%S}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with open(out, "w", encoding="utf-8") as f:
        for i in range(polls):
            params = {"area": area} if area else None
            data = get_json(URL, SOURCE, s, params=params, headers={"Accept": "application/geo+json"})
            polled = now_utc()
            for feat in data.get("features", []):
                p = feat.get("properties", {})
                rec = {
                    "polled_at": polled, "id": p.get("id"), "event": p.get("event"),
                    "severity": p.get("severity"), "urgency": p.get("urgency"),
                    "onset": p.get("onset"), "expires": p.get("expires"),
                    "county_fips": same_to_fips(p.get("geocode", {}).get("SAME")),
                    "area_desc": p.get("areaDesc"),
                }
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            total += len(data.get("features", []))
            log.info("Poll %d/%d: %d active alerts", i + 1, polls, len(data.get("features", [])))
            if i < polls - 1:
                time.sleep(interval)
    write_manifest(SOURCE, URL, out, "ok", polls=polls, records=total)
    return str(out)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--polls", type=int, default=3)
    p.add_argument("--interval", type=int, default=60)
    p.add_argument("--area", default=None, help="e.g. NC (default: whole US)")
    a = p.parse_args()
    run(a.polls, a.interval, a.area)
