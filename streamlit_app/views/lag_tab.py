"""Lead-Lag & Spikes tab: does complaint activity follow PM2.5 spikes?

Purpose: show lead-lag correlations and complaint counts around city-level PM2.5 spike days.
Inputs:  sidebar state and the city-daily frame.
Outputs: renders Streamlit elements; nothing is returned.
Used by: streamlit_app/app.py.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from streamlit_app.analytics import compute_lag_correlations, compute_spike_concordance
from streamlit_app.sidebar import SidebarState
from streamlit_app.theme import style_fig


def render_lag_tab(ui: SidebarState, city_daily: pd.DataFrame) -> None:
    theme = ui.theme
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
            color_continuous_scale=theme["diverging"],
            range_color=[-1, 1],
            title="Lead-lag correlation: PM2.5(t) vs Complaints(t+lag)",
        )
        lag_fig.update_layout(margin={"l": 0, "r": 0, "t": 45, "b": 0})
        style_fig(lag_fig, theme)
        st.plotly_chart(lag_fig, use_container_width=True)

        valid = lag_df.dropna(subset=["correlation"]).copy()
        if not valid.empty:
            valid["abs_corr"] = valid["correlation"].abs()
            best = valid.nlargest(1, "abs_corr").iloc[0]
            st.info(
                f"Strongest absolute lag is {best['lag_days']:.0f} days "
                f"with correlation {best['correlation']:.3f}."
            )

        spike_percentile = ui.spike_percentile_pct / 100.0
        spike_df, baseline = compute_spike_concordance(
            city_daily,
            spike_percentile=spike_percentile,
            window_days=2,
        )
        spike_title = (
            f"Complaint response around PM2.5 spike days "
            f"(top {100 - ui.spike_percentile_pct}%, city-level)"
        )
        spike_fig = px.line(
            spike_df,
            x="offset_day",
            y="mean_complaints",
            markers=True,
            title=spike_title,
            color_discrete_sequence=[theme["accent"]],
        )
        if not np.isnan(baseline):
            spike_fig.add_hline(
                y=baseline,
                line_dash="dash",
                line_color=theme["muted"],
                annotation_text="non-spike baseline",
                annotation_font_color=theme["muted"],
            )
        spike_fig.update_xaxes(dtick=1, title="Days relative to spike day")
        spike_fig.update_yaxes(title="Mean complaints")
        spike_fig.update_layout(margin={"l": 0, "r": 0, "t": 45, "b": 0})
        style_fig(spike_fig, theme)
        st.plotly_chart(spike_fig, use_container_width=True)
