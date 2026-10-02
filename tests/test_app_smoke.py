"""Headless smoke test: run the real Streamlit app against synthetic data across widget combinations.

Catches exceptions in any tab/theme/map-mode, which no unit test of the data layer can.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import streamlit_app.dashboard_data as dashboard_data

APP_PATH = str(Path(__file__).resolve().parents[1] / "streamlit_app" / "app.py")

HOODS = {
    "A": (41.10, -87.60),
    "B": (41.20, -87.70),
    "C": (41.15, -87.65),  # no sensor: exercises the IDW-estimated path
}

METRICS = [
    "Air Quality Index (PM2.5)",
    "PM2.5 mean (selected period)",
    "NO2 mean (selected period)",
    "Complaints (selected period)",
    "Sensor coverage (all-time)",
]


def _square(lat: float, lon: float, half: float = 0.02) -> dict:
    ring = [
        [lon - half, lat - half], [lon + half, lat - half], [lon + half, lat + half],
        [lon - half, lat + half], [lon - half, lat - half],
    ]
    return {"type": "Polygon", "coordinates": [ring]}


@pytest.fixture
def synthetic_pipeline_data(monkeypatch: pytest.MonkeyPatch) -> dashboard_data.PipelineData:
    rng = np.random.default_rng(0)
    dates = pd.date_range("2026-01-01", periods=45)
    rows = []
    for sensor, hood in (("S1", "A"), ("S2", "B")):
        lat, lon = HOODS[hood]
        for d in dates:
            pm25 = float(rng.uniform(4, 60))
            rows.append(
                {
                    "sensor_name": sensor, "date": d, "pm25_mean": pm25, "no2_mean": float(rng.uniform(2, 30)),
                    "lat": lat, "lon": lon, "complaint_count": int(rng.integers(0, 4)),
                    "pm25_spike": int(pm25 > 35), "neighborhood": hood,
                }
            )
    merged = pd.DataFrame(rows)

    complaints = pd.DataFrame(
        {
            "complaint_id": [1, 2, 3],
            "date": pd.to_datetime(["2026-01-03", "2026-01-10", "2026-01-20"]),
            "latitude": [41.10, 41.20, 41.15],
            "longitude": [-87.60, -87.70, -87.65],
            "neighborhood": ["A", "B", "C"],
            "nearest_sensor": ["S1", "S2", "S1"],
        }
    )
    summary = pd.DataFrame(
        {
            "neighborhood": list(HOODS),
            "neighborhood_secondary": ["A2", "B2", "C2"],
            "sensor_count": [1, 1, 0],
            "reading_days": [45, 45, 0],
            "has_sensor_coverage": [1, 1, 0],
            "total_complaints": [1, 1, 1],
        }
    )
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"neighborhood": n}, "geometry": _square(*ll)}
            for n, ll in HOODS.items()
        ],
    }
    data = dashboard_data.PipelineData(
        complaints=complaints, merged=merged, summary=summary, neighborhoods_geojson=geojson
    )
    monkeypatch.setattr(dashboard_data, "load_pipeline_data", lambda *_a, **_k: data)
    return data


def _set(at: AppTest, label: str, value: object) -> None:
    for kind in ("radio", "selectbox", "toggle", "slider", "multiselect"):
        for widget in getattr(at.sidebar, kind):
            if widget.label == label:
                widget.set_value(value)
                return
    raise AssertionError(f"sidebar widget not found: {label}")


def _run(**settings: object) -> AppTest:
    at = AppTest.from_file(APP_PATH, default_timeout=120).run()
    for label, value in settings.items():
        _set(at, label.replace("__", " "), value)
    return at.run()


def test_app_renders_all_tabs_without_exceptions(synthetic_pipeline_data) -> None:
    at = _run()

    assert not at.exception
    assert len(at.tabs) == 5
    assert len(at.get("plotly_chart")) >= 5


@pytest.mark.parametrize("theme", ["Terminal", "Accessible"])
@pytest.mark.parametrize("mode", ["Neighborhood choropleth", "Continuous heatmap"])
@pytest.mark.parametrize("metric", METRICS)
def test_app_map_theme_metric_combinations(synthetic_pipeline_data, theme, mode, metric) -> None:
    at = _run(Theme=theme, Map__mode=mode, Map__metric=metric, Show__complaint__locations=True)

    assert not at.exception


def test_app_alternate_trend_and_filter_options(synthetic_pipeline_data) -> None:
    at = _run(
        Primary__trend__metric="NO2",
        Trend__chart__style="Area + complaints",
        Calendar__heatmap__metric="Complaints",
        Neighborhoods=["A"],
    )

    assert not at.exception
