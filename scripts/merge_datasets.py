"""
merge_datasets.py
-----------------
Join complaint daily counts with Open Air sensor daily readings to
produce the analysis-ready merged dataset.

Approach:
  - Start from ALL sensor-day combinations (so days with zero complaints
    are preserved — important for correlation analysis).
  - Aggregate complaints per sensor per day directly from the cleaned
    complaint-level file (no intermediate daily file).
  - Left-join the complaint counts.
  - Add lag/lead features for lead-lag analysis:
      pm25_lag1      — previous day's PM2.5 for the same sensor
      complaints_lead1 — next day's complaint count

Inputs
------
  data/clean/complaints_cleaned.csv
  data/clean/openair_daily_cleaned.csv

Output
------
  data/clean/merged_complaints_air.csv
"""

import pandas as pd
from _common import COMPLAINTS_CLEANED, MERGED_FILE, OPENAIR_CLEANED, setup_logging

log = setup_logging(__name__)


def _aggregate_complaints(comp: pd.DataFrame) -> pd.DataFrame:
    # ---- Aggregate complaints per sensor per day ----------------------------
    # Group directly from the cleaned complaint-level file so that every
    # complaint is counted regardless of whether it has a neighborhood.
    comp = comp.copy()
    comp["date"] = pd.to_datetime(comp["date"])
    comp_agg = (
        comp.groupby(["nearest_sensor", "date"], as_index=False, dropna=False)
        .agg(complaint_count=("complaint_id", "size"))
        .rename(columns={"nearest_sensor": "sensor_name"})
    )
    return comp_agg


def main() -> None:
    # ---- Load cleaned datasets ----------------------------------------------
    for p in (OPENAIR_CLEANED, COMPLAINTS_CLEANED):
        if not p.exists():
            log.error("Missing: %s — run cleaning scripts first.", p)
            return

    air = pd.read_csv(OPENAIR_CLEANED, parse_dates=["date"])
    comp = pd.read_csv(COMPLAINTS_CLEANED)

    log.info("Sensor readings: %d rows  |  Complaints (row-level): %d rows",
             len(air), len(comp))

    comp_agg = _aggregate_complaints(comp)

    # ---- Left join: keep all sensor-days, add complaint counts --------------
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
    merged.to_csv(MERGED_FILE, index=False)
    log.info("Saved merged dataset → %s  (%d rows, %d columns)",
             MERGED_FILE, len(merged), len(merged.columns))

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
