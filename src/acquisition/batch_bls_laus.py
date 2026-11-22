"""BLS LAUS - monthly county unemployment (OPTIONAL factor: economy / retrospective voting).

File:   https://download.bls.gov/pub/time.series/la/la.data.64.County  (~330 MB, tab-separated text,
        all counties, monthly since January 1990). BLS requires a User-Agent with contact info:
        set EDUS_CONTACT to your e-mail before running.
Series id: 'LAU' + 'CN' + 5-digit county FIPS + 8 zeros + 2-digit measure, e.g. LAUCN370010000000003
        measures: 03 = unemployment rate, 04 = unemployed, 06 = labour force; period M01-M12, M13 = annual avg.
Output: data/bronze/bls_laus/la.data.64.County
        data/silver/unemployment_county_monthly.csv   - county_fips x year x month
        data/silver/unemployment_election_features.csv - per county and presidential election:
            October unemployment rate and its change vs October of the previous year
"""
from __future__ import annotations

import pandas as pd

from common import BRONZE, SILVER, download, get_logger, make_session

SOURCE = "bls_laus"
URL = "https://download.bls.gov/pub/time.series/la/la.data.64.County"
MEASURES = {"03": "unemp_rate", "04": "unemployed", "06": "labor_force"}
ELECTION_YEARS = [2000, 2004, 2008, 2012, 2016, 2020, 2024]
log = get_logger(SOURCE)


def parse(path, chunksize: int = 1_000_000) -> pd.DataFrame:
    parts, n = [], 0
    for chunk in pd.read_csv(path, sep="\t", dtype=str, chunksize=chunksize):
        chunk.columns = [c.strip() for c in chunk.columns]
        n += len(chunk)
        sid = chunk["series_id"].str.strip()
        chunk = chunk.assign(
            county_fips=sid.str[5:10],
            measure=sid.str[-2:],
            period=chunk["period"].str.strip(),
            value=pd.to_numeric(chunk["value"].str.strip(), errors="coerce"),  # '-' = not available
            year=chunk["year"].str.strip().astype(int),
        )
        chunk = chunk[chunk["measure"].isin(MEASURES) & chunk["period"].str.match(r"M(0[1-9]|1[0-2])$")]
        parts.append(chunk[["county_fips", "year", "period", "measure", "value"]])
        log.info("Read %d rows", n)
    long = pd.concat(parts, ignore_index=True)
    long["month"] = long["period"].str[1:].astype(int)
    wide = (long.pivot_table(index=["county_fips", "year", "month"], columns="measure",
                             values="value", aggfunc="first")
                .rename(columns=MEASURES).reset_index())
    wide.columns.name = None
    return wide


def election_features(monthly: pd.DataFrame) -> pd.DataFrame:
    octo = monthly[monthly["month"] == 10].set_index(["county_fips", "year"])["unemp_rate"]
    rows = []
    for y in ELECTION_YEARS:
        if y not in octo.index.get_level_values("year"):
            continue
        cur = octo.xs(y, level="year")
        prev = octo.xs(y - 1, level="year") if (y - 1) in octo.index.get_level_values("year") else None
        df = cur.rename("unemp_rate_oct").to_frame()
        if prev is not None:
            df["unemp_change_12m"] = (cur - prev.reindex(cur.index)).round(2)
        df["election_year"] = y
        rows.append(df.reset_index())
    return pd.concat(rows, ignore_index=True)


def run() -> str | None:
    dest = download(URL, BRONZE / SOURCE / "la.data.64.County", SOURCE, make_session(), timeout=900)
    if dest is None:
        log.error("Download failed - BLS often answers 403 without a User-Agent e-mail: "
                  'set it first, PowerShell: $env:EDUS_CONTACT="your.email@university.edu"')
        return None
    monthly = parse(dest)
    p1 = SILVER / "unemployment_county_monthly.csv"
    monthly.to_csv(p1, index=False)
    log.info("Monthly: %d rows, %d counties, years %d-%d -> %s", len(monthly),
             monthly["county_fips"].nunique(), monthly["year"].min(), monthly["year"].max(), p1)
    feats = election_features(monthly)
    p2 = SILVER / "unemployment_election_features.csv"
    feats.to_csv(p2, index=False)
    log.info("Election features: %d rows (county x election) -> %s", len(feats), p2)
    return str(p2)


if __name__ == "__main__":
    run()
