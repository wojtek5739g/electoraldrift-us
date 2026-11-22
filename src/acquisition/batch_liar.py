"""LIAR (PolitiFact) - 12.8k labelled political statements for training the
disinformation classifier (Wang, 2017).

File:   https://www.cs.ucsb.edu/~william/data/liar_dataset.zip  (train/valid/test .tsv, no header)
Output: data/bronze/liar/liar_dataset.zip + extracted files
        data/silver/liar_all.csv (with header and a 'split' column)
"""
from __future__ import annotations

import zipfile

import pandas as pd

from common import BRONZE, SILVER, download, get_logger, make_session

SOURCE = "liar"
URL = "https://www.cs.ucsb.edu/~william/data/liar_dataset.zip"
COLS = ["id", "label", "statement", "subject", "speaker", "job", "state", "party",
        "barely_true_cnt", "false_cnt", "half_true_cnt", "mostly_true_cnt", "pants_fire_cnt", "context"]
log = get_logger(SOURCE)


def run() -> str | None:
    dest = download(URL, BRONZE / SOURCE / "liar_dataset.zip", SOURCE, make_session())
    if dest is None:
        return None
    frames = []
    with zipfile.ZipFile(dest) as z:
        z.extractall(dest.parent)
        for split in ("train", "valid", "test"):
            name = next(n for n in z.namelist() if n.endswith(f"{split}.tsv"))
            with z.open(name) as f:
                df = pd.read_csv(f, sep="\t", header=None, names=COLS, quoting=3, dtype=str)
            df["split"] = split
            frames.append(df)
    all_df = pd.concat(frames, ignore_index=True)
    out = SILVER / "liar_all.csv"
    all_df.to_csv(out, index=False)
    log.info("LIAR: %d statements; labels: %s", len(all_df), all_df["label"].value_counts().to_dict())
    return str(out)


if __name__ == "__main__":
    run()
