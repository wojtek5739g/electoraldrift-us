"""MEDSL - county-level US presidential election returns 2000-2024.

Source: Harvard Dataverse, doi:10.7910/DVN/VOQCHQ (MIT Election Data and Science Lab).
Method: Dataverse API -> list dataset files -> download 'countypres...'.
Note:   the dataset has a Guestbook; since Dataverse 6.x the access API returns HTTP 400
        without a guestbook response, so the file is downloaded once manually in a browser
        and placed in data/bronze/medsl/. The script then validates the local copy.
Output: data/bronze/medsl/countypres_2000-2024.csv
"""
from __future__ import annotations

import pandas as pd

from common import BRONZE, download, get_json, get_logger, make_session, write_manifest

SOURCE = "medsl"
DOI = "doi:10.7910/DVN/VOQCHQ"
API = "https://dataverse.harvard.edu/api"
MANUAL = ("Dataverse requires a Guestbook form before download (API returns 400). "
          "Download manually: https://doi.org/10.7910/DVN/VOQCHQ -> countypres_2000-2024.csv -> "
          "Access File -> 'Comma Separated Values (Original File Format)'. Save it to: {dir}")
log = get_logger(SOURCE)


def _validate(dest) -> str:
    sep = "\t" if dest.suffix == ".tab" else ","
    data = pd.read_csv(dest, sep=sep, dtype={"county_fips": str}, low_memory=False)
    log.info("File %s: %d rows, columns: %s", dest.name, len(data), list(data.columns))
    if "year" in data.columns:
        log.info("Years in data: %s", sorted(data["year"].dropna().unique().tolist()))
    return str(dest)


def run() -> str | None:
    local = sorted((BRONZE / SOURCE).glob("countypres*.csv")) + sorted((BRONZE / SOURCE).glob("countypres*.tab"))
    if local:
        log.info("Using previously downloaded file: %s", local[0].name)
        write_manifest(SOURCE, "manual-download", local[0], "ok_local")
        return _validate(local[0])

    s = make_session()
    meta = get_json(f"{API}/datasets/:persistentId/", SOURCE, s, params={"persistentId": DOI})
    files = meta["data"]["latestVersion"]["files"]
    log.info("Dataset version: %s.%s, files: %d",
             meta["data"]["latestVersion"].get("versionNumber"),
             meta["data"]["latestVersion"].get("versionMinorNumber"), len(files))
    target = None
    for f in files:
        df = f["dataFile"]
        name = df.get("originalFileName") or df["filename"]
        log.info("  file in dataset: %s (id=%s)", name, df["id"])
        if "countypres" in name.lower() and target is None:
            target = (df, name)
    if target is None:
        log.error("No countypres file found in the dataset")
        return None

    df, name = target
    url = f"{API}/access/datafile/{df['id']}"
    params = {"format": "original"} if df.get("originalFileFormat") else None
    if not name.lower().endswith((".csv", ".tab")):
        name += ".csv"
    dest = download(url, BRONZE / SOURCE / name, SOURCE, s, params=params)
    if dest is None and params:
        log.info("Retrying without format=original")
        dest = download(url, BRONZE / SOURCE / name, SOURCE, s)
    if dest is None:
        (BRONZE / SOURCE).mkdir(parents=True, exist_ok=True)
        log.error(MANUAL.format(dir=BRONZE / SOURCE))
        return None
    return _validate(dest)


if __name__ == "__main__":
    run()
