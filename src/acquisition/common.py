"""Shared helpers for data acquisition (Bronze layer).

- one HTTP session with a User-Agent (required e.g. by api.weather.gov),
- streaming file download with retries,
- manifest: every downloaded file is recorded in data/bronze/_manifest.jsonl
  (source, URL, size, timestamp, status) -> used by tests and the report.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
BRONZE = DATA / "bronze"
SILVER = DATA / "silver"
REFERENCE = DATA / "reference"
LOGS = ROOT / "logs"
REPORTS = ROOT / "reports"
MANIFEST = BRONZE / "_manifest.jsonl"

for _d in (BRONZE, SILVER, REFERENCE, LOGS, REPORTS):
    _d.mkdir(parents=True, exist_ok=True)

CONTACT = os.environ.get("EDUS_CONTACT", "student-project@example.com")
USER_AGENT = f"ElectoralDriftUS student project ({CONTACT})"


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s | %(name)s | %(levelname)s | %(message)s")
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    fh = logging.FileHandler(LOGS / f"{name}.log", encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(sh)
    logger.addHandler(fh)
    return logger


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    return s


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_manifest(source: str, url: str, dest: Path | None, status: str, **extra) -> None:
    rec = {
        "ts_utc": now_utc(),
        "source": source,
        "url": url,
        "path": str(dest.relative_to(ROOT)) if dest else None,
        "bytes": dest.stat().st_size if dest and dest.exists() else None,
        "status": status,
        **extra,
    }
    with open(MANIFEST, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _sleep_backoff(attempt: int, resp: requests.Response | None = None) -> None:
    wait = 2 ** attempt
    if resp is not None and resp.headers.get("Retry-After", "").isdigit():
        wait = int(resp.headers["Retry-After"])
    time.sleep(min(wait, 60))


def download(url: str, dest: Path, source: str, session: requests.Session | None = None,
             retries: int = 3, timeout: int = 120, overwrite: bool = False,
             params: dict | None = None) -> Path | None:
    """Stream a file to dest. Returns the path, or None on a client error (e.g. 404)."""
    log = get_logger(source)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0 and not overwrite:
        log.info("Already downloaded, skipping: %s", dest.name)
        return dest
    s = session or make_session()
    tmp = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(retries):
        resp = None
        try:
            resp = s.get(url, params=params, stream=True, timeout=timeout)
            if resp.status_code in (429, 500, 502, 503, 504):
                log.warning("HTTP %s, retrying (%s/%s)", resp.status_code, attempt + 1, retries)
                _sleep_backoff(attempt, resp)
                continue
            if 400 <= resp.status_code < 500:
                log.warning("HTTP %s (client error, not retrying): %s", resp.status_code, resp.url)
                write_manifest(source, resp.url, None, f"http_{resp.status_code}")
                return None
            resp.raise_for_status()
            with open(tmp, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1 << 20):
                    if chunk:
                        f.write(chunk)
            tmp.replace(dest)
            log.info("Downloaded %s (%.1f MB)", dest.name, dest.stat().st_size / 1e6)
            write_manifest(source, resp.url, dest, "ok")
            return dest
        except requests.RequestException as e:
            log.warning("Network error (%s/%s): %s", attempt + 1, retries, e)
            _sleep_backoff(attempt, resp)
    write_manifest(source, url, None, "failed")
    log.error("Download failed: %s", url)
    return None


def get_json(url: str, source: str, session: requests.Session | None = None,
             params: dict | None = None, headers: dict | None = None,
             retries: int = 3, timeout: int = 60):
    log = get_logger(source)
    s = session or make_session()
    for attempt in range(retries):
        resp = None
        try:
            resp = s.get(url, params=params, headers=headers, timeout=timeout)
            if resp.status_code in (429, 500, 502, 503, 504):
                log.warning("HTTP %s, retrying (%s/%s)", resp.status_code, attempt + 1, retries)
                _sleep_backoff(attempt, resp)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            log.warning("Error (%s/%s): %s", attempt + 1, retries, e)
            if resp is not None and resp.status_code in (400, 401, 403, 404):
                raise
            _sleep_backoff(attempt, resp)
    raise RuntimeError(f"Failed to fetch JSON: {url}")


def save_json(obj, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    return dest
