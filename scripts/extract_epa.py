"""
extract_epa.py
--------------
Pull EPA Air Quality System (AQS) *daily* reference-monitor data for
Cook County, Illinois (PM2.5 and NO2) from the AQS REST API.

Why: the Open Air Chicago sensors are low-cost devices. EPA AQS provides
regulatory-grade FRM/FEM monitor readings that let us validate the low-cost
network ("sensor vs. reference monitor") and supply an authoritative AQI.

API docs: https://aqs.epa.gov/aqsweb/documents/data_api.html
Endpoint: {api_base}/dailyData/byCounty
Auth:     email + key query params (register free; the key is emailed to you).

Respectful / correct API usage:
  - Credentials from .env (EPA_API_EMAIL / EPA_API_KEY).
  - AQS requires bdate/edate within a SINGLE calendar year, so requests are
    chunked by year.
  - PM2.5 (88101) and NO2 (42602) are requested together (AQS allows up to 5
    params per call).
  - A short sleep between calls; a CSV cache with a freshness check.

Output: data/raw/epa_aqs_daily.csv (raw daily rows for the cleaner to process).
"""

from __future__ import annotations

import argparse
import configparser
import logging
import os
import time
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = PROJECT_ROOT / "config.ini"

config = configparser.ConfigParser()
config.read(CONFIG_FILE)

EPA_CONFIG = config["epa"]
API_BASE = EPA_CONFIG["api_base"].rstrip("/")
EMAIL_ENV_VAR = EPA_CONFIG["email_env_var"]
KEY_ENV_VAR = EPA_CONFIG["key_env_var"]
STATE_CODE = EPA_CONFIG["state_code"]
COUNTY_CODE = EPA_CONFIG["county_code"]
PM25_PARAM = EPA_CONFIG["pm25_param"]
NO2_PARAM = EPA_CONFIG["no2_param"]

# Reuse the pipeline-wide start date from the socrata section for consistency.
START_DATE = config["socrata"]["start_date"]
CACHE_MAX_AGE_HOURS = int(config["socrata"].get("cache_max_age_hours", "24"))

RAW_DIR = PROJECT_ROOT / "data" / "raw"
CACHE_FILE = RAW_DIR / "epa_aqs_daily.csv"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
log = logging.getLogger(__name__)


def cache_is_fresh(path: Path, max_age_hours: float) -> bool:
    if not path.exists():
        return False
    age_hours = (time.time() - path.stat().st_mtime) / 3600
    return age_hours < max_age_hours


def _year_chunks(start: date, end: date) -> list[tuple[str, str]]:
    """Split [start, end] into (bdate, edate) YYYYMMDD strings per calendar year.

    AQS requires both dates to fall in the same year, so we clip each year to
    the overall range.
    """
    chunks: list[tuple[str, str]] = []
    for year in range(start.year, end.year + 1):
        b = max(start, date(year, 1, 1))
        e = min(end, date(year, 12, 31))
        if b <= e:
            chunks.append((b.strftime("%Y%m%d"), e.strftime("%Y%m%d")))
    return chunks


def pull_epa(email: str, key: str, start: date, end: date) -> pd.DataFrame:
    """Download daily PM2.5 + NO2 reference data for the configured county."""
    url = f"{API_BASE}/dailyData/byCounty"
    all_rows: list[dict] = []

    for i, (bdate, edate) in enumerate(_year_chunks(start, end)):
        params = {
            "email": email,
            "key": key,
            "param": f"{PM25_PARAM},{NO2_PARAM}",
            "bdate": bdate,
            "edate": edate,
            "state": STATE_CODE,
            "county": COUNTY_CODE,
        }
        if i > 0:
            time.sleep(2)  # respectful pacing between AQS calls
        log.info("GET dailyData/byCounty  %s → %s  (state=%s county=%s)",
                 bdate, edate, STATE_CODE, COUNTY_CODE)
        resp = requests.get(url, params=params, timeout=120)
        resp.raise_for_status()
        payload = resp.json()

        header = (payload.get("Header") or [{}])[0]
        status = header.get("status", "Unknown")
        if status not in ("Success", "No data matched your selection"):
            # Surface AQS error messages (bad key, throttling, etc.).
            raise RuntimeError(f"AQS returned status '{status}': {header.get('error') or header}")

        rows = payload.get("Data") or []
        log.info("  status=%s  rows=%d", status, len(rows))
        all_rows.extend(rows)

    df = pd.DataFrame.from_records(all_rows)
    log.info("Pulled %d total EPA daily rows.", len(df))
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract EPA AQS daily reference data (Cook County)")
    parser.add_argument("--force", action="store_true", help="Ignore cache and re-pull")
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")
    email = os.getenv(EMAIL_ENV_VAR)
    key = os.getenv(KEY_ENV_VAR)

    if not email or not key or key.upper().startswith("YOUR"):
        log.warning(
            "No valid %s / %s in .env — skipping EPA extraction. "
            "Register free at https://aqs.epa.gov/aqsweb/documents/data_api.html#signup",
            EMAIL_ENV_VAR, KEY_ENV_VAR,
        )
        # Not an error: EPA is an optional enrichment. Exit cleanly.
        return

    if not args.force and cache_is_fresh(CACHE_FILE, CACHE_MAX_AGE_HOURS):
        log.info("Cache is fresh (%s). Use --force to re-pull.", CACHE_FILE)
        return

    start = datetime.fromisoformat(START_DATE).date()
    end = datetime.now().date()

    df = pull_epa(email, key, start, end)
    if df.empty:
        log.warning("No EPA rows returned for %s → %s.", start, end)
        return

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(CACHE_FILE, index=False)
    log.info("Saved %d rows → %s", len(df), CACHE_FILE)
    if "date_local" in df.columns:
        log.info("Date range: %s → %s", df["date_local"].min(), df["date_local"].max())
    if "parameter" in df.columns:
        log.info("Parameters: %s", ", ".join(sorted(df["parameter"].dropna().unique())))


if __name__ == "__main__":
    main()
