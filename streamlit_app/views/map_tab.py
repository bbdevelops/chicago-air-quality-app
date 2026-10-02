"""Neighborhood Map tab: choropleth or sensor heatmap with optional sensor and complaint overlays.

Purpose: draw the main map, its floating colorbar/legend, and the mobile-only HTML legend below it.
Inputs:  sidebar state, PipelineData (for the GeoJSON), neighborhood map metrics, the sensor snapshot
         and the date/neighborhood-filtered complaint points.
Outputs: renders Streamlit elements; nothing is returned.
Used by: streamlit_app/app.py.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from streamlit_app.constants import (
    CHICAGO_CENTER,
    CHICAGO_ZOOM,
    COLUMN_LABELS,
    HOVER_EXTRA_LABELS,
    MAP_METRICS,
)
from streamlit_app.loading import PipelineData
from streamlit_app.map_layers import add_complaint_locations, add_neighborhood_boundaries, add_sensor_markers
from streamlit_app.sidebar import SidebarState
from streamlit_app.theme import AQI_COLORSCALE, AQI_CSS_GRADIENT, AQI_RANGE, style_fig


def render_map_tab(
    ui: SidebarState,
    data: PipelineData,
    map_metrics: pd.DataFrame,
    sensors: pd.DataFrame,
    complaint_points: pd.DataFrame,
) -> None:
    theme = ui.theme
    metric_cfg = MAP_METRICS[ui.map_metric_label]

    # AQI uses the fixed EPA band scale over 0–500 so colors are absolute;
    # other metrics use the active theme's sequential/density ramp.
    choropleth_scale = AQI_COLORSCALE if metric_cfg.is_aqi else theme["sequential"]
    density_scale = AQI_COLORSCALE if metric_cfg.is_aqi else theme["density"]
    metric_range = list(AQI_RANGE) if metric_cfg.is_aqi else None

    if ui.map_mode == "Neighborhood choropleth":
        st.caption(
            "Neighborhoods without direct sensor-period values are filled using IDW placeholders "
            f"from nearby sensors (k={ui.idw_k}, max distance={ui.idw_max_km} km)."
        )

        fig = px.choropleth_map(
            map_metrics,
            geojson=data.map_geojson,
            locations="neighborhood",
            featureidkey="properties.neighborhood",
            color=metric_cfg.choropleth_col,
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
            labels=COLUMN_LABELS,
            color_continuous_scale=choropleth_scale,
            range_color=metric_range,
            map_style=theme["map_style"],
            center=CHICAGO_CENTER,
            zoom=CHICAGO_ZOOM,
            opacity=0.58,
        )
    else:
        heat_col = metric_cfg.heatmap_col
        heat_points = sensors.dropna(subset=["lat", "lon", heat_col]).copy()

        if heat_points.empty:
            st.warning("No sensor rows available in the selected filter range for the heatmap.")
            fig = go.Figure()
            fig.update_layout(
                map={
                    "style": theme["map_style"],
                    "center": CHICAGO_CENTER,
                    "zoom": CHICAGO_ZOOM,
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
                labels={**COLUMN_LABELS, **HOVER_EXTRA_LABELS},
                color_continuous_scale=density_scale,
                range_color=metric_range,
                map_style=theme["map_style"],
                center=CHICAGO_CENTER,
                zoom=CHICAGO_ZOOM,
                title="Continuous sensor density heatmap",
            )

        add_neighborhood_boundaries(fig, data.map_geojson, theme["boundary_line"])

    size_legend_bins: list[tuple[int, float]] = []
    if ui.show_sensor_markers:
        size_legend_bins = add_sensor_markers(fig, sensors, theme)

    if ui.show_complaint_locations:
        add_complaint_locations(fig, complaint_points, theme["marker_solid"])

    # Colorbar: vertical floating overlay on the right side (desktop).
    # On mobile the Plotly colorbar is hidden via CSS; a custom HTML bar shows below.
    fig.update_coloraxes(
        colorbar_title=metric_cfg.colorbar_title,
        colorbar_thicknessmode="pixels",
        colorbar_thickness=ui.color_scale_width_px,
        colorbar_len=ui.color_scale_height_pct / 100.0,
        colorbar_x=ui.color_scale_x,
        colorbar_xanchor="right",
        colorbar_y=0.5,
        colorbar_yanchor="middle",
        colorbar_tickfont={"size": 10, "color": theme["accent"]},
        colorbar_title_font={"size": 11, "color": theme["accent"]},
        colorbar_bgcolor=theme["panel_bg"],
        colorbar_bordercolor=theme["panel_border"],
        colorbar_borderwidth=1,
        colorbar_outlinewidth=1,
        colorbar_outlinecolor=theme["panel_border"],
    )

    fig = style_fig(fig, theme, margin={"l": 0, "r": 0, "t": 10, "b": 0})
    fig.update_layout(
        height=ui.map_height_px,
        uirevision="map-view",
        # Legend only shows toggleable layer names (sensor markers, complaints).
        legend={
            "title": {"text": "Map layers", "font": {"color": theme["accent"], "size": 13}},
            "font": {"color": theme["accent"], "size": 11},
            "yanchor": "top",
            "y": 0.99,
            "xanchor": "right",
            "x": 0.99,
            "bgcolor": theme["panel_bg"],
            "bordercolor": theme["panel_border"],
            "borderwidth": 1,
        },
    )
    st.plotly_chart(
        fig,
        width="stretch",
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
                f'<span style="font-size:{em}em; color:{theme["marker_solid"]}; line-height:1;">&#11044;</span>'
                f'<span style="font-size:0.75em; color:{theme["muted"]}; margin-left:3px;">{count}</span>'
            )
        dots_html = f'<span style="margin:0 8px; color:{theme["muted"]};"> &middot; </span>'.join(dot_parts)
        metric_label = metric_cfg.colorbar_title
        legend_gradient = AQI_CSS_GRADIENT if metric_cfg.is_aqi else theme["css_gradient"]
        low_label, high_label = ("0", "500") if metric_cfg.is_aqi else ("Low", "High")
        st.markdown(
            f"""
            <div class="mobile-map-legend"
                 style="padding:10px 0 4px; font-family:{theme['font_family']};">
              <!-- Gradient colorbar strip -->
              <div style="display:flex; align-items:center; gap:8px; margin-bottom:6px;">
                <span style="font-size:0.72em; color:{theme['muted']}; white-space:nowrap;">{low_label}</span>
                <div style="
                  flex:1;
                  height:13px;
                  background:{legend_gradient};
                  border-radius:3px;
                  border:1px solid {theme['panel_border']};
                "></div>
                <span style="font-size:0.72em; color:{theme['muted']}; white-space:nowrap;">{high_label}</span>
              </div>
              <div style="text-align:center; font-size:0.7em; color:{theme['muted']};
                          margin-bottom:8px;">{metric_label}</div>
              <!-- Marker size legend -->
              <div style="text-align:center; font-size:0.78em; color:{theme['muted']};">
                Marker size&nbsp;&rarr;&nbsp;complaints:&nbsp;&nbsp;{dots_html}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
