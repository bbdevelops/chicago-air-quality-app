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

import argparse
import sys
import time

import pandas as pd

from _common import COMPLAINTS_RAW, RAW_DIR, cache_is_fresh, setup_logging
from _socrata import load_socrata_config, load_token, make_client

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
_cfg = load_socrata_config()
DATASET_ID = _cfg["complaints_dataset_id"]
DOMAIN = _cfg["domain"]
BATCH_SIZE = _cfg["batch_size"]
CACHE_MAX_AGE_HOURS = _cfg["cache_max_age_hours"]
START_DATE = _cfg["start_date"]
APP_TOKEN_ENV_VAR = _cfg["app_token_env_var"]
APP_SECRET_ENV_VAR = _cfg["app_secret_env_var"]

log = setup_logging(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
            client = make_client(DOMAIN, tok, sec)
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

    app_token, app_secret = load_token(APP_TOKEN_ENV_VAR, APP_SECRET_ENV_VAR)

    # Check cache freshness
    if not args.force and cache_is_fresh(COMPLAINTS_RAW, CACHE_MAX_AGE_HOURS):
        log.info("Cache is fresh (%s). Use --force to re-pull.", COMPLAINTS_RAW)
        df = pd.read_csv(COMPLAINTS_RAW)
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

    df.to_csv(COMPLAINTS_RAW, index=False)
    log.info("Saved %d rows → %s", len(df), COMPLAINTS_RAW)

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
