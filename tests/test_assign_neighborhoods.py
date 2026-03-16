from pathlib import Path

import pandas as pd

from scripts.assign_neighborhoods import assign_neighborhood, load_neighborhoods


def _write_neighborhood_csv(path: Path) -> None:
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
    df.to_csv(path, index=False)


def test_assign_neighborhood_exact_point_in_polygon(tmp_path: Path) -> None:
    csv_path = tmp_path / "neighborhoods.csv"
    _write_neighborhood_csv(csv_path)
    neighborhoods = load_neighborhoods(csv_path)

    pri, sec = assign_neighborhood(lat=0.5, lon=0.5, neighborhoods=neighborhoods)

    assert pri == "A"
    assert sec == "A2"


def test_assign_neighborhood_snaps_to_nearest_boundary(tmp_path: Path) -> None:
    csv_path = tmp_path / "neighborhoods.csv"
    _write_neighborhood_csv(csv_path)
    neighborhoods = load_neighborhoods(csv_path)

    # Just outside neighborhood A boundary (x=1.0), within snap tolerance.
    pri, sec = assign_neighborhood(lat=0.5, lon=1.005, neighborhoods=neighborhoods)

    assert pri == "A"
    assert sec == "A2"


def test_assign_neighborhood_outside_tolerance_returns_none(tmp_path: Path) -> None:
    csv_path = tmp_path / "neighborhoods.csv"
    _write_neighborhood_csv(csv_path)
    neighborhoods = load_neighborhoods(csv_path)

    pri, sec = assign_neighborhood(lat=10.0, lon=10.0, neighborhoods=neighborhoods)

    assert pri is None
    assert sec is None
