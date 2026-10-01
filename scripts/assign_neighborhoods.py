"""
assign_neighborhoods.py
-----------------------
Assign a Chicago neighborhood to every complaint and sensor reading
using point-in-polygon spatial joins against the official City of Chicago
neighborhood boundaries (2012b).

Boundary source
---------------
  data/Neighborhoods_2012b_20260228.csv
  Columns: the_geom (WKT MULTIPOLYGON), PRI_NEIGH, SEC_NEIGH, SHAPE_AREA, SHAPE_LEN

Inputs
------
  data/clean/complaints_cleaned.csv
  data/clean/openair_daily_cleaned.csv

Outputs (overwrites in-place)
-------
  data/clean/complaints_cleaned.csv          — adds 'neighborhood' column
  data/clean/openair_daily_cleaned.csv       — adds 'neighborhood' column
"""

import pandas as pd
from _common import COMPLAINTS_CLEANED, OPENAIR_CLEANED, setup_logging
from _neighborhoods import load_boundaries
from shapely.geometry import Point

# Max distance (in degrees, ~1 km) to snap an unmatched point to the
# nearest neighborhood boundary.  Points beyond this remain unassigned.
SNAP_TOLERANCE_DEG = 0.01   # ~1.1 km at Chicago's latitude

log = setup_logging(__name__)


def assign_neighborhood(
    lat: float, lon: float, neighborhoods: list
) -> tuple[str | None, str | None]:
    """
    Return (pri_neigh, sec_neigh) for a lat/lon point.

    Strategy:
      1. Exact point-in-polygon test (fast, via prepared geometry).
      2. If no polygon contains the point, fall back to the nearest
         boundary within SNAP_TOLERANCE_DEG (~1 km).  This handles
         sensors that sit right on a polygon edge or just outside
         Chicago's city limits.
      3. If still no match, return (None, None).
    """
    if pd.isna(lat) or pd.isna(lon):
        return None, None
    pt = Point(lon, lat)  # shapely uses (x=lon, y=lat)

    # 1. Exact containment
    for pri, sec, prepared_geom, _raw in neighborhoods:
        if prepared_geom.contains(pt):
            return pri, sec

    # 2. Nearest-boundary fallback
    best_dist = float("inf")
    best_pri, best_sec = None, None
    for pri, sec, _prep, raw_geom in neighborhoods:
        d = raw_geom.boundary.distance(pt)
        if d < best_dist:
            best_dist = d
            best_pri, best_sec = pri, sec

    if best_dist <= SNAP_TOLERANCE_DEG:
        return best_pri, best_sec

    return None, None


def assign_column(
    df: pd.DataFrame,
    lat_col: str,
    lon_col: str,
    neighborhoods: list,
) -> pd.DataFrame:
    """
    Add 'neighborhood' and 'neighborhood_secondary' columns to df.
    """
    results = df.apply(
        lambda row: assign_neighborhood(row[lat_col], row[lon_col], neighborhoods),
        axis=1,
        result_type="expand",
    )
    df["neighborhood"] = results[0]
    df["neighborhood_secondary"] = results[1]
    matched = df["neighborhood"].notna().sum()
    log.info(
        "  Matched %d / %d rows to a neighborhood (%.1f%%)",
        matched, len(df), 100 * matched / max(len(df), 1),
    )
    return df


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    neighborhoods = load_boundaries()
    if not neighborhoods:
        return

    # ---- 1. Complaints (row-level) ------------------------------------------
    if COMPLAINTS_CLEANED.exists():
        log.info("Assigning neighborhoods to complaints …")
        comp = pd.read_csv(COMPLAINTS_CLEANED)
        comp = assign_column(comp, "latitude", "longitude", neighborhoods)
        comp.to_csv(COMPLAINTS_CLEANED, index=False)
        log.info("Updated %s", COMPLAINTS_CLEANED.name)
    else:
        log.warning("Skipping complaints — %s not found.", COMPLAINTS_CLEANED)


    # ---- 2. Sensor readings -------------------------------------------------
    if OPENAIR_CLEANED.exists():
        log.info("Assigning neighborhoods to sensor readings …")
        air = pd.read_csv(OPENAIR_CLEANED)
        air = assign_column(air, "lat", "lon", neighborhoods)
        air.to_csv(OPENAIR_CLEANED, index=False)
        log.info("Updated %s", OPENAIR_CLEANED.name)
    else:
        log.warning("Skipping sensor readings — %s not found.", OPENAIR_CLEANED)

    log.info("Neighborhood assignment complete.")


if __name__ == "__main__":
    main()
