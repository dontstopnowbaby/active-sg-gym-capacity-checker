#!/usr/bin/env python3
"""
Hougang ActiveSG Gym capacity poller (GitHub Actions edition).

Fetches the current capacity from the (unofficial, reverse-engineered)
ActiveSG tRPC endpoint, appends a row to data/capacity.csv, and rebuilds
docs/data.json which the GitHub Pages dashboard reads.

This endpoint is undocumented and may change or start rate-limiting without
notice -- failures are logged, not raised, so a bad run doesn't break the
Pages site or crash the whole Action.
"""

import csv
import json
import logging
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

API_URL = (
    "https://activesg.gov.sg/api/trpc/pass.getFacilityCapacities"
    "?input=%7B%22json%22%3Anull%2C%22meta%22%3A%7B%22values%22%3A%5B%22undefined%22%5D%7D%7D"
)
FACILITY_ID = "XcptrxSXxwEMzzOdhC4e8"  # Hougang ActiveSG Gym
FACILITY_NAME = "Hougang ActiveSG Gym"
SGT = ZoneInfo("Asia/Singapore")
TIMEOUT_SECONDS = 10

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "data" / "capacity.csv"
JSON_PATH = ROOT / "docs" / "data.json"
FIELDNAMES = ["timestamp", "date", "hour", "weekday", "capacity_percentage", "is_closed"]

# Keep the line-chart payload from growing forever: ~14 days of hourly points.
MAX_RECENT_POINTS = 24 * 14

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def fetch_capacity() -> dict:
    req = Request(
        API_URL,
        headers={
            "accept": "*/*",
            "user-agent": "Mozilla/5.0 (compatible; hourly-capacity-logger/1.0)",
        },
    )
    with urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    for gym in payload["result"]["data"]["json"]["gymFacilities"]:
        if gym["id"] == FACILITY_ID:
            return gym
    raise ValueError(f"Facility id {FACILITY_ID} not found in response")


def load_existing_rows() -> list[dict]:
    if not CSV_PATH.exists():
        return []
    with open(CSV_PATH, newline="") as f:
        return list(csv.DictReader(f))


def append_row(row: dict) -> None:
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_header = not CSV_PATH.exists()
    with open(CSV_PATH, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def build_dashboard(rows: list[dict]) -> dict:
    hour_stats: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        if str(r.get("is_closed", "")).strip().lower() == "true":
            continue
        try:
            pct = float(r["capacity_percentage"])
        except (TypeError, ValueError):
            continue
        hour_stats[r["hour"]].append(pct)

    hourly_average = [
        {"hour": hour, "avg_capacity": round(sum(vals) / len(vals), 1), "samples": len(vals)}
        for hour, vals in sorted(hour_stats.items())
    ]
    quietest_hours = sorted(hourly_average, key=lambda x: x["avg_capacity"])[:5]

    return {
        "facility_name": FACILITY_NAME,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "hourly_average": hourly_average,
        "quietest_hours": quietest_hours,
        "recent_readings": rows[-MAX_RECENT_POINTS:],
    }


def write_dashboard(dashboard: dict) -> None:
    JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(json.dumps(dashboard, indent=2))


def main() -> int:
    rows = load_existing_rows()

    try:
        gym = fetch_capacity()
    except (HTTPError, URLError) as e:
        log.error("Network/API error fetching capacity: %s", e)
        # Still rebuild the dashboard from existing data so the Pages site
        # doesn't go stale-looking or break on a transient failure.
        write_dashboard(build_dashboard(rows))
        return 1
    except (KeyError, ValueError, json.JSONDecodeError) as e:
        log.error("Unexpected response shape (API may have changed): %s", e)
        write_dashboard(build_dashboard(rows))
        return 1

    now = datetime.now(SGT)
    row = {
        "timestamp": now.isoformat(timespec="seconds"),
        "date": now.strftime("%Y-%m-%d"),
        "hour": now.strftime("%H:00"),
        "weekday": now.strftime("%A"),
        "capacity_percentage": gym.get("capacityPercentage"),
        "is_closed": gym.get("isClosed", False),
    }
    append_row(row)
    rows.append(row)

    write_dashboard(build_dashboard(rows))
    log.info("%s: %s%% at %s SGT -> logged", FACILITY_NAME, row["capacity_percentage"], row["hour"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
