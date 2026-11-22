"""North Carolina - absentee file (every mail and early in-person "one-stop" ballot), NCSBE.

File:   https://s3.amazonaws.com/dl.ncsbe.gov/ENRS/<YYYY_MM_DD>/absentee_<YYYYMMDD>.zip
Available for elections from 2004 to 2026. The 2024 file is ~207 MB zipped (4.7M rows).
Election Day votes are NOT included in this file.
Role in the project: detailed day-by-day turnout validation and party-of-registration split
of early votes (NC as the "showcase" state).

The script reads the file in chunks and aggregates accepted ballots:
county x return date x party x ballot type.
Output: data/bronze/nc_absentee/absentee_<date>.zip
        reports/nc_absentee_columns_<date>.txt      - column list only (no personal data)
        reports/nc_rejected_dates_<date>.csv        - aggregate rows outside the voting window
        data/silver/nc_early_votes_daily_<date>.csv - aggregate
"""
from __future__ import annotations

import argparse
import zipfile

import pandas as pd

from common import BRONZE, REPORTS, SILVER, download, get_logger, make_session

SOURCE = "nc_absentee"
URL = "https://s3.amazonaws.com/dl.ncsbe.gov/ENRS/{d}/absentee_{c}.zip"
log = get_logger(SOURCE)

COUNTY, PARTY, RETURN_DT, STATUS, BALLOT_TYPE = (
    "county_desc", "voter_party_code", "ballot_rtn_dt", "ballot_rtn_status", "ballot_req_type")


def run(election: str = "2024_11_05", chunksize: int = 500_000) -> str | None:
    compact = election.replace("_", "")
    dest = download(URL.format(d=election, c=compact), BRONZE / SOURCE / f"absentee_{compact}.zip",
                    SOURCE, make_session(), timeout=600)
    if dest is None:
        return None
    with zipfile.ZipFile(dest) as z:
        member = [n for n in z.namelist() if n.lower().endswith((".csv", ".txt"))][0]
        with z.open(member) as f:
            head = pd.read_csv(f, nrows=5, dtype=str, encoding="latin-1")
    cols = [c.strip() for c in head.columns]
    info = REPORTS / f"nc_absentee_columns_{compact}.txt"
    # only column names are saved - rows contain personal voter data (names, addresses)
    info.write_text("Columns:\n" + "\n".join(cols) + "\n", encoding="utf-8")
    log.info("Columns (%d): %s", len(cols), cols)

    needed = [COUNTY, PARTY, RETURN_DT, STATUS, BALLOT_TYPE]
    missing = [c for c in needed if c not in cols]
    if missing:
        raise ValueError(f"Missing required NC ballot columns: {', '.join(missing)}. See {info.name}")

    parts, n_rows = [], 0
    with zipfile.ZipFile(dest) as z:
        with z.open(member) as f:
            for chunk in pd.read_csv(f, usecols=needed, dtype=str, encoding="latin-1", chunksize=chunksize):
                n_rows += len(chunk)
                chunk = chunk[chunk[STATUS].fillna("").str.upper().str.startswith("ACCEPTED")]
                parts.append(chunk.groupby([COUNTY, RETURN_DT, PARTY, BALLOT_TYPE]).size())
                log.info("Read %d rows", n_rows)
    agg = pd.concat(parts).groupby(level=[0, 1, 2, 3]).sum().reset_index(name="n_ballots")
    agg["date"] = pd.to_datetime(agg[RETURN_DT], errors="coerce")

    # quality check: return date must lie in [election day - 90 days, election day]
    eday = pd.Timestamp(election.replace("_", "-"))
    valid = agg["date"].between(eday - pd.Timedelta(days=90), eday)
    rejected = agg[~valid].copy()
    if len(rejected):
        # up to 10 days after election day = legitimate late ballots (e.g. military/overseas, UOCAVA);
        # anything else = data error (e.g. year 2204)
        late_ok = rejected["date"].between(eday + pd.Timedelta(days=1), eday + pd.Timedelta(days=10))
        rejected["reason"] = late_ok.map({True: "after_election_day", False: "invalid_date"})
        rej_path = REPORTS / f"nc_rejected_dates_{compact}.csv"
        rejected.to_csv(rej_path, index=False)
        for reason, g in rejected.groupby("reason"):
            log.warning("Excluded [%s]: %d aggregate rows (%d ballots), e.g. %s",
                        reason, len(g), g["n_ballots"].sum(), g[RETURN_DT].unique()[:3].tolist())
        log.info("Excluded rows -> %s", rej_path)
    agg = agg[valid]
    out = SILVER / f"nc_early_votes_daily_{compact}.csv"
    agg.to_csv(out, index=False)
    log.info("NC: %d ballots in file, aggregate %d rows (%d accepted ballots in window) -> %s",
             n_rows, len(agg), agg["n_ballots"].sum(), out)
    return str(out)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--election", default="2024_11_05", help="e.g. 2020_11_03, 2016_11_08")
    run(p.parse_args().election)
