"""County centroids (Census Gazetteer) - used to query weather by coordinates
and to map airports to counties.

File:   https://www2.census.gov/geo/docs/maps-data/data/gazetteer/<year>_Gazetteer/<year>_Gaz_counties_national.zip
Output: data/reference/county_centroids.csv (county_fips, state, name, lat, lon, land_sqmi)

Quality notes: includes Puerto Rico (FIPS 72xxx), which has no presidential electoral votes;
since 2022 Connecticut uses "planning regions" (09110-09190) instead of the old counties
(09001-09015) used by MEDSL - needs a crosswalk in the Silver layer.
"""
from __future__ import annotations

import zipfile

import pandas as pd

from common import BRONZE, REFERENCE, download, get_logger, make_session

SOURCE = "census_gazetteer"
URL = "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/{y}_Gazetteer/{y}_Gaz_counties_national.zip"
log = get_logger(SOURCE)


def run(year: int = 2024) -> str | None:
    s = make_session()
    dest = None
    for y in (year, year - 1, year - 2):
        dest = download(URL.format(y=y), BRONZE / SOURCE / f"{y}_Gaz_counties_national.zip", SOURCE, s)
        if dest:
            break
    if dest is None:
        return None
    with zipfile.ZipFile(dest) as z:
        member = [n for n in z.namelist() if n.endswith(".txt")][0]
        with z.open(member) as f:
            df = pd.read_csv(f, sep="\t", dtype={"GEOID": str}, encoding="latin-1")
    df.columns = [c.strip() for c in df.columns]
    out = pd.DataFrame({
        "county_fips": df["GEOID"].str.zfill(5),
        "state": df["USPS"],
        "name": df["NAME"],
        "lat": df["INTPTLAT"],
        "lon": df["INTPTLONG"],
        "land_sqmi": df["ALAND_SQMI"],
    })
    path = REFERENCE / "county_centroids.csv"
    out.to_csv(path, index=False)
    log.info("Centroids: %d counties -> %s", len(out), path)
    return str(path)


if __name__ == "__main__":
    run()
