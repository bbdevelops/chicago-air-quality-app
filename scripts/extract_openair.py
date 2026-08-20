"""
extract_openair.py
------------------
Pull Open Air Chicago *Day Aggregations* from the Chicago Data Portal
via the Socrata SODA API.

Dataset: Open Air Chicago Day Aggregations
Socrata ID: rtmx-vkjr
Endpoint:   data.cityofchicago.org/resource/rtmx-vkjr.json

Using daily aggregations (not the 4.2 M-row individual measurements)
because daily means align naturally with daily complaint counts and keep
the data volume manageable (~286 sensors × ~180 days ≈ 51 K rows).

Respectful API usage:
  - App token from .env
  - CSV cache with 24 h freshness check
  - 1 s sleep between paginated requests
  - $select to pull only needed columns
  - $where date filter to limit payload
"""

import argparse
import configparser
import logging
import os
import sys
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sodapy import Socrata

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = PROJECT_ROOT / "config.ini"

config = configparser.ConfigParser()
config.read(CONFIG_FILE)

SOCRATA_CONFIG = config["socrata"]
DATASET_ID = SOCRATA_CONFIG["openair_dataset_id"]
DOMAIN = SOCRATA_CONFIG["domain"]
BATCH_SIZE = int(SOCRATA_CONFIG["batch_size"])
CACHE_MAX_AGE_HOURS = int(SOCRATA_CONFIG["cache_max_age_hours"])
START_DATE = SOCRATA_CONFIG["start_date"]
APP_TOKEN_ENV_VAR = SOCRATA_CONFIG["app_token_env_var"]
APP_SECRET_ENV_VAR = SOCRATA_CONFIG["app_secret_env_var"]


# Only pull the columns we need — keeps payload small
# Actual column names from the Day Aggregations dataset:
#   startofperiod  (not "time")
#   pm2_5concmass24hourmean_value  (not "pm2_5ConcMassDay_mean_value")
#   no2conc24hourmean_value        (not "no2ConcDay_mean_value")
SELECT_COLS = (
    "datasourceid, startofperiod, sensor_name, "
    "pm2_5concmass24hourmean_value, "
    "no2conc24hourmean_value, "
    "latitude, longitude"
)

RAW_DIR = PROJECT_ROOT / "data" / "raw"
CACHE_FILE = RAW_DIR / "openair_daily.csv"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def cache_is_fresh(path: Path, max_age_hours: float) -> bool:
    if not path.exists():
        return False
    age_hours = (time.time() - path.stat().st_mtime) / 3600
    return age_hours < max_age_hours


def _make_client(app_token: str | None, app_secret: str | None, timeout: int = 120) -> Socrata:
    """Create a Socrata client with optional HTTP Basic Auth."""
    if app_token and app_secret:
        return Socrata(DOMAIN, app_token, username=app_token,
                       password=app_secret, timeout=timeout)
    return Socrata(DOMAIN, app_token, timeout=timeout)


def pull_openair(app_token: str | None, app_secret: str | None = None) -> pd.DataFrame:
    """Download daily sensor aggregations from the Socrata API."""
    where_clause = f"startofperiod >= '{START_DATE}'"

    all_rows: list[dict] = []
    offset = 0

    def _get(cl, use_select=True, **kwargs):
        params = dict(where=where_clause, limit=BATCH_SIZE, order="startofperiod ASC", **kwargs)
        if use_select:
            params["select"] = SELECT_COLS
        return cl.get(DATASET_ID, **params)

    # Try authenticated → token-only → unauthenticated
    client = None
    batch = []
    for attempt, (tok, sec) in enumerate([
        (app_token, app_secret),
        (app_token, None),
        (None, None),
    ]):
        if attempt > 0 and tok == app_token and sec == app_secret:
            continue
        try:
            client = _make_client(tok, sec)
            log.info("Pulling Open Air Day Aggregations since %s (auth attempt %d) …",
                     START_DATE, attempt + 1)
            log.info("  GET  offset=%d  limit=%d", offset, BATCH_SIZE)
            batch = _get(client, offset=offset)
            break
        except Exception as e:
            err = str(e).lower()
            if "column" in err or "field" in err:
                log.warning("Column name issue with $select — retrying without: %s", e)
                try:
                    batch = _get(client, use_select=False, offset=offset)
                    break
                except Exception:
                    pass
            log.warning("Auth attempt %d failed: %s", attempt + 1, e)
            if attempt == 2:
                raise

    if batch:
        all_rows.extend(batch)
        offset += BATCH_SIZE

    # Continue paginating
    while len(batch) == BATCH_SIZE:
        time.sleep(1)  # respectful pacing
        log.info("  GET  offset=%d  limit=%d", offset, BATCH_SIZE)
        try:
            batch = _get(client, offset=offset)
        except Exception as e:
            if "column" in str(e).lower() or "field" in str(e).lower():
                log.warning("Column name issue — retrying without $select: %s", e)
                batch = _get(client, use_select=False, offset=offset)
            else:
                raise
        if not batch:
            break
        all_rows.extend(batch)
        offset += BATCH_SIZE

    client.close()

    df = pd.DataFrame.from_records(all_rows)
    log.info("Pulled %d rows  (columns: %s)", len(df), ", ".join(df.columns))
    return df


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract Open Air Chicago daily sensor aggregations"
    )
    parser.add_argument("--force", action="store_true", help="Ignore cache and re-pull")
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")
    app_token = os.getenv(APP_TOKEN_ENV_VAR)
    app_secret = os.getenv(APP_SECRET_ENV_VAR)

    if not app_token or app_token.startswith("PASTE"):
        log.warning(
            f"No valid {APP_TOKEN_ENV_VAR} in .env — throttled to 1 000 req/hr.  "
            "Register free: https://data.cityofchicago.org/profile/edit/developer"
        )
        app_token = None
        app_secret = None

    if not args.force and cache_is_fresh(CACHE_FILE, CACHE_MAX_AGE_HOURS):
        log.info("Cache is fresh (%s). Use --force to re-pull.", CACHE_FILE)
        df = pd.read_csv(CACHE_FILE)
        log.info("Loaded %d cached rows.", len(df))
        return

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    df = pull_openair(app_token, app_secret)

    if df.empty:
        log.error("No rows returned — check date filter or API connectivity.")
        sys.exit(1)

    # Dtype housekeeping — use actual column names from Day Aggregations
    time_col = "startofperiod" if "startofperiod" in df.columns else "time"
    if time_col in df.columns:
        df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
    for num_col in ("latitude", "longitude"):
        if num_col in df.columns:
            df[num_col] = pd.to_numeric(df[num_col], errors="coerce")
    # PM2.5 / NO2 columns
    for candidate in [
        "pm2_5concmass24hourmean_value",
        "no2conc24hourmean_value",
    ]:
        if candidate in df.columns:
            df[candidate] = pd.to_numeric(df[candidate], errors="coerce")

    df.to_csv(CACHE_FILE, index=False)
    log.info("Saved %d rows → %s", len(df), CACHE_FILE)

    # Summary
    time_col = "startofperiod" if "startofperiod" in df.columns else "time"
    if time_col in df.columns:
        log.info(
            "Date range: %s → %s",
            df[time_col].min(),
            df[time_col].max(),
        )
    if "sensor_name" in df.columns:
        log.info("Unique sensors: %d", df["sensor_name"].nunique())


if __name__ == "__main__":
    main()
