"""
clean_epa.py
------------
Clean raw EPA AQS daily rows into one tidy row per (reference site, date) with
PM2.5 and NO2 daily means plus EPA's own AQI.

Input:  data/raw/epa_aqs_daily.csv   (from extract_epa.py)
Output: data/clean/epa_reference_daily.csv

AQS returns one row per (site, parameter, POC, sample duration, pollutant
standard), so a single site/day can have several PM2.5 rows. We collapse to one
value per site/day: mean of ``arithmetic_mean`` and the max reported ``aqi``
(AQI is only populated on rows tied to the primary NAAQS standard).
"""

from __future__ import annotations

import pandas as pd
from _common import CLEAN_DIR, EPA_CLEANED, EPA_RAW, setup_logging

PM25_PARAM = "88101"
NO2_PARAM = "42602"

log = setup_logging(__name__)


def _site_id(df: pd.DataFrame) -> pd.Series:
    """Build a stable AQS site id: state-county-site (zero-padded parts)."""
    state = df["state_code"].astype(str).str.zfill(2)
    county = df["county_code"].astype(str).str.zfill(3)
    site = df["site_number"].astype(str).str.zfill(4)
    return state + "-" + county + "-" + site


def _one_param(df: pd.DataFrame, param_code: str, value_name: str, aqi_name: str) -> pd.DataFrame:
    """Collapse one parameter's rows to one value per (site, date)."""
    sub = df[df["parameter_code"].astype(str) == param_code].copy()
    if sub.empty:
        return pd.DataFrame(
            columns=["site_id", "date", "site_name", "latitude", "longitude", value_name, aqi_name]
        )

    sub["arithmetic_mean"] = pd.to_numeric(sub["arithmetic_mean"], errors="coerce")
    sub["aqi"] = pd.to_numeric(sub.get("aqi"), errors="coerce")

    grouped = (
        sub.groupby(["site_id", "date"], as_index=False)
        .agg(
            site_name=("local_site_name", "first"),
            latitude=("latitude", "first"),
            longitude=("longitude", "first"),
            **{value_name: ("arithmetic_mean", "mean"), aqi_name: ("aqi", "max")},
        )
    )
    return grouped


def clean_epa_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Transform raw AQS daily rows into one tidy row per (site, date).

    Pure function (no I/O) so it can be unit-tested with a small fixture.
    """
    if df.empty:
        return pd.DataFrame(
            columns=[
                "site_id", "date", "site_name", "latitude", "longitude",
                "pm25_mean", "pm25_aqi", "no2_mean", "no2_aqi",
            ]
        )

    df = df.copy()
    df.columns = df.columns.str.lower()
    df["date"] = pd.to_datetime(df["date_local"], errors="coerce").dt.date
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    df["site_id"] = _site_id(df)

    pm25 = _one_param(df, PM25_PARAM, "pm25_mean", "pm25_aqi")
    no2 = _one_param(df, NO2_PARAM, "no2_mean", "no2_aqi")

    merged = pd.merge(
        pm25,
        no2,
        on=["site_id", "date", "site_name", "latitude", "longitude"],
        how="outer",
    )
    return merged.sort_values(["site_id", "date"]).reset_index(drop=True)


def main() -> None:
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)

    if not EPA_RAW.exists():
        log.warning("Raw EPA file not found: %s — skipping (run extract_epa.py first).", EPA_RAW)
        return

    df = pd.read_csv(EPA_RAW)
    log.info("Loaded %d raw EPA rows.", len(df))

    clean = clean_epa_frame(df)
    clean.to_csv(EPA_CLEANED, index=False)
    log.info("Saved cleaned EPA reference file → %s  (%d rows)", EPA_CLEANED, len(clean))

    if not clean.empty:
        log.info("Sites: %d   Date range: %s → %s",
                 clean["site_id"].nunique(), clean["date"].min(), clean["date"].max())
        if "pm25_mean" in clean and clean["pm25_mean"].notna().any():
            log.info("PM2.5 mean=%.1f  max=%.1f",
                     clean["pm25_mean"].mean(), clean["pm25_mean"].max())


if __name__ == "__main__":
    main()
