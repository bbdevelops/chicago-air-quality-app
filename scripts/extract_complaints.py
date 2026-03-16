"""
extract_complaints.py
---------------------
Pull CDPH Environmental Complaints (Air Pollution Work Orders) from the
Chicago Data Portal via the Socrata SODA API.

Dataset: CDPH Environmental Complaints
Socrata ID: fypr-ksnz
Endpoint:   data.cityofchicago.org/resource/fypr-ksnz.json

Respectful API usage:
  - Loads app token from .env (10 000 req/hr vs. 1 000 without)
  - Caches results to CSV; skips re-pull if cache < 24 h old
  - 1-second sleep between paginated requests
  - Uses $where date filter to minimize payload
"""

import os
import sys
import time
import argparse
import logging
from pathlib import Path
import configparser

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
DATASET_ID = SOCRATA_CONFIG["complaints_dataset_id"]
DOMAIN = SOCRATA_CONFIG["domain"]
BATCH_SIZE = int(SOCRATA_CONFIG["batch_size"])
CACHE_MAX_AGE_HOURS = int(SOCRATA_CONFIG["cache_max_age_hours"])
START_DATE = SOCRATA_CONFIG["start_date"]
APP_TOKEN_ENV_VAR = SOCRATA_CONFIG["app_token_env_var"]
APP_SECRET_ENV_VAR = SOCRATA_CONFIG["app_secret_env_var"]

RAW_DIR = PROJECT_ROOT / "data" / "raw"
CACHE_FILE = RAW_DIR / "cdph_air_complaints.csv"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def cache_is_fresh(path: Path, max_age_hours: float) -> bool:
    """Return True if *path* exists and was modified less than *max_age_hours* ago."""
    if not path.exists():
        return False
    age_hours = (time.time() - path.stat().st_mtime) / 3600
    return age_hours < max_age_hours


def _make_client(app_token: str | None, app_secret: str | None, timeout: int = 60) -> Socrata:
    """
    Create a Socrata client.  Per the Socrata docs:
      - app_token  → sent as X-App-Token header (Key ID / public)
      - app_secret → used with app_token for HTTP Basic Auth (Key Secret / private)
    """
    if app_token and app_secret:
        # HTTP Basic Auth: Key ID as username, Key Secret as password
        return Socrata(DOMAIN, app_token, username=app_token,
                       password=app_secret, timeout=timeout)
    return Socrata(DOMAIN, app_token, timeout=timeout)


def pull_complaints(app_token: str | None, app_secret: str | None = None) -> pd.DataFrame:
    """Download air-pollution complaints from the Socrata API."""
    where_clause = (
        f"complaint_type = 'Air Pollution Work Order' "
        f"AND complaint_date >= '{START_DATE}'"
    )

    all_rows: list[dict] = []
    offset = 0

    # Try authenticated first, then token-only, then unauthenticated
    client = None
    for attempt, (tok, sec) in enumerate([
        (app_token, app_secret),   # full auth
        (app_token, None),         # token-only (no basic auth)
        (None, None),              # unauthenticated
    ]):
        if attempt > 0 and tok == app_token and sec == app_secret:
            continue  # skip duplicate combos
        try:
            client = _make_client(tok, sec)
            log.info("Pulling CDPH complaints since %s (auth attempt %d) …",
                     START_DATE, attempt + 1)
            log.info("  GET  offset=%d  limit=%d", offset, BATCH_SIZE)
            batch = client.get(
                DATASET_ID,
                where=where_clause,
                limit=BATCH_SIZE,
                offset=offset,
                order="complaint_date ASC",
            )
            break  # success
        except Exception as e:
            log.warning("Auth attempt %d failed: %s", attempt + 1, e)
            if attempt == 2:  # last attempt
                raise

    if batch:
        all_rows.extend(batch)
        offset += BATCH_SIZE

    # Continue paginating
    while len(batch) == BATCH_SIZE:
        time.sleep(1)  # Respectful pacing
        log.info("  GET  offset=%d  limit=%d", offset, BATCH_SIZE)
        batch = client.get(
            DATASET_ID,
            where=where_clause,
            limit=BATCH_SIZE,
            offset=offset,
            order="complaint_date ASC",
        )
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
    parser = argparse.ArgumentParser(description="Extract CDPH air-pollution complaints")
    parser.add_argument("--force", action="store_true", help="Ignore cache and re-pull")
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")
    app_token = os.getenv(APP_TOKEN_ENV_VAR)
    app_secret = os.getenv(APP_SECRET_ENV_VAR)

    if not app_token or app_token.startswith("PASTE"):
        log.warning(
            f"No valid {APP_TOKEN_ENV_VAR} found in .env — API requests will be "
            "throttled to 1 000/hr.  Register a free token at:\n"
            "  https://data.cityofchicago.org/profile/edit/developer"
        )
        app_token = None
        app_secret = None

    # Check cache freshness
    if not args.force and cache_is_fresh(CACHE_FILE, CACHE_MAX_AGE_HOURS):
        log.info("Cache is fresh (%s). Use --force to re-pull.", CACHE_FILE)
        df = pd.read_csv(CACHE_FILE)
        log.info("Loaded %d cached rows.", len(df))
        return

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    df = pull_complaints(app_token, app_secret)

    if df.empty:
        log.error("No rows returned — check date filter or API connectivity.")
        sys.exit(1)

    # Basic dtype housekeeping before caching
    if "complaint_date" in df.columns:
        df["complaint_date"] = pd.to_datetime(df["complaint_date"], errors="coerce")
    if "resolved_date" in df.columns:
        df["resolved_date"] = pd.to_datetime(df["resolved_date"], errors="coerce")
    for col in ("latitude", "longitude"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df.to_csv(CACHE_FILE, index=False)
    log.info("Saved %d rows → %s", len(df), CACHE_FILE)

    # Summary stats
    date_min = df["complaint_date"].min()
    date_max = df["complaint_date"].max()
    geocoded = df["latitude"].notna().sum()
    log.info(
        "Date range: %s → %s  |  Geocoded: %d / %d (%.0f%%)",
        date_min.date() if pd.notna(date_min) else "?",
        date_max.date() if pd.notna(date_max) else "?",
        geocoded,
        len(df),
        100 * geocoded / max(len(df), 1),
    )


if __name__ == "__main__":
    main()
