"""Verify the specific PM2 snapshots after acquisition. Missing files fail the check."""
from pathlib import Path
import json
import sys
import unittest
import zipfile

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "acquisition"))
import stream_faa_airports as faa
from batch_open_meteo import SAMPLE_END, SAMPLE_START

DATA = ROOT / "data"
SILVER = DATA / "silver"
LIVE_SAMPLE = ROOT / "tests" / "fixtures" / "live_20261121.zip"


class SampleQuality(unittest.TestCase):
    def test_faa_xml_replay(self):
        with zipfile.ZipFile(LIVE_SAMPLE) as sample:
            records = [json.loads(line) for line in
                       sample.read("faa_nas/events_20261121_124751.jsonl").splitlines()]
            stamps = sorted({r["polled_at"] for r in records})
            self.assertEqual(len(stamps), 2)
            for stamp, suffix in zip(stamps, ["124752", "124852"]):
                xml = sample.read(f"faa_nas/raw_20261121_{suffix}.xml").decode("utf8")
                decoded = faa.parse(xml, stamp)
                self.assertEqual(len(decoded), 5)
                self.assertEqual(decoded, [r for r in records if r["polled_at"] == stamp])

    def test_nc_counts_and_keys(self):
        ballots = pd.read_csv(SILVER / "nc_early_votes_daily_20241105.csv")
        key = ["county_desc", "date", "voter_party_code", "ballot_req_type"]
        self.assertFalse(ballots.duplicated(key).any())
        self.assertEqual((len(ballots), ballots.n_ballots.sum()), (18555, 4520768))
        excluded = pd.read_csv(ROOT / "reports" / "nc_rejected_dates_20241105.csv")
        self.assertEqual(excluded.groupby("reason").n_ballots.sum().to_dict(),
                         {"after_election_day": 1173, "invalid_date": 2})

    def test_weather_covers_ballots(self):
        weather = pd.read_csv(SILVER / f"weather_daily_NC_{SAMPLE_START}_{SAMPLE_END}.csv",
                              dtype={"county_fips": str})
        county = pd.read_csv(DATA / "reference" / "county_centroids.csv", dtype={"county_fips": str})
        nc = county.loc[county.state.eq("NC"), ["name", "county_fips"]].copy()
        nc["county_desc"] = nc.name.str.removesuffix(" County").str.upper()
        days = pd.date_range(SAMPLE_START, SAMPLE_END).strftime("%Y-%m-%d")
        expected = pd.MultiIndex.from_product([nc.county_fips, days], names=["county_fips", "date"])
        actual = pd.MultiIndex.from_frame(weather[["county_fips", "date"]])
        self.assertEqual(len(expected), 4700)
        self.assertTrue(actual.is_unique)
        self.assertTrue(expected.sort_values().equals(actual.sort_values()))
        self.assertFalse(weather.isna().any().any())
        votes = pd.read_csv(SILVER / "nc_early_votes_daily_20241105.csv")
        votes = votes.merge(nc, on="county_desc", how="left", validate="many_to_one")
        joined = votes.merge(weather, on=["county_fips", "date"], how="left",
                             indicator=True, validate="many_to_one")
        self.assertTrue(joined["_merge"].eq("both").all())
        self.assertEqual(joined.n_ballots.sum(), 4520768)

    def test_bts_daily_volume_and_ranges(self):
        for month, flights in [("09", 582622), ("10", 615497), ("11", 575404)]:
            df = pd.read_csv(SILVER / f"airport_daily_2024_{month}.csv")
            self.assertFalse(df.duplicated(["airport", "date"]).any())
            for name in ["share_cancelled", "share_delayed_15"]:
                self.assertTrue(df[name].dropna().between(0, 1).all())
            self.assertEqual(df.n_flights.sum(), flights)

    def test_nws_poll_counts(self):
        with zipfile.ZipFile(LIVE_SAMPLE) as sample:
            records = [json.loads(line) for line in
                       sample.read("nws_alerts/alerts_20261121_124650.jsonl").splitlines()]
        self.assertEqual(len(records), 874)
        self.assertEqual(len({r["id"] for r in records}), 437)
        self.assertEqual(len({(r["polled_at"], r["id"]) for r in records}), 874)


if __name__ == "__main__":
    unittest.main(verbosity=2)

