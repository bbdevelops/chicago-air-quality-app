"""
scripts/_neighborhoods.py — Shared neighborhood boundary loading.

Parses WKT geometry from the Neighborhoods_2012b CSV and returns
prepared polygons ready for point-in-polygon operations.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
from _common import NEIGHBORHOODS_CSV
from shapely import wkt
from shapely.prepared import prep

log = logging.getLogger(__name__)


def load_boundaries(
    path: Path | None = None,
) -> list[tuple[str, str, object, object]]:
    """Load neighborhood polygons from the WKT CSV.

    Returns a list of (pri_neigh, sec_neigh, prepared_geometry, raw_geometry)
    tuples.  The prepared geometry is for fast containment tests; the raw
    geometry is kept for distance-based fallback matching.
    """
    csv_path = path or NEIGHBORHOODS_CSV

    if not csv_path.exists():
        log.error("Neighborhood boundaries file not found: %s", csv_path)
        return []

    df = pd.read_csv(csv_path)
    neighborhoods: list[tuple[str, str, object, object]] = []

    for _, row in df.iterrows():
        try:
            geom = wkt.loads(row["the_geom"])
            neighborhoods.append(
                (row["PRI_NEIGH"], row["SEC_NEIGH"], prep(geom), geom)
            )
        except Exception as e:
            log.warning("Skipping neighborhood %s: %s", row.get("PRI_NEIGH", "?"), e)

    log.info("Loaded %d neighborhood polygons.", len(neighborhoods))
    return neighborhoods
