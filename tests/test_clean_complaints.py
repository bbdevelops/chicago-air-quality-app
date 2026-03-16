from pathlib import Path

import pandas as pd
import pytest

from scripts.clean_complaints import build_sensor_locations, find_nearest_sensor


def test_build_sensor_locations_uses_sensor_median_coordinates(tmp_path: Path) -> None:
    source = tmp_path / "openair_daily.csv"
    pd.DataFrame(
        {
            "sensor_name": ["A", "A", "B"],
            "latitude": [41.0, 41.3, 42.0],
            "longitude": [-87.7, -87.5, -87.9],
        }
    ).to_csv(source, index=False)

    sensors = build_sensor_locations(source)

    assert set(sensors["sensor_name"]) == {"A", "B"}
    sensor_a = sensors.loc[sensors["sensor_name"] == "A"].iloc[0]
    assert sensor_a["sensor_lat"] == pytest.approx(41.15)
    assert sensor_a["sensor_lon"] == pytest.approx(-87.6)


def test_find_nearest_sensor_returns_expected_sensor() -> None:
    sensors = pd.DataFrame(
        {
            "sensor_name": ["Near", "Far"],
            "sensor_lat": [41.88, 41.0],
            "sensor_lon": [-87.63, -88.0],
        }
    )

    sensor_name, distance_m = find_nearest_sensor(41.881, -87.629, sensors)

    assert sensor_name == "Near"
    assert distance_m < 500
