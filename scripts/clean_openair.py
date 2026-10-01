"""
clean_openair.py
----------------
Clean the raw Open Air Chicago Day Aggregations:
  - Convert timestamps from UTC → America/Chicago
    - Drop rows where both PM2.5 and NO2 are missing
  - Rename to clean snake_case columns
  - Flag outliers

Input:   data/raw/openair_daily.csv
Output:  data/clean/openair_daily_cleaned.csv
"""

import pandas as pd

from _common import CLEAN_DIR, OPENAIR_CLEANED, OPENAIR_RAW, setup_logging

PM25_OUTLIER_UPPER = 150.0   # µg/m³ — flag but keep
PM25_OUTLIER_LOWER = 0.0

log = setup_logging(__name__)


def main() -> None:
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)

    if not OPENAIR_RAW.exists():
        log.error("Raw file not found: %s  — run extract_openair.py first.", OPENAIR_RAW)
        return

    df = pd.read_csv(OPENAIR_RAW)
    log.info("Loaded %d raw rows.", len(df))

    # ---- Normalise column names to lowercase --------------------------------
    df.columns = df.columns.str.lower()

    # ---- Identify PM2.5 and NO2 columns (case-insensitive match) ------------
    pm25_col = None
    no2_col = None
    for c in df.columns:
        if "pm2_5" in c and "mass" in c and "mean" in c and "value" in c:
            pm25_col = c
        if "no2" in c and "mean" in c and "value" in c:
            no2_col = c

    if pm25_col is None:
        log.error("Could not identify PM2.5 mean column. Available: %s", list(df.columns))
        return

    log.info("PM2.5 column: %s", pm25_col)
    log.info("NO2 column:   %s", no2_col or "(not found)")

    # ---- Convert timestamp from UTC → Chicago --------------------------------
    # Day Aggregations use "startofperiod" (not "time")
    time_col = "startofperiod" if "startofperiod" in df.columns else "time"
    df[time_col] = pd.to_datetime(df[time_col], errors="coerce", utc=True)
    df[time_col] = df[time_col].dt.tz_convert("America/Chicago")

    # Extract date (local)
    df["date"] = df[time_col].dt.date

    # ---- Numeric coercion ---------------------------------------------------
    df[pm25_col] = pd.to_numeric(df[pm25_col], errors="coerce")
    if no2_col:
        df[no2_col] = pd.to_numeric(df[no2_col], errors="coerce")
    for col in ("latitude", "longitude"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # ---- Drop rows only when all pollutant values are missing --------------
    before = len(df)
    pollutant_cols = [pm25_col]
    if no2_col:
        pollutant_cols.append(no2_col)

    df = df.dropna(subset=pollutant_cols, how="all")
    log.info(
        "Dropped %d rows with both PM2.5 and NO2 missing (%d remaining).",
        before - len(df),
        len(df),
    )

    # ---- Flag outliers (keep them — just add flag) --------------------------
    df["pm25_outlier"] = (df[pm25_col] > PM25_OUTLIER_UPPER) | (df[pm25_col] < PM25_OUTLIER_LOWER)
    n_outliers = df["pm25_outlier"].sum()
    if n_outliers:
        log.warning("%d outlier rows flagged (PM2.5 outside [%.0f, %.0f]).",
                    n_outliers, PM25_OUTLIER_LOWER, PM25_OUTLIER_UPPER)

    # ---- Rename to clean schema --------------------------------------------
    rename_map = {
        "datasourceid": "sensor_id",
        pm25_col: "pm25_mean",
        "latitude": "lat",
        "longitude": "lon",
    }
    if no2_col:
        rename_map[no2_col] = "no2_mean"

    df = df.rename(columns=rename_map)

    # Keep only the columns we need
    keep = ["sensor_id", "sensor_name", "date", "pm25_mean", "lat", "lon", "pm25_outlier"]
    if "no2_mean" in df.columns:
        keep.insert(4, "no2_mean")
    df = df[[c for c in keep if c in df.columns]]

    # ---- Save ---------------------------------------------------------------
    df.to_csv(OPENAIR_CLEANED, index=False)
    log.info("Saved cleaned file → %s  (%d rows)", OPENAIR_CLEANED, len(df))

    # Summary
    log.info("Date range:     %s → %s", df["date"].min(), df["date"].max())
    log.info("Unique sensors: %d", df["sensor_name"].nunique() if "sensor_name" in df.columns else "?")
    log.info("PM2.5 stats:    mean=%.1f  median=%.1f  max=%.1f",
             df["pm25_mean"].mean(), df["pm25_mean"].median(), df["pm25_mean"].max())


if __name__ == "__main__":
    main()
