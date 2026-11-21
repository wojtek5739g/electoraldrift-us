"""Bluesky Jetstream - live stream of new posts (WebSocket, JSON).

URL: wss://jetstream2.us-east.bsky.network/subscribe?wantedCollections=app.bsky.feed.post
No key. Posts about US elections/politics are kept (KEYWORDS list).
The script also measures stream velocity (messages/s) for the report.

Target design: the producer publishes records to Redpanda (topic raw_social);
in this sample they are written to JSONL.
Output: data/bronze/bluesky/posts_<YYYYmmdd_HHMMSS>.jsonl
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
from datetime import datetime

import websockets

from common import BRONZE, get_logger, write_manifest

SOURCE = "bluesky"
URL = "wss://jetstream2.us-east.bsky.network/subscribe?wantedCollections=app.bsky.feed.post"
KEYWORDS = ["election", "ballot", "vote", "voting", "voter", "polling place", "early voting",
            "mail-in", "democrat", "republican", "gop", "senate", "congress", "rigged", "fraud"]
PATTERN = re.compile(r"\b(" + "|".join(re.escape(k) for k in KEYWORDS) + r")", re.IGNORECASE)
log = get_logger(SOURCE)


def extract(msg: dict) -> dict | None:
    c = msg.get("commit") or {}
    if msg.get("kind") != "commit" or c.get("operation") != "create":
        return None
    rec = c.get("record") or {}
    text = rec.get("text") or ""
    if not PATTERN.search(text):
        return None
    return {"did": msg.get("did"), "time_us": msg.get("time_us"), "created_at": rec.get("createdAt"),
            "langs": rec.get("langs"), "text": text, "rkey": c.get("rkey")}


async def consume(seconds: int) -> str:
    out = BRONZE / SOURCE / f"posts_{datetime.now():%Y%m%d_%H%M%S}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    seen = kept = 0
    t0 = time.time()
    async with websockets.connect(URL, max_size=2**22) as ws:
        with open(out, "w", encoding="utf-8") as f:
            while time.time() - t0 < seconds:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=10)
                except asyncio.TimeoutError:
                    continue
                seen += 1
                rec = extract(json.loads(raw))
                if rec:
                    kept += 1
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    dt = time.time() - t0
    log.info("Bluesky: %d messages in %.0fs (%.1f/s), political posts kept: %d -> %s",
             seen, dt, seen / dt, kept, out)
    write_manifest(SOURCE, URL, out, "ok", seconds=round(dt), msgs_seen=seen, msgs_kept=kept,
                   msgs_per_sec=round(seen / dt, 1))
    return str(out)


def run(seconds: int = 60) -> str:
    return asyncio.run(consume(seconds))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--seconds", type=int, default=60)
    run(p.parse_args().seconds)
