from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from shapely.geometry import shape

# ── EPA Air Quality Index (AQI) ────────────────────────────────────────────
# US EPA AQI breakpoints as (conc_low, conc_high, aqi_low, aqi_high).
#
# PM2.5 uses the **2024-revised** 24-hour breakpoints (effective 2024-05-06;
# EPA "Final Updates to the AQI for Particulate Matter" fact sheet). The daily
# ``pm25_mean`` in the pipeline is the correct 24-hour input. The open-ended
# "225.5+" Hazardous range is implemented as 225.5–325.4 → 301–500 (the AirNow
# calculator convention); concentrations above 325.4 are capped at AQI 500.
PM25_AQI_BREAKPOINTS: list[tuple[float, float, int, int]] = [
    (0.0, 9.0, 0, 50),
    (9.1, 35.4, 51, 100),
    (35.5, 55.4, 101, 150),
    (55.5, 125.4, 151, 200),
    (125.5, 225.4, 201, 300),
    (225.5, 325.4, 301, 500),
]

# NO2 1-hour breakpoints in ppb (unchanged in 2024). NOTE: a valid NO2 sub-index
# requires the daily *1-hour max*; our ``no2_mean`` is a daily mean, so
# ``no2_to_aqi`` is INFORMATIONAL ONLY and must be labeled as such in the UI.
NO2_AQI_BREAKPOINTS: list[tuple[float, float, int, int]] = [
    (0, 53, 0, 50),
    (54, 100, 51, 100),
    (101, 360, 101, 150),
    (361, 649, 151, 200),
    (650, 1249, 201, 300),
    (1250, 2049, 301, 500),
]

# (aqi_low, aqi_high, label, hex_color, short health guidance). Colors are the
# official EPA AQI category colors (green → maroon).
AQI_CATEGORIES: list[tuple[int, int, str, str, str]] = [
    (0, 50, "Good", "#00e400", "Air quality is satisfactory; little or no risk."),
    (51, 100, "Moderate", "#ffff00", "Acceptable; unusually sensitive people should consider limiting prolonged outdoor exertion."),
    (101, 150, "Unhealthy for Sensitive Groups", "#ff7e00", "Sensitive groups should limit prolonged outdoor exertion."),
    (151, 200, "Unhealthy", "#ff0000", "Everyone may begin to feel effects; sensitive groups feel stronger effects."),
    (201, 300, "Very Unhealthy", "#8f3f97", "Health alert: everyone may experience more serious health effects."),
    (301, 500, "Hazardous", "#7e0023", "Health warning of emergency conditions; everyone should avoid outdoor exertion."),
]

_AQI_UNAVAILABLE = ("Unavailable", "#666666", "No reading available for this selection.")


def _conc_to_aqi(
    concentration: float,
    breakpoints: list[tuple[float, float, int, int]],
    trunc_decimals: int,
) -> float:
    """Piecewise-linear AQI from a pollutant concentration. NaN in → NaN out."""
    if concentration is None:
        return float("nan")
    try:
        conc = float(concentration)
    except (TypeError, ValueError):
        return float("nan")
    if math.isnan(conc) or conc < 0:
        return float("nan")

    # EPA truncates the concentration before applying the formula.
    factor = 10 ** trunc_decimals
    conc = math.floor(conc * factor) / factor

    for c_lo, c_hi, i_lo, i_hi in breakpoints:
        if conc <= c_hi:
            aqi = (i_hi - i_lo) / (c_hi - c_lo) * (conc - c_lo) + i_lo
            return float(round(aqi))
    # Above the highest breakpoint: cap at the top of the scale.
    return float(breakpoints[-1][3])


def pm25_to_aqi(concentration: float) -> float:
    """US EPA AQI (2024 breakpoints) from a 24-hour mean PM2.5 in µg/m³."""
    return _conc_to_aqi(concentration, PM25_AQI_BREAKPOINTS, trunc_decimals=1)


def no2_to_aqi(concentration_ppb: float) -> float:
    """INFORMATIONAL NO2 sub-index from ppb.

    EPA's official NO2 sub-index needs the daily 1-hour maximum; the pipeline
    only carries a daily mean, so treat this as a rough indicator, never as an
    official AQI. Callers must label it accordingly.
    """
    return _conc_to_aqi(concentration_ppb, NO2_AQI_BREAKPOINTS, trunc_decimals=0)


