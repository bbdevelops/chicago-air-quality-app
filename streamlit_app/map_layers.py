"""Plotly map overlays for the Neighborhood Map tab.

Purpose: add neighborhood outlines, sensor markers (sized by complaints) and complaint points to a map figure.
Inputs:  a Plotly figure plus the sensor snapshot / complaint points / GeoJSON and the active theme dict.
Outputs: the figure is modified in place; ``add_sensor_markers`` also returns the marker-size legend bins.
Used by: streamlit_app/views/map_tab.py (via app.py until the tabs are split out).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go


def add_neighborhood_boundaries(
    fig: go.Figure, neighborhoods_geojson: dict[str, object], line_color: str
) -> None:
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
                    line={"color": line_color, "width": 1},
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


def add_sensor_markers(
    fig: go.Figure, sensors: pd.DataFrame, theme: dict[str, object]
) -> list[tuple[int, float]]:
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
                "colorscale": theme["marker_scale"],
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
                marker={"size": legend_size, "color": theme["marker_solid"], "opacity": 0.85},
                hoverinfo="skip",
                name=f"{count} complaints",
                showlegend=True,
            )
        )
    return bin_data


def add_complaint_locations(
    fig: go.Figure, complaints: pd.DataFrame, marker_color: str
) -> None:
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
                "color": marker_color,
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
