"""US Census ACS 5-year estimates - county socio-economic features.

API:    https://api.census.gov/data/{year}/acs/acs5  (free API key REQUIRED, env var CENSUS_API_KEY;
        sign up at https://api.census.gov/data/key_signup.html)
Years:  2012, 2016, 2020, 2024 by default (presidential election years). The education table
        A vintage is a reference period. A historical model may only use estimates
        already published on its forecast date. Earlier cycles without an eligible
        vintage require a reduced feature set or exclusion from the ACS model.
Output: data/bronze/census_acs/acs5_<year>.json (raw response)
        data/bronze/census_acs/acs5_<year>.csv  (same table with header + county_fips)
        data/silver/census_acs_<year>.csv       (numeric columns, sentinels replaced with NULL)
Quality note: the API uses negative sentinel values such as -666666666 for "not available";
        they are replaced with NULL in the Silver layer (clean_to_silver).
        Rebuild Silver from saved Bronze files without an API key:
        python src/acquisition/batch_census_acs.py --silver-only
"""
from __future__ import annotations

import argparse
import os

import pandas as pd

from common import BRONZE, SILVER, get_json, get_logger, make_session, save_json, write_manifest

SOURCE = "census_acs"
log = get_logger(SOURCE)

VARIABLES = {
    "B01003_001E": "total_pop",
    "B01002_001E": "median_age",
    "B19013_001E": "median_hh_income",
    "B15003_001E": "edu_pop_25plus",
    "B15003_022E": "edu_bachelors",
    "B15003_023E": "edu_masters",
    "B15003_024E": "edu_professional",
    "B15003_025E": "edu_doctorate",
    "B08301_001E": "commuters_total",
    "B08301_010E": "commuters_public_transit",
    "B23025_003E": "civilian_labor_force",
    "B23025_005E": "unemployed",
}

# Census "annotation" codes returned instead of an estimate
# (https://www.census.gov/data/developers/data-sets/acs-1year/notes-on-acs-estimate-and-annotation-values.html)
SENTINELS = [-999999999, -888888888, -666666666, -555555555, -333333333, -222222222]


def clean_to_silver(year: int) -> str | None:
    """Bronze acs5_<year>.csv -> Silver census_acs_<year>.csv with sentinels set to NULL."""
    src = BRONZE / SOURCE / f"acs5_{year}.csv"
    if not src.exists():
        log.warning("No Bronze file for ACS %s: %s", year, src)
        return None
    df = pd.read_csv(src, dtype={"county_fips": str, "state": str, "county": str})
    n_replaced = 0
    for col in VARIABLES.values():
        df[col] = pd.to_numeric(df[col], errors="coerce")
        mask = df[col].isin(SENTINELS)
        n_replaced += int(mask.sum())
        df.loc[mask, col] = pd.NA
    SILVER.mkdir(parents=True, exist_ok=True)
    out = SILVER / f"census_acs_{year}.csv"
    df.to_csv(out, index=False)
    log.info("ACS %s Silver: %d counties, %d sentinel values set to NULL", year, len(df), n_replaced)
    return str(out)


def fetch_year(year: int, session) -> pd.DataFrame | None:
    url = f"https://api.census.gov/data/{year}/acs/acs5"
    params = {"get": "NAME," + ",".join(VARIABLES), "for": "county:*", "in": "state:*",
              "key": os.environ["CENSUS_API_KEY"]}
    try:
        rows = get_json(url, SOURCE, session, params=params)
    except Exception as e:  # e.g. 404 when the year is not published yet
        log.warning("Year %s not available: %s", year, e)
        write_manifest(SOURCE, url, None, "failed", year=year)
        return None
    raw_path = save_json(rows, BRONZE / SOURCE / f"acs5_{year}.json")
    write_manifest(SOURCE, url, raw_path, "ok", year=year)

    df = pd.DataFrame(rows[1:], columns=rows[0]).rename(columns=VARIABLES)
    df["county_fips"] = df["state"].str.zfill(2) + df["county"].str.zfill(3)
    df["acs_year"] = year
    out = BRONZE / SOURCE / f"acs5_{year}.csv"
    df.to_csv(out, index=False)
    log.info("ACS %s: %d counties, columns: %s", year, len(df), list(df.columns))
    clean_to_silver(year)
    return df


def run(years=(2012, 2016, 2020, 2024)) -> list[str]:
    if not os.environ.get("CENSUS_API_KEY"):
        log.error("Census API requires a key ('Missing Key' response). Get a free key at "
                  "https://api.census.gov/data/key_signup.html and set it, in PowerShell: "
                  '$env:CENSUS_API_KEY="<key>"   (cmd: set CENSUS_API_KEY=<key>)')
        write_manifest(SOURCE, "https://api.census.gov/data", None, "missing_key")
        return []
    s = make_session()
    done = []
    for y in years:
        df = fetch_year(y, s)
        if df is None:  # fallback: previous year
            y = y - 1
            df = fetch_year(y, s)
        if df is not None:
            done.append(str(BRONZE / SOURCE / f"acs5_{y}.csv"))
    return done


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--years", nargs="+", type=int, default=[2012, 2016, 2020, 2024])
    p.add_argument("--silver-only", action="store_true",
                   help="only rebuild Silver tables from saved Bronze CSVs (no API key needed)")
    a = p.parse_args()
    if a.silver_only:
        for y in a.years:
            clean_to_silver(y)
    else:
        run(a.years)
