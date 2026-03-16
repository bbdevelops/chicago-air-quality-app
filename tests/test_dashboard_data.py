import pandas as pd
import pytest

from streamlit_app.dashboard_data import (
    build_city_daily_metrics,
    build_neighborhood_metrics,
    build_sensor_snapshot,
    compute_lag_correlations,
    compute_spike_concordance,
    enrich_neighborhood_metrics_with_estimates,
    filter_merged_data,
)


def _sample_merged() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "sensor_name": ["S1", "S2", "S1", "S2"],
            "date": pd.to_datetime(["2026-01-01", "2026-01-01", "2026-01-02", "2026-01-02"]),
            "pm25_mean": [10.0, 20.0, 30.0, 40.0],
            "no2_mean": [5.0, 6.0, 7.0, 8.0],
            "lat": [41.1, 41.2, 41.1, 41.2],
            "lon": [-87.6, -87.7, -87.6, -87.7],
            "complaint_count": [1, 2, 3, 4],
            "pm25_spike": [0, 0, 0, 1],
            "neighborhood": ["A", "B", "A", "B"],
        }
    )


def _sample_summary() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "neighborhood": ["A", "B", "C"],
            "neighborhood_secondary": ["A2", "B2", "C2"],
            "sensor_count": [1, 1, 0],
            "reading_days": [2, 2, 0],
            "has_sensor_coverage": [1, 1, 0],
            "total_complaints": [4, 6, 0],
        }
    )


def _sample_geojson() -> dict:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"neighborhood": "A", "neighborhood_secondary": "A2"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [-87.62, 41.08],
                        [-87.58, 41.08],
                        [-87.58, 41.12],
                        [-87.62, 41.12],
                        [-87.62, 41.08],
                    ]],
                },
            },
            {
                "type": "Feature",
                "properties": {"neighborhood": "B", "neighborhood_secondary": "B2"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [-87.72, 41.18],
                        [-87.68, 41.18],
                        [-87.68, 41.22],
                        [-87.72, 41.22],
                        [-87.72, 41.18],
                    ]],
                },
            },
            {
                "type": "Feature",
                "properties": {"neighborhood": "C", "neighborhood_secondary": "C2"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [-87.67, 41.13],
                        [-87.63, 41.13],
                        [-87.63, 41.17],
                        [-87.67, 41.17],
                        [-87.67, 41.13],
                    ]],
                },
            },
        ],
    }


def test_filter_merged_data_applies_date_and_neighborhood_filters() -> None:
    merged = _sample_merged()
    filtered = filter_merged_data(
        merged,
        start_date=pd.Timestamp("2026-01-02"),
        end_date=pd.Timestamp("2026-01-02"),
        neighborhoods=["A"],
    )

    assert len(filtered) == 1
    assert filtered.iloc[0]["sensor_name"] == "S1"


def test_build_city_daily_metrics_aggregates_sensor_rows_to_city_day() -> None:
    city = build_city_daily_metrics(_sample_merged())

    assert list(city["complaint_count"]) == [3, 7]
    assert list(city["pm25_mean"]) == [15.0, 35.0]


def test_build_neighborhood_metrics_preserves_neighborhoods_without_data() -> None:
    metrics = build_neighborhood_metrics(_sample_summary(), _sample_merged())

    assert set(metrics["neighborhood"]) == {"A", "B", "C"}
    row_c = metrics.loc[metrics["neighborhood"] == "C"].iloc[0]
    assert pd.isna(row_c["pm25_mean_period"])


def test_compute_lag_correlations_detects_positive_one_day_lag() -> None:
    city_daily = pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=6),
            "pm25_mean": [1, 0, 1, 0, 1, 0],
            "complaint_count": [0, 1, 0, 1, 0, 1],
        }
    )

    lag = compute_lag_correlations(city_daily, max_lag=2).set_index("lag_days")["correlation"]

    assert lag.loc[1] == pytest.approx(1.0)
    assert lag.loc[1] > lag.loc[0]


def test_compute_spike_concordance_returns_expected_window_and_baseline() -> None:
    city_daily = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]),
            "pm25_mean": [10.0, 40.0, 20.0],
            "complaint_count": [2, 5, 3],
        }
    )

    spike_df, baseline = compute_spike_concordance(city_daily, threshold=35.0, window_days=1)

    assert set(spike_df["offset_day"]) == {-1, 0, 1}
    center = spike_df.loc[spike_df["offset_day"] == 0, "mean_complaints"].iloc[0]
    assert center == pytest.approx(5.0)
    assert baseline == pytest.approx(2.5)


def test_enrich_neighborhood_metrics_with_estimates_fills_uncovered_neighborhoods() -> None:
    base_metrics = build_neighborhood_metrics(_sample_summary(), _sample_merged())
    sensors = build_sensor_snapshot(_sample_merged())

    enriched = enrich_neighborhood_metrics_with_estimates(
        neighborhood_metrics=base_metrics,
        sensors=sensors,
        neighborhoods_geojson=_sample_geojson(),
        k=2,
        idw_power=2.0,
        max_distance_km=50.0,
    )

    row_a = enriched.loc[enriched["neighborhood"] == "A"].iloc[0]
    row_c = enriched.loc[enriched["neighborhood"] == "C"].iloc[0]

    assert row_a["coverage_source"] == "direct"
    assert row_a["pm25_map_value"] == pytest.approx(row_a["pm25_mean_period"])

    assert row_c["coverage_source"] == "estimated_idw"
    assert not pd.isna(row_c["pm25_map_value"])
    assert not pd.isna(row_c["no2_map_value"])
    assert not pd.isna(row_c["complaints_map_value"])
    assert row_c["estimated_sensor_count"] > 0


def test_enrich_neighborhood_metrics_with_estimates_marks_unavailable_when_no_nearby_sensor() -> None:
    base_metrics = build_neighborhood_metrics(_sample_summary(), _sample_merged())
    sensors = build_sensor_snapshot(_sample_merged())

    enriched = enrich_neighborhood_metrics_with_estimates(
        neighborhood_metrics=base_metrics,
        sensors=sensors,
        neighborhoods_geojson=_sample_geojson(),
        k=2,
        idw_power=2.0,
        max_distance_km=0.1,
    )

    row_c = enriched.loc[enriched["neighborhood"] == "C"].iloc[0]
    assert row_c["coverage_source"] == "unavailable"
    assert pd.isna(row_c["pm25_map_value"])
