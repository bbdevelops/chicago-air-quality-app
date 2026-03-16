"""
export_neighborhoods_geojson.py
-------------------------------
Convert the Neighborhoods_2012b CSV (WKT geometry) into a GeoJSON file
that Tableau can read as a spatial data source for polygon map overlays.

Input:   data/Neighborhoods_2012b_20260228.csv
Output:  data/clean/chicago_neighborhoods.geojson
"""

import json
import logging
from pathlib import Path

import pandas as pd
from shapely import wkt
from shapely.geometry import mapping

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CLEAN_DIR = DATA_DIR / "clean"
NEIGHBORHOODS_CSV = DATA_DIR / "Neighborhoods_2012b_20260228.csv"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
log = logging.getLogger(__name__)


def main() -> None:
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(NEIGHBORHOODS_CSV)
    log.info("Loaded %d neighborhoods from CSV.", len(df))

    features = []
    for _, row in df.iterrows():
        try:
            geom = wkt.loads(row["the_geom"])
            feature = {
                "type": "Feature",
                "properties": {
                    "neighborhood": row["PRI_NEIGH"],
                    "neighborhood_secondary": row["SEC_NEIGH"],
                    "shape_area": row["SHAPE_AREA"],
                    "shape_len": row["SHAPE_LEN"],
                },
                "geometry": mapping(geom),
            }
            features.append(feature)
        except Exception as e:
            log.warning("Skipping %s: %s", row.get("PRI_NEIGH", "?"), e)

    geojson = {
        "type": "FeatureCollection",
        "features": features,
    }

    out_path = CLEAN_DIR / "chicago_neighborhoods.geojson"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(geojson, f)

    log.info("Wrote %d features → %s (%.1f MB)",
             len(features), out_path, out_path.stat().st_size / 1e6)


if __name__ == "__main__":
    main()
