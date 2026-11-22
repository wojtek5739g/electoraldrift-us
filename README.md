# ElectoralDrift US

ElectoralDrift US is a county-level US presidential election analytics project. Milestone 2 delivers Python collectors, local transformations and tests. The planned national model estimates two-party margin and total presidential vote count. A separate North Carolina count model will study daily accepted early and mail ballots by party of registration and ballot type. Its dynamic factors are weather and road accidents. Live NWS alerts and DriveNC road events will appear as map overlays.

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
| Roads (NC) | US Accidents (Kaggle, Feb 2016 – Mar 2023) | batch (manual download, large CSV) | Model 2 feature: accidents per county and day (history, elections 2016/2020/2022) | `batch_us_accidents.py` |
| Roads (NC) | DriveNC events API (NCDOT) | stream (REST every 60 s, key) | Model 2 feature (live): accidents per county and day + road-event map overlay | `stream_drivenc_events.py` |
| Roads (NC) | NCDOT Hurricane Helene closure list (PDF) | batch (file) | case study: road closures per county and day in 2024 (not a model feature) | `batch_ncdot_helene.py` |
| Reference | US Census ACS 5-year | batch (Census API, key) | socio-economic features | `batch_census_acs.py` |
| Reference | Census Gazetteer | batch (file) | county centroids | `batch_county_centroids.py` |
| Economy (optional) | BLS LAUS – county unemployment, monthly since 1990 | batch (bulk text file, ~330 MB) | Model 1 feature + "unemployment change" slider | `batch_bls_laus.py` |

The NC samples use the 47 days before election day: 20 September – 5 November 2024, and the same windows for 2016, 2020 and 2022 (`nc_absentee_<year>`, `open_meteo_<year>`). Road accidents enter the model as `accidents_rel`, the daily count relative to the county's own 120-day baseline; the batch and speed layers share this definition in `src/acquisition/road_features.py`, so training and live features are computed the same way. US Accidents ends in March 2023, so the road feature covers the 2016, 2020 and 2022 elections. Closures (Helene) and accidents are different measures, so Helene is analysed separately. The national model will only use structural data published by the forecast cutoff. The NC scenarios will report changes in expected ballot counts within NC.

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
$env:DRIVENC_API_KEY="your_drivenc_key"
```

cmd: `set CENSUS_API_KEY=your_key`. The setting only lives in the current terminal window.

MEDSL requires a guestbook form before download, so `countypres_2000-2024.csv` is downloaded manually
from https://doi.org/10.7910/DVN/VOQCHQ ("Comma Separated Values (Original File Format)")
and saved in `data/bronze/medsl/`.

The Helene closure list is downloaded automatically when the NCDOT site allows it. Otherwise save
https://www.ncdot.gov/TIMS/Helene%20Closures%20for%20Citizen%20Info.pdf as
`data/bronze/ncdot_helene/helene_closures.pdf`. The DriveNC live feed needs a free developer key
from https://www.drivenc.gov (env var `DRIVENC_API_KEY`); the API allows 10 calls per 60 s.
`python src/acquisition/stream_drivenc_events.py --aggregate` (step `drivenc_daily`) turns all saved
snapshots into `data/silver/nc_accidents_daily_live.csv`; `accidents_rel` needs 28 days of snapshots.

US Accidents requires a Kaggle login, so download it manually from
https://www.kaggle.com/datasets/sobhanmoosavi/us-accidents and save `archive.zip` (or the extracted
`US_Accidents_March23.csv`) in `data/bronze/us_accidents/`. Licence: CC BY-NC-SA 4.0.

Run `python run_samples.py` after the manual download and environment setup. For a shorter run use `--skip-nc` or `--skip-bls`. Select named steps with `python run_samples.py --only us_accidents profile`. Run `python run_samples.py --help` for the full list. A failed step produces a nonzero process exit code.

## Outputs

- `data/bronze/` – downloaded files, API snapshots and a manifest; NWS and DriveNC keep selected fields per poll
- `data/silver/` – first cleaned tables (e.g. weather, accidents and early votes county × day, ACS with Census sentinel codes such as -666666666 replaced by NULL)
- `data/reference/` – lookup tables (county centroids)
- `logs/` – per-source logs + `run_summary_*.txt` (OK/FAIL per step)
- `reports/data_profile.md` – data profile: rows, columns, missing values, date ranges

`data/` is not committed to git (see `.gitignore`); `reports/` is.


## Reproduce the PM2 tests

With the project environment active, run the ten functional tests without API keys or downloads:

```powershell
python -m unittest discover -s tests -p test_acquisition.py -v
```

To rebuild the batch inputs for the three dated sample checks from a clean clone, run the first command below. Skip that first command when the PM2 files are already present. The second command checks the saved NWS snapshot in `tests/fixtures/live_20261121.zip` as well as the local NC and weather outputs. The counts in these checks are pinned to the submitted snapshot. A later upstream revision can legitimately change them.

```powershell
python run_samples.py --only centroids nc_absentee open_meteo
python tests/verify_samples.py
```

## Documents

The project report is written in Overleaf (LaTeX). The PDFs for this milestone are exported from Overleaf and stored in `output/pdf/`:
`ElectoralDrift_Report.pdf`, `ElectoralDrift_Presentation.pdf` and `ElectoralDrift_Tests.pdf`.
