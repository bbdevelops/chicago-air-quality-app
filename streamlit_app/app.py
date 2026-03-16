from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

try:
    # Works when launched from project root as a package import.
    from streamlit_app.dashboard_data import (
        build_city_daily_metrics,
        build_neighborhood_metrics,
        build_sensor_snapshot,
        compute_lag_correlations,
        compute_spike_concordance,
        enrich_neighborhood_metrics_with_estimates,
        filter_merged_data,
        load_pipeline_data,
    )
except ModuleNotFoundError:
    # Works when Streamlit executes this file as a direct script.
    from dashboard_data import (  # type: ignore
        build_city_daily_metrics,
        build_neighborhood_metrics,
        build_sensor_snapshot,
        compute_lag_correlations,
        compute_spike_concordance,
        enrich_neighborhood_metrics_with_estimates,
        filter_merged_data,
        load_pipeline_data,
    )


st.set_page_config(
    page_title="Chicago Air Quality Explorer",
    page_icon="wind_face",
    layout="wide",
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@st.cache_data(show_spinner=False)
def cached_load_data(project_root: str):
    return load_pipeline_data(Path(project_root))


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


def add_neighborhood_boundaries(fig: go.Figure, neighborhoods_geojson: dict[str, object]) -> None:
    """Overlay neighborhood boundary lines for map orientation."""
    features = neighborhoods_geojson.get("features", [])
    if not isinstance(features, list):
        return

    for feature in features:
        if not isinstance(feature, dict):
            continue

        geometry = feature.get("geometry", {})
        if not isinstance(geometry, dict):
            continue

        geom_type = geometry.get("type")
        coords = geometry.get("coordinates", [])

        polygons: list[object] = []
        if geom_type == "Polygon":
            polygons = [coords]
        elif geom_type == "MultiPolygon":
            polygons = coords if isinstance(coords, list) else []
        else:
            continue

        for polygon in polygons:
            if not isinstance(polygon, list) or not polygon:
                continue

            outer_ring = polygon[0]
            if not isinstance(outer_ring, list) or not outer_ring:
                continue

            lons = [point[0] for point in outer_ring if isinstance(point, list) and len(point) >= 2]
            lats = [point[1] for point in outer_ring if isinstance(point, list) and len(point) >= 2]
            if not lons or not lats:
                continue

            fig.add_trace(
                go.Scattermapbox(
                    lon=lons,
                    lat=lats,
                    mode="lines",
                    line={"color": "rgba(20, 20, 20, 0.35)", "width": 1},
                    hoverinfo="skip",
                    showlegend=False,
                    name="Neighborhood boundary",
                )
            )


def main() -> None:
    st.title("Chicago Air Quality Explorer")
    st.caption(
        "Streamlit dashboard powered by the existing ETL pipeline outputs in data/clean/. "
        "Run python run_pipeline.py --skip-api before refreshing."
    )

    try:
        data = cached_load_data(str(PROJECT_ROOT))
    except (FileNotFoundError, ValueError) as exc:
        st.error(str(exc))
        st.stop()

    merged = data.merged
    summary = data.summary

    min_date = merged["date"].min().date()
    max_date = merged["date"].max().date()

    with st.sidebar:
        st.header("Filters")
        date_selection = st.date_input(
            "Date range",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
        )
        start_date, end_date = normalize_date_range(date_selection, min_date, max_date)

        neighborhood_options = sorted(summary["neighborhood"].dropna().unique())
        selected_neighborhoods = st.multiselect(
            "Neighborhoods",
            options=neighborhood_options,
            default=[],
            help="Leave empty to show all neighborhoods.",
        )

        map_metric_label = st.selectbox(
            "Map metric",
            options=[
                "PM2.5 mean (selected period)",
                "NO2 mean (selected period)",
                "Complaints (selected period)",
                "Sensor coverage (all-time)",
            ],
        )

        st.subheader("Map options")
        map_mode = st.radio(
            "Map mode",
            options=["Neighborhood choropleth", "Continuous heatmap"],
            index=0,
            help="Choropleth keeps neighborhood fill. Heatmap shows a continuous sensor-driven surface.",
        )
        enable_scroll_zoom = st.toggle(
            "Enable mouse-wheel zoom",
            value=True,
            help="Use the middle mouse wheel to zoom in/out on the map.",
        )
        map_height_px = st.slider(
            "Map height (px)",
            min_value=500,
            max_value=1200,
            value=760,
            step=20,
            help="Increase this if the map feels too tight vertically.",
        )

    filtered = filter_merged_data(
        merged=merged,
        start_date=pd.Timestamp(start_date),
        end_date=pd.Timestamp(end_date),
        neighborhoods=selected_neighborhoods,
    )

    base_map_metrics = build_neighborhood_metrics(summary, filtered)
    city_daily = build_city_daily_metrics(filtered)
    sensors = build_sensor_snapshot(filtered)
    map_metrics = enrich_neighborhood_metrics_with_estimates(
        neighborhood_metrics=base_map_metrics,
        sensors=sensors,
        neighborhoods_geojson=data.neighborhoods_geojson,
        k=3,
        idw_power=2.0,
        max_distance_km=15.0,
    )

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Rows in selection", f"{len(filtered):,}")
    col2.metric("Avg PM2.5", f"{filtered['pm25_mean'].mean():.2f}" if not filtered.empty else "n/a")
    col3.metric("Total complaints", f"{int(filtered['complaint_count'].sum()):,}" if not filtered.empty else "0")
    col4.metric("Active sensors", f"{filtered['sensor_name'].nunique():,}" if not filtered.empty else "0")

    tab_map, tab_trends, tab_lag, tab_quality = st.tabs(
        ["Neighborhood Map", "Temporal Trends", "Lead-Lag & Spikes", "Coverage QA"]
    )

    with tab_map:
        choropleth_metric_lookup = {
            "PM2.5 mean (selected period)": "pm25_map_value",
            "NO2 mean (selected period)": "no2_map_value",
            "Complaints (selected period)": "complaints_map_value",
            "Sensor coverage (all-time)": "sensor_count",
        }

        heatmap_metric_lookup = {
            "PM2.5 mean (selected period)": "pm25_mean",
            "NO2 mean (selected period)": "no2_mean",
            "Complaints (selected period)": "total_complaints",
            "Sensor coverage (all-time)": "active_days",
        }

        if map_mode == "Neighborhood choropleth":
            st.caption(
                "Neighborhoods without direct sensor-period values are filled using IDW placeholders "
                "from nearby sensors (k=3, max distance=15 km)."
            )

            color_col = choropleth_metric_lookup[map_metric_label]
            fig = px.choropleth_mapbox(
                map_metrics,
                geojson=data.neighborhoods_geojson,
                locations="neighborhood",
                featureidkey="properties.neighborhood",
                color=color_col,
                hover_name="neighborhood",
                hover_data={
                    "neighborhood_secondary": True,
                    "coverage_source": True,
                    "sensor_count": True,
                    "pm25_map_value": ":.2f",
                    "pm25_mean_period": ":.2f",
                    "pm25_mean_estimated": ":.2f",
                    "no2_map_value": ":.2f",
                    "no2_mean_period": ":.2f",
                    "no2_mean_estimated": ":.2f",
                    "complaints_map_value": ":.1f",
                    "complaints_period": True,
                    "complaints_estimated": ":.1f",
                    "estimated_sensor_count": True,
                    "estimated_nearest_km": ":.2f",
                },
                color_continuous_scale="YlOrRd",
                mapbox_style="carto-positron",
                center={"lat": 41.8781, "lon": -87.6298},
                zoom=9,
                opacity=0.58,
            )

            if not sensors.empty:
                marker_sizes = np.clip(np.sqrt(sensors["total_complaints"].fillna(0) + 1) * 2.2, 6, 18)
                fig.add_trace(
                    go.Scattermapbox(
                        lat=sensors["lat"],
                        lon=sensors["lon"],
                        mode="markers",
                        marker={
                            "size": marker_sizes,
                            "color": sensors["pm25_mean"],
                            "colorscale": "Viridis",
                            "showscale": False,
                            "opacity": 0.85,
                        },
                        text=sensors["sensor_name"],
                        customdata=np.stack(
                            [
                                sensors["neighborhood"].fillna("Unassigned"),
                                sensors["pm25_mean"].round(2),
                                sensors["total_complaints"].astype(int),
                                sensors["active_days"].astype(int),
                            ],
                            axis=-1,
                        ),
                        hovertemplate=(
                            "<b>%{text}</b><br>"
                            "Neighborhood: %{customdata[0]}<br>"
                            "Avg PM2.5: %{customdata[1]}<br>"
                            "Complaints: %{customdata[2]}<br>"
                            "Active days: %{customdata[3]}<extra></extra>"
                        ),
                        name="Sensors",
                    )
                )
        else:
            heat_col = heatmap_metric_lookup[map_metric_label]
            heat_points = sensors.dropna(subset=["lat", "lon", heat_col]).copy()

            if heat_points.empty:
                st.warning("No sensor rows available in the selected filter range for the heatmap.")
                fig = go.Figure()
                fig.update_layout(
                    mapbox={
                        "style": "carto-positron",
                        "center": {"lat": 41.8781, "lon": -87.6298},
                        "zoom": 9,
                    }
                )
            else:
                fig = px.density_mapbox(
                    heat_points,
                    lat="lat",
                    lon="lon",
                    z=heat_col,
                    radius=28,
                    hover_name="sensor_name",
                    hover_data={
                        "neighborhood": True,
                        "pm25_mean": ":.2f",
                        "no2_mean": ":.2f",
                        "total_complaints": True,
                        "active_days": True,
                    },
                    color_continuous_scale="YlOrRd",
                    mapbox_style="carto-positron",
                    center={"lat": 41.8781, "lon": -87.6298},
                    zoom=9,
                    title="Continuous sensor density heatmap",
                )

            add_neighborhood_boundaries(fig, data.neighborhoods_geojson)

        fig.update_layout(
            margin={"l": 0, "r": 0, "t": 10, "b": 0},
            height=map_height_px,
            uirevision="map-view",
        )
        st.plotly_chart(
            fig,
            use_container_width=True,
            config={
                "scrollZoom": enable_scroll_zoom,
                "displaylogo": False,
                "modeBarButtonsToAdd": ["resetViewMapbox"],
            },
        )

    with tab_trends:
        if city_daily.empty:
            st.warning("No rows in selected range.")
        else:
            trend = make_subplots(specs=[[{"secondary_y": True}]])
            trend.add_trace(
                go.Scatter(
                    x=city_daily["date"],
                    y=city_daily["pm25_mean"],
                    mode="lines",
                    name="Citywide PM2.5 mean",
                    line={"width": 2},
                ),
                secondary_y=False,
            )
            trend.add_trace(
                go.Bar(
                    x=city_daily["date"],
                    y=city_daily["complaint_count"],
                    name="Daily complaints",
                    opacity=0.35,
                ),
                secondary_y=True,
            )
            trend.update_layout(
                title="PM2.5 vs 311 complaints over time",
                margin={"l": 0, "r": 0, "t": 45, "b": 0},
                legend={"orientation": "h", "y": 1.08},
            )
            trend.update_yaxes(title_text="PM2.5 (ug/m3)", secondary_y=False)
            trend.update_yaxes(title_text="Complaint count", secondary_y=True)
            st.plotly_chart(trend, use_container_width=True)

            rank = (
                map_metrics.dropna(subset=["pm25_mean_period"])
                .sort_values("pm25_mean_period", ascending=False)
                .head(15)
            )
            if not rank.empty:
                rank_fig = px.bar(
                    rank,
                    x="pm25_mean_period",
                    y="neighborhood",
                    orientation="h",
                    color="pm25_mean_period",
                    color_continuous_scale="YlOrRd",
                    title="Top 15 neighborhoods by PM2.5 in selected period",
                )
                rank_fig.update_layout(yaxis={"categoryorder": "total ascending"}, margin={"l": 0, "r": 0, "t": 45, "b": 0})
                st.plotly_chart(rank_fig, use_container_width=True)

    with tab_lag:
        lag_df = compute_lag_correlations(city_daily, max_lag=7)
        if lag_df.empty:
            st.warning("No rows in selected range.")
        else:
            lag_fig = px.bar(
                lag_df,
                x="lag_days",
                y="correlation",
                color="correlation",
                color_continuous_scale="RdBu",
                range_color=[-1, 1],
                title="Lead-lag correlation: PM2.5(t) vs Complaints(t+lag)",
            )
            lag_fig.update_layout(margin={"l": 0, "r": 0, "t": 45, "b": 0})
            st.plotly_chart(lag_fig, use_container_width=True)

            valid = lag_df.dropna(subset=["correlation"]).copy()
            if not valid.empty:
                valid["abs_corr"] = valid["correlation"].abs()
                best = valid.nlargest(1, "abs_corr").iloc[0]
                st.info(
                    f"Strongest absolute lag is {best['lag_days']:.0f} days "
                    f"with correlation {best['correlation']:.3f}."
                )

            spike_df, baseline = compute_spike_concordance(city_daily, threshold=35.0, window_days=2)
            spike_fig = px.line(
                spike_df,
                x="offset_day",
                y="mean_complaints",
                markers=True,
                title="Complaint response around PM2.5 spike days (city-level)",
            )
            if not np.isnan(baseline):
                spike_fig.add_hline(y=baseline, line_dash="dash", annotation_text="non-spike baseline")
            spike_fig.update_xaxes(dtick=1, title="Days relative to spike day")
            spike_fig.update_yaxes(title="Mean complaints")
            spike_fig.update_layout(margin={"l": 0, "r": 0, "t": 45, "b": 0})
            st.plotly_chart(spike_fig, use_container_width=True)

    with tab_quality:
        no_coverage = map_metrics[map_metrics["sensor_count"].fillna(0) == 0].copy()
        st.subheader("Neighborhoods without sensor coverage")
        st.caption(
            "These polygons remain individually represented. Coverage source shows whether a neighborhood "
            "currently uses direct period values, IDW estimates, or remains unavailable."
        )
        st.dataframe(
            no_coverage[[
                "neighborhood",
                "neighborhood_secondary",
                "sensor_count",
                "coverage_source",
                "pm25_map_value",
                "no2_map_value",
                "complaints_period",
                "complaints_map_value",
                "estimated_sensor_count",
                "estimated_nearest_km",
            ]].sort_values("neighborhood"),
            use_container_width=True,
            hide_index=True,
        )

        st.subheader("Filtered neighborhood metrics")
        st.dataframe(
            map_metrics.sort_values("neighborhood"),
            use_container_width=True,
            hide_index=True,
        )


if __name__ == "__main__":
    main()
