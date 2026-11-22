"""FAA NAS Status - current delays, ground stops and closures at US airports (XML), every 60 s.
Live counterpart of the historical BTS data (air transport disruption).

API: https://nasstatus.faa.gov/api/airport-status-information  (no key, public data)
Output: data/bronze/faa_nas/raw_<ts>.xml        - raw response of every poll
        data/bronze/faa_nas/events_<ts>.jsonl   - records: event type, airport, reason, delays
"""
from __future__ import annotations

import argparse
import json
import time
import xml.etree.ElementTree as ET
from datetime import datetime

from common import BRONZE, get_logger, make_session, now_utc, write_manifest

SOURCE = "faa_nas"
URL = "https://nasstatus.faa.gov/api/airport-status-information"
log = get_logger(SOURCE)


def parse(xml_text: str, polled_at: str) -> list[dict]:
    """Every element with an <ARPT> child is one event; all its leaf values become fields."""
    root = ET.fromstring(xml_text)
    out = []
    for dtype in root.iter("Delay_type"):
        dname = (dtype.findtext("Name") or "").strip()
        for el in dtype.iter():
            if el.find("ARPT") is None:
                continue
            rec = {"polled_at": polled_at, "delay_type": dname, "element": el.tag}
            for leaf in el.iter():
                if len(leaf) == 0 and leaf.text and leaf.text.strip():
                    rec[leaf.tag] = leaf.text.strip()
            out.append(rec)
    return out


def run(polls: int = 3, interval: int = 60) -> str:
    s = make_session()
    d = BRONZE / SOURCE
    d.mkdir(parents=True, exist_ok=True)
    out = d / f"events_{datetime.now():%Y%m%d_%H%M%S}.jsonl"
    total = 0
    with open(out, "w", encoding="utf-8") as f:
        for i in range(polls):
            r = s.get(URL, timeout=30)
            r.raise_for_status()
            polled = now_utc()
            (d / f"raw_{datetime.now():%Y%m%d_%H%M%S}.xml").write_text(r.text, encoding="utf-8")
            events = parse(r.text, polled)
            for e in events:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
            total += len(events)
            log.info("Poll %d/%d: %d airport events", i + 1, polls, len(events))
            if i < polls - 1:
                time.sleep(interval)
    write_manifest(SOURCE, URL, out, "ok", polls=polls, records=total)
    return str(out)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--polls", type=int, default=3)
    p.add_argument("--interval", type=int, default=60)
    a = p.parse_args()
    run(a.polls, a.interval)
