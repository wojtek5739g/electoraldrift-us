"""Build the NC 2024 presidential county map file served by the API.

Inputs
  data/bronze/medsl/countypres_2000-2024.csv   (manual MEDSL download, see README)
  Census cartographic boundary counties (downloaded automatically, cached in data/reference/)

Output
  app/backend/assets/nc_2024_counties.geojson  (committed to git; ~1 MB, 100 counties)

Run from the repo root:
  pip install -r scripts/requirements-geo.txt
  python scripts/prepare_nc_2024_map.py
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MEDSL = ROOT / "data" / "bronze" / "medsl" / "countypres_2000-2024.csv"
SHAPES_URL = "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_county_500k.zip"
SHAPES_ZIP = ROOT / "data" / "reference" / "cb_2023_us_county_500k.zip"
OUT = ROOT / "app" / "backend" / "assets" / "nc_2024_counties.geojson"

STATE_PO = "NC"
STATE_FIPS = "37"
YEAR = 2024


def load_results() -> pd.DataFrame:
    if not MEDSL.exists():
        sys.exit(f"Missing {MEDSL}. Download it manually first (see README, MEDSL section).")
    df = pd.read_csv(MEDSL, dtype={"county_fips": str}, low_memory=False)
    df = df[(df["year"] == YEAR) & (df["state_po"] == STATE_PO) & (df["office"] == "US PRESIDENT")]
    if df.empty:
        sys.exit("No 2024 NC presidential rows found in the MEDSL file.")

    df["county_fips"] = (df["county_fips"].str.replace(r"\.0$", "", regex=True).str.zfill(5))
    df["mode"] = df["mode"].fillna("TOTAL").str.upper()

    # MEDSL sometimes splits a county by vote mode (ELECTION DAY, ABSENTEE, ...).
    # Use the TOTAL row where it exists, otherwise sum the mode rows.
    has_total = df.groupby("county_fips")["mode"].transform(lambda m: (m == "TOTAL").any())
    df = df[~has_total | (df["mode"] == "TOTAL")]

    party = df["party"].fillna("OTHER").str.upper()
    df["bucket"] = party.map({"DEMOCRAT": "dem", "REPUBLICAN": "rep"}).fillna("other")

    wide = (df.pivot_table(index=["county_fips", "county_name"], columns="bucket",
                           values="candidatevotes", aggfunc="sum", fill_value=0)
              .reset_index())
    for col in ("dem", "rep", "other"):
        if col not in wide:
            wide[col] = 0
    wide["total"] = wide["dem"] + wide["rep"] + wide["other"]
    # Two-party margin in percentage points: positive = Republican lead.
    two_party = (wide["dem"] + wide["rep"]).replace(0, pd.NA)
    wide["margin_pp"] = ((wide["rep"] - wide["dem"]) / two_party * 100).astype(float).round(2)
    wide["winner"] = wide.apply(lambda r: "REP" if r["rep"] > r["dem"] else "DEM", axis=1)
    return wide


def load_shapes() -> gpd.GeoDataFrame:
    if not SHAPES_ZIP.exists():
        SHAPES_ZIP.parent.mkdir(parents=True, exist_ok=True)
        print(f"Downloading {SHAPES_URL}")
        urllib.request.urlretrieve(SHAPES_URL, SHAPES_ZIP)
    gdf = gpd.read_file(f"zip://{SHAPES_ZIP}")
    gdf = gdf[gdf["STATEFP"] == STATE_FIPS][["GEOID", "NAME", "geometry"]].to_crs(4326)
    # Light simplification keeps the file small without visible loss at state zoom.
    gdf["geometry"] = gdf.geometry.simplify(0.0005, preserve_topology=True)
    return gdf


def main() -> None:
    results = load_results()
    shapes = load_shapes()
    merged = shapes.merge(results, left_on="GEOID", right_on="county_fips", how="left")

    missing = merged[merged["total"].isna()]["NAME"].tolist()
    if missing:
        print(f"WARNING: no results for {len(missing)} counties: {missing}")
    print(f"Counties with results: {merged['total'].notna().sum()} / {len(merged)}")

    merged = merged.rename(columns={"GEOID": "fips", "NAME": "name"})
    merged = merged[["fips", "name", "dem", "rep", "other", "total", "margin_pp", "winner", "geometry"]]
    for col in ("dem", "rep", "other", "total"):
        merged[col] = merged[col].fillna(0).astype(int)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    geojson = json.loads(merged.to_json(drop_id=True))
    geojson["metadata"] = {
        "state": STATE_PO, "year": YEAR, "office": "US PRESIDENT",
        "source": "MEDSL county presidential returns 2000-2024 (doi:10.7910/DVN/VOQCHQ); "
                  "US Census cartographic boundary counties 2023 (1:500k)",
    }
    OUT.write_text(json.dumps(geojson, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {OUT} ({OUT.stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
