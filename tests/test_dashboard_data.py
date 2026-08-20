import math

import pandas as pd
import pytest

from streamlit_app.dashboard_data import (
    add_aqi_columns,
    aqi_category,
    aqi_health_message,
    build_city_daily_metrics,
    build_neighborhood_metrics,
    build_sensor_snapshot,
    compute_lag_correlations,
    compute_spike_concordance,
    enrich_neighborhood_metrics_with_estimates,
    filter_complaint_points,
    filter_merged_data,
    no2_to_aqi,
    pm25_to_aqi,
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


def _sample_complaints() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "complaint_id": [101, 102, 103],
            "date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-02"]),
            "latitude": [41.11, 41.21, pd.NA],
            "longitude": [-87.61, -87.71, -87.72],
            "neighborhood": ["A", "B", "B"],
            "nearest_sensor": ["S1", "S2", "S2"],
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


def test_filter_complaint_points_applies_date_neighborhood_and_geocode_filters() -> None:
    complaints = _sample_complaints()
    filtered = filter_complaint_points(
        complaints,
        start_date=pd.Timestamp("2026-01-02"),
        end_date=pd.Timestamp("2026-01-02"),
        neighborhoods=["B"],
    )

    assert len(filtered) == 1
    assert filtered.iloc[0]["complaint_id"] == 102


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


# ── AQI ─────────────────────────────────────────────────────────────────────
def test_pm25_to_aqi_category_endpoints() -> None:
    # 2024-revised PM2.5 breakpoints: concentration -> exact AQI index endpoint.
    assert pm25_to_aqi(0.0) == 0
    assert pm25_to_aqi(9.0) == 50
    assert pm25_to_aqi(9.1) == 51
    assert pm25_to_aqi(35.4) == 100
    assert pm25_to_aqi(35.5) == 101
    assert pm25_to_aqi(55.4) == 150
    assert pm25_to_aqi(125.4) == 200
    assert pm25_to_aqi(225.4) == 300


def test_pm25_to_aqi_midpoint_is_linear() -> None:
    # Midpoint of the Good band (0-9 µg/m³ -> 0-50 AQI): 4.5 -> 25.
    assert pm25_to_aqi(4.5) == 25


def test_pm25_to_aqi_truncates_and_caps() -> None:
    # EPA truncates to 0.1 before the formula: 9.09 truncates to 9.0 -> Good (50).
    assert pm25_to_aqi(9.09) == 50
    # Above the top breakpoint caps at 500.
    assert pm25_to_aqi(1000.0) == 500


def test_aqi_helpers_handle_nan_and_negatives() -> None:
    assert math.isnan(pm25_to_aqi(float("nan")))
    assert math.isnan(pm25_to_aqi(-1.0))
    label, color = aqi_category(float("nan"))
    assert label == "Unavailable"
    assert color.startswith("#")
    assert "Unavailable".lower() not in aqi_health_message(75).lower()


def test_aqi_category_and_message_bands() -> None:
    assert aqi_category(25)[0] == "Good"
    assert aqi_category(75)[0] == "Moderate"
    assert aqi_category(125)[0] == "Unhealthy for Sensitive Groups"
    assert aqi_category(175)[0] == "Unhealthy"
    assert aqi_category(250)[0] == "Very Unhealthy"
    assert aqi_category(400)[0] == "Hazardous"
    # Colors are the official green -> maroon anchors.
    assert aqi_category(25)[1] == "#00e400"
    assert aqi_category(400)[1] == "#7e0023"


def test_no2_to_aqi_informational_endpoints() -> None:
    assert no2_to_aqi(53) == 50
    assert no2_to_aqi(100) == 100


def test_add_aqi_columns_vectorized() -> None:
    df = pd.DataFrame({"pm25_mean": [4.5, 20.0, float("nan")]})
    out = add_aqi_columns(df)
    assert list(out["pm25_aqi"].iloc[:2]) == [25, 71]
    assert out["aqi_category"].iloc[0] == "Good"
    assert out["aqi_category"].iloc[1] == "Moderate"
    assert math.isnan(out["pm25_aqi"].iloc[2])
    assert out["aqi_category"].iloc[2] == "Unavailable"
    # Original frame is untouched.
    assert "pm25_aqi" not in df.columns


def test_add_aqi_columns_missing_source_column() -> None:
    out = add_aqi_columns(pd.DataFrame({"other": [1, 2]}))
    assert out["aqi_category"].tolist() == ["Unavailable", "Unavailable"]


def test_spike_concordance_absolute_threshold_matches_percentile_default() -> None:
    # With an absolute threshold, only days at/above it count as spikes.
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
    # offset -1 -> day before spike (Jan 1) = 2 complaints; offset +1 -> Jan 3 = 3.
    assert spike_df.loc[spike_df["offset_day"] == -1, "mean_complaints"].iloc[0] == pytest.approx(2.0)
    assert spike_df.loc[spike_df["offset_day"] == 1, "mean_complaints"].iloc[0] == pytest.approx(3.0)
    assert baseline == pytest.approx(2.5)
