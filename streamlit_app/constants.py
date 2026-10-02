"""Static configuration shared by the dashboard's sidebar, map and chart code.

Purpose: one home for display labels, map-metric definitions and map defaults so views never drift apart.
Inputs:  none (plain constants).
Outputs: COLUMN_LABELS, HOVER_EXTRA_LABELS, MAP_METRICS, POLLUTANTS, CHICAGO_CENTER, CHICAGO_ZOOM.
Used by: streamlit_app/app.py, sidebar.py and the views/ tab modules.
"""

from __future__ import annotations

from dataclasses import dataclass

# Human-readable labels for NEIGHBORHOOD-level columns — used both for choropleth
# hover cards and the Coverage QA tables. One source of truth so the two views
# never drift apart. Each source column maps to a distinct label, so these are
# safe to use with DataFrame.rename (no collisions).
COLUMN_LABELS = {
    "neighborhood": "Neighborhood",
    "neighborhood_secondary": "Neighborhood alias",
    "coverage_source": "Coverage source",
    "sensor_count": "Sensors in neighborhood",
    "pm25_aqi_map_value": "Air Quality Index (PM2.5)",
    "pm25_map_value": "PM2.5 average (µg/m³)",
    "pm25_mean_period": "PM2.5 direct value (µg/m³)",
    "pm25_mean_estimated": "PM2.5 IDW estimate (µg/m³)",
    "no2_map_value": "NO2 average (ppb)",
    "no2_mean_period": "NO2 direct value (ppb)",
    "no2_mean_estimated": "NO2 IDW estimate (ppb)",
    "complaints_map_value": "Complaints (period)",
    "complaints_period": "Complaints direct value",
    "complaints_estimated": "Complaints IDW estimate",
    "estimated_sensor_count": "Sensors used for estimate",
    "estimated_nearest_km": "Nearest sensor distance (km)",
}

# Extra labels for SENSOR-snapshot columns, used only for the continuous-heatmap
# hover card. Kept separate because some share display text with neighborhood
# columns (e.g. total_complaints ↔ complaints_map_value) and would collide if
# used to rename the neighborhood table.
HOVER_EXTRA_LABELS = {
    "pm25_mean": "PM2.5 average (µg/m³)",
    "no2_mean": "NO2 average (ppb)",
    "total_complaints": "Complaints (period)",
    "active_days": "Active sensor days",
}


@dataclass
class MapMetric:
    choropleth_col: str
    heatmap_col: str
    colorbar_title: str
    is_aqi: bool


MAP_METRICS = {
    "Air Quality Index (PM2.5)": MapMetric("pm25_aqi_map_value", "pm25_aqi", "AQI", True),
    "PM2.5 mean (selected period)": MapMetric("pm25_map_value", "pm25_mean", "PM2.5 Avg.", False),
    "NO2 mean (selected period)": MapMetric("no2_map_value", "no2_mean", "NO2 Avg.", False),
    "Complaints (selected period)": MapMetric("complaints_map_value", "total_complaints", "Complaints", False),
    "Sensor coverage (all-time)": MapMetric("sensor_count", "active_days", "Sensors", False),
}


@dataclass
class PolConfig:
    column: str
    label: str
    unit: str


POLLUTANTS = {
    "PM2.5": PolConfig(column="pm25_mean", label="PM2.5", unit="µg/m³"),
    "NO2": PolConfig(column="no2_mean", label="NO2", unit="ppb"),
}

CHICAGO_CENTER = {"lat": 41.8781, "lon": -87.6298}
CHICAGO_ZOOM = 9
