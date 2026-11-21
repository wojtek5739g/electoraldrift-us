"""BTS Airline On-Time Performance - historical flight delays (transport disruption proxy).

Monthly files (whole US, one row per flight):
https://transtats.bts.gov/PREZIP/On_Time_Reporting_Carrier_On_Time_Performance_1987_present_<YEAR>_<MONTH>.zip
(month without leading zero; data since Oct 1987; BTS publishes with a lag of a few months).
Default sample: October and November 2024.
Output: data/bronze/bts_ontime/<file>.zip
        data/silver/airport_daily_<year>_<month>.csv - origin airport x day aggregate
        (number of flights, mean departure delay, share cancelled, share delayed >15 min)
"""
from __future__ import annotations

import argparse
import zipfile

import pandas as pd

from common import BRONZE, SILVER, download, get_logger, make_session

SOURCE = "bts_ontime"
URL = ("https://transtats.bts.gov/PREZIP/"
       "On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{y}_{m}.zip")
COLS = ["FlightDate", "Origin", "OriginCityName", "OriginState", "DepDelay",
        "DepDelayMinutes", "DepDel15", "Cancelled", "Diverted"]
log = get_logger(SOURCE)


def aggregate(zip_path) -> pd.DataFrame:
    with zipfile.ZipFile(zip_path) as z:
        member = [n for n in z.namelist() if n.lower().endswith(".csv")][0]
        with z.open(member) as f:
            df = pd.read_csv(f, usecols=lambda c: c in COLS, low_memory=False)
    log.info("Raw flights: %d rows", len(df))
    g = df.groupby(["FlightDate", "Origin", "OriginState"], as_index=False).agg(
        n_flights=("Cancelled", "size"),
        mean_dep_delay_min=("DepDelayMinutes", "mean"),
        share_delayed_15=("DepDel15", "mean"),
        share_cancelled=("Cancelled", "mean"),
    )
    return g.rename(columns={"FlightDate": "date", "Origin": "airport", "OriginState": "state"})


def run(months=((2024, 10), (2024, 11))) -> list[str]:
    s = make_session()
    out = []
    for y, m in months:
        url = URL.format(y=y, m=m)
        dest = download(url, BRONZE / SOURCE / url.rsplit("/", 1)[-1], SOURCE, s, timeout=300)
        if dest is None:
            continue
        agg = aggregate(dest)
        p = SILVER / f"airport_daily_{y}_{m:02d}.csv"
        agg.to_csv(p, index=False)
        log.info("Airport x day aggregate: %d rows -> %s", len(agg), p)
        out.append(str(p))
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--months", nargs="+", default=["2024-10", "2024-11"], help="e.g. 2020-10 2020-11")
    a = p.parse_args()
    run([tuple(int(x) for x in s.split("-")) for s in a.months])
