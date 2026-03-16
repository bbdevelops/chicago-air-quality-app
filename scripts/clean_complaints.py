"""
clean_complaints.py
-------------------
Clean the raw CDPH air-pollution complaints and spatially assign each
complaint to the nearest Open Air Chicago sensor using Haversine distance.

Inputs
------
  data/raw/cdph_air_complaints.csv   (from extract_complaints.py)
  data/raw/openair_daily.csv         (from extract_openair.py — used to
                                      build the sensor location lookup)

Outputs
-------
  data/clean/complaints_cleaned.csv          — one row per complaint
  data/clean/complaints_daily_by_sensor.csv  — daily complaint counts
                                               aggregated to nearest sensor
"""

import logging
from pathlib import Path

import numpy as np
import pandas as pd
from geopy.distance import great_circle

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
CLEAN_DIR = PROJECT_ROOT / "data" / "clean"

MAX_SENSOR_DISTANCE_M = 2_000  # flag complaints farther than 2 km

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def build_sensor_locations(openair_path: Path) -> pd.DataFrame:
    """
    Return a DataFrame with one row per sensor: sensor_name, lat, lon.
    Uses the median lat/lon across all daily records for each sensor.
    """
    df = pd.read_csv(openair_path)

    # Normalise column names to lowercase
    df.columns = df.columns.str.lower()

    for col in ("latitude", "longitude"):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    sensors = (
        df.dropna(subset=["latitude", "longitude"])
        .groupby("sensor_name", as_index=False)
        .agg(sensor_lat=("latitude", "median"), sensor_lon=("longitude", "median"))
    )
    log.info("Built location lookup for %d sensors.", len(sensors))
    return sensors


def find_nearest_sensor(
    lat: float, lon: float, sensors: pd.DataFrame
) -> tuple[str, float]:
    """
    Return (sensor_name, distance_in_metres) for the closest sensor.
    Uses Haversine via geopy.
    """
    dists = sensors.apply(
        lambda row: great_circle(
            (lat, lon), (row["sensor_lat"], row["sensor_lon"])
        ).meters,
        axis=1,
    )
    idx = dists.idxmin()
    return sensors.loc[idx, "sensor_name"], dists[idx]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)

    # ---- Load raw complaints ------------------------------------------------
    raw_path = RAW_DIR / "cdph_air_complaints.csv"
    if not raw_path.exists():
        log.error("Raw complaints file not found: %s  — run extract_complaints.py first.", raw_path)
        return

    df = pd.read_csv(raw_path, parse_dates=["complaint_date"])
    log.info("Loaded %d raw complaints.", len(df))

    # ---- Drop rows missing date or location ---------------------------------
    before = len(df)
    df = df.dropna(subset=["complaint_date", "latitude", "longitude"])
    log.info("Dropped %d rows with missing date/location (%d remaining).", before - len(df), len(df))

    # ---- Parse dates & add time features ------------------------------------
    df["date"] = df["complaint_date"].dt.date
    df["day_of_week"] = df["complaint_date"].dt.day_name()
    df["month"] = df["complaint_date"].dt.month

    # ---- Spatial join: nearest sensor ---------------------------------------
    openair_path = RAW_DIR / "openair_daily.csv"
    if not openair_path.exists():
        log.error("Open Air daily file not found: %s  — run extract_openair.py first.", openair_path)
        return

    sensors = build_sensor_locations(openair_path)

    log.info("Assigning each complaint to nearest sensor (Haversine) …")
    nearest = df.apply(
        lambda row: find_nearest_sensor(row["latitude"], row["longitude"], sensors),
        axis=1,
        result_type="expand",
    )
    df["nearest_sensor"] = nearest[0]
    df["distance_to_sensor_m"] = nearest[1].round(1)

    matched = (df["distance_to_sensor_m"] <= MAX_SENSOR_DISTANCE_M).sum()
    log.info(
        "Sensor match: %d / %d within %d m  (%.0f%%)",
        matched, len(df), MAX_SENSOR_DISTANCE_M,
        100 * matched / max(len(df), 1),
    )

    # ---- Save cleaned complaint-level file ----------------------------------
    out_path = CLEAN_DIR / "complaints_cleaned.csv"
    df.to_csv(out_path, index=False)
    log.info("Saved complaint-level file → %s  (%d rows)", out_path, len(df))

    # ---- Aggregate daily counts per sensor ----------------------------------
    daily = (
        df.groupby(["nearest_sensor", "date"])
        .agg(
            complaint_count=("complaint_id", "size"),
            mean_distance_m=("distance_to_sensor_m", "mean"),
        )
        .reset_index()
    )
    daily["date"] = pd.to_datetime(daily["date"])

    daily_path = CLEAN_DIR / "complaints_daily_by_sensor.csv"
    daily.to_csv(daily_path, index=False)
    log.info("Saved daily aggregation → %s  (%d rows)", daily_path, len(daily))


if __name__ == "__main__":
    main()
