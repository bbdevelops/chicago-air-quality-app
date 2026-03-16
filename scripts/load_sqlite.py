"""
load_sqlite.py
--------------
Load cleaned CSVs into a SQLite database for relational querying.

Creates three tables:
  - complaints       — one row per complaint (cleaned, with nearest sensor)
  - sensor_readings   — one row per sensor-day (cleaned daily aggregations)
  - daily_merged      — joined analysis table (sensor-day with complaint counts
                         and lag/lead features)

Input:   data/clean/*.csv
Output:  db/citizen_sensor.db
"""

import logging
import sqlite3
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CLEAN_DIR = PROJECT_ROOT / "data" / "clean"
DB_DIR = PROJECT_ROOT / "db"
DB_PATH = DB_DIR / "citizen_sensor.db"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------
DDL = """
DROP TABLE IF EXISTS complaints;
CREATE TABLE complaints (
    complaint_id        TEXT PRIMARY KEY,
    complaint_date      TEXT,   -- ISO date
    date                TEXT,   -- date only
    day_of_week         TEXT,
    month               INTEGER,
    latitude            REAL,
    longitude           REAL,
    nearest_sensor      TEXT,
    distance_to_sensor_m REAL,
    complaint_detail    TEXT,
    address             TEXT,
    complaint_type      TEXT,
    neighborhood        TEXT,
    neighborhood_secondary TEXT
);

DROP TABLE IF EXISTS sensor_readings;
CREATE TABLE sensor_readings (
    sensor_name         TEXT,
    sensor_id           TEXT,
    date                TEXT,   -- date only
    pm25_mean           REAL,
    no2_mean            REAL,
    lat                 REAL,
    lon                 REAL,
    pm25_outlier        INTEGER,
    neighborhood        TEXT,
    neighborhood_secondary TEXT,
    PRIMARY KEY (sensor_name, date)
);

DROP TABLE IF EXISTS daily_merged;
CREATE TABLE daily_merged (
    sensor_name         TEXT,
    date                TEXT,
    pm25_mean           REAL,
    no2_mean            REAL,
    complaint_count     INTEGER DEFAULT 0,
    pm25_lag1           REAL,
    pm25_lag2           REAL,
    complaints_lead1    INTEGER,
    complaints_lag1     INTEGER,
    pm25_7d_mean        REAL,
    pm25_spike          INTEGER,
    lat                 REAL,
    lon                 REAL,
    neighborhood        TEXT,
    neighborhood_secondary TEXT,
    PRIMARY KEY (sensor_name, date)
);
"""


def main() -> None:
    DB_DIR.mkdir(parents=True, exist_ok=True)

    # ---- Connect & create schema -------------------------------------------
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(DDL)
    log.info("Created schema in %s", DB_PATH)

    # ---- Load complaints ---------------------------------------------------
    comp_path = CLEAN_DIR / "complaints_cleaned.csv"
    if comp_path.exists():
        df = pd.read_csv(comp_path)
        # Keep only columns that exist in the table
        keep = [
            "complaint_id", "complaint_date", "date", "day_of_week", "month",
            "latitude", "longitude", "nearest_sensor", "distance_to_sensor_m",
            "complaint_detail", "address", "complaint_type",
            "neighborhood", "neighborhood_secondary",
        ]
        df = df[[c for c in keep if c in df.columns]]
        # Deduplicate on complaint_id (source data may have dupes)
        if "complaint_id" in df.columns:
            before = len(df)
            df = df.drop_duplicates(subset=["complaint_id"], keep="first")
            if len(df) < before:
                log.warning("Dropped %d duplicate complaint_id rows.", before - len(df))
        df.to_sql("complaints", conn, if_exists="append", index=False)
        log.info("Loaded %d rows → complaints", len(df))
    else:
        log.warning("Skipping complaints — file not found: %s", comp_path)

    # ---- Load sensor readings -----------------------------------------------
    air_path = CLEAN_DIR / "openair_daily_cleaned.csv"
    if air_path.exists():
        df = pd.read_csv(air_path)
        keep = ["sensor_name", "sensor_id", "date", "pm25_mean", "no2_mean",
                "lat", "lon", "pm25_outlier",
                "neighborhood", "neighborhood_secondary"]
        df = df[[c for c in keep if c in df.columns]]
        df.to_sql("sensor_readings", conn, if_exists="append", index=False)
        log.info("Loaded %d rows → sensor_readings", len(df))
    else:
        log.warning("Skipping sensor_readings — file not found: %s", air_path)

    # ---- Load merged ---------------------------------------------------------
    merged_path = CLEAN_DIR / "merged_complaints_air.csv"
    if merged_path.exists():
        df = pd.read_csv(merged_path)
        keep = [
            "sensor_name", "date", "pm25_mean", "no2_mean",
            "complaint_count", "pm25_lag1", "pm25_lag2",
            "complaints_lead1", "complaints_lag1",
            "pm25_7d_mean", "pm25_spike", "lat", "lon",
            "neighborhood", "neighborhood_secondary",
        ]
        df = df[[c for c in keep if c in df.columns]]
        df.to_sql("daily_merged", conn, if_exists="append", index=False)
        log.info("Loaded %d rows → daily_merged", len(df))
    else:
        log.warning("Skipping daily_merged — file not found: %s", merged_path)

    conn.close()
    log.info("Done — database: %s", DB_PATH)


if __name__ == "__main__":
    main()
