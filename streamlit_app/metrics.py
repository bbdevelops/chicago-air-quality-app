"""Filtering and aggregation of the merged sensor-day table into the views the dashboard shows.

Purpose: turn pipeline frames into city-daily, per-sensor and per-neighborhood metrics.
Inputs:  frames from ``loading.PipelineData`` (merged sensor-days, neighborhood summary).
Outputs: small DataFrames ready to plot; every function returns a new frame.
Used by: streamlit_app/app.py, estimation.py (consumes the sensor snapshot and neighborhood metrics).
"""

from __future__ import annotations

import pandas as pd


def filter_by_date_range(
    df: pd.DataFrame,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
    neighborhoods: list[str] | None = None,
    date_col: str = "date",
) -> pd.DataFrame:
    """Filter dataframe by date range and optional neighborhood list."""
    filtered = df[(df[date_col] >= start_date) & (df[date_col] <= end_date)]
    if neighborhoods:
        filtered = filtered[filtered["neighborhood"].isin(neighborhoods)]
    return filtered.copy()


def build_city_daily_metrics(merged: pd.DataFrame) -> pd.DataFrame:
    """Aggregate sensor-level rows to city-level daily metrics."""
    if merged.empty:
        return pd.DataFrame(
            columns=["date", "pm25_mean", "no2_mean", "complaint_count", "spike_sensor_days"]
        )

    city = (
        merged.groupby("date", as_index=False)
        .agg(
            pm25_mean=("pm25_mean", "mean"),
            no2_mean=("no2_mean", "mean"),
            complaint_count=("complaint_count", "sum"),
            spike_sensor_days=("pm25_spike", "sum"),
        )
        .sort_values("date")
    )
    return city


def build_sensor_snapshot(merged: pd.DataFrame) -> pd.DataFrame:
    """Build one row per sensor for map marker overlays."""
    if merged.empty:
        return pd.DataFrame(
            columns=[
                "sensor_name", "lat", "lon", "neighborhood",
                "pm25_mean", "no2_mean", "total_complaints", "active_days",
            ]
        )

    snapshot = (
        merged.groupby(["sensor_name", "lat", "lon", "neighborhood"], as_index=False)
        .agg(
            pm25_mean=("pm25_mean", "mean"),
            no2_mean=("no2_mean", "mean"),
            total_complaints=("complaint_count", "sum"),
            active_days=("date", "nunique"),
        )
    )
    return snapshot


def build_neighborhood_metrics(summary: pd.DataFrame, merged: pd.DataFrame) -> pd.DataFrame:
    """
    Build date-filtered neighborhood metrics while preserving all neighborhoods.

    This avoids empty buckets by ensuring every neighborhood
    remains present, even when there is no sensor coverage in the selected range.
    """
    base_cols = [
        "neighborhood", "neighborhood_secondary", "sensor_count",
        "reading_days", "has_sensor_coverage", "total_complaints",
    ]
    available_base = [c for c in base_cols if c in summary.columns]
    base = summary[available_base].drop_duplicates(subset=["neighborhood"])

    if merged.empty:
        out = base.copy()
        for col in ["pm25_mean_period", "no2_mean_period", "complaints_period", "active_sensors_period"]:
            out[col] = pd.NA
        return out

    period = (
        merged.groupby("neighborhood", as_index=False)
        .agg(
            pm25_mean_period=("pm25_mean", "mean"),
            no2_mean_period=("no2_mean", "mean"),
            complaints_period=("complaint_count", "sum"),
            active_sensors_period=("sensor_name", "nunique"),
        )
    )

    out = base.merge(period, on="neighborhood", how="left")
    return out
