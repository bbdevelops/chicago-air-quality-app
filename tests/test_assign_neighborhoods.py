from pathlib import Path

import pandas as pd

from scripts.assign_neighborhoods import assign_neighborhood
from scripts._neighborhoods import load_boundaries


import pytest

@pytest.fixture
def mock_neighborhoods(tmp_path: Path):
    csv_path = tmp_path / "neighborhoods.csv"
    df = pd.DataFrame(
        {
            "the_geom": [
                "MULTIPOLYGON (((0 0, 1 0, 1 1, 0 1, 0 0)))",
                "MULTIPOLYGON (((2 2, 3 2, 3 3, 2 3, 2 2)))",
            ],
            "PRI_NEIGH": ["A", "B"],
            "SEC_NEIGH": ["A2", "B2"],
            "SHAPE_AREA": ["1", "1"],
            "SHAPE_LEN": ["4", "4"],
        }
    )
    df.to_csv(csv_path, index=False)
    return load_boundaries(csv_path)


def test_assign_neighborhood_exact_point_in_polygon(mock_neighborhoods) -> None:
    neighborhoods = mock_neighborhoods

    pri, sec = assign_neighborhood(lat=0.5, lon=0.5, neighborhoods=neighborhoods)

    assert pri == "A"
    assert sec == "A2"


def test_assign_neighborhood_snaps_to_nearest_boundary(mock_neighborhoods) -> None:
    neighborhoods = mock_neighborhoods

    # Just outside neighborhood A boundary (x=1.0), within snap tolerance.
    pri, sec = assign_neighborhood(lat=0.5, lon=1.005, neighborhoods=neighborhoods)

    assert pri == "A"
    assert sec == "A2"


def test_assign_neighborhood_outside_tolerance_returns_none(mock_neighborhoods) -> None:
    neighborhoods = mock_neighborhoods

    pri, sec = assign_neighborhood(lat=10.0, lon=10.0, neighborhoods=neighborhoods)

    assert pri is None
    assert sec is None
