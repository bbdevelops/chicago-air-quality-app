import pandas as pd

from scripts.build_neighborhood_summary import _aggregate_neighborhoods


def test_aggregate_neighborhoods_counts_pm25_spike() -> None:
    # 1.3 fix regression: make sure we use pm25_spike instead of pm25_outlier.
    merged = pd.DataFrame({
        "neighborhood": ["A", "A", "B", "B"],
        "sensor_name": ["S1", "S1", "S2", "S2"],
        "date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-01", "2026-01-02"]),
        "pm25_spike": [1, 0, 0, 0],
        "pm25_mean": [40.0, 10.0, 15.0, 20.0],
        "no2_mean": [1.0, 2.0, 3.0, 4.0],
        "complaint_count": [1, 2, 0, 0]
    })

    summary = _aggregate_neighborhoods(merged)

    row_a = summary[summary["neighborhood"] == "A"].iloc[0]
    assert row_a["spike_days"] == 1

    row_b = summary[summary["neighborhood"] == "B"].iloc[0]
    assert row_b["spike_days"] == 0
