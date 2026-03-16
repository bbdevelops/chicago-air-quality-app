import pandas as pd
import pytest

from scripts.aggregate_hourly_to_daily import weighted_reaggregate_daily


def test_weighted_reaggregate_daily_uses_reading_count_weights() -> None:
    combined = pd.DataFrame(
        {
            "datasourceid": ["ds1", "ds1"],
            "sensor_name": ["S1", "S1"],
            "date": ["2026-02-01", "2026-02-01"],
            "pm25_mean": [10.0, 30.0],
            "no2_mean": [20.0, 40.0],
            "latitude": [41.0, 41.4],
            "longitude": [-87.0, -87.4],
            "reading_count": [1, 3],
        }
    )

    result = weighted_reaggregate_daily(combined)
    row = result.iloc[0]

    assert len(result) == 1
    assert row["pm25_mean"] == pytest.approx(25.0)
    assert row["no2_mean"] == pytest.approx(35.0)
    assert row["latitude"] == pytest.approx(41.2)
    assert row["longitude"] == pytest.approx(-87.2)
    assert row["reading_count"] == 4


def test_weighted_reaggregate_daily_validates_required_columns() -> None:
    bad = pd.DataFrame({"sensor_name": ["S1"]})

    with pytest.raises(ValueError):
        weighted_reaggregate_daily(bad)
