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
        filter_complaint_points,
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
        filter_complaint_points,
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


def format_delta(current: float | int, previous: float | int, decimals: int = 2) -> str | None:
    """Format KPI deltas as signed strings for Streamlit metric cards."""
    if pd.isna(previous):
        return None
    change = float(current) - float(previous)
    return f"{change:+.{decimals}f} vs prior period"


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
                go.Scattermap(
                    lon=lons,
                    lat=lats,
                    mode="lines",
                    line={"color": "rgba(0, 255, 65, 0.25)", "width": 1},
                    hoverinfo="skip",
                    showlegend=False,
                    name="Neighborhood boundary",
                )
            )


def sensor_marker_sizes(complaint_counts: pd.Series) -> np.ndarray:
    """Translate complaint totals into marker sizes for sensor points."""
    counts = pd.to_numeric(complaint_counts, errors="coerce").fillna(0)
    return np.clip(((counts + 1) ** 0.65) * 1.6, 6, 18)


def sensor_size_legend_counts(complaint_counts: pd.Series) -> list[int]:
    """Choose visually distinct complaint bins for the marker-size legend."""
    counts = pd.to_numeric(complaint_counts, errors="coerce").fillna(0)
    if counts.empty:
        return [0, 10, 40]

    low = max(0, int(np.floor(float(counts.min()))))
    high = max(low, int(np.ceil(float(counts.max()))))

    if high == low:
        return [low]

    # For wide ranges, geometric spacing avoids bins like 1 / 2 / 50.
    if high / max(low, 1) >= 6:
        mid = int(round(np.sqrt(max(low, 2.75) * high)))
        candidates = [low, mid, high]
    else:
        q35, q70 = counts.quantile([0.35, 0.70]).tolist()
        candidates = [low, int(round(float(q35))), int(round(float(q70))), high]

    ordered_candidates: list[int] = []
    for value in candidates:
        clean_value = max(0, int(value))
        if clean_value not in ordered_candidates:
            ordered_candidates.append(clean_value)

    def marker_size_for_count(count: int) -> float:
        return float(sensor_marker_sizes(pd.Series([count], dtype=float))[0])

    # Keep bins only when their legend marker sizes are visibly different.
    bins: list[int] = []
    min_size_gap = 2.5
    for idx, value in enumerate(ordered_candidates):
        marker_size = marker_size_for_count(value)
        is_last = idx == len(ordered_candidates) - 1
        if not bins:
            bins.append(value)
            continue

        prev_size = marker_size_for_count(bins[-1])
        if abs(marker_size - prev_size) >= min_size_gap or is_last:
            bins.append(value)

    if bins[-1] != high:
        bins.append(high)

    unique_bins: list[int] = []
    for value in bins:
        if value not in unique_bins:
            unique_bins.append(value)

    if len(unique_bins) > 3:
        mid_idx = len(unique_bins) // 2
        unique_bins = [unique_bins[0], unique_bins[mid_idx], unique_bins[-1]]

    return unique_bins


def add_sensor_markers(fig: go.Figure, sensors: pd.DataFrame) -> list[tuple[int, float]]:
    """Add sensor markers sized by complaint totals.

    Returns a list of (complaint_count, pixel_size) tuples so the caller can
    render a mobile-friendly caption below the map.
    """
    if sensors.empty:
        return []

    marker_sizes = sensor_marker_sizes(sensors["total_complaints"])
    fig.add_trace(
        go.Scattermap(
            lat=sensors["lat"],
            lon=sensors["lon"],
            mode="markers",
            marker={
                "size": marker_sizes,
                "color": sensors["pm25_mean"],
                # Color scheme for sensor markers
                "colorscale": [[0, "#003300"], [0.25, "#00aa33"], [0.5, "#00ff41"], [0.75, "#aaff44"], [1, "#ffffff"]],
                "showscale": False,
                "opacity": 0.85,
            },
            text=sensors["sensor_name"],
            customdata=np.stack(
                [
                    sensors["neighborhood"].fillna("Unassigned"),
                    sensors["pm25_mean"].round(2),
                    sensors["no2_mean"].round(2),
                    sensors["total_complaints"].round(0).astype(int),
                    sensors["active_days"].astype(int),
                ],
                axis=-1,
            ),
            hovertemplate=(
                "<b>%{text}</b><br>"
                "Neighborhood: %{customdata[0]}<br>"
                "Avg PM2.5: %{customdata[1]} ug/m³<br>"
                "Avg NO2: %{customdata[2]} ppb<br>"
                "Complaints: %{customdata[3]}<br>"
                "Active days: %{customdata[4]}<extra></extra>"
            ),
            name="Sensors (size = complaints)",
            showlegend=True,
        )
    )

    # Phantom traces drive the desktop marker-size legend inside the Plotly panel.
    # On mobile the Plotly legend is hidden via CSS; the HTML caption below takes over.
    bins = sensor_size_legend_counts(sensors["total_complaints"])
    bin_data = [
        (count, float(sensor_marker_sizes(pd.Series([count], dtype=float))[0]))
        for count in bins
    ]
    for count, legend_size in bin_data:
        fig.add_trace(
            go.Scattermap(
                lat=[None],
                lon=[None],
                mode="markers",
                marker={"size": legend_size, "color": "#00ff41", "opacity": 0.85},
                hoverinfo="skip",
                name=f"{count} complaints",
                showlegend=True,
            )
        )
    return bin_data


