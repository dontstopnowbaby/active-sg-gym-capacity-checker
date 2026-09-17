#!/usr/bin/env python3
"""
Hougang ActiveSG Gym capacity poller (GitHub Actions edition).

Fetches the current capacity from the (unofficial, reverse-engineered)
ActiveSG tRPC endpoint, records one reading, and rebuilds docs/data.json
which the GitHub Pages dashboard reads.

The poller is intended to be run once per hour by GitHub Actions. It keeps a
rolling seven-day window of hourly readings, so the dashboard's averages and
recent trend represent the current week rather than all historical data.

This endpoint is undocumented and may change or start rate-limiting without
notice -- failures are logged, not raised, so a bad run doesn't break the
Pages site or crash the whole Action.
"""

import csv
import json
import logging
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

API_URL = (
    "https://activesg.gov.sg/api/trpc/pass.getFacilityCapacities"
)
FACILITY_ID = "XcptrxSXxwEMzzOdhC4e8"  # Hougang ActiveSG Gym
FACILITY_NAME = "Hougang ActiveSG Gym"
SGT = ZoneInfo("Asia/Singapore")
TIMEOUT_SECONDS = 10
TRACKING_DAYS = 7

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "data" / "capacity.csv"
JSON_PATH = ROOT / "docs" / "data.json"
FIELDNAMES = ["timestamp", "date", "hour", "weekday", "capacity_percentage", "is_closed"]

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def fetch_capacity() -> dict:
    req = Request(
        API_URL,
        headers={
            "accept": "application/json, text/plain, */*",
            "accept-language": "en-US,en;q=0.9",
            "referer": "https://activesg.gov.sg/gym-pool-crowd",
            "user-agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"
            ),
        },
    )
    with urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    for gym in payload["result"]["data"]["json"]["gymFacilities"]:
        if gym["id"] == FACILITY_ID:
            return gym
    raise ValueError(f"Facility id {FACILITY_ID} not found in response")


def describe_error(e: Exception) -> str:
    """Turn an exception into a short, committable diagnostic string."""
    if isinstance(e, HTTPError):
        try:
            body = e.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            body = "<could not read body>"
        return f"HTTP {e.code} {e.reason} — body: {body}"
    if isinstance(e, URLError):
        return f"URLError: {e.reason}"
    return f"{type(e).__name__}: {e}"


def load_existing_rows() -> list[dict]:
    if not CSV_PATH.exists():
        return []
    with open(CSV_PATH, newline="") as f:
        return list(csv.DictReader(f))


def parse_timestamp(row: dict) -> datetime | None:
    try:
        timestamp = datetime.fromisoformat(row["timestamp"])
        return timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=SGT)
    except (KeyError, TypeError, ValueError):
        return None


def keep_week(rows: list[dict], now: datetime) -> list[dict]:
    """Keep only valid readings from the current rolling seven-day window."""
    cutoff = now - timedelta(days=TRACKING_DAYS)
    current_rows = [
        row for row in rows
        if (timestamp := parse_timestamp(row)) is not None and timestamp >= cutoff
    ]
    return sorted(current_rows, key=lambda row: parse_timestamp(row))


def write_rows(rows: list[dict]) -> None:
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CSV_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def build_dashboard(rows: list[dict], last_error: str | None = None) -> dict:
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
        "tracking_period_days": TRACKING_DAYS,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "hourly_average": hourly_average,
        "quietest_hours": quietest_hours,
        "recent_readings": rows,
        "last_error": last_error,
    }


def write_dashboard(dashboard: dict) -> None:
    JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(json.dumps(dashboard, indent=2))


def main() -> int:
    now = datetime.now(SGT)
    rows = load_existing_rows()

    try:
        gym = fetch_capacity()
    except (HTTPError, URLError, KeyError, ValueError, json.JSONDecodeError) as e:
        reason = describe_error(e)
        log.error("Poll failed: %s", reason)
        rows = keep_week(rows, now)
        write_rows(rows)
        write_dashboard(
            build_dashboard(
                rows,
                last_error=f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} — {reason}",
            )
        )
        # The fallback files are valid output. Return success so the workflow
        # can commit the updated dashboard and its visible error message.
        return 0

    row = {
        "timestamp": now.isoformat(timespec="seconds"),
        "date": now.strftime("%Y-%m-%d"),
        "hour": now.strftime("%H:00"),
        "weekday": now.strftime("%A"),
        "capacity_percentage": gym.get("capacityPercentage"),
        "is_closed": gym.get("isClosed", False),
    }
    rows = keep_week(rows + [row], now)
    write_rows(rows)
    write_dashboard(build_dashboard(rows))
    log.info(
        "%s: %s%% at %s SGT -> logged (%d readings in rolling %d-day window)",
        FACILITY_NAME,
        row["capacity_percentage"],
        row["hour"],
        len(rows),
        TRACKING_DAYS,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
