"""Offline functional tests. All source records and HTTP responses are fixtures."""
import csv
import io
import sys
import tempfile
import unittest
import zipfile

import pandas as pd
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import run_samples
import batch_nc_absentee as nc
import batch_open_meteo as weather
import batch_ncdot_helene as helene
import stream_drivenc_events as drivenc
import common


class AcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.archive = self.folder / "sample.zip"
        self.dest = self.folder / "archive.csv"
        self.session = Mock()
        self.stack.enter_context(patch.object(common, "ROOT", self.folder))
        self.stack.enter_context(patch.object(common, "MANIFEST", self.folder / "manifest.jsonl"))

    def response(self, status):
        response = Mock(status_code=status, headers={}, url="https://example.invalid/sample")
        response.iter_content.return_value = [b"county,date\n"]
        return response

    def test_retry_429_then_success(self):
        self.session.get.side_effect = [self.response(429), self.response(200)]
        with patch.object(common.time, "sleep") as sleep:
            result = common.download("sample", self.dest, "fixture", self.session)
        sleep.assert_called_once()
        self.assertEqual(self.session.get.call_count, 2)
        self.assertEqual(result.read_bytes(), b"county,date\n")
        self.assertFalse(self.dest.with_suffix(".csv.part").exists())

    def test_repeat_download(self):
        self.session.get.return_value = self.response(200)
        first = common.download("sample", self.dest, "fixture", self.session)
        second = common.download("sample", self.dest, "fixture", self.session)
        self.assertEqual(first, second)
        self.assertEqual(second.read_bytes(), b"county,date\n")
        self.session.get.assert_called_once()

    def nc_input(self, body):
        with zipfile.ZipFile(self.archive, "w") as archive:
            archive.writestr("absentee.csv", body)
        self.stack.enter_context(patch.object(nc, "download", return_value=self.archive))
        self.stack.enter_context(patch.object(nc, "REPORTS", self.folder))
        self.stack.enter_context(patch.object(nc, "SILVER", self.folder))

    def test_missing_schema_fails_runner(self):
        self.nc_input("county_desc,voter_party_code\nTEST,DEM\n")
        (self.folder / "logs").mkdir()
        with patch.object(run_samples, "ROOT", self.folder), \
             patch.object(run_samples, "STEPS", [("nc_absentee", nc.run)]), \
             patch.object(sys, "argv", ["run_samples.py", "--only", "nc_absentee"]), \
             redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            status = run_samples.main()
        summary = next((self.folder / "logs").glob("run_summary*.txt")).read_text()
        self.assertEqual(status, 1)
        self.assertIn("FAIL (ValueError: Missing required NC ballot columns", summary)
        self.assertFalse(list(self.folder.glob("nc_early_votes*.csv")))

    def test_ballots_across_chunks(self):
        self.nc_input("county_desc,voter_party_code,ballot_rtn_dt,ballot_rtn_status,ballot_req_type\n"
                      "WAKE,DEM,11/05/2024,ACCEPTED,MAIL\n"
                      "WAKE,DEM,11/05/2024,ACCEPTED,MAIL\n"
                      "WAKE,DEM,11/05/2024,REJECTED,MAIL\n"
                      "WAKE,UNA,11/06/2024,ACCEPTED,MAIL\n")
        result = Path(nc.run(chunksize=1))
        with result.open() as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["date"], rows[0]["n_ballots"]), ("2024-11-05", "2"))
        with next(self.folder.glob("nc_rejected*.csv")).open() as f:
            late = list(csv.DictReader(f))
        self.assertEqual([(r["reason"], r["n_ballots"]) for r in late], [("after_election_day", "1")])

    def test_weather_missing_location(self):
        with self.assertRaisesRegex(ValueError, "Expected 2 weather locations, received 1"):
            weather.flatten([{"daily": {}}], ["37001", "37003"])

    COUNTIES = pd.DataFrame({"county_fips": ["37021", "37087", "37129"],
                             "county": ["Buncombe", "Haywood", "New Hanover"],
                             "lat": [35.6, 35.56, 34.18], "lon": [-82.53, -82.97, -77.87]})

    def test_helene_daily_closure_counts(self):
        counties = self.COUNTIES
        lines = ["714542 2024-10-02 02:39:00 2024-10-10 15:23:35 SR-1505 Bald Creek Road "
                 "Both Directions McElroy Lane Haywood Near Canton 35.61189 -82.89631",
                 "720001 2024-10-05 08:00:00 2024-10-06 08:00:00 US-17 Ocean Hwy Heading North "
                 "Market St New Hanover Wilmington 34.2 -77.9"]
        rows = helene.parse_text_lines(lines, counties["county"].tolist())
        self.assertEqual([r["county"] for r in rows], ["Haywood", "New Hanover"])
        closures = helene.clean(pd.DataFrame(rows), counties)
        daily = helene.daily_counts(closures, counties, "2024-09-20", "2024-11-05")
        self.assertEqual(len(daily), 3 * 47)

        def active(fips, day):
            row = daily[(daily.county_fips == fips) & (daily.date == day)]
            return int(row.closures_active.iloc[0])
        self.assertEqual((active("37087", "2024-10-05"), active("37087", "2024-10-11")), (1, 0))
        self.assertEqual(active("37129", "2024-10-05"), 1)

    def test_drivenc_record_and_missing_key(self):
        rec = drivenc.to_record({"ID": 1, "County": "Buncombe", "IsFullClosure": True,
                                 "StartDate": 1727740800}, "2026-11-22T18:00:00+00:00",
                                {"buncombe": "37021"})
        self.assertEqual((rec["county_fips"], rec["StartDate"]), ("37021", "2024-10-01T00:00:00+00:00"))
        with patch.dict(drivenc.os.environ, {}, clear=True):
            self.assertIsNone(drivenc.run(polls=1))

