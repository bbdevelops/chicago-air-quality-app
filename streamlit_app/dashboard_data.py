"""Backward-compatible import surface for the dashboard's data layer.

The implementation lives in focused modules; this file only re-exports their public names so
``from streamlit_app.dashboard_data import ...`` (app.py, tests, docs) keeps working.

    loading.py     read + validate data/clean files   -> PipelineData
    metrics.py     filter and aggregate               -> city / sensor / neighborhood frames
    estimation.py  IDW fill for uncovered areas       -> map-ready neighborhood metrics
    analytics.py   lead-lag and spike analysis        -> correlation / concordance frames
    aqi.py (root)  AQI maths and categories           -> pm25_to_aqi, add_aqi_columns, ...
"""

from __future__ import annotations

from aqi import add_aqi_columns, aqi_category, aqi_health_message, no2_to_aqi, pm25_to_aqi
from streamlit_app.analytics import compute_lag_correlations, compute_spike_concordance
from streamlit_app.estimation import enrich_neighborhood_metrics_with_estimates
from streamlit_app.loading import PipelineData, load_pipeline_data
from streamlit_app.metrics import (
    build_city_daily_metrics,
    build_neighborhood_metrics,
    build_sensor_snapshot,
    filter_by_date_range,
)

__all__ = [
    "PipelineData",
    "add_aqi_columns",
    "aqi_category",
    "aqi_health_message",
    "build_city_daily_metrics",
    "build_neighborhood_metrics",
    "build_sensor_snapshot",
    "compute_lag_correlations",
    "compute_spike_concordance",
    "enrich_neighborhood_metrics_with_estimates",
    "filter_by_date_range",
    "load_pipeline_data",
    "no2_to_aqi",
    "pm25_to_aqi",
]
