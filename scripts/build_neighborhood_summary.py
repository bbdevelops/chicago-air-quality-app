"""
build_neighborhood_summary.py
-----------------------------
Produce a single-row-per-neighborhood summary table that covers ALL 98
Chicago neighborhoods — including the 14 that have no Open Air sensors.

This file is designed to be the **data source joined to the GeoJSON**
in Tableau so every polygon gets its own name and colour on the map,
even when a neighbourhood has no sensor coverage.

Inputs
------
  data/Neighborhoods_2012b_20260228.csv     — boundary names (authority list)
  data/clean/openair_daily_cleaned.csv      — sensor readings with neighborhood
  data/clean/complaints_cleaned.csv         — complaints with neighborhood

Output
------
  data/clean/neighborhood_summary.csv       — one row per neighborhood
"""

import logging
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CLEAN_DIR = DATA_DIR / "clean"
NEIGHBORHOODS_CSV = DATA_DIR / "Neighborhoods_2012b_20260228.csv"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
log = logging.getLogger(__name__)


def main() -> None:
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)

    # ---- Authority list of all 98 neighborhoods ----------------------------
    bounds = pd.read_csv(NEIGHBORHOODS_CSV)
    all_neighs = (
        bounds[["PRI_NEIGH", "SEC_NEIGH"]]
        .rename(columns={"PRI_NEIGH": "neighborhood",
                          "SEC_NEIGH": "neighborhood_secondary"})
    )
    log.info("Authority list: %d neighborhoods.", len(all_neighs))

    # ---- Sensor-reading aggregates ------------------------------------------
    air_path = CLEAN_DIR / "openair_daily_cleaned.csv"
    if air_path.exists():
        air = pd.read_csv(air_path)
        sensor_agg = (
            air.groupby("neighborhood", as_index=False)
            .agg(
                sensor_count=("sensor_name", "nunique"),
                reading_days=("date", "nunique"),
                pm25_mean=("pm25_mean", "mean"),
                pm25_median=("pm25_mean", "median"),
                pm25_max=("pm25_mean", "max"),
                pm25_min=("pm25_mean", "min"),
                pm25_std=("pm25_mean", "std"),
                no2_mean=("no2_mean", "mean"),
                spike_days=("pm25_outlier", "sum"),
            )
        )
        sensor_agg = sensor_agg.round(2)
    else:
        log.warning("Sensor data not found — skipping air quality metrics.")
        sensor_agg = pd.DataFrame(columns=["neighborhood"])

    # ---- Complaint aggregates -----------------------------------------------
    comp_path = CLEAN_DIR / "complaints_cleaned.csv"
    if comp_path.exists():
        comp = pd.read_csv(comp_path)
        comp_agg = (
            comp.groupby("neighborhood", as_index=False)
            .agg(
                total_complaints=("complaint_id", "nunique"),
                complaint_days=("date", "nunique"),
            )
        )
    else:
        log.warning("Complaint data not found — skipping complaint metrics.")
        comp_agg = pd.DataFrame(columns=["neighborhood"])

    # ---- Merge everything onto the authority list ---------------------------
    summary = all_neighs.merge(sensor_agg, on="neighborhood", how="left")
    summary = summary.merge(comp_agg, on="neighborhood", how="left")

    # Fill NaN counts with 0, leave means as NaN (Tableau will show "no data")
    for col in ("sensor_count", "reading_days", "spike_days",
                "total_complaints", "complaint_days"):
        if col in summary.columns:
            summary[col] = summary[col].fillna(0).astype(int)

    # Flag neighborhoods without sensor coverage
    summary["has_sensor_coverage"] = (summary["sensor_count"] > 0).astype(int)

    # Sort by PM2.5 descending (neighborhoods without data sink to the bottom)
    summary = summary.sort_values("pm25_mean", ascending=False, na_position="last")

    # ---- Save ---------------------------------------------------------------
    out_path = CLEAN_DIR / "neighborhood_summary.csv"
    summary.to_csv(out_path, index=False)
    log.info("Saved → %s  (%d rows, %d columns)", out_path, len(summary), len(summary.columns))

    # ---- Report -------------------------------------------------------------
    with_data = (summary["has_sensor_coverage"] == 1).sum()
    without = (summary["has_sensor_coverage"] == 0).sum()
    log.info("Neighborhoods WITH sensor data:  %d", with_data)
    log.info("Neighborhoods WITHOUT sensors:   %d", without)
    if without:
        missing = summary.loc[summary["has_sensor_coverage"] == 0, "neighborhood"].tolist()
        log.info("  No-sensor list: %s", ", ".join(missing))


if __name__ == "__main__":
    main()
