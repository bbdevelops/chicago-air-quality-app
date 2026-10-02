"""Fill neighborhoods that lack direct sensor readings using inverse-distance weighting (IDW).

Purpose: give every neighborhood polygon a map value, flagged as direct / estimated_idw / unavailable.
Inputs:  neighborhood metrics (metrics.build_neighborhood_metrics), the sensor snapshot
         (metrics.build_sensor_snapshot) and the neighborhoods GeoJSON.
Outputs: neighborhood metrics plus ``*_estimated``, ``*_map_value`` and ``coverage_source`` columns.
Used by: streamlit_app/app.py (choropleth map and Coverage QA tab).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from shapely.geometry import shape

from aqi import haversine_km as _haversine_km


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

    return out
