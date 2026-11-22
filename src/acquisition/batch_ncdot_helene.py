"""NCDOT - road closures after Hurricane Helene (North Carolina, autumn 2024).

Source: NCDOT public list "Helene Closures for Citizen Info" (PDF table, 12 columns:
        Incident ID, time closed, time re-opened / expected, road name, suffix, common name,
        direction, nearest cross street, county, nearest city, start latitude, start longitude).
        https://www.ncdot.gov/TIMS/Helene%20Closures%20for%20Citizen%20Info.pdf
Download: the script tries to download the PDF. If that fails (e.g. a blocked network),
        download it in a browser and save it as data/bronze/ncdot_helene/helene_closures.pdf.
Output: data/silver/nc_helene_closures.csv           (one row per closure, with county_fips)
        data/silver/nc_road_closures_daily_<start>_<end>.csv
            (every NC county x day in the voting window: closures active that day and
             closures that started that day; 0 when there was no closure)
The daily table has the same keys (county_fips, date) as the NC weather and early-vote tables,
so it can be joined to them directly. Times are Eastern Time, as in the source.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd

from common import BRONZE, REFERENCE, SILVER, download, get_logger, write_manifest

SOURCE = "ncdot_helene"
URL = "https://www.ncdot.gov/TIMS/Helene%20Closures%20for%20Citizen%20Info.pdf"
PDF_PATH = BRONZE / SOURCE / "helene_closures.pdf"
WINDOW = ("2024-09-20", "2024-11-05")  # same window as the NC early-vote and weather samples
COLUMNS = ["incident_id", "closed_at", "reopened_at", "road_name", "suffix", "common_name",
           "direction", "cross_street", "county", "city", "lat", "lon"]
log = get_logger(SOURCE)

_TS = r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}(?::\d{2})?"
_LINE = re.compile(rf"^(\d{{5,8}})\s+({_TS})\s+({_TS})?\s*(.*?)\s*(-?\d{{1,3}}\.\d+)?\s*(-?\d{{1,3}}\.\d+)?\s*$")


def nc_counties() -> pd.DataFrame:
    """NC county names (without ' County') and FIPS from the reference table."""
    ref = pd.read_csv(REFERENCE / "county_centroids.csv", dtype={"county_fips": str})
    ref = ref[ref["state"] == "NC"].copy()
    ref["county"] = ref["name"].str.replace(r" County$", "", regex=True)
    return ref[["county_fips", "county", "lat", "lon"]]


def parse_text_lines(lines, county_names) -> list[dict]:
    """Fallback parser for plain text lines (one closure per line).
    The county is the right-most known NC county name in the middle part of the line."""
    names = sorted(county_names, key=len, reverse=True)
    rows = []
    for line in lines:
        m = _LINE.match(line.strip())
        if not m:
            continue
        inc, closed, reopened, middle, lat, lon = m.groups()
        county, city, best = None, None, -1
        for n in names:
            for hit in re.finditer(rf"\b{re.escape(n)}\b", middle):
                if hit.start() > best:
                    best, county = hit.start(), n
                    city = middle[hit.end():].strip() or None
        rows.append({"incident_id": inc, "closed_at": closed, "reopened_at": reopened,
                     "road_name": middle.split(" ")[0] if middle else None,
                     "county": county, "city": city, "lat": lat, "lon": lon})
    return rows


def parse_pdf(path: Path, county_names) -> pd.DataFrame:
    import pdfplumber  # optional dependency, only needed for this source

    rows = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            table_rows = [r for t in page.extract_tables() for r in t
                          if r and len(r) == 12 and str(r[0] or "").strip().isdigit()]
            if table_rows:
                for r in table_rows:
                    cells = [(" ".join(str(c).split()) if c is not None else None) for c in r]
                    rows.append(dict(zip(COLUMNS, cells)))
            else:  # no ruled table on this page -> read text lines
                rows.extend(parse_text_lines((page.extract_text() or "").splitlines(), county_names))
    return pd.DataFrame(rows)


def clean(df: pd.DataFrame, counties: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["closed_at"] = pd.to_datetime(df["closed_at"], errors="coerce")
    df["reopened_at"] = pd.to_datetime(df.get("reopened_at"), errors="coerce")
    for c in ("lat", "lon"):
        df[c] = pd.to_numeric(df.get(c), errors="coerce")
    df["county"] = df["county"].str.replace(r" County$", "", regex=True).str.strip()
    df = df.merge(counties[["county", "county_fips"]], on="county", how="left")
    # county name missing or unknown -> nearest NC county centroid, if coordinates exist
    miss = df["county_fips"].isna() & df["lat"].notna() & df["lon"].notna()
    for i in df.index[miss]:
        d = (counties["lat"] - df.at[i, "lat"]) ** 2 + (counties["lon"] - df.at[i, "lon"]) ** 2
        df.at[i, "county_fips"] = counties.loc[d.idxmin(), "county_fips"]
    df = df.dropna(subset=["incident_id", "closed_at"]).drop_duplicates("incident_id")
    return df


def daily_counts(closures: pd.DataFrame, counties: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    """County x day grid: closures active during the day and closures that started that day."""
    days = pd.date_range(start, end, freq="D")
    grid = pd.MultiIndex.from_product([counties["county_fips"], days], names=["county_fips", "date"])
    out = pd.DataFrame(index=grid).reset_index()
    out["closures_active"] = 0
    out["closures_new"] = 0
    c = closures.dropna(subset=["county_fips"])
    for _, r in c.iterrows():
        reopen = r["reopened_at"] if pd.notna(r["reopened_at"]) else pd.Timestamp(end) + pd.Timedelta(days=1)
        sel = out["county_fips"] == r["county_fips"]
        day_start, day_end = out["date"], out["date"] + pd.Timedelta(days=1)
        out.loc[sel & (r["closed_at"] < day_end) & (reopen > day_start), "closures_active"] += 1
        out.loc[sel & (out["date"] == r["closed_at"].normalize()), "closures_new"] += 1
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    return out


def run(start: str = WINDOW[0], end: str = WINDOW[1]) -> str | None:
    if not PDF_PATH.exists():
        try:
            ok = download(URL, PDF_PATH, SOURCE)
        except Exception as e:  # noqa: BLE001
            log.warning("Download error: %s", e)
            ok = None
        if not ok or not PDF_PATH.exists():
            log.error("Download failed. Save the PDF manually from %s as %s", URL, PDF_PATH)
            write_manifest(SOURCE, URL, None, "failed")
            return None
    counties = nc_counties()
    raw = parse_pdf(PDF_PATH, counties["county"].tolist())
    if raw.empty:
        log.error("No closures parsed from %s", PDF_PATH)
        return None
    closures = clean(raw, counties)
    unmatched = int(closures["county_fips"].isna().sum())
    closures.to_csv(SILVER / "nc_helene_closures.csv", index=False)
    daily = daily_counts(closures, counties, start, end)
    out = SILVER / f"nc_road_closures_daily_{start}_{end}.csv"
    daily.to_csv(out, index=False)
    write_manifest(SOURCE, URL, PDF_PATH, "ok", closures=len(closures), unmatched_county=unmatched)
    log.info("Helene: %d closures (%d without county), %d county-days with an active closure -> %s",
             len(closures), unmatched, int((daily["closures_active"] > 0).sum()), out)
    return str(out)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--start", default=WINDOW[0])
    p.add_argument("--end", default=WINDOW[1])
    a = p.parse_args()
    run(a.start, a.end)
