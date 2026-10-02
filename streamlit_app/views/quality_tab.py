"""Coverage QA tab: which neighborhoods lack sensors and how each value was obtained.

Purpose: transparency on direct sensor values vs IDW estimates vs unavailable.
Inputs:  the neighborhood map metrics (output of the IDW enrichment step).
Outputs: renders two Streamlit dataframes; nothing is returned.
Used by: streamlit_app/app.py.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from streamlit_app.constants import COLUMN_LABELS


def render_quality_tab(map_metrics: pd.DataFrame) -> None:
    quality_columns = [
        "neighborhood",
        "neighborhood_secondary",
        "sensor_count",
        "coverage_source",
        "pm25_aqi_map_value",
        "pm25_map_value",
        "no2_map_value",
        "complaints_period",
        "complaints_map_value",
        "estimated_sensor_count",
        "estimated_nearest_km",
    ]
    no_coverage = map_metrics[map_metrics["sensor_count"].fillna(0) == 0].copy()
    st.subheader("Neighborhoods without sensor coverage")
    st.caption(
        "These polygons remain individually represented. Coverage source shows whether a neighborhood "
        "currently uses direct period values, IDW estimates, or remains unavailable."
    )
    st.dataframe(
        no_coverage[quality_columns].rename(columns=COLUMN_LABELS).sort_values("Neighborhood"),
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("Filtered neighborhood metrics")
    # Curated column set (in order); avoids dumping internal geometry/flags
    # and keeps the rename collision-free.
    metrics_columns = [
        "neighborhood",
        "neighborhood_secondary",
        "sensor_count",
        "coverage_source",
        "pm25_aqi_map_value",
        "pm25_map_value",
        "pm25_mean_period",
        "pm25_mean_estimated",
        "no2_map_value",
        "no2_mean_period",
        "no2_mean_estimated",
        "complaints_map_value",
        "complaints_period",
        "complaints_estimated",
        "estimated_sensor_count",
        "estimated_nearest_km",
    ]
    present_metrics_columns = [c for c in metrics_columns if c in map_metrics.columns]
    st.dataframe(
        map_metrics[present_metrics_columns].rename(columns=COLUMN_LABELS).sort_values("Neighborhood"),
        use_container_width=True,
        hide_index=True,
    )
