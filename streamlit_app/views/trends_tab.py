"""Temporal Trends tab: citywide pollutant-vs-complaints timeline and a monthly calendar heatmap.

Purpose: show day-to-day patterns and weekly seasonality for the selected window.
Inputs:  sidebar state and the city-daily frame (one row per calendar day in the window).
Outputs: renders Streamlit elements; nothing is returned.
Used by: streamlit_app/app.py.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from streamlit_app.constants import POLLUTANTS
from streamlit_app.sidebar import SidebarState
from streamlit_app.theme import style_fig


def render_trends_tab(ui: SidebarState, city_daily: pd.DataFrame) -> None:
    theme = ui.theme
    if city_daily.empty:
        st.warning("No rows in selected range.")
    else:
        pol_cfg = POLLUTANTS[ui.trend_metric_label]
        trend_value_col = pol_cfg.column
        trend_value_title = f"{pol_cfg.label} ({pol_cfg.unit})"
        missing_days = int(city_daily[trend_value_col].isna().sum())
        if missing_days > 0:
            st.caption(
                f"Note: {missing_days} day(s) in this window have no {ui.trend_metric_label} readings from source sensors. "
                "Visible breaks in the pollutant line reflect collection gaps, not dashboard errors."
            )

        trend = make_subplots(specs=[[{"secondary_y": True}]])
        trend.add_trace(
            go.Scatter(
                x=city_daily["date"],
                y=city_daily[trend_value_col],
                mode="lines" if ui.trend_chart_style == "Line + complaints" else "lines+markers",
                name=f"Citywide {ui.trend_metric_label} average",
                line={"width": 2, "color": theme["accent"]},
                marker={"color": theme["accent"]},
                fillcolor=theme["panel_bg"],
                fill="tozeroy" if ui.trend_chart_style == "Area + complaints" else None,
            ),
            secondary_y=False,
        )
        trend.add_trace(
            go.Bar(
                x=city_daily["date"],
                y=city_daily["complaint_count"],
                name="Daily complaints",
                marker_color=theme["bar_secondary"],
                opacity=0.55,
            ),
            secondary_y=True,
        )
        trend.update_layout(
            title=f"{ui.trend_metric_label} vs 311 Complaints Over Time",
            margin={"l": 0, "r": 0, "t": 45, "b": 45},
            legend={"orientation": "h", "y": 1.04},
        )
        style_fig(trend, theme)
        trend.update_yaxes(title_text=trend_value_title, secondary_y=False)
        trend.update_yaxes(title_text="Complaint count", secondary_y=True)
        st.plotly_chart(trend, width="stretch")

        if ui.calendar_metric_label in POLLUTANTS:
            pol_cfg = POLLUTANTS[ui.calendar_metric_label]
            calendar_value_col = pol_cfg.column
            calendar_title = f"{pol_cfg.label} Avg."
        else:
            calendar_value_col = "complaint_count"
            calendar_title = "Complaint count"
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
                    color_continuous_scale=theme["sequential"],
                    labels={
                        "x": "Day of week",
                        "y": "Week starting",
                        "color": calendar_title,
                    },
                    title=f"{ui.calendar_metric_label} calendar heatmap ({selected_month})",
                )
                calendar_fig.update_layout(margin={"l": 0, "r": 0, "t": 45, "b": 0})
                style_fig(calendar_fig, theme, axes=False)
                st.plotly_chart(calendar_fig, width="stretch")
