"""Sidebar controls for the dashboard.

Purpose: render every filter/option widget and hand the choices back as one typed object.
Inputs:  the data's date bounds and the list of neighborhood names.
Outputs: ``SidebarState`` (frozen); Streamlit reruns the whole script on any widget change.
Used by: streamlit_app/app.py, which passes the state to banner.py and the views/ tab modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import streamlit as st

from streamlit_app.constants import MAP_METRICS
from streamlit_app.theme import get_theme


@dataclass(frozen=True)
class SidebarState:
    theme: dict[str, Any]
    start_date: date
    end_date: date
    selected_neighborhoods: list[str]
    map_metric_label: str
    trend_metric_label: str
    trend_chart_style: str
    calendar_metric_label: str
    spike_percentile_pct: int
    show_quick_tour: bool
    map_mode: str
    show_sensor_markers: bool
    show_complaint_locations: bool
    map_height_px: int
    color_scale_width_px: int
    color_scale_height_pct: int
    color_scale_x: float
    idw_k: int
    idw_power: float
    idw_max_km: int


def normalize_date_range(selection: object, fallback_start: date, fallback_end: date) -> tuple[date, date]:
    """Normalize Streamlit date_input return value to a guaranteed (start, end) tuple."""
    if isinstance(selection, tuple):
        if len(selection) >= 2 and isinstance(selection[0], date) and isinstance(selection[1], date):
            return selection[0], selection[1]
        if len(selection) == 1 and isinstance(selection[0], date):
            return selection[0], selection[0]
        return fallback_start, fallback_end

    if isinstance(selection, date):
        return selection, selection

    return fallback_start, fallback_end


def render_sidebar(min_date: date, max_date: date, neighborhood_options: list[str]) -> SidebarState:
    with st.sidebar:
        theme_name = st.radio(
            "Theme",
            options=["Terminal", "Accessible"],
            index=0,
            horizontal=True,
            help="Terminal keeps the dark neon look. Accessible switches to a light, "
            "high-contrast palette using official EPA AQI health colors.",
        )
        theme = get_theme(theme_name)

        st.header("Filters")
        date_selection = st.date_input(
            "Date range",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
        )
        start_date, end_date = normalize_date_range(date_selection, min_date, max_date)
        if isinstance(date_selection, (tuple, list)) and len(date_selection) == 1:
            st.caption("Pick an end date to complete the range — showing a single day until then.")

        selected_neighborhoods = st.multiselect(
            "Neighborhoods",
            options=neighborhood_options,
            default=[],
            help="Leave empty to show all neighborhoods.",
        )

        map_metric_label = st.selectbox(
            "Map metric",
            options=list(MAP_METRICS),
            help="Air Quality Index uses the official EPA 2024 PM2.5 breakpoints and health colors.",
        )

        st.subheader("Temporal trends")
        trend_metric_label = st.selectbox(
            "Primary trend metric",
            options=["PM2.5", "NO2"],
            help="Choose which pollutant drives trend and ranking charts.",
        )
        trend_chart_style = st.radio(
            "Trend chart style",
            options=["Line + complaints", "Area + complaints"],
            index=0,
            horizontal=True,
        )
        calendar_metric_label = st.selectbox(
            "Calendar heatmap metric",
            options=["PM2.5", "NO2", "Complaints"],
        )
        spike_percentile_pct = st.slider(
            "Spike threshold (percentile)",
            min_value=60,
            max_value=95,
            value=80,
            step=5,
            help="Days with PM2.5 above this percentile of the selected period are treated as spike days in the Lead-Lag & Spikes tab.",
        )

        show_quick_tour = st.toggle(
            "Show quick tour",
            value=True,
            help="Display a short walkthrough for first-time visitors.",
        )

        st.subheader("Map options")
        map_mode = st.radio(
            "Map mode",
            options=["Neighborhood choropleth", "Continuous heatmap"],
            index=0,
            help="Choropleth keeps neighborhood fill. Heatmap shows a continuous sensor-driven surface.",
        )
        show_sensor_markers = st.toggle(
            "Show sensor markers",
            value=True,
            help="Overlay individual sensors. Marker size reflects complaint totals in the selected range.",
        )
        show_complaint_locations = st.toggle(
            "Show complaint locations",
            value=False,
            help="Overlay geocoded complaint points for the selected date range and neighborhood filter.",
        )
        map_height_px = st.slider(
            "Map height (px)",
            min_value=500,
            max_value=1200,
            value=760,
            step=20,
            help="Increase this if the map feels too tight vertically.",
        )

        st.caption("Color scale layout")
        # Sliders let desktop users fine-tune the floating colorbar overlay.
        color_scale_width_px = st.slider(
            "Color scale thickness (px)",
            min_value=8,
            max_value=56,
            value=14,
            step=1,
        )
        color_scale_height_pct = st.slider(
            "Color scale length (%)",
            min_value=20,
            max_value=95,
            value=58,
            step=1,
        )
        color_scale_x = st.slider(
            "Color scale horizontal offset",
            min_value=0.0,
            max_value=1.0,
            value=0.99,
            step=0.01,
            format="%.2f",
            help="Shifts the colorbar left or right along the bottom of the map.",
        )

        with st.expander("Neighborhood estimation (IDW)", expanded=False):
            st.caption(
                "Neighborhoods without direct sensor readings are filled using "
                "inverse-distance weighting from nearby sensors. Tune the estimator here."
            )
            idw_k = st.slider(
                "Nearest sensors (k)",
                min_value=1,
                max_value=8,
                value=3,
                help="How many nearby sensors contribute to each estimate.",
            )
            idw_power = st.slider(
                "Distance power",
                min_value=1.0,
                max_value=4.0,
                value=2.0,
                step=0.5,
                help="Higher values weight the closest sensors more heavily.",
            )
            idw_max_km = st.slider(
                "Max sensor distance (km)",
                min_value=2,
                max_value=40,
                value=15,
                help="Sensors farther than this are ignored; neighborhoods with none stay 'unavailable'.",
            )

    return SidebarState(
        theme=theme,
        start_date=start_date,
        end_date=end_date,
        selected_neighborhoods=selected_neighborhoods,
        map_metric_label=map_metric_label,
        trend_metric_label=trend_metric_label,
        trend_chart_style=trend_chart_style,
        calendar_metric_label=calendar_metric_label,
        spike_percentile_pct=spike_percentile_pct,
        show_quick_tour=show_quick_tour,
        map_mode=map_mode,
        show_sensor_markers=show_sensor_markers,
        show_complaint_locations=show_complaint_locations,
        map_height_px=map_height_px,
        color_scale_width_px=color_scale_width_px,
        color_scale_height_pct=color_scale_height_pct,
        color_scale_x=color_scale_x,
        idw_k=idw_k,
        idw_power=idw_power,
        idw_max_km=idw_max_km,
    )
