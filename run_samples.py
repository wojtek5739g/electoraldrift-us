"""Runs sample acquisition for all Milestone 2 sources, then the data profile.

Usage (in the project folder):
    python run_samples.py                # everything (~20 min, ~0.9 GB)
    python run_samples.py --skip-nc      # without the large North Carolina file
    python run_samples.py --skip-bls     # without the optional unemployment file (~330 MB)
    python run_samples.py --only bls_laus profile   # selected steps only (names from STEPS)

An OK/FAIL summary is written to logs/run_summary_<time>.txt (the "actual result" for tests).
"""
from __future__ import annotations

import argparse
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "src" / "acquisition"), str(ROOT / "src" / "profiling")]

import batch_airports_reference  # noqa: E402
import batch_bls_laus  # noqa: E402
import batch_bts_ontime  # noqa: E402
import batch_census_acs  # noqa: E402
import batch_county_centroids  # noqa: E402
import batch_medsl  # noqa: E402
import batch_nc_absentee  # noqa: E402
import batch_open_meteo  # noqa: E402
import profile_data  # noqa: E402
import stream_faa_airports  # noqa: E402
import stream_nws_alerts  # noqa: E402

STEPS = [
    # reference tables
    ("centroids", batch_county_centroids.run),
    ("acs", batch_census_acs.run),
    ("airports", batch_airports_reference.run),
    # elections
    ("medsl", batch_medsl.run),
    ("nc_absentee", batch_nc_absentee.run),
    # weather
    ("open_meteo", batch_open_meteo.run),
    ("nws_live", lambda: stream_nws_alerts.run(polls=2, interval=60)),
    # transport
    ("bts", batch_bts_ontime.run),
    ("faa_live", lambda: stream_faa_airports.run(polls=2, interval=60)),
    # optional: economy
    ("bls_laus", batch_bls_laus.run),
    # profile of everything above
    ("profile", profile_data.run),
]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--skip-nc", action="store_true")
    p.add_argument("--skip-bls", action="store_true")
    p.add_argument("--only", nargs="+", choices=[name for name, _ in STEPS])
    a = p.parse_args()
    skip = {"nc_absentee"} if a.skip_nc else set()
    if a.skip_bls:
        skip.add("bls_laus")
    steps = [s for s in STEPS if (a.only is None or s[0] in a.only) and s[0] not in skip]
    if not steps:
        p.error("No steps selected after applying the skip options")
    results = []
    for name, fn in steps:
        print(f"\n===== {name} =====", flush=True)
        t0 = time.time()
        try:
            out = fn()
            status = "OK" if out else "FAIL (no output)"
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            out, status = None, f"FAIL ({type(e).__name__}: {e})"
        results.append((name, status, round(time.time() - t0), out))

    (ROOT / "logs").mkdir(exist_ok=True)
    path = ROOT / "logs" / f"run_summary_{datetime.now():%Y%m%d_%H%M%S}.txt"
    lines = [f"{n:14s} {s:40s} {t:5d}s  {o}" for n, s, t, o in results]
    path.write_text("\n".join(lines), encoding="utf-8")
    print("\n===== SUMMARY =====\n" + "\n".join(lines) + f"\n\nSaved: {path}")
    return int(any(status != "OK" for _, status, _, _ in results))


if __name__ == "__main__":
    sys.exit(main())
