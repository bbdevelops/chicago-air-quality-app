import json
from pathlib import Path

import pandas as pd

from streamlit_app.loading import PipelineData, load_pipeline_data, round_geojson_coordinates

PRECISE = [[-87.60670812560372, 41.816813771373916], [-87.60170812560372, 41.826813771373916]]


def _geojson() -> dict:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"neighborhood": "A", "shape_area": 1.23456789012},
                "geometry": {"type": "Polygon", "coordinates": [PRECISE]},
            },
            {
                "type": "Feature",
                "properties": {"neighborhood": "B"},
                "geometry": {"type": "MultiPolygon", "coordinates": [[PRECISE], [PRECISE]]},
            },
        ],
    }


def test_round_geojson_coordinates_rounds_every_nesting_level_and_keeps_properties() -> None:
    out = round_geojson_coordinates(_geojson(), decimals=6)

    assert out["features"][0]["geometry"]["coordinates"][0][0] == [-87.606708, 41.816814]
    assert out["features"][1]["geometry"]["coordinates"][1][0][1] == [-87.601708, 41.826814]
    assert [f["properties"] for f in out["features"]] == [f["properties"] for f in _geojson()["features"]]
    assert [f["geometry"]["type"] for f in out["features"]] == ["Polygon", "MultiPolygon"]


def test_round_geojson_coordinates_does_not_mutate_the_input() -> None:
    original = _geojson()

    round_geojson_coordinates(original)

    assert original == _geojson()


def test_round_geojson_coordinates_tolerates_missing_geometry() -> None:
    gj = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry": None}]}

    assert round_geojson_coordinates(gj)["features"][0]["geometry"] is None


def test_map_geojson_falls_back_to_full_precision_when_no_display_copy() -> None:
    frame = pd.DataFrame()
    data = PipelineData(complaints=frame, merged=frame, summary=frame, neighborhoods_geojson=_geojson())

    assert data.map_geojson is data.neighborhoods_geojson


def test_load_pipeline_data_keeps_full_precision_and_adds_rounded_display_copy(tmp_path: Path) -> None:
    clean = tmp_path / "data" / "clean"
    clean.mkdir(parents=True)
    pd.DataFrame(
        {"complaint_id": [1], "date": ["2026-01-01"], "latitude": [41.8], "longitude": [-87.6], "neighborhood": ["A"]}
    ).to_csv(clean / "complaints_cleaned.csv", index=False)
    pd.DataFrame(
        {
            "sensor_name": ["S1"], "date": ["2026-01-01"], "pm25_mean": [10.0], "no2_mean": [5.0], "lat": [41.8],
            "lon": [-87.6], "complaint_count": [1], "pm25_spike": [0], "neighborhood": ["A"],
        }
    ).to_csv(clean / "merged_complaints_air.csv", index=False)
    pd.DataFrame({"neighborhood": ["A"], "sensor_count": [1], "has_sensor_coverage": [1]}).to_csv(
        clean / "neighborhood_summary.csv", index=False
    )
    (clean / "chicago_neighborhoods.geojson").write_text(json.dumps(_geojson()), encoding="utf-8")

    data = load_pipeline_data(tmp_path)

    assert data.neighborhoods_geojson["features"][0]["geometry"]["coordinates"][0][0] == PRECISE[0]
    assert data.map_geojson["features"][0]["geometry"]["coordinates"][0][0] == [-87.606708, 41.816814]