def add_complaint_locations(fig: go.Figure, complaints: pd.DataFrame) -> None:
    """Add complaint-level geocoded points as a toggleable overlay."""
    if complaints.empty:
        return

    complaint_dates = complaints["date"].dt.strftime("%Y-%m-%d")
    nearest_sensor = complaints.get("nearest_sensor", pd.Series("Unknown", index=complaints.index)).fillna("Unknown")
    fig.add_trace(
        go.Scattermap(
            lat=complaints["latitude"],
            lon=complaints["longitude"],
            mode="markers",
            marker={
                "size": 7,
                "color": "#00ff41",
                "opacity": 0.95,
            },
            text=complaints["complaint_id"].astype(str),
            customdata=np.stack(
                [
                    complaint_dates,
                    complaints["neighborhood"].fillna("Unassigned"),
                    nearest_sensor,
                ],
                axis=-1,
            ),
            hovertemplate=(
                "<b>Complaint %{text}</b><br>"
                "Date: %{customdata[0]}<br>"
                "Neighborhood: %{customdata[1]}<br>"
                "Nearest sensor: %{customdata[2]}<extra></extra>"
            ),
            name="Complaint locations",
            showlegend=True,
        )
    )


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
        # Mouse-wheel zoom is always enabled.
        map_height_px = st.slider(
            "Map height (px)",
            min_value=500,
            max_value=1200,
            value=760,
            step=20,
            help="Increase this if the map feels too tight vertically.",
        )

        st.caption("Color scale layout")
        # Compact color scale is always on; sliders let desktop users fine-tune.
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

    filtered = filter_merged_data(
        merged=merged,
        start_date=pd.Timestamp(start_date),
        end_date=pd.Timestamp(end_date),
        neighborhoods=selected_neighborhoods,
    )
    complaint_points = filter_complaint_points(
        complaints=data.complaints,
        start_date=pd.Timestamp(start_date),
        end_date=pd.Timestamp(end_date),
        neighborhoods=selected_neighborhoods,
    )

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
    map_metrics = enrich_neighborhood_metrics_with_estimates(
        neighborhood_metrics=base_map_metrics,
        sensors=sensors,
        neighborhoods_geojson=data.neighborhoods_geojson,
        k=3,
        idw_power=2.0,
        max_distance_km=15.0,
    )

    if show_quick_tour:
        with st.expander("Quick tour: how to use this dashboard", expanded=False):
            st.markdown(
                """
                1. Set your date range and optionally focus on specific neighborhoods.
                2. Start in Neighborhood Map to compare air conditions and complaint activity.
                3. Use Temporal Trends to explore citywide day-to-day patterns and calendar seasonality.
                4. Visit Neighborhood Trends for ranked neighborhood comparisons.
                5. Check Lead-Lag & Spikes to explore whether complaint activity follows pollution spikes.
                6. Open Coverage QA for transparency on direct sensor coverage vs estimated neighborhoods.
                """
            )

    selected_days = int((pd.Timestamp(end_date) - pd.Timestamp(start_date)).days) + 1
    prev_end = pd.Timestamp(start_date) - pd.Timedelta(days=1)
    prev_start = prev_end - pd.Timedelta(days=max(selected_days - 1, 0))
    previous_filtered = filter_merged_data(
        merged=merged,
        start_date=prev_start,
        end_date=prev_end,
        neighborhoods=selected_neighborhoods,
    )

    current_pm25 = float(filtered["pm25_mean"].mean()) if not filtered.empty else float("nan")
    previous_pm25 = float(previous_filtered["pm25_mean"].mean()) if not previous_filtered.empty else float("nan")

    current_no2 = float(filtered["no2_mean"].mean()) if not filtered.empty else float("nan")
    previous_no2 = float(previous_filtered["no2_mean"].mean()) if not previous_filtered.empty else float("nan")

    current_complaints = int(filtered["complaint_count"].sum()) if not filtered.empty else 0
    previous_complaints = int(previous_filtered["complaint_count"].sum()) if not previous_filtered.empty else 0

    current_sensors = int(filtered["sensor_name"].nunique()) if not filtered.empty else 0
    previous_sensors = int(previous_filtered["sensor_name"].nunique()) if not previous_filtered.empty else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric(
        "Average PM2.5 (ug/m3)",
        f"{current_pm25:.2f}" if not np.isnan(current_pm25) else "n/a",
        delta=format_delta(current_pm25, previous_pm25, decimals=2),
    )
    col2.metric(
        "Average NO2 (ppb)",
        f"{current_no2:.2f}" if not np.isnan(current_no2) else "n/a",
        delta=format_delta(current_no2, previous_no2, decimals=2),
    )
    col3.metric(
        "Total 311 air complaints",
        f"{current_complaints:,}",
        delta=f"{current_complaints - previous_complaints:+,} vs prior period",
    )
    col4.metric(
        "Active sensors",
        f"{current_sensors:,}",
        delta=f"{current_sensors - previous_sensors:+,} vs prior period",
    )

    st.caption(
        f"Selection window: {start_date:%b %d, %Y} to {end_date:%b %d, %Y} ({selected_days} days)."
    )

    tab_map, tab_trends, tab_neighborhood, tab_lag, tab_quality = st.tabs(
        ["Neighborhood Map", "Temporal Trends", "Neighborhood Trends", "Lead-Lag & Spikes", "Coverage QA"]
    )

    with tab_map:
        map_label_lookup = {
            "neighborhood": "Neighborhood",
            "neighborhood_secondary": "Neighborhood alias",
            "coverage_source": "Coverage source",
            "sensor_count": "Sensors in neighborhood",
            "pm25_map_value": "PM2.5 average (ug/m3)",
            "pm25_mean_period": "PM2.5 direct value (ug/m3)",
            "pm25_mean_estimated": "PM2.5 IDW estimate (ug/m3)",
            "no2_map_value": "NO2 average (ppb)",
            "no2_mean_period": "NO2 direct value (ppb)",
            "no2_mean_estimated": "NO2 IDW estimate (ppb)",
            "complaints_map_value": "Complaints (period)",
            "complaints_period": "Complaints direct value",
            "complaints_estimated": "Complaints IDW estimate",
            "estimated_sensor_count": "Sensors used for estimate",
            "estimated_nearest_km": "Nearest sensor distance (km)",
            "pm25_mean": "PM2.5 average (ug/m3)",
            "no2_mean": "NO2 average (ppb)",
            "total_complaints": "Complaints (period)",
            "active_days": "Active sensor days",
        }

        colorbar_title_lookup = {
            "PM2.5 mean (selected period)": "PM2.5 Avg.",
            "NO2 mean (selected period)": "NO2 Avg.",
            "Complaints (selected period)": "Complaints",
            "Sensor coverage (all-time)": "Sensors",
        }

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
            fig = px.choropleth_map(
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
                labels=map_label_lookup,
                # Color scheme for neighborhood map, neighborhood polygons
                color_continuous_scale=[[0, "#001a00"], [0.25, "#005500"], [0.5, "#00aa33"], [0.75, "#00ff41"], [1, "#aaffaa"]],
                map_style="carto-darkmatter",
                center={"lat": 41.8781, "lon": -87.6298},
                zoom=9,
                opacity=0.58,
            )
        else:
            heat_col = heatmap_metric_lookup[map_metric_label]
            heat_points = sensors.dropna(subset=["lat", "lon", heat_col]).copy()

            if heat_points.empty:
                st.warning("No sensor rows available in the selected filter range for the heatmap.")
                fig = go.Figure()
                fig.update_layout(
                    map={
                        "style": "carto-positron",
                        "center": {"lat": 41.8781, "lon": -87.6298},
                        "zoom": 9,
                    }
                )
            else:
                fig = px.density_map(
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
                    labels=map_label_lookup,
                    #Color scheme for neighborhood map, "continuous heatmap" mode
                    color_continuous_scale=[[0, "#000000"], [0.25, "#003300"], [0.5, "#00aa33"], [0.75, "#00ff41"], [1, "#ccffcc"]],
                    map_style="carto-darkmatter",
                    center={"lat": 41.8781, "lon": -87.6298},
                    zoom=9,
                    title="Continuous sensor density heatmap",
                )

            add_neighborhood_boundaries(fig, data.neighborhoods_geojson)

        size_legend_bins: list[tuple[int, float]] = []
        if show_sensor_markers:
            size_legend_bins = add_sensor_markers(fig, sensors)

        if show_complaint_locations:
            add_complaint_locations(fig, complaint_points)

        # Colorbar: vertical floating overlay on the right side (desktop).
        # On mobile the Plotly colorbar is hidden via CSS; a custom HTML bar shows below.
        fig.update_coloraxes(
            colorbar_title=colorbar_title_lookup[map_metric_label],
            colorbar_thicknessmode="pixels",
            colorbar_thickness=color_scale_width_px,
            colorbar_len=color_scale_height_pct / 100.0,
            colorbar_x=color_scale_x,
            colorbar_xanchor="right",
            colorbar_y=0.5,
            colorbar_yanchor="middle",
            colorbar_tickfont={"size": 10, "color": "#00ff41"},
            colorbar_title_font={"size": 11, "color": "#00ff41"},
            colorbar_bgcolor="rgba(10, 10, 10, 0.88)",
            colorbar_bordercolor="rgba(0, 255, 65, 0.35)",
            colorbar_borderwidth=.11,
            colorbar_outlinewidth=1,
            colorbar_outlinecolor="rgba(0, 255, 65, 0.5)",
        )

        fig.update_layout(
            margin={"l": 0, "r": 0, "t": 10, "b": 0},
            height=map_height_px,
            uirevision="map-view",
            # Legend only shows toggleable layer names (sensor markers, complaints).
            legend={
                "title": {"text": "Map layers", "font": {"color": "#00ff41", "size": 13}},
                "font": {"color": "#00ff41", "size": 11},
                "yanchor": "top",
                "y": 0.99,
                "xanchor": "right",
                "x": 0.99,
                "bgcolor": "rgba(10, 10, 10, 0.88)",
                "bordercolor": "rgba(0, 255, 65, 0.40)",
                "borderwidth": 1,
            },
        )
        st.plotly_chart(
            fig,
            use_container_width=True,
            config={
                "scrollZoom": True,
                "displaylogo": False,
            },
        )

        # ── Responsive legend handling ─────────────────────────────────────────
        # Desktop: the Plotly legend panel and colorbar float over the map.
        # Mobile:  CSS hides those overlays; a custom HTML section appears below.
        st.markdown(
            """
            <style>
            @media (max-width: 768px) {
                /* Hide Plotly floating overlays on mobile */
                .js-plotly-plot .legend { display: none !important; }
                .js-plotly-plot .colorbar { display: none !important; }
                /* Reveal the mobile legend section */
                .mobile-map-legend { display: block !important; }
            }
            .mobile-map-legend { display: none; }
            </style>
            """,
            unsafe_allow_html=True,
        )

        if size_legend_bins:
            # Scale dot sizes to em units: map [6, 18]px range to [0.55, 1.3]em.
            def _px_to_em(dot_px: float) -> float:
                return round(0.55 + (dot_px - 6) / (18 - 6) * 0.75, 2)

            dot_parts = []
            for count, dot_px in size_legend_bins:
                em = _px_to_em(dot_px)
                dot_parts.append(
                    f'<span style="font-size:{em}em; color:#00ff41; line-height:1;">&#11044;</span>'
                    f'<span style="font-size:0.75em; color:#888; margin-left:3px;">{count}</span>'
                )
            dots_html = '<span style="margin:0 8px; color:#333;"> &middot; </span>'.join(dot_parts)
            metric_label = colorbar_title_lookup[map_metric_label]
            st.markdown(
                f"""
                <div class="mobile-map-legend"
                     style="padding:10px 0 4px; font-family:monospace;">
                  <!-- Gradient colorbar strip -->
                  <div style="display:flex; align-items:center; gap:8px; margin-bottom:6px;">
                    <span style="font-size:0.72em; color:#888; white-space:nowrap;">Low</span>
                    <div style="
                      flex:1;
                      height:13px;
                      background:linear-gradient(to right,#001a00,#005500,#00aa33,#00ff41,#aaffaa);
                      border-radius:3px;
                      border:1px solid rgba(0,255,65,0.3);
                    "></div>
                    <span style="font-size:0.72em; color:#888; white-space:nowrap;">High</span>
                  </div>
                  <div style="text-align:center; font-size:0.7em; color:#666;
                              margin-bottom:8px;">{metric_label}</div>
                  <!-- Marker size legend -->
                  <div style="text-align:center; font-size:0.78em; color:#888;">
                    Marker size&nbsp;&rarr;&nbsp;complaints:&nbsp;&nbsp;{dots_html}
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    with tab_trends:
        if city_daily.empty:
            st.warning("No rows in selected range.")
        else:
            trend_value_col = "pm25_mean" if trend_metric_label == "PM2.5" else "no2_mean"
            trend_value_title = "PM2.5 (ug/m3)" if trend_metric_label == "PM2.5" else "NO2 (ppb)"
            missing_days = int(city_daily[trend_value_col].isna().sum())
            if missing_days > 0:
                st.caption(
                    f"Note: {missing_days} day(s) in this window have no {trend_metric_label} readings from source sensors. "
                    "Visible breaks in the pollutant line reflect collection gaps, not dashboard errors."
                )

            trend = make_subplots(specs=[[{"secondary_y": True}]])
            trend.add_trace(
                go.Scatter(
                    x=city_daily["date"],
                    y=city_daily[trend_value_col],
                    mode="lines" if trend_chart_style == "Line + complaints" else "lines+markers",
                    name=f"Citywide {trend_metric_label} average",
                    line={"width": 2, "color": "#00ff41"},
                    marker={"color": "#00ff41"},
                    fillcolor="rgba(0, 255, 65, 0.15)",
                    fill="tozeroy" if trend_chart_style == "Area + complaints" else None,
                ),
                secondary_y=False,
            )
            trend.add_trace(
                go.Bar(
                    x=city_daily["date"],
                    y=city_daily["complaint_count"],
                    name="Daily complaints",
                    marker_color="#4a9a5a",
                    opacity=0.45,
                ),
                secondary_y=True,
            )
            trend.update_layout(
                title=f"{trend_metric_label} vs 311 Complaints Over Time",
                margin={"l": 0, "r": 0, "t": 45, "b": 45},
                legend={"orientation": "h", "y": 1.04},
                paper_bgcolor="#0a0a0a",
                plot_bgcolor="#0a0a0a",
                font={"color": "#e0e0e0", "family": "monospace"},
                title_font={"color": "#00ff41"},
                xaxis={"gridcolor": "#1a3a1a", "color": "#e0e0e0"},
                yaxis={"gridcolor": "#1a3a1a", "color": "#e0e0e0"},
            )
            trend.update_yaxes(title_text=trend_value_title, secondary_y=False)
            trend.update_yaxes(title_text="Complaint count", secondary_y=True)
            st.plotly_chart(trend, use_container_width=True)

            calendar_value_lookup = {
                "PM2.5": ("pm25_mean", "PM2.5 Avg."),
                "NO2": ("no2_mean", "NO2 Avg."),
                "Complaints": ("complaint_count", "Complaint count"),
            }
            calendar_value_col, calendar_title = calendar_value_lookup[calendar_metric_label]
            monthly_options = sorted(city_daily["date"].dt.to_period("M").astype(str).unique().tolist())
            default_month_idx = max(len(monthly_options) - 1, 0)
            selected_month = st.selectbox(
                "Calendar month",
                options=monthly_options,
                index=default_month_idx,
                help="Calendar-like grid with days grouped by week and weekday.",
            )

            calendar_source = city_daily[city_daily["date"].dt.to_period("M").astype(str) == selected_month].copy()
            if calendar_source.empty:
                st.info("No rows available for the selected calendar month.")
            else:
                calendar_source["week_start"] = calendar_source["date"] - pd.to_timedelta(calendar_source["date"].dt.weekday, unit="D")
                calendar_source["weekday"] = pd.Categorical(
                    calendar_source["date"].dt.day_name().str.slice(0, 3),
                    categories=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
                    ordered=True,
                )

                calendar_pivot = (
                    calendar_source.pivot_table(
                        index="week_start",
                        columns="weekday",
                        values=calendar_value_col,
                        aggfunc="mean",
                    )
                    .sort_index()
                )

                if not calendar_pivot.empty:
                    calendar_fig = px.imshow(
                        calendar_pivot,
                        aspect="auto",
                        # Color scheme for calendar heatmap
                        color_continuous_scale=[[0, "#001a00"], [0.5, "#00aa33"], [1, "#00ff41"]],
                        labels={
                            "x": "Day of week",
                            "y": "Week starting",
                            "color": calendar_title,
                        },
                        title=f"{calendar_metric_label} calendar heatmap ({selected_month})",
                    )
                    calendar_fig.update_layout(
                        margin={"l": 0, "r": 0, "t": 45, "b": 0},
                        paper_bgcolor="#0a0a0a",
                        plot_bgcolor="#0a0a0a",
                        font={"color": "#e0e0e0", "family": "monospace"},
                        title_font={"color": "#00ff41"},
                    )
                    st.plotly_chart(calendar_fig, use_container_width=True)

    with tab_neighborhood:
        ranking_value_col = "pm25_mean_period" if trend_metric_label == "PM2.5" else "no2_mean_period"
        ranking_value_title = "PM2.5 average (selected period)" if trend_metric_label == "PM2.5" else "NO2 average (selected period)"

        rank = (
            map_metrics.dropna(subset=[ranking_value_col])
            .sort_values(ranking_value_col, ascending=False)
            .head(15)
        )
        if rank.empty:
            st.warning("No neighborhood trend rows available for the current filters.")
        else:
            rank_fig = px.bar(
                rank,
                x=ranking_value_col,
                y="neighborhood",
                orientation="h",
                color=ranking_value_col,
                # Color scheme for neighborhood trends tab
                color_continuous_scale=[[0, "#001a00"], [0.5, "#00aa33"], [1, "#00ff41"]],
                title=f"Top 15 neighborhoods by {trend_metric_label} in selected period",
                labels={
                    "neighborhood": "Neighborhood",
                    ranking_value_col: ranking_value_title,
                },
            )
            rank_fig.update_layout(
                yaxis={"categoryorder": "total ascending"},
                margin={"l": 0, "r": 0, "t": 45, "b": 0},
                paper_bgcolor="#0a0a0a",
                plot_bgcolor="#0a0a0a",
                font={"color": "#e0e0e0", "family": "monospace"},
                title_font={"color": "#00ff41"},
                xaxis={"gridcolor": "#1a3a1a", "color": "#e0e0e0"},
                yaxis2={"gridcolor": "#1a3a1a", "color": "#e0e0e0"},
            )
            st.plotly_chart(rank_fig, use_container_width=True)

    with tab_lag:
        with st.expander("About these charts", expanded=False):
            st.markdown(
                """
                **Lead-lag correlation** asks: when PM2.5 is elevated on day *t*, \
does complaint activity rise or fall on day *t + lag*? \
Positive lags (right side of the chart) mean complaints *trail* pollution — \
residents react after sensors register a spike. \
Negative lags mean complaints *precede* measured pollution — \
possibly capturing smell/odor reports before instruments register them. \
A bar near zero correlation at a given lag means pollution levels at that delay \
have little predictive relationship with complaints.

                **Complaint response around spike days** identifies every day in the \
selected window where city-wide average PM2.5 is in the top *N%* (set in the sidebar), \
then averages complaint counts at offsets −2 through +2 days around those events. \
The dashed baseline is the mean complaint count on *non-spike* days. \
A line rising above the baseline on days 0–2 suggests complaints measurably follow \
pollution spikes; a line below baseline on day −1 or −2 could indicate \
anticipatory or odor-driven reporting.
                """
            )

        lag_df = compute_lag_correlations(city_daily, max_lag=7)
        if lag_df.empty:
            st.warning("No rows in selected range.")
        else:
            lag_fig = px.bar(
                lag_df,
                x="lag_days",
                y="correlation",
                color="correlation",
                color_continuous_scale=[[0, "#550000"], [0.5, "#1a3a1a"], [1, "#00ff41"]],
                range_color=[-1, 1],
                title="Lead-lag correlation: PM2.5(t) vs Complaints(t+lag)",
            )
            lag_fig.update_layout(
                margin={"l": 0, "r": 0, "t": 45, "b": 0},
                paper_bgcolor="#0a0a0a",
                plot_bgcolor="#0a0a0a",
                font={"color": "#e0e0e0", "family": "monospace"},
                title_font={"color": "#00ff41"},
                xaxis={"gridcolor": "#1a3a1a", "color": "#e0e0e0"},
                yaxis={"gridcolor": "#1a3a1a", "color": "#e0e0e0"},
            )
            st.plotly_chart(lag_fig, use_container_width=True)

            valid = lag_df.dropna(subset=["correlation"]).copy()
            if not valid.empty:
                valid["abs_corr"] = valid["correlation"].abs()
                best = valid.nlargest(1, "abs_corr").iloc[0]
                st.info(
                    f"Strongest absolute lag is {best['lag_days']:.0f} days "
                    f"with correlation {best['correlation']:.3f}."
                )

            spike_percentile = spike_percentile_pct / 100.0
            spike_df, baseline = compute_spike_concordance(
                city_daily,
                spike_percentile=spike_percentile,
                window_days=2,
            )
            spike_title = (
                f"Complaint response around PM2.5 spike days "
                f"(top {100 - spike_percentile_pct}%, city-level)"
            )
            spike_fig = px.line(
                spike_df,
                x="offset_day",
                y="mean_complaints",
                markers=True,
                title=spike_title,
            )
            if not np.isnan(baseline):
                spike_fig.add_hline(y=baseline, line_dash="dash", line_color="#888888", annotation_text="non-spike baseline", annotation_font_color="#888888")
            spike_fig.update_xaxes(dtick=1, title="Days relative to spike day")
            spike_fig.update_yaxes(title="Mean complaints")
            spike_fig.update_layout(
                margin={"l": 0, "r": 0, "t": 45, "b": 0},
                paper_bgcolor="#0a0a0a",
                plot_bgcolor="#0a0a0a",
                font={"color": "#e0e0e0", "family": "monospace"},
                title_font={"color": "#00ff41"},
                xaxis={"gridcolor": "#1a3a1a", "color": "#e0e0e0"},
                yaxis={"gridcolor": "#1a3a1a", "color": "#e0e0e0"},
            )
            st.plotly_chart(spike_fig, use_container_width=True)

    with tab_quality:
        quality_columns = [
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
        ]
        quality_label_lookup = {
            "neighborhood": "Neighborhood",
            "neighborhood_secondary": "Neighborhood alias",
            "sensor_count": "Sensors in neighborhood",
            "coverage_source": "Coverage source",
            "pm25_map_value": "PM2.5 average (ug/m3)",
            "no2_map_value": "NO2 average (ppb)",
            "complaints_period": "Complaints direct value",
            "complaints_map_value": "Complaints (period)",
            "estimated_sensor_count": "Sensors used for estimate",
            "estimated_nearest_km": "Nearest sensor distance (km)",
        }

        no_coverage = map_metrics[map_metrics["sensor_count"].fillna(0) == 0].copy()
        st.subheader("Neighborhoods without sensor coverage")
        st.caption(
            "These polygons remain individually represented. Coverage source shows whether a neighborhood "
            "currently uses direct period values, IDW estimates, or remains unavailable."
        )
        st.dataframe(
            no_coverage[quality_columns].rename(columns=quality_label_lookup).sort_values("Neighborhood"),
            use_container_width=True,
            hide_index=True,
        )

        st.subheader("Filtered neighborhood metrics")
        st.dataframe(
            map_metrics.rename(columns=quality_label_lookup).sort_values("Neighborhood"),
            use_container_width=True,
            hide_index=True,
        )


if __name__ == "__main__":
    main()
