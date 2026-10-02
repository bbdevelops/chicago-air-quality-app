"""Headline section above the tabs: AQI hero banner, KPI cards and the selection-window caption.

Purpose: summarize the selected window (and compare it with the equally long prior window).
Inputs:  date-filtered merged sensor-day frames for the current and prior period, plus the date range.
Outputs: renders Streamlit elements; nothing is returned.
Used by: streamlit_app/app.py.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import streamlit as st

from aqi import aqi_category, aqi_health_message, pm25_to_aqi


def format_delta(current: float | int, previous: float | int, decimals: int = 2) -> str | None:
    """Format KPI deltas as signed strings for Streamlit metric cards."""
    if pd.isna(previous):
        return None
    change = float(current) - float(previous)
    return f"{change:+.{decimals}f} vs prior period"


def _safe_metric(df_sub: pd.DataFrame, col: str, agg: str, fill_val: float | int) -> float | int:
    if df_sub.empty:
        return fill_val
    val = getattr(df_sub[col], agg)()
    return float(val) if isinstance(fill_val, float) else int(val)


def render_summary(
    filtered: pd.DataFrame,
    previous_filtered: pd.DataFrame,
    start_date: date,
    end_date: date,
    selected_days: int,
) -> None:
    """Render the AQI banner, the four KPI cards and the selection-window caption."""
    current_pm25 = _safe_metric(filtered, "pm25_mean", "mean", float("nan"))
    previous_pm25 = _safe_metric(previous_filtered, "pm25_mean", "mean", float("nan"))
    current_no2 = _safe_metric(filtered, "no2_mean", "mean", float("nan"))
    previous_no2 = _safe_metric(previous_filtered, "no2_mean", "mean", float("nan"))
    current_complaints = _safe_metric(filtered, "complaint_count", "sum", 0)
    previous_complaints = _safe_metric(previous_filtered, "complaint_count", "sum", 0)
    current_sensors = _safe_metric(filtered, "sensor_name", "nunique", 0)
    previous_sensors = _safe_metric(previous_filtered, "sensor_name", "nunique", 0)

    # ── AQI hero banner ────────────────────────────────────────────────────
    # Translate the selection-average PM2.5 into the public-facing EPA AQI so the
    # headline number is the one people recognize, with a plain-language health line.
    current_aqi = pm25_to_aqi(current_pm25) if not np.isnan(current_pm25) else float("nan")
    aqi_label, aqi_color = aqi_category(current_aqi)
    aqi_message = aqi_health_message(current_aqi)
    aqi_value_text = f"{current_aqi:.0f}" if not np.isnan(current_aqi) else "n/a"
    # Dark text on the light-yellow/green bands, white elsewhere, for contrast.
    text_color = "#1a1a1a" if not np.isnan(current_aqi) and current_aqi <= 100 else "#ffffff"
    st.markdown(
        f"""
        <div style="background:{aqi_color}; border-radius:10px; padding:14px 18px;
                    margin-bottom:14px; display:flex; align-items:center; gap:18px;
                    flex-wrap:wrap; color:{text_color};">
          <div style="font-size:2.4em; font-weight:700; line-height:1;">{aqi_value_text}</div>
          <div style="min-width:180px;">
            <div style="font-size:1.15em; font-weight:700;">Air Quality Index &mdash; {aqi_label}</div>
            <div style="font-size:0.9em; opacity:0.92;">{aqi_message}</div>
          </div>
          <div style="font-size:0.78em; opacity:0.85; margin-left:auto;">
            Based on average PM2.5 in the selected window (EPA 2024 breakpoints).
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

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
