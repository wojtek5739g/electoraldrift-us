"""Open-Meteo Historical Weather API - daily weather at county centroids.

API:    https://archive-api.open-meteo.com/v1/archive  (no key, free for non-commercial use;
        ~10,000 "calls"/day - long periods and many locations count as several calls,
        so the full US is fetched in batches, possibly over several days).
        Multiple locations per request: latitude=a,b,c&longitude=x,y,z.
Default sample: North Carolina, 2024 voting window (2024-10-01 .. 2024-11-10).
Output: data/bronze/open_meteo/<state>_<start>_<end>/batch_XXX.json  (raw responses)
        data/silver/weather_daily_<state>_<start>_<end>.csv          (county_fips x day)
"""
from __future__ import annotations

import argparse
import time

import pandas as pd

from common import BRONZE, REFERENCE, SILVER, get_json, get_logger, make_session, save_json, write_manifest

SOURCE = "open_meteo"
URL = "https://archive-api.open-meteo.com/v1/archive"
DAILY = ["weather_code", "temperature_2m_max", "temperature_2m_min", "precipitation_sum",
         "rain_sum", "snowfall_sum", "wind_gusts_10m_max"]
log = get_logger(SOURCE)


def flatten(responses: list[dict], fips: list[str]) -> pd.DataFrame:
    frames = []
    for code, r in zip(fips, responses):
        d = pd.DataFrame(r["daily"])
        d.insert(0, "county_fips", code)
        frames.append(d)
    return pd.concat(frames, ignore_index=True).rename(columns={"time": "date"})


def run(state: str | None = "NC", start: str = "2024-10-01", end: str = "2024-11-10",
        batch_size: int = 20, pause: float = 1.5) -> str | None:
    cent_path = REFERENCE / "county_centroids.csv"
    if not cent_path.exists():
        log.error("Missing %s - run batch_county_centroids.py first", cent_path)
        return None
    cent = pd.read_csv(cent_path, dtype={"county_fips": str})
    if state:
        cent = cent[cent["state"] == state]
    tag = f"{state or 'US'}_{start}_{end}"
    raw_dir = BRONZE / SOURCE / tag
    s = make_session()
    rows = []
    for i in range(0, len(cent), batch_size):
        b = cent.iloc[i:i + batch_size]
        params = {
            "latitude": ",".join(f"{x:.4f}" for x in b["lat"]),
            "longitude": ",".join(f"{x:.4f}" for x in b["lon"]),
            "start_date": start, "end_date": end,
            "daily": ",".join(DAILY), "timezone": "auto",
        }
        resp = get_json(URL, SOURCE, s, params=params)
        resp = resp if isinstance(resp, list) else [resp]
        p = save_json(resp, raw_dir / f"batch_{i // batch_size:03d}.json")
        write_manifest(SOURCE, URL, p, "ok", n_locations=len(b), start=start, end=end)
        rows.append(flatten(resp, b["county_fips"].tolist()))
        log.info("Batch %d: %d counties", i // batch_size, len(b))
        time.sleep(pause)
    df = pd.concat(rows, ignore_index=True)
    out = SILVER / f"weather_daily_{tag}.csv"
    df.to_csv(out, index=False)
    log.info("Weather: %d rows (county x day) -> %s", len(df), out)
    return str(out)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--state", default="NC", help="state code, e.g. NC; 'ALL' = whole US")
    p.add_argument("--start", default="2024-10-01")
    p.add_argument("--end", default="2024-11-10")
    a = p.parse_args()
    run(None if a.state == "ALL" else a.state, a.start, a.end)
