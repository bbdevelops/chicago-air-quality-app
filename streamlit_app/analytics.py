"""Lead-lag and spike analytics on the city-daily series.

Purpose: answer "do complaints follow PM2.5 spikes?" for the Lead-Lag & Spikes tab.
Inputs:  the city-daily frame from ``metrics.build_city_daily_metrics`` (date, pm25_mean, complaint_count).
Outputs: a lag-correlation frame, and a (offset frame, non-spike baseline) pair.
Used by: streamlit_app/app.py.
"""

from __future__ import annotations

import pandas as pd


def compute_lag_correlations(city_daily: pd.DataFrame, max_lag: int = 7) -> pd.DataFrame:
    """
    Correlate PM2.5 at day t with complaints at day t+lag for lag in [-max_lag, +max_lag].
    Positive lag means complaints trail PM2.5 spikes.
    """
    if city_daily.empty:
        return pd.DataFrame(columns=["lag_days", "correlation"])

    rows: list[dict[str, float | int]] = []
    series = city_daily.sort_values("date")[["pm25_mean", "complaint_count"]]

    for lag in range(-max_lag, max_lag + 1):
        shifted = series["complaint_count"].shift(-lag)
        corr = series["pm25_mean"].corr(shifted)
        rows.append({"lag_days": lag, "correlation": corr})

    return pd.DataFrame(rows)


def compute_spike_concordance(
    city_daily: pd.DataFrame,
    spike_percentile: float = 0.80,
    window_days: int = 2,
    threshold: float | None = None,
) -> tuple[pd.DataFrame, float]:
    """Summarize complaint activity around city-level PM2.5 spike days.

    A spike day is any day where city-wide average PM2.5 is at or above a
    threshold. The threshold is either:

    * an absolute ``threshold`` (µg/m³) when provided — e.g. the EPA 24-hour
      PM2.5 standard of 35 — which anchors spikes to a health-meaningful level; or
    * the ``spike_percentile`` quantile of PM2.5 over the selected range
      (default) — which guarantees spike days exist regardless of the absolute
      pollution level in the window.

    Returns ``(offsets_frame, baseline)`` where ``baseline`` is the mean
    complaint count on non-spike days.
    """
    empty = pd.DataFrame(columns=["offset_day", "mean_complaints", "total_complaints"])
    if city_daily.empty:
        return empty, float("nan")

    city = city_daily.sort_values("date").copy()
    pm25_valid = city["pm25_mean"].dropna()
    if pm25_valid.empty:
        return empty, float("nan")

    spike_level = float(threshold) if threshold is not None else float(pm25_valid.quantile(spike_percentile))
    city["is_spike"] = city["pm25_mean"] >= spike_level

    spike_dates = city.loc[city["is_spike"], "date"]
    baseline = city.loc[~city["is_spike"], "complaint_count"].mean()

    # Vectorized offset join: look complaint counts up by date rather than
    # scanning the frame once per (offset, spike-day) pair.
    complaints_by_date = city.set_index("date")["complaint_count"]

    rows = []
    for offset in range(-window_days, window_days + 1):
        target_dates = spike_dates + pd.Timedelta(days=offset)
        matched = complaints_by_date.reindex(target_dates).dropna()
        if not matched.empty:
            rows.append(
                {
                    "offset_day": offset,
                    "mean_complaints": float(matched.mean()),
                    "total_complaints": float(matched.sum()),
                }
            )
        else:
            rows.append(
                {
                    "offset_day": offset,
                    "mean_complaints": float("nan"),
                    "total_complaints": 0.0,
                }
            )

    return pd.DataFrame(rows), float(baseline)