def aqi_category(aqi: float) -> tuple[str, str]:
    """Return the (label, hex_color) for an AQI value; ('Unavailable', grey) for NaN.

    Converts to float first so NumPy scalars (e.g. numpy.float64('nan')) and other
    numeric-like inputs are handled correctly; non-numeric inputs are treated as
    unavailable rather than misclassified.
    """
    try:
        value = float(aqi)
    except (TypeError, ValueError):
        return _AQI_UNAVAILABLE[0], _AQI_UNAVAILABLE[1]
    if math.isnan(value):
        return _AQI_UNAVAILABLE[0], _AQI_UNAVAILABLE[1]
    for _i_lo, i_hi, label, color, _ in AQI_CATEGORIES:
        if value <= i_hi:
            return label, color
    last = AQI_CATEGORIES[-1]
    return last[2], last[3]


def aqi_health_message(aqi: float) -> str:
    """Return the short health-guidance string for an AQI value.

    Uses the same float-first NaN handling as ``aqi_category`` so NumPy scalars and
    non-numeric inputs are treated as unavailable rather than misclassified.
    """
    try:
        value = float(aqi)
    except (TypeError, ValueError):
        return _AQI_UNAVAILABLE[2]
    if math.isnan(value):
        return _AQI_UNAVAILABLE[2]
    for _i_lo, i_hi, _, _, message in AQI_CATEGORIES:
        if value <= i_hi:
            return message
    return AQI_CATEGORIES[-1][4]


def add_aqi_columns(df: pd.DataFrame, pm25_col: str = "pm25_mean") -> pd.DataFrame:
    """Add ``pm25_aqi`` / ``aqi_category`` / ``aqi_color`` columns from a PM2.5 column.

    Vectorized over the frame. Rows with a missing/NaN PM2.5 get NaN AQI and the
    'Unavailable' category. Returns a copy; input is not mutated.
    """
    out = df.copy()
    if pm25_col not in out.columns:
        out["pm25_aqi"] = np.nan
        out["aqi_category"] = _AQI_UNAVAILABLE[0]
        out["aqi_color"] = _AQI_UNAVAILABLE[1]
        return out

    out["pm25_aqi"] = pd.to_numeric(out[pm25_col], errors="coerce").map(pm25_to_aqi)
    categories = out["pm25_aqi"].map(aqi_category)
    out["aqi_category"] = categories.map(lambda pair: pair[0])
    out["aqi_color"] = categories.map(lambda pair: pair[1])
    return out


@dataclass(frozen=True)
class PipelineData:
    complaints: pd.DataFrame
    merged: pd.DataFrame
    summary: pd.DataFrame
    neighborhoods_geojson: dict[str, Any]


