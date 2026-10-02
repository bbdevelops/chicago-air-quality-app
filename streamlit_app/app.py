"""Chicago Air Quality Explorer: Streamlit entry point.

Purpose: wire the dashboard together. Streamlit re-runs this whole script on every widget change, so
         main() is a straight pipeline: load -> sidebar -> filter/aggregate -> render summary and tabs.
Inputs:  data/clean/* (via loading.py, cached) and the sidebar widgets (via sidebar.py).
Outputs: the rendered page; all layout/chart code lives in banner.py, map_layers.py and views/.
Used by: `streamlit run streamlit_app/app.py` (see README and the Dockerfile).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# `streamlit run` only puts this file's folder on sys.path, so add the repo root
# once here and every module can use plain `streamlit_app.*` / `aqi` imports.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from aqi import add_aqi_columns, pm25_to_aqi
from streamlit_app.banner import render_summary
from streamlit_app.estimation import enrich_neighborhood_metrics_with_estimates
from streamlit_app.loading import load_pipeline_data
from streamlit_app.metrics import (
    build_city_daily_metrics,
    build_neighborhood_metrics,
    build_sensor_snapshot,
    filter_by_date_range,
)
from streamlit_app.sidebar import render_sidebar
from streamlit_app.theme import chrome_css
from streamlit_app.views.lag_tab import render_lag_tab
from streamlit_app.views.map_tab import render_map_tab
from streamlit_app.views.neighborhood_tab import render_neighborhood_tab
from streamlit_app.views.quality_tab import render_quality_tab
from streamlit_app.views.trends_tab import render_trends_tab

st.set_page_config(
    page_title="Chicago Air Quality Explorer",
    page_icon=":wind_face:",
    layout="wide",
)


@st.cache_data(show_spinner=False)
def cached_load_data(project_root: str):
    return load_pipeline_data(Path(project_root))


def main() -> None:
    st.title("Chicago Air Quality Explorer")
    st.caption(
        "Track neighborhood air quality and 311 complaint trends across Chicago using city sensor data."
    )

    try:
        data = cached_load_data(str(PROJECT_ROOT))
    except (FileNotFoundError, ValueError) as exc:
        st.error(str(exc))
        st.stop()

    merged = data.merged
    summary = data.summary

    ui = render_sidebar(
        min_date=merged["date"].min().date(),
        max_date=merged["date"].max().date(),
        neighborhood_options=sorted(summary["neighborhood"].dropna().unique()),
    )
    start_date, end_date = ui.start_date, ui.end_date
    selected_neighborhoods = ui.selected_neighborhoods

    if ui.theme["name"] != "Terminal":
        st.markdown(chrome_css(ui.theme), unsafe_allow_html=True)

    # ── Filter and aggregate for the selected window ───────────────────────
    filtered = filter_by_date_range(
        df=merged,
        start_date=pd.Timestamp(start_date),
        end_date=pd.Timestamp(end_date),
        neighborhoods=selected_neighborhoods,
    )
    complaint_points = filter_by_date_range(
        df=data.complaints,
        start_date=pd.Timestamp(start_date),
        end_date=pd.Timestamp(end_date),
        neighborhoods=selected_neighborhoods,
    ).dropna(subset=["latitude", "longitude"])

    base_map_metrics = build_neighborhood_metrics(summary, filtered)
    if selected_neighborhoods:
        base_map_metrics = base_map_metrics[
            base_map_metrics["neighborhood"].isin(selected_neighborhoods)
        ].copy()

    city_daily = build_city_daily_metrics(filtered)
    if not city_daily.empty:
        full_dates = pd.date_range(start=pd.Timestamp(start_date), end=pd.Timestamp(end_date), freq="D")
        city_daily = (
            city_daily.set_index("date")
            .reindex(full_dates)
            .rename_axis("date")
            .reset_index()
        )
        city_daily["complaint_count"] = city_daily["complaint_count"].fillna(0)
        city_daily["spike_sensor_days"] = city_daily["spike_sensor_days"].fillna(0)
    sensors = build_sensor_snapshot(filtered)
    sensors = add_aqi_columns(sensors, pm25_col="pm25_mean")
    map_metrics = enrich_neighborhood_metrics_with_estimates(
        neighborhood_metrics=base_map_metrics,
        sensors=sensors,
        neighborhoods_geojson=data.neighborhoods_geojson,
        k=ui.idw_k,
        idw_power=ui.idw_power,
        max_distance_km=float(ui.idw_max_km),
    )
    # Neighborhood-level AQI derived from the (direct or estimated) PM2.5 value.
    map_metrics["pm25_aqi_map_value"] = map_metrics["pm25_map_value"].map(pm25_to_aqi)

    if ui.show_quick_tour:
        with st.expander("Quick tour: how to use this dashboard", expanded=False):
            st.markdown(
                """
                1. Click >> in the upper left corner to open filter menu. Set your date range and optionally focus on specific neighborhoods.
                2. Start in Neighborhood Map to compare air conditions and complaint activity.
                3. Use Temporal Trends to explore citywide day-to-day patterns and calendar seasonality.
                4. Visit Neighborhood Trends for ranked neighborhood comparisons.
                5. Check Lead-Lag & Spikes to explore whether complaint activity follows pollution spikes.
                6. Open Coverage QA for transparency on direct sensor coverage vs estimated neighborhoods.
                """
            )

    # ── Headline: AQI banner + KPI cards (compared with the prior equal-length window) ──
    selected_days = int((pd.Timestamp(end_date) - pd.Timestamp(start_date)).days) + 1
    prev_end = pd.Timestamp(start_date) - pd.Timedelta(days=1)
    prev_start = prev_end - pd.Timedelta(days=max(selected_days - 1, 0))
    previous_filtered = filter_by_date_range(
        df=merged,
        start_date=prev_start,
        end_date=prev_end,
        neighborhoods=selected_neighborhoods,
    )
    render_summary(filtered, previous_filtered, start_date, end_date, selected_days)

    # ── Tabs ───────────────────────────────────────────────────────────────
    tab_map, tab_trends, tab_neighborhood, tab_lag, tab_quality = st.tabs(
        ["Neighborhood Map", "Temporal Trends", "Neighborhood Trends", "Lead-Lag & Spikes", "Coverage QA"]
    )
    with tab_map:
        render_map_tab(ui, data, map_metrics, sensors, complaint_points)
    with tab_trends:
        render_trends_tab(ui, city_daily)
    with tab_neighborhood:
        render_neighborhood_tab(ui, map_metrics)
    with tab_lag:
        render_lag_tab(ui, city_daily)
    with tab_quality:
        render_quality_tab(map_metrics)


if __name__ == "__main__":
    main()
