"""Load and validate the pipeline outputs the dashboard reads.

Purpose: one place that knows which data/clean files the app needs and checks their schemas.
Inputs:  data/clean/{complaints_cleaned,merged_complaints_air,neighborhood_summary}.csv and chicago_neighborhoods.geojson.
Outputs: ``PipelineData`` (raw frames + geojson; no filtering or aggregation happens here).
Used by: streamlit_app/app.py (cached with st.cache_data), via the dashboard_data facade.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

# 6 decimal degrees is ~0.11 m: invisible on the map, but ~40% smaller figures sent to the browser.
MAP_COORD_DECIMALS = 6


def _round_coords(coords: Any, decimals: int) -> Any:
    if coords and isinstance(coords[0], (int, float)):
        return [round(v, decimals) for v in coords]
    return [_round_coords(c, decimals) for c in coords]


def round_geojson_coordinates(geojson: dict[str, Any], decimals: int = MAP_COORD_DECIMALS) -> dict[str, Any]:
    """Return a copy of ``geojson`` with coordinates rounded; properties are untouched."""
    features = []
    for feature in geojson.get("features", []):
        geometry = feature.get("geometry")
        if geometry and "coordinates" in geometry:
            geometry = {**geometry, "coordinates": _round_coords(geometry["coordinates"], decimals)}
            feature = {**feature, "geometry": geometry}
        features.append(feature)
    return {**geojson, "features": features}


@dataclass(frozen=True)
class PipelineData:
    complaints: pd.DataFrame
    merged: pd.DataFrame
    summary: pd.DataFrame
    neighborhoods_geojson: dict[str, Any]
    # Rounded copy for the browser. Centroids and IDW keep using the full-precision geojson above.
    display_geojson: dict[str, Any] | None = None

    @property
    def map_geojson(self) -> dict[str, Any]:
        """Geometry to hand to Plotly."""
        return self.display_geojson if self.display_geojson is not None else self.neighborhoods_geojson


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
        display_geojson=round_geojson_coordinates(geojson),
    )
