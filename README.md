# ElectoralDrift US

ElectoralDrift US is a county-level US presidential election analytics project. Milestone 2 delivers Python collectors, local transformations and tests. The planned national model estimates two-party margin and total presidential vote count. A separate North Carolina count model will study daily accepted early and mail ballots by party of registration and ballot type. Its dynamic factors are weather and road accidents. Live NWS alerts and DriveNC road events will appear as map overlays.

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

To rebuild the batch inputs for the six dated sample checks from a clean clone, run the first command below. Skip that first command when the PM2 files are already present. The second command checks the saved NWS snapshot in `tests/fixtures/live_20261121.zip` as well as the local NC early-vote, weather, accident and Helene outputs (2016, 2020, 2022 and 2024). The counts in these checks are pinned to the submitted snapshot. A later upstream revision can legitimately change them.

```powershell
python run_samples.py --only centroids nc_absentee nc_absentee_2016 nc_absentee_2020 nc_absentee_2022 open_meteo open_meteo_2016 open_meteo_2020 open_meteo_2022 us_accidents helene
python tests/verify_samples.py
```

## Deployment (OVHcloud, Terraform)

The web app (FastAPI + React/deck.gl, NC 2024 county results) runs on one OVHcloud Public Cloud VM.
Terraform (`deploy/terraform/`) creates the VM, firewall and SSH key; on first boot cloud-init
(`cloud-init.yaml.tftpl`) installs Docker, clones this repo and runs `docker compose up -d --build`.

### First deployment

One-time setup:

1. Install Terraform and Git for Windows (for Git Bash): `winget install Hashicorp.Terraform`, `winget install Git.Git`.
2. Create an SSH key: `ssh-keygen -t ed25519` (accept the default path).
3. In the OVHcloud Control Panel: Public Cloud → your project → Project Management → Users → create a user with
   the Administrator role. On its `...` menu choose **Download OpenStack's RC file** for your region and save it as
   `deploy/terraform/openrc.sh` (git-ignored, never commit it).

Build the map data and push the code (cloud-init deploys the `main` branch from GitHub):

```
python scripts/prepare_nc_2024_map.py      # writes app/backend/assets/nc_2024_counties.geojson
git add . && git commit -m "..." && git push origin main
```

Create the VM (in **Git Bash**):

```bash
cd deploy/terraform
cp terraform.tfvars.example terraform.tfvars   # set admin_cidr = "<your IP from ifconfig.me>/32"
source openrc.sh                               # asks for the OpenStack user's password
terraform init
terraform plan
terraform apply                                # prints url, public_ip, ssh
```

Wait ~5 minutes and open the printed `url`. If it does not load:
`ssh ubuntu@<public_ip> "sudo tail -n 50 /var/log/cloud-init-output.log"`.

### Redeploying changed code

For changes in `app/`, `scripts/`, the map data or `docker-compose.yml` (same VM, same IP):

```bash
git add . && git commit -m "..." && git push origin main
bash deploy/deploy_update.sh $(terraform -chdir=deploy/terraform output -raw public_ip)
```

The script pulls the latest commit on the VM and runs `docker compose up -d --build`.
Hard-refresh the page (Ctrl+F5) to see the new frontend.

For infrastructure changes (`deploy/terraform/*.tf` or `terraform.tfvars`, e.g. `flavor = "d2-8"`):
`source openrc.sh && terraform plan && terraform apply` in `deploy/terraform`.
A changed `cloud-init.yaml.tftpl` only runs on a new VM:
`terraform apply -replace=openstack_compute_instance_v2.app` (the IP may change).

To stop all costs: `terraform destroy`.
