# ElectoralDrift US

ElectoralDrift US is a county-level US presidential election analytics project. Milestone 2 delivers Python collectors, local transformations and tests. The planned national model estimates two-party margin and total presidential vote count. A separate North Carolina count model will study daily accepted early and mail ballots by party of registration and ballot type. Live NWS alerts and FAA airport status will appear as map overlays.

## Milestone 2 submission

- [Project report (PDF)](output/pdf/ElectoralDrift_Report.pdf)
- [Presentation (PDF)](output/pdf/ElectoralDrift_Presentation.pdf)
- [Test documentation (PDF)](output/pdf/ElectoralDrift_Tests.pdf)
- [Git repository](https://github.com/wojtek5739g/electoraldrift-us)

## Data sources (Milestone 2)

| Factor | Source | Mode | Role | Script |
|---|---|---|---|---|
| Elections | MEDSL – county presidential returns 2000–2024 | batch (manual download, Dataverse guestbook) | Model 1 target + baseline | `batch_medsl.py` |
| Elections | NC absentee (NCSBE) | batch (S3 files) | Model 2 target: daily returns by registration party and ballot type | `batch_nc_absentee.py` |
| Weather | Open-Meteo Historical | batch (REST API) | historical weather (training) | `batch_open_meteo.py` |
| Weather | NOAA NWS alerts | stream (REST every 60 s) | weather map overlay | `stream_nws_alerts.py` |
| Transport | BTS Airline On-Time | batch (ZIP files) | flight delays – history | `batch_bts_ontime.py` |
| Transport | FAA NAS Status | stream (REST every 60 s) | airport-status map overlay | `stream_faa_airports.py` |
| Reference | US Census ACS 5-year | batch (Census API, key) | socio-economic features | `batch_census_acs.py` |
| Reference | Census Gazetteer | batch (file) | county centroids | `batch_county_centroids.py` |
| Reference | OurAirports | batch (file) | airport → county | `batch_airports_reference.py` |
| Economy (optional) | BLS LAUS – county unemployment, monthly since 1990 | batch (bulk text file, ~330 MB) | Model 1 feature + "unemployment change" slider | `batch_bls_laus.py` |

The NC weather sample covers 20 September through 5 November 2024 (100 counties and 47 days). The September, October and November BTS files cover the same voting period. The national model will only use structural data published by the forecast cutoff. The NC scenarios will report changes in expected ballot counts within NC.

Planned for Milestone 3 (disinformation; scripts already in `src/acquisition/`, not run by `run_samples.py`):
GDELT GKG 2.x (`batch_gdelt_gkg.py`), Bluesky Jetstream (`stream_bluesky.py`), PolitiFact LIAR (`batch_liar.py`).

## How to run (Windows)

1. Install Python 3.10+ (python.org, tick "Add Python to PATH").
2. Open a terminal in this folder and run:

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Environment variables (Census key, User-Agent contact) are set differently per terminal.
PowerShell (prompt starts with `PS`):

```
$env:CENSUS_API_KEY="your_key"
$env:EDUS_CONTACT="your.email@university.edu"
```

cmd: `set CENSUS_API_KEY=your_key`. The setting only lives in the current terminal window.

MEDSL requires a guestbook form before download, so `countypres_2000-2024.csv` is downloaded manually
from https://doi.org/10.7910/DVN/VOQCHQ ("Comma Separated Values (Original File Format)")
and saved in `data/bronze/medsl/`.

Run `python run_samples.py` after the manual download and environment setup. For a shorter run use `--skip-nc` or `--skip-bls`. Select named steps with `python run_samples.py --only bts profile`. Run `python run_samples.py --help` for the full list. A failed step produces a nonzero process exit code.

## Outputs

- `data/bronze/` – downloaded files, API snapshots and a manifest; NWS retains selected fields, FAA keeps XML plus extracted JSONL
- `data/silver/` – first cleaned tables (e.g. weather county × day, airport × day)
- `data/reference/` – lookup tables (county centroids, airport → county)
- `logs/` – per-source logs + `run_summary_*.txt` (OK/FAIL per step)
- `reports/data_profile.md` – data profile: rows, columns, missing values, date ranges

`data/` is not committed to git (see `.gitignore`); `reports/` is.


## Reproduce the PM2 tests

With the project environment active, run the five functional tests without API keys or downloads:

```powershell
python -m unittest discover -s tests -p test_acquisition.py -v
```

To rebuild the batch inputs for the five dated sample checks from a clean clone, run the first command below. Skip that first command when the PM2 files are already present. The second command checks the saved FAA/NWS snapshots in `tests/fixtures/live_20261121.zip` as well as the local NC, weather and BTS outputs. The counts in these checks are pinned to the submitted snapshot. A later upstream revision can legitimately change them.

```powershell
python run_samples.py --only centroids nc_absentee open_meteo bts
python tests/verify_samples.py
```

## Rebuild the documents

The report source is `reports/overleaf/main.tex`. Import the root `ElectoralDrift_Report_overleaf.zip` into Overleaf or compile the source with LaTeX. The PDFs submitted for this milestone are in `output/pdf/`. To regenerate the presentation and test PDF after checking the local samples, install the optional document dependency with `python -m pip install reportlab` and run `python reports/build_companions.py`.
