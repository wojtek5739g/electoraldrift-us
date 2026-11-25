"""US Accidents (Moosavi et al.) - road accidents, history for North Carolina.

Dataset: countrywide accident records collected from traffic-incident feeds, Feb 2016 - Mar 2023
         (about 7.7 million rows, 49 states). Licence CC BY-NC-SA 4.0 (non-commercial use).
         https://www.kaggle.com/datasets/sobhanmoosavi/us-accidents
Download: manual (Kaggle login required). Save the downloaded archive.zip, or the extracted
         US_Accidents_March23.csv, in data/bronze/us_accidents/.
Output:  data/silver/nc_accidents_daily_2016_2023.csv  (every NC county x day, accidents,
             severe accidents (severity 3-4), baseline and accidents_rel - see road_features.py)
         data/silver/nc_accidents_election_windows.csv (the same rows for the early-voting windows
             of the 2016, 2020 and 2022 elections, with an `election` column)
The election windows have the same length as the 2024 sample (47 days ending on election day).
"""
from __future__ import annotations

import zipfile
from pathlib import Path

import pandas as pd

from common import BRONZE, REFERENCE, SILVER, get_logger, write_manifest
from road_features import add_relative, county_day_counts

SOURCE = "us_accidents"
FOLDER = BRONZE / SOURCE
URL = "https://www.kaggle.com/datasets/sobhanmoosavi/us-accidents"
COLS = ["Severity", "Start_Time", "County", "State"]
ELECTIONS = {"2016": "2016-11-08", "2020": "2020-11-03", "2022": "2022-11-08"}
WINDOW_DAYS = 47
log = get_logger(SOURCE)


def election_windows() -> dict[str, tuple[str, str]]:
    return {y: ((pd.Timestamp(d) - pd.Timedelta(days=WINDOW_DAYS - 1)).strftime("%Y-%m-%d"), d)
            for y, d in ELECTIONS.items()}


def nc_county_lookup() -> dict[str, str]:
    ref = pd.read_csv(REFERENCE / "county_centroids.csv", dtype={"county_fips": str})
    ref = ref[ref["state"] == "NC"]
    return dict(zip(ref["name"].str.replace(r" County$", "", regex=True).str.lower(), ref["county_fips"]))


def find_input() -> Path | None:
    files = sorted(FOLDER.glob("*.csv")) + sorted(FOLDER.glob("*.zip"))
    return files[0] if files else None


def read_nc(path: Path, chunksize: int = 500_000) -> pd.DataFrame:
    """Reads only the needed columns in chunks and keeps North Carolina rows."""
    def chunks(f):
        return pd.read_csv(f, usecols=COLS, dtype=str, chunksize=chunksize, encoding="latin-1")
    parts, n = [], 0
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as z:
            member = [m for m in z.namelist() if m.lower().endswith(".csv")][0]
            with z.open(member) as f:
                for c in chunks(f):
                    n += len(c)
                    parts.append(c[c["State"] == "NC"])
    else:
        for c in chunks(path):
            n += len(c)
            parts.append(c[c["State"] == "NC"])
    log.info("Read %d rows, %d in North Carolina", n, sum(len(p) for p in parts))
    return pd.concat(parts, ignore_index=True)


def to_events(nc: pd.DataFrame, lookup: dict[str, str]) -> pd.DataFrame:
    ts = pd.to_datetime(nc["Start_Time"].str.slice(0, 19), errors="coerce")
    county = nc["County"].fillna("").str.replace(r" County$", "", regex=True).str.strip().str.lower()
    return pd.DataFrame({
        "county_fips": county.map(lookup),
        "date": ts.dt.strftime("%Y-%m-%d"),
        "severe": pd.to_numeric(nc["Severity"], errors="coerce").fillna(0) >= 3,
    })


def run() -> str | None:
    path = find_input()
    if path is None:
        log.error("No input file. Download the dataset from %s and save it in %s", URL, FOLDER)
        write_manifest(SOURCE, URL, None, "missing_input")
        return None
    lookup = nc_county_lookup()
    events = to_events(read_nc(path), lookup)
    n_bad_county = int(events["county_fips"].isna().sum())
    n_bad_date = int(events["date"].isna().sum())
    events = events.dropna()
    start, end = events["date"].min(), events["date"].max()
    daily = add_relative(county_day_counts(events, list(lookup.values()), start, end))
    out_all = SILVER / "nc_accidents_daily_2016_2023.csv"
    daily.to_csv(out_all, index=False)

    parts = []
    for year, (w_start, w_end) in election_windows().items():
        if w_start < start or w_end > end:
            log.warning("Election %s window %s..%s is not fully covered by the data (%s..%s)",
                        year, w_start, w_end, start, end)
        w = daily[daily["date"].between(w_start, w_end)].copy()
        w["election"] = year
        parts.append(w)
    windows = pd.concat(parts, ignore_index=True)
    out = SILVER / "nc_accidents_election_windows.csv"
    windows.to_csv(out, index=False)
    write_manifest(SOURCE, URL, path, "ok", nc_accidents=len(events),
                   unmatched_county=n_bad_county, bad_date=n_bad_date)
    log.info("NC accidents %s..%s: %d (unmatched county %d, bad date %d); election windows: %d rows -> %s",
             start, end, len(events), n_bad_county, n_bad_date, len(windows), out)
    return str(out)


if __name__ == "__main__":
    run()
