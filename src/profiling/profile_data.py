"""Profile of downloaded data -> reports/data_profile.md

For every CSV/JSONL file: row count, columns, dtypes, % missing, date range,
number of unique values. Basis for "Description of Data Sets" and data quality tests.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
REPORTS = ROOT / "reports"

PATTERNS = [
    "bronze/medsl/*.csv", "bronze/medsl/*.tab", "bronze/census_acs/*.csv",
    "reference/*.csv", "silver/*.csv",
    "bronze/nws_alerts/*.jsonl", "bronze/drivenc_events/*.jsonl",
]
# outputs of sources postponed to Milestone 3 (disinformation) are not profiled
SKIP_PREFIXES = ("gdelt_", "liar_", "ga_")
DATE_HINTS = ("date", "time", "_dt", "created", "polled", "onset", "expires")


def load(p: Path) -> pd.DataFrame:
    if p.suffix == ".jsonl":
        return pd.read_json(p, lines=True)
    sep = "\t" if p.suffix == ".tab" else ","
    # FIPS codes are read as text so leading zeros are kept (e.g. 01001)
    return pd.read_csv(p, sep=sep, low_memory=False, dtype={"county_fips": str})


def profile(p: Path) -> str:
    df = load(p)
    lines = [f"## {p.relative_to(DATA)}", "",
             f"- File size: {p.stat().st_size / 1e6:.2f} MB",
             f"- Rows: {len(df):,}", f"- Columns: {df.shape[1]}", "",
             "| column | dtype | % missing | unique | min | max |", "|---|---|---|---|---|---|"]
    for c in df.columns:
        s = df[c]
        mn = mx = ""
        if c == "time_us":
            d = pd.to_datetime(s, unit="us", utc=True)
            mn, mx = str(d.min())[:19], str(d.max())[:19]
        elif any(h in c.lower() for h in DATE_HINTS) and not pd.api.types.is_numeric_dtype(s):
            d = pd.to_datetime(s, errors="coerce", utc=True, format="mixed")
            if d.notna().any():
                mn, mx = str(d.min())[:19], str(d.max())[:19]
        elif pd.api.types.is_numeric_dtype(s):
            mn, mx = f"{s.min():.4g}" if s.notna().any() else "", f"{s.max():.4g}" if s.notna().any() else ""
        try:
            nun = s.nunique()
        except TypeError:  # lists in JSONL
            nun = s.astype(str).nunique()
        lines.append(f"| {c} | {s.dtype} | {s.isna().mean() * 100:.1f} | {nun:,} | {mn} | {mx} |")
    lines.append("")
    return "\n".join(lines)


def run() -> str:
    REPORTS.mkdir(exist_ok=True)
    parts = ["# Data profile (samples)", ""]
    for pat in PATTERNS:
        for p in sorted(DATA.glob(pat)):
            if p.name.startswith(SKIP_PREFIXES):
                continue
            try:
                parts.append(profile(p))
                print("OK  ", p.relative_to(DATA))
            except Exception as e:  # noqa: BLE001
                parts.append(f"## {p.relative_to(DATA)}\n\nProfiling error: {e}\n")
                print("FAIL", p.relative_to(DATA), e, file=sys.stderr)
    out = REPORTS / "data_profile.md"
    out.write_text("\n".join(parts), encoding="utf-8")
    print("Saved", out)
    return str(out)


if __name__ == "__main__":
    run()
