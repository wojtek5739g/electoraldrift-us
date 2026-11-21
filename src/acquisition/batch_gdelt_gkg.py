"""GDELT GKG 2.x - news articles with themes, locations and tone (since Feb 2015,
a new file every 15 minutes). The same source serves history (training) and live (map).

File:   http://data.gdeltproject.org/gdeltv2/YYYYMMDDHHMMSS.gkg.csv.zip  (tab-separated, no header)
Filter: articles whose themes contain 'ELECTION' and that mention a US location.
Per article: US states (ADM1 code, e.g. USNC), tone, ELECTION_FRAUD flag,
number of "disinformation" themes (DISINFO_THEMES list - to be refined).
Default sample: 2024-11-01, 00:00-01:45 (8 files).
Full history: ~96 files/day x ~40 days x 3 elections -> tens of GB (processed in Spark).
Output: data/bronze/gdelt_gkg/<timestamp>.gkg.csv.zip
        data/silver/gdelt_election_us_<date>.csv - article x state
"""
from __future__ import annotations

import argparse
import csv
import io
import zipfile
from datetime import datetime, timedelta

import pandas as pd

from common import BRONZE, SILVER, download, get_logger, make_session

SOURCE = "gdelt_gkg"
URL = "http://data.gdeltproject.org/gdeltv2/{ts}.gkg.csv.zip"
DISINFO_THEMES = ("ELECTION_FRAUD", "MISINFORMATION", "PROPAGANDA", "RUMOR", "HOAX", "CONSPIRACY")
log = get_logger(SOURCE)
csv.field_size_limit(2**31 - 1)  # GKG fields can be very long (sys.maxsize overflows on Windows)

# GKG 2.1 column indexes
C_ID, C_DATE, C_SRC, C_URL, C_THEMES, C_V2THEMES, C_LOCS, C_TONE = 0, 1, 3, 4, 7, 8, 9, 15


def parse_line(fields: list[str]) -> list[dict]:
    """Return article x state records for one GKG line (empty list if it does not match)."""
    if len(fields) <= C_TONE:
        return []
    themes = fields[C_THEMES] + ";" + fields[C_V2THEMES]
    if "ELECTION" not in themes:
        return []
    states = set()
    for loc in fields[C_LOCS].split(";"):
        p = loc.split("#")
        if len(p) >= 4 and p[2] == "US" and p[3].startswith("US") and len(p[3]) == 4:
            states.add(p[3][2:])
    if not states:
        return []
    tone = fields[C_TONE].split(",")[0] if fields[C_TONE] else None
    v1 = fields[C_THEMES] or fields[C_V2THEMES]  # count in one column only to avoid double counting
    n_disinfo = sum(v1.count(t) for t in DISINFO_THEMES)
    return [{
        "gkg_id": fields[C_ID], "datetime": fields[C_DATE], "source": fields[C_SRC],
        "url": fields[C_URL], "state": st, "tone": float(tone) if tone else None,
        "election_fraud": "ELECTION_FRAUD" in themes, "n_disinfo_themes": n_disinfo,
    } for st in sorted(states)]


def parse_zip(path) -> list[dict]:
    out = []
    with zipfile.ZipFile(path) as z:
        with z.open(z.namelist()[0]) as f:
            text = io.TextIOWrapper(f, encoding="utf-8", errors="replace")
            for fields in csv.reader(text, delimiter="\t", quoting=csv.QUOTE_NONE):
                out.extend(parse_line(fields))
    return out


def run(date: str = "2024-11-01", n_files: int = 8) -> str | None:
    s = make_session()
    t = datetime.strptime(date, "%Y-%m-%d")
    records, ok = [], 0
    for i in range(n_files):
        ts = (t + timedelta(minutes=15 * i)).strftime("%Y%m%d%H%M%S")
        dest = download(URL.format(ts=ts), BRONZE / SOURCE / f"{ts}.gkg.csv.zip", SOURCE, s)
        if dest is None:
            continue
        ok += 1
        recs = parse_zip(dest)
        log.info("%s: %d article x state records about US elections", ts, len(recs))
        records.extend(recs)
    if not records:
        log.error("No records (files downloaded: %d)", ok)
        return None
    df = pd.DataFrame(records)
    df["datetime"] = pd.to_datetime(df["datetime"].astype(str), format="%Y%m%d%H%M%S", utc=True)
    out = SILVER / f"gdelt_election_us_{date}.csv"
    df.to_csv(out, index=False)
    log.info("GDELT: %d records, %d unique articles, %d states -> %s",
             len(df), df["gkg_id"].nunique(), df["state"].nunique(), out)
    return str(out)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--date", default="2024-11-01")
    p.add_argument("--n-files", type=int, default=8, help="number of 15-minute files (96 = full day)")
    a = p.parse_args()
    run(a.date, a.n_files)
