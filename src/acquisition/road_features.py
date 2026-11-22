"""Road-accident feature shared by the batch layer (US Accidents) and the speed layer (DriveNC).

Both layers produce one row per county and day with the number of accidents. The model feature is
the same in both layers: accidents relative to the county's own recent baseline,

    accidents_rel = (accidents + 0.5) / (baseline + 0.5)

where baseline = mean daily number of accidents in that county over the previous BASELINE_DAYS days
(the current day is excluded). A relative measure is used because the two sources count accidents
differently (commercial traffic feeds vs. NCDOT); the ratio to each source's own baseline makes the
values comparable. 0.5 smooths counties with few accidents.
"""
from __future__ import annotations

import pandas as pd

BASELINE_DAYS = 120   # length of the baseline window
MIN_BASELINE_DAYS = 28  # fewer days of history -> accidents_rel is left empty


def county_day_counts(events: pd.DataFrame, counties: list[str], start: str, end: str) -> pd.DataFrame:
    """events: columns county_fips, date (YYYY-MM-DD), severe (bool).
    Returns the full county x day grid (0 when there was no accident)."""
    days = pd.date_range(start, end, freq="D").strftime("%Y-%m-%d")
    grid = pd.MultiIndex.from_product([sorted(counties), days], names=["county_fips", "date"])
    ev = events.dropna(subset=["county_fips", "date"])
    counts = ev.groupby(["county_fips", "date"]).size().rename("accidents")
    severe = ev[ev["severe"]].groupby(["county_fips", "date"]).size().rename("accidents_severe")
    out = pd.DataFrame(index=grid).join(counts).join(severe).fillna(0).astype(int)
    return out.reset_index()


def add_relative(daily: pd.DataFrame, baseline_days: int = BASELINE_DAYS,
                 min_days: int = MIN_BASELINE_DAYS) -> pd.DataFrame:
    """Adds baseline (previous days only) and accidents_rel to a full county x day grid."""
    daily = daily.sort_values(["county_fips", "date"]).copy()
    daily["baseline"] = (daily.groupby("county_fips")["accidents"]
                         .transform(lambda s: s.shift(1).rolling(baseline_days, min_periods=min_days).mean()))
    daily["accidents_rel"] = (daily["accidents"] + 0.5) / (daily["baseline"] + 0.5)
    return daily
