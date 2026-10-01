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
  data/clean/complaints_cleaned.csv  — one row per complaint
"""

from pathlib import Path

import pandas as pd
from _common import CLEAN_DIR, COMPLAINTS_CLEANED, COMPLAINTS_RAW, OPENAIR_RAW, setup_logging

from aqi import haversine_km

MAX_SENSOR_DISTANCE_M = 2_000  # flag complaints farther than 2 km

log = setup_logging(__name__)


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
    Uses vectorized haversine_km from aqi module.
    """
    dists_km = haversine_km(lat, lon, sensors["sensor_lat"], sensors["sensor_lon"])
    idx = dists_km.idxmin()
    return sensors.loc[idx, "sensor_name"], dists_km[idx] * 1000


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)

    # ---- Load raw complaints ------------------------------------------------
    if not COMPLAINTS_RAW.exists():
        log.error("Raw complaints file not found: %s  — run extract_complaints.py first.", COMPLAINTS_RAW)
        return

    df = pd.read_csv(COMPLAINTS_RAW, parse_dates=["complaint_date"])
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
    if not OPENAIR_RAW.exists():
        log.error("Open Air daily file not found: %s  — run extract_openair.py first.", OPENAIR_RAW)
        return

    sensors = build_sensor_locations(OPENAIR_RAW)

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
    df.to_csv(COMPLAINTS_CLEANED, index=False)
    log.info("Saved complaint-level file → %s  (%d rows)", COMPLAINTS_CLEANED, len(df))


if __name__ == "__main__":
    main()