def _clean_paths(project_root: Path) -> dict[str, Path]:
    clean_dir = project_root / "data" / "clean"
    return {
        "complaints": clean_dir / "complaints_cleaned.csv",
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

    complaints = pd.read_csv(paths["complaints"], parse_dates=["date"])
    merged = pd.read_csv(paths["merged"], parse_dates=["date"])
    summary = pd.read_csv(paths["summary"])
    with paths["geojson"].open("r", encoding="utf-8") as f:
        geojson = json.load(f)

    expected_complaints = {"complaint_id", "date", "latitude", "longitude", "neighborhood"}
    missing_complaints = expected_complaints - set(complaints.columns)
    if missing_complaints:
        raise ValueError(f"complaints_cleaned.csv missing columns: {sorted(missing_complaints)}")

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

    return PipelineData(
        complaints=complaints,
        merged=merged,
        summary=summary,
        neighborhoods_geojson=geojson,
    )


def filter_complaint_points(
    complaints: pd.DataFrame,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
    neighborhoods: list[str] | None = None,
) -> pd.DataFrame:
    """Filter complaint-level rows to mappable geocoded points."""
    filtered = complaints[(complaints["date"] >= start_date) & (complaints["date"] <= end_date)]
    filtered = filtered.dropna(subset=["latitude", "longitude"])
    if neighborhoods:
        filtered = filtered[filtered["neighborhood"].isin(neighborhoods)]
    return filtered.copy()


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


def _extract_neighborhood_centroids(neighborhoods_geojson: dict[str, Any]) -> pd.DataFrame:
    """Extract one centroid per neighborhood from GeoJSON features."""
    rows: list[dict[str, float | str]] = []
    features = neighborhoods_geojson.get("features", [])

    if not isinstance(features, list):
        return pd.DataFrame(columns=["neighborhood", "centroid_lat", "centroid_lon"])

    for feature in features:
        if not isinstance(feature, dict):
            continue

        properties = feature.get("properties", {})
        geometry = feature.get("geometry")
        if not isinstance(properties, dict) or not isinstance(geometry, dict):
            continue

        neighborhood = properties.get("neighborhood")
        if not isinstance(neighborhood, str) or not neighborhood:
            continue

        try:
            centroid = shape(geometry).centroid
        except Exception:
            continue

        rows.append(
            {
                "neighborhood": neighborhood,
                "centroid_lat": float(centroid.y),
                "centroid_lon": float(centroid.x),
            }
        )

    if not rows:
        return pd.DataFrame(columns=["neighborhood", "centroid_lat", "centroid_lon"])

    return pd.DataFrame(rows).drop_duplicates(subset=["neighborhood"])


def _haversine_km(lat: float, lon: float, lat_series: pd.Series, lon_series: pd.Series) -> pd.Series:
    """Return great-circle distance from one point to many points in kilometers."""
    lat1 = np.radians(lat)
    lon1 = np.radians(lon)
    lat2 = np.radians(lat_series.astype(float))
    lon2 = np.radians(lon_series.astype(float))

    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    c = 2.0 * np.arcsin(np.sqrt(a))

    earth_radius_km = 6371.0088
    return pd.Series(earth_radius_km * c, index=lat_series.index)


def _nearest_sensor_rows(
    lat: float,
    lon: float,
    sensors: pd.DataFrame,
    k: int,
    max_distance_km: float,
) -> pd.DataFrame:
    """Return up to k nearest sensor rows within the max distance."""
    required = {"lat", "lon"}
    if sensors.empty or not required.issubset(set(sensors.columns)):
        return pd.DataFrame(columns=[*sensors.columns, "distance_km"])

    candidates = sensors.dropna(subset=["lat", "lon"]).copy()
    if candidates.empty:
        return pd.DataFrame(columns=[*sensors.columns, "distance_km"])

    candidates["distance_km"] = _haversine_km(lat, lon, candidates["lat"], candidates["lon"])
    candidates = candidates.sort_values("distance_km")

    if max_distance_km > 0:
        candidates = candidates[candidates["distance_km"] <= max_distance_km]

    if candidates.empty:
        return pd.DataFrame(columns=[*sensors.columns, "distance_km"])

    return candidates.head(max(k, 1)).reset_index(drop=True)


def _idw_estimate(nearby: pd.DataFrame, value_col: str, power: float) -> float:
    """Estimate a value column using inverse-distance weighting."""
    if nearby.empty or value_col not in nearby.columns:
        return float("nan")

    valid = nearby.dropna(subset=[value_col]).copy()
    if valid.empty:
        return float("nan")

    zero_dist = valid[valid["distance_km"] == 0]
    if not zero_dist.empty:
        return float(zero_dist[value_col].iloc[0])

    safe_power = power if power > 0 else 1.0
    weights = 1.0 / np.power(valid["distance_km"].astype(float), safe_power)
    estimate = np.average(valid[value_col].astype(float), weights=weights)
    return float(estimate)


def enrich_neighborhood_metrics_with_estimates(
    neighborhood_metrics: pd.DataFrame,
    sensors: pd.DataFrame,
    neighborhoods_geojson: dict[str, Any],
    *,
    k: int = 3,
    idw_power: float = 2.0,
    max_distance_km: float = 15.0,
) -> pd.DataFrame:
    """
    Enrich neighborhood metrics with IDW placeholders for uncovered neighborhoods.

    Direct period values are preserved. Placeholder values are only used when a
    direct period value is missing.
    """
    out = neighborhood_metrics.copy()

    def _numeric_or_nan(frame: pd.DataFrame, col: str) -> pd.Series:
        if col in frame.columns:
            return pd.to_numeric(frame[col], errors="coerce")
        return pd.Series(np.nan, index=frame.index, dtype=float)

    pm25_direct = _numeric_or_nan(out, "pm25_mean_period")
    no2_direct = _numeric_or_nan(out, "no2_mean_period")
    complaints_direct = _numeric_or_nan(out, "complaints_period")

    out["pm25_mean_estimated"] = np.nan
    out["no2_mean_estimated"] = np.nan
    out["complaints_estimated"] = np.nan
    out["estimated_sensor_count"] = 0
    out["estimated_nearest_km"] = np.nan

    out["pm25_map_value"] = pm25_direct
    out["no2_map_value"] = no2_direct
    out["complaints_map_value"] = complaints_direct

    centroids = _extract_neighborhood_centroids(neighborhoods_geojson)
    out = out.merge(centroids, on="neighborhood", how="left").reset_index(drop=True)

    needs_estimate = (
        out["pm25_map_value"].isna() | out["no2_map_value"].isna() | out["complaints_map_value"].isna()
    ) & out["centroid_lat"].notna() & out["centroid_lon"].notna()

    estimate_targets = out.loc[needs_estimate, ["centroid_lat", "centroid_lon"]].copy()
    estimate_targets["centroid_lat"] = pd.to_numeric(estimate_targets["centroid_lat"], errors="coerce")
    estimate_targets["centroid_lon"] = pd.to_numeric(estimate_targets["centroid_lon"], errors="coerce")

    for row_idx, centroid_lat, centroid_lon in zip(
        estimate_targets.index.to_list(),
        estimate_targets["centroid_lat"].to_list(),
        estimate_targets["centroid_lon"].to_list(),
        strict=True,
    ):
        if pd.isna(centroid_lat) or pd.isna(centroid_lon):
            continue

        row_i = int(row_idx)
        centroid_lat_f = float(centroid_lat)
        centroid_lon_f = float(centroid_lon)

        nearby = _nearest_sensor_rows(
            lat=centroid_lat_f,
            lon=centroid_lon_f,
            sensors=sensors,
            k=k,
            max_distance_km=max_distance_km,
        )

        if nearby.empty:
            continue

        out.loc[row_i, "estimated_sensor_count"] = int(len(nearby))
        out.loc[row_i, "estimated_nearest_km"] = float(nearby["distance_km"].min())

        pm25_est = _idw_estimate(nearby, "pm25_mean", idw_power)
        no2_est = _idw_estimate(nearby, "no2_mean", idw_power)
        complaints_est = _idw_estimate(nearby, "total_complaints", idw_power)

        out.loc[row_i, "pm25_mean_estimated"] = pm25_est
        out.loc[row_i, "no2_mean_estimated"] = no2_est
        out.loc[row_i, "complaints_estimated"] = complaints_est

        if pd.isna(out.loc[row_i, "pm25_map_value"]):
            out.loc[row_i, "pm25_map_value"] = pm25_est
        if pd.isna(out.loc[row_i, "no2_map_value"]):
            out.loc[row_i, "no2_map_value"] = no2_est
        if pd.isna(out.loc[row_i, "complaints_map_value"]):
            out.loc[row_i, "complaints_map_value"] = complaints_est

    has_direct = (
        pm25_direct.notna() | no2_direct.notna() | complaints_direct.notna()
    )
    has_estimate = (
        pd.to_numeric(out["pm25_mean_estimated"], errors="coerce").notna()
        | pd.to_numeric(out["no2_mean_estimated"], errors="coerce").notna()
        | pd.to_numeric(out["complaints_estimated"], errors="coerce").notna()
    )

    out["coverage_source"] = np.where(
        has_direct,
        "direct",
        np.where(has_estimate, "estimated_idw", "unavailable"),
    )
    out["is_estimated"] = out["coverage_source"] == "estimated_idw"

    return out


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
    spike_percentile: float = 0.80,
    window_days: int = 2,
    threshold: float | None = None,
) -> tuple[pd.DataFrame, float]:
    """Summarize complaint activity around city-level PM2.5 spike days.

    A spike day is any day where city-wide average PM2.5 is at or above a
    threshold. The threshold is either:

    * an absolute ``threshold`` (µg/m³) when provided — e.g. the EPA 24-hour
      PM2.5 standard of 35 — which anchors spikes to a health-meaningful level; or
    * the ``spike_percentile`` quantile of PM2.5 over the selected range
      (default) — which guarantees spike days exist regardless of the absolute
      pollution level in the window.

    Returns ``(offsets_frame, baseline)`` where ``baseline`` is the mean
    complaint count on non-spike days.
    """
    empty = pd.DataFrame(columns=["offset_day", "mean_complaints", "total_complaints"])
    if city_daily.empty:
        return empty, float("nan")

    city = city_daily.sort_values("date").copy()
    pm25_valid = city["pm25_mean"].dropna()
    if pm25_valid.empty:
        return empty, float("nan")

    spike_level = float(threshold) if threshold is not None else float(pm25_valid.quantile(spike_percentile))
    city["is_spike"] = city["pm25_mean"] >= spike_level

    spike_dates = city.loc[city["is_spike"], "date"]
    baseline = city.loc[~city["is_spike"], "complaint_count"].mean()

    # Vectorized offset join: look complaint counts up by date rather than
    # scanning the frame once per (offset, spike-day) pair.
    complaints_by_date = city.set_index("date")["complaint_count"]

    rows = []
    for offset in range(-window_days, window_days + 1):
        target_dates = spike_dates + pd.Timedelta(days=offset)
        matched = complaints_by_date.reindex(target_dates).dropna()
        if not matched.empty:
            rows.append(
                {
                    "offset_day": offset,
                    "mean_complaints": float(matched.mean()),
                    "total_complaints": float(matched.sum()),
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
