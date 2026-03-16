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
  data/clean/complaints_daily_by_sensor.csv  — adds 'neighborhood' column
  data/clean/openair_daily_cleaned.csv       — adds 'neighborhood' column
"""

import logging
from pathlib import Path

import pandas as pd
from shapely import wkt
from shapely.geometry import Point
from shapely.prepared import prep

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CLEAN_DIR = DATA_DIR / "clean"

NEIGHBORHOODS_CSV = DATA_DIR / "Neighborhoods_2012b_20260228.csv"

# Max distance (in degrees, ~1 km) to snap an unmatched point to the
# nearest neighborhood boundary.  Points beyond this remain unassigned.
SNAP_TOLERANCE_DEG = 0.01   # ~1.1 km at Chicago's latitude

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Load & parse neighborhood polygons
# ---------------------------------------------------------------------------
def load_neighborhoods(path: Path) -> list[tuple[str, str, object, object]]:
    """
    Return a list of (pri_neigh, sec_neigh, prepared_geometry, raw_geometry)
    tuples.  The prepared geometry is used for fast point-in-polygon tests;
    the raw geometry is kept for nearest-boundary distance fallback.
    """
    df = pd.read_csv(path)
    neighborhoods = []
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
    if not NEIGHBORHOODS_CSV.exists():
        log.error("Neighborhood boundaries file not found: %s", NEIGHBORHOODS_CSV)
        return

    neighborhoods = load_neighborhoods(NEIGHBORHOODS_CSV)

    # ---- 1. Complaints (row-level) ------------------------------------------
    comp_path = CLEAN_DIR / "complaints_cleaned.csv"
    if comp_path.exists():
        log.info("Assigning neighborhoods to complaints …")
        comp = pd.read_csv(comp_path)
        comp = assign_column(comp, "latitude", "longitude", neighborhoods)
        comp.to_csv(comp_path, index=False)
        log.info("Updated %s", comp_path.name)
    else:
        log.warning("Skipping complaints — %s not found.", comp_path)

    # ---- 2. Daily complaint aggregation -------------------------------------
    #   Re-aggregate with neighborhood from updated complaints
    if comp_path.exists():
        log.info("Re-aggregating daily complaint counts with neighborhood …")
        comp = pd.read_csv(comp_path, parse_dates=["date"])
        daily = (
            comp.groupby(["nearest_sensor", "date", "neighborhood"])
            .agg(
                complaint_count=("complaint_id", "size"),
                mean_distance_m=("distance_to_sensor_m", "mean"),
            )
            .reset_index()
        )
        daily["date"] = pd.to_datetime(daily["date"])
        daily_path = CLEAN_DIR / "complaints_daily_by_sensor.csv"
        daily.to_csv(daily_path, index=False)
        log.info("Updated %s  (%d rows)", daily_path.name, len(daily))

    # ---- 3. Sensor readings -------------------------------------------------
    air_path = CLEAN_DIR / "openair_daily_cleaned.csv"
    if air_path.exists():
        log.info("Assigning neighborhoods to sensor readings …")
        air = pd.read_csv(air_path)
        air = assign_column(air, "lat", "lon", neighborhoods)
        air.to_csv(air_path, index=False)
        log.info("Updated %s", air_path.name)
    else:
        log.warning("Skipping sensor readings — %s not found.", air_path)

    log.info("Neighborhood assignment complete.")


if __name__ == "__main__":
    main()
