"""
merge_datasets.py
-----------------
Join complaint daily counts with Open Air sensor daily readings to
produce the analysis-ready merged dataset.

Approach:
  - Start from ALL sensor-day combinations (so days with zero complaints
    are preserved — important for correlation analysis).
  - Left-join the complaint counts.
  - Add lag/lead features for lead-lag analysis:
      pm25_lag1      — previous day's PM2.5 for the same sensor
      complaints_lead1 — next day's complaint count

Inputs
------
  data/clean/complaints_daily_by_sensor.csv
  data/clean/openair_daily_cleaned.csv

Output
------
  data/clean/merged_complaints_air.csv
"""

import logging
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CLEAN_DIR = PROJECT_ROOT / "data" / "clean"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
log = logging.getLogger(__name__)


def main() -> None:
    # ---- Load cleaned datasets ----------------------------------------------
    air_path = CLEAN_DIR / "openair_daily_cleaned.csv"
    comp_path = CLEAN_DIR / "complaints_daily_by_sensor.csv"

    for p in (air_path, comp_path):
        if not p.exists():
            log.error("Missing: %s — run cleaning scripts first.", p)
            return

    air = pd.read_csv(air_path, parse_dates=["date"])
    comp = pd.read_csv(comp_path, parse_dates=["date"])

    log.info("Sensor readings: %d rows  |  Complaint aggregations: %d rows",
             len(air), len(comp))

    # Normalise join key name from complaints
    comp = comp.rename(columns={"nearest_sensor": "sensor_name"})

    # ---- Left join: keep all sensor-days, add complaint counts --------------
    # Only bring complaint_count from complaints (sensor's own neighborhood is
    # more meaningful for the merged spatial analysis)
    comp_agg = (
        comp.groupby(["sensor_name", "date"], as_index=False)["complaint_count"].sum()
    )

    merged = air.merge(
        comp_agg,
        on=["sensor_name", "date"],
        how="left",
    )
    merged["complaint_count"] = merged["complaint_count"].fillna(0).astype(int)

    log.info("Merged dataset: %d rows  (%d with complaints > 0)",
             len(merged), (merged["complaint_count"] > 0).sum())

    # ---- Lag / lead features ------------------------------------------------
    merged = merged.sort_values(["sensor_name", "date"])

    merged["pm25_lag1"] = merged.groupby("sensor_name")["pm25_mean"].shift(1)
    merged["pm25_lag2"] = merged.groupby("sensor_name")["pm25_mean"].shift(2)
    merged["complaints_lead1"] = (
        merged.groupby("sensor_name")["complaint_count"].shift(-1)
    )
    merged["complaints_lag1"] = (
        merged.groupby("sensor_name")["complaint_count"].shift(1)
    )

    # Rolling 7-day mean PM2.5 (sensor-level)
    merged["pm25_7d_mean"] = (
        merged.groupby("sensor_name")["pm25_mean"]
        .transform(lambda s: s.rolling(7, min_periods=3).mean())
    )

    # Binary spike flag: PM2.5 above EPA 24-hr standard (35 µg/m³)
    merged["pm25_spike"] = (merged["pm25_mean"] > 35).astype(int)

    # ---- Save ---------------------------------------------------------------
    out_path = CLEAN_DIR / "merged_complaints_air.csv"
    merged.to_csv(out_path, index=False)
    log.info("Saved merged dataset → %s  (%d rows, %d columns)",
             out_path, len(merged), len(merged.columns))

    # Summary
    log.info("Date range: %s → %s", merged["date"].min().date(), merged["date"].max().date())
    log.info("Sensors:    %d", merged["sensor_name"].nunique())
    log.info("Spike days (PM2.5 > 35): %d  (%.1f%%)",
             merged["pm25_spike"].sum(),
             100 * merged["pm25_spike"].mean())
    log.info("Days with complaints:    %d  (%.1f%%)",
             (merged["complaint_count"] > 0).sum(),
             100 * (merged["complaint_count"] > 0).mean())


if __name__ == "__main__":
    main()
