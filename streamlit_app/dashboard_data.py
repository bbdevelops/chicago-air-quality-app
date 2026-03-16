from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class PipelineData:
    merged: pd.DataFrame
    summary: pd.DataFrame
    neighborhoods_geojson: dict[str, Any]


def _clean_paths(project_root: Path) -> dict[str, Path]:
    clean_dir = project_root / "data" / "clean"
    return {
        "merged": clean_dir / "merged_complaints_air.csv",
        "summary": clean_dir / "neighborhood_summary.csv",
        "geojson": clean_dir / "chicago_neighborhoods.geojson",
    }


def load_pipeline_data(project_root: Path | None = None) -> PipelineData:
    """Load all Streamlit dashboard inputs produced by the pipeline."""
    root = project_root or Path(__file__).resolve().parents[1]
    paths = _clean_paths(root)

    missing = [name for name, path in paths.items() if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "Missing pipeline outputs for dashboard: "
            + ", ".join(f"{name} ({paths[name]})" for name in missing)
            + ". Run: python run_pipeline.py --skip-api"
        )

    merged = pd.read_csv(paths["merged"], parse_dates=["date"])
    summary = pd.read_csv(paths["summary"])
    with paths["geojson"].open("r", encoding="utf-8") as f:
        geojson = json.load(f)

    expected_merged = {
        "sensor_name", "date", "pm25_mean", "no2_mean", "lat", "lon",
        "complaint_count", "pm25_spike", "neighborhood",
    }
    missing_merged = expected_merged - set(merged.columns)
    if missing_merged:
        raise ValueError(f"merged_complaints_air.csv missing columns: {sorted(missing_merged)}")

    expected_summary = {"neighborhood", "sensor_count", "has_sensor_coverage"}
    missing_summary = expected_summary - set(summary.columns)
    if missing_summary:
        raise ValueError(f"neighborhood_summary.csv missing columns: {sorted(missing_summary)}")

    return PipelineData(merged=merged, summary=summary, neighborhoods_geojson=geojson)


def filter_merged_data(
    merged: pd.DataFrame,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
    neighborhoods: list[str] | None = None,
) -> pd.DataFrame:
    """Filter merged sensor-day data by date range and optional neighborhood list."""
    filtered = merged[(merged["date"] >= start_date) & (merged["date"] <= end_date)]
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

    This avoids Tableau's NULL-bucket behavior by ensuring every neighborhood
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


def compute_lag_correlations(city_daily: pd.DataFrame, max_lag: int = 7) -> pd.DataFrame:
    """
    Correlate PM2.5 at day t with complaints at day t+lag for lag in [-max_lag, +max_lag].
    Positive lag means complaints trail PM2.5 spikes.
    """
    if city_daily.empty:
        return pd.DataFrame(columns=["lag_days", "correlation"])

    rows: list[dict[str, float | int]] = []
    series = city_daily.sort_values("date")[["pm25_mean", "complaint_count"]]

    for lag in range(-max_lag, max_lag + 1):
        shifted = series["complaint_count"].shift(-lag)
        corr = series["pm25_mean"].corr(shifted)
        rows.append({"lag_days": lag, "correlation": corr})

    return pd.DataFrame(rows)


def compute_spike_concordance(
    city_daily: pd.DataFrame,
    threshold: float = 35.0,
    window_days: int = 2,
) -> tuple[pd.DataFrame, float]:
    """Summarize complaint activity around city-level PM2.5 spike days."""
    if city_daily.empty:
        return pd.DataFrame(columns=["offset_day", "mean_complaints", "total_complaints"]), float("nan")

    city = city_daily.sort_values("date").copy()
    city["is_spike"] = city["pm25_mean"] > threshold

    spike_dates = city.loc[city["is_spike"], "date"]
    baseline = city.loc[~city["is_spike"], "complaint_count"].mean()

    rows = []
    for offset in range(-window_days, window_days + 1):
        vals = []
        for spike_date in spike_dates:
            d = spike_date + pd.Timedelta(days=offset)
            match_rows = city.loc[city["date"] == d]
            if not match_rows.empty:
                vals.append(float(match_rows["complaint_count"].iloc[0]))

        if vals:
            rows.append(
                {
                    "offset_day": offset,
                    "mean_complaints": sum(vals) / len(vals),
                    "total_complaints": sum(vals),
                }
            )
        else:
            rows.append(
                {
                    "offset_day": offset,
                    "mean_complaints": float("nan"),
                    "total_complaints": 0.0,
                }
            )

    return pd.DataFrame(rows), float(baseline)
