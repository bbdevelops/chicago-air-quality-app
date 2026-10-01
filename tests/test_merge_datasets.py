import pandas as pd


def test_merge_datasets_aggregates_all_complaints_without_dropping_missing_neighborhoods() -> None:
    # 1.4 fix regression: make sure we aggregate by [sensor_name, date] without dropping complaints
    # that don't have a neighborhood.
    # In reality this tests the logic that was moved into merge_datasets.
    from scripts.merge_datasets import _aggregate_complaints

    complaints = pd.DataFrame({
        "complaint_id": [1, 2, 3],
        "date": pd.to_datetime(["2026-01-01", "2026-01-01", "2026-01-02"]),
        "nearest_sensor": ["S1", "S1", "S2"],
        "neighborhood": ["A", None, "B"]
    })

    daily = _aggregate_complaints(complaints)

    # S1 on Jan 1 should have 2 complaints, even though one lacks a neighborhood
    s1_jan1 = daily[(daily["sensor_name"] == "S1") & (daily["date"] == pd.Timestamp("2026-01-01"))].iloc[0]
    assert s1_jan1["complaint_count"] == 2

    s2_jan2 = daily[(daily["sensor_name"] == "S2") & (daily["date"] == pd.Timestamp("2026-01-02"))].iloc[0]
    assert s2_jan2["complaint_count"] == 1
