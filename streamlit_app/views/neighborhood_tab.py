"""Neighborhood Trends tab: top-15 neighborhood ranking for the chosen pollutant.

Purpose: rank neighborhoods by period-average PM2.5 or NO2.
Inputs:  sidebar state and the neighborhood map metrics (direct values only are ranked).
Outputs: renders Streamlit elements; nothing is returned.
Used by: streamlit_app/app.py.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from streamlit_app.constants import POLLUTANTS
from streamlit_app.sidebar import SidebarState
from streamlit_app.theme import style_fig


def render_neighborhood_tab(ui: SidebarState, map_metrics: pd.DataFrame) -> None:
    theme = ui.theme
    pol_cfg = POLLUTANTS[ui.trend_metric_label]
    ranking_value_col = f"{pol_cfg.column}_period"
    ranking_value_title = f"{pol_cfg.label} average (selected period)"

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
            color_continuous_scale=theme["sequential"],
            title=f"Top 15 neighborhoods by {ui.trend_metric_label} in selected period",
            labels={
                "neighborhood": "Neighborhood",
                ranking_value_col: ranking_value_title,
            },
        )
        rank_fig.update_layout(margin={"l": 0, "r": 0, "t": 45, "b": 0})
        style_fig(rank_fig, theme)
        rank_fig.update_yaxes(categoryorder="total ascending")
        st.plotly_chart(rank_fig, width="stretch")
