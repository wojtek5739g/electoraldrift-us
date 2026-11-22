# ElectoralDrift US

County-level electoral nowcast for the US. The model predicts the result in every county
(two-party margin %Dem − %Rep and turnout) from the previous result, socio-economic features
and the weather, transport disruption and disinformation intensity during the voting period.
"What-if" sliders change these features and the map shows how the result shifts.

## Data sources (Milestone 2)

| Factor | Source | Mode | Role | Script |
|---|---|---|---|---|
| Elections | MEDSL – county presidential returns 2000–2024 | batch (manual download, Dataverse guestbook) | Model 1 target + baseline | `batch_medsl.py` |
| Elections | NC absentee (NCSBE) | batch (S3 files) | Model 2 target: daily early votes by party | `batch_nc_absentee.py` |
| Weather | Open-Meteo Historical | batch (REST API) | historical weather (training) | `batch_open_meteo.py` |
| Weather | NOAA NWS alerts | stream (REST every 60 s) | live weather alerts | `stream_nws_alerts.py` |
| Transport | BTS Airline On-Time | batch (ZIP files) | flight delays – history | `batch_bts_ontime.py` |
| Transport | FAA NAS Status | stream (REST every 60 s) | live airport delays | `stream_faa_airports.py` |
| Reference | US Census ACS 5-year | batch (Census API, key) | socio-economic features | `batch_census_acs.py` |
| Reference | Census Gazetteer | batch (file) | county centroids | `batch_county_centroids.py` |
| Reference | OurAirports | batch (file) | airport → county | `batch_airports_reference.py` |
| Economy (optional) | BLS LAUS – county unemployment, monthly since 1990 | batch (bulk text file, ~330 MB) | Model 1 feature + "unemployment change" slider | `batch_bls_laus.py` |

Model 1 (county result, whole US) is trained on the 2000–2024 presidential elections; Model 2 (daily turnout
by party) on North Carolina's early-vote files and supplies the weather and transport effects used by the sliders.

Planned for Milestone 3 (disinformation; scripts already in `src/acquisition/`, not run by `run_samples.py`):
GDELT GKG 2.x (`batch_gdelt_gkg.py`), Bluesky Jetstream (`stream_bluesky.py`), PolitiFact LIAR (`batch_liar.py`).

## How to run (Windows)

1. Install Python 3.10+ (python.org, tick "Add Python to PATH").
2. Open a terminal in this folder and run:

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python run_samples.py
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

The full run takes ~15–20 minutes and downloads ~0.5 GB (mostly the North Carolina file).
Without it: `python run_samples.py --skip-nc`. A single step: `python run_samples.py --only gdelt`.

## Outputs

- `data/bronze/` – raw files exactly as received from the source (+ `_manifest.jsonl` download log)
- `data/silver/` – first cleaned tables (e.g. weather county × day, airport × day)
- `data/reference/` – lookup tables (county centroids, airport → county)
- `logs/` – per-source logs + `run_summary_*.txt` (OK/FAIL per step)
- `reports/data_profile.md` – data profile: rows, columns, missing values, date ranges

`data/` is not committed to git (see `.gitignore`); `reports/` is.

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
