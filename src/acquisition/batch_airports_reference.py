"""Airport dictionary (OurAirports, public domain) -> airport-to-county mapping.

File:    https://davidmegginson.github.io/ourairports-data/airports.csv
Mapping: nearest county centroid (approximation; a point-in-polygon join on county
         boundaries is planned for the Silver layer).
Output:  data/reference/airport_county.csv (airport, name, type, lat, lon, county_fips, dist_km)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from common import BRONZE, REFERENCE, download, get_logger, make_session

SOURCE = "ourairports"
URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"
log = get_logger(SOURCE)


def nearest_county(ap: pd.DataFrame, cent: pd.DataFrame) -> pd.DataFrame:
    lat1, lon1 = np.radians(ap["lat"].to_numpy())[:, None], np.radians(ap["lon"].to_numpy())[:, None]
    lat2, lon2 = np.radians(cent["lat"].to_numpy())[None, :], np.radians(cent["lon"].to_numpy())[None, :]
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    d = 2 * 6371 * np.arcsin(np.sqrt(a))  # haversine distance in km
    idx = d.argmin(axis=1)
    ap = ap.copy()
    ap["county_fips"] = cent["county_fips"].to_numpy()[idx]
    ap["dist_km"] = d[np.arange(len(ap)), idx].round(1)
    return ap


def run() -> str | None:
    dest = download(URL, BRONZE / SOURCE / "airports.csv", SOURCE, make_session())
    cent_path = REFERENCE / "county_centroids.csv"
    if dest is None or not cent_path.exists():
        log.error("Missing airports.csv or county_centroids.csv")
        return None
    df = pd.read_csv(dest, low_memory=False)
    us = df[(df["iso_country"] == "US") & df["iata_code"].notna()
            & df["type"].isin(["large_airport", "medium_airport", "small_airport"])]
    ap = us.rename(columns={"iata_code": "airport", "latitude_deg": "lat", "longitude_deg": "lon"})[
        ["airport", "name", "type", "lat", "lon"]]
    cent = pd.read_csv(cent_path, dtype={"county_fips": str})
    out = nearest_county(ap.reset_index(drop=True), cent)
    path = REFERENCE / "airport_county.csv"
    out.to_csv(path, index=False)
    log.info("US airports with IATA code: %d -> %s", len(out), path)
    return str(path)


if __name__ == "__main__":
    run()
