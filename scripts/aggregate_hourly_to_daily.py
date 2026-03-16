"""
aggregate_hourly_to_daily.py
----------------------------
Convert the large Open Air Chicago *Individual Measurements* CSV into
the same daily-aggregation format that the rest of the pipeline expects.

This lets you feed the 4M-row hourly file through the existing pipeline
instead of (or in addition to) pulling daily aggregations from the API.

Input:   Data Sets/Open_Air_Chicago_Individual_Measurements_20260220.csv
Output:  data/raw/openair_daily.csv  (overwrites the API-pulled cache)

Usage:
    python scripts/aggregate_hourly_to_daily.py
    python scripts/aggregate_hourly_to_daily.py --input "path/to/file.csv"

After running this, use:
    python run_pipeline.py --skip-api
"""

import argparse
import logging
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Default input — the large hourly file in Data Sets/
DEFAULT_INPUT = (
    PROJECT_ROOT
    / "Data Sets"
    / "Open_Air_Chicago_Individual_Measurements_20260220.csv"
)
OUTPUT_FILE = PROJECT_ROOT / "data" / "raw" / "openair_daily.csv"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
log = logging.getLogger(__name__)

# The columns we need from the individual-measurements file
USE_COLS = [
    "datasourceid",
    "time",
    "sensor_name",
    "pm2_5ConcMassIndividual.value",
    "no2ConcIndividual.value",
    "latitude",
    "longitude",
]

# Output column names must match what clean_openair.py expects from the
# daily aggregations dataset.


def weighted_reaggregate_daily(combined: pd.DataFrame) -> pd.DataFrame:
    """
    Re-aggregate partially aggregated chunk outputs into one row per
    (datasourceid, sensor_name, date) using reading-count weights.

    This is required because a sensor-day can appear in multiple read chunks.
    """
    if combined.empty:
        return combined.copy()

    required = {
        "datasourceid", "sensor_name", "date",
        "pm25_mean", "no2_mean", "latitude", "longitude", "reading_count",
    }
    missing = required - set(combined.columns)
    if missing:
        raise ValueError(f"combined is missing required columns: {sorted(missing)}")

    return (
        combined.groupby(["datasourceid", "sensor_name", "date"], as_index=False)
        .apply(
            lambda g: pd.Series({
                "pm25_mean": (g["pm25_mean"] * g["reading_count"]).sum()
                             / g["reading_count"].sum(),
                "no2_mean": (g["no2_mean"] * g["reading_count"]).sum()
                            / g["reading_count"].sum(),
                "latitude": g["latitude"].median(),
                "longitude": g["longitude"].median(),
                "reading_count": g["reading_count"].sum(),
            }),
            include_groups=False,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Aggregate hourly Open Air measurements into daily means"
    )
    parser.add_argument(
        "--input", "-i",
        type=Path,
        default=DEFAULT_INPUT,
        help="Path to the individual-measurements CSV",
    )
    args = parser.parse_args()

    input_path: Path = args.input
    if not input_path.exists():
        log.error("Input file not found: %s", input_path)
        return

    # ---- Read in chunks to keep memory manageable ---------------------------
    log.info("Reading %s (this may take a minute) …", input_path.name)
    chunks = pd.read_csv(
        input_path,
        usecols=USE_COLS,
        dtype={
            "datasourceid": str,
            "sensor_name": str,
        },
        chunksize=500_000,
    )

    daily_parts: list[pd.DataFrame] = []
    total_rows = 0

    for i, chunk in enumerate(chunks):
        total_rows += len(chunk)
        log.info("  chunk %d: %d rows (cumulative %d)", i + 1, len(chunk), total_rows)

        # Parse timestamps
        chunk["time"] = pd.to_datetime(chunk["time"], errors="coerce", format="mixed")

        # Coerce numeric columns
        for col in ["pm2_5ConcMassIndividual.value", "no2ConcIndividual.value",
                     "latitude", "longitude"]:
            chunk[col] = pd.to_numeric(chunk[col], errors="coerce")

        # Extract date for grouping
        chunk["date"] = chunk["time"].dt.date

        # Aggregate to daily means per sensor
        agg = (
            chunk.groupby(["datasourceid", "sensor_name", "date"], as_index=False)
            .agg(
                pm25_mean=("pm2_5ConcMassIndividual.value", "mean"),
                no2_mean=("no2ConcIndividual.value", "mean"),
                latitude=("latitude", "median"),
                longitude=("longitude", "median"),
                reading_count=("time", "size"),
            )
        )
        daily_parts.append(agg)

    # ---- Combine chunks & re-aggregate (a sensor-day may span chunks) -------
    log.info("Combining %d chunks …", len(daily_parts))
    combined = pd.concat(daily_parts, ignore_index=True)

    # Weighted re-aggregation for sensor-days that were split across chunks
    daily = weighted_reaggregate_daily(combined)

    # ---- Rename columns to match API daily-aggregation schema ---------------
    daily = daily.rename(columns={
        "pm25_mean": "pm2_5concmass24hourmean_value",
        "no2_mean": "no2conc24hourmean_value",
        "date": "startofperiod",
    })

    # Sort chronologically
    daily = daily.sort_values(["sensor_name", "startofperiod"]).reset_index(drop=True)

    # Drop the helper column
    daily = daily.drop(columns=["reading_count"])

    # ---- Save ---------------------------------------------------------------
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    daily.to_csv(OUTPUT_FILE, index=False)

    log.info("Aggregated %d hourly rows → %d daily rows", total_rows, len(daily))
    log.info("Saved → %s", OUTPUT_FILE)
    log.info("Sensors: %d", daily["sensor_name"].nunique())
    log.info("Date range: %s → %s",
             daily["startofperiod"].min(), daily["startofperiod"].max())
    log.info("")
    log.info("Next step:  python run_pipeline.py --skip-api")


if __name__ == "__main__":
    main()
