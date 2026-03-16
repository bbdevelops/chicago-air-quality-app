"""
run_pipeline.py
---------------
End-to-end orchestrator for the Chicago Air Quality pipeline.

Focuses on:
  - PM2.5 and NO2 daily averages by sensor and neighborhood
  - 311 air-pollution complaints by neighborhood
  - Merged analysis-ready dataset for complaint / air quality correlation

Usage:
    python run_pipeline.py              # run all steps (uses cache)
    python run_pipeline.py --force      # force re-pull from API
    python run_pipeline.py --skip-api   # skip extraction, run cleaning only
"""

import argparse
import subprocess
import sys
import logging
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

# --- Logging: console + file ------------------------------------------------
log_file = LOG_DIR / f"pipeline_{datetime.now():%Y%m%d_%H%M%S}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_file, encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# ---- Pipeline steps (extraction -> cleaning -> enrichment -> output) --------
EXTRACT_STEPS = [
    ("Extract complaints",    "extract_complaints.py"),
    ("Extract Open Air data", "extract_openair.py"),
]

TRANSFORM_STEPS = [
    ("Clean complaints",             "clean_complaints.py"),
    ("Clean Open Air data",          "clean_openair.py"),
    ("Export neighborhoods GeoJSON", "export_neighborhoods_geojson.py"),
    ("Assign neighborhoods",         "assign_neighborhoods.py"),
    ("Merge datasets",               "merge_datasets.py"),
    ("Neighborhood summary",         "build_neighborhood_summary.py"),
    ("Load SQLite",                  "load_sqlite.py"),
]


def run_step(name: str, script: str, extra_args: list[str] | None = None) -> bool:
    """Run a pipeline step as a subprocess. Returns True on success."""
    cmd = [sys.executable, str(SCRIPTS_DIR / script)]
    if extra_args:
        cmd.extend(extra_args)

    log.info("=== %s ===", name)
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))

    if result.returncode != 0:
        log.error("FAILED: %s (exit code %d)", name, result.returncode)
        return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Chicago Air Quality pipeline")
    parser.add_argument("--force",    action="store_true", help="Force API re-pull")
    parser.add_argument("--skip-api", action="store_true", help="Skip extraction steps")
    args = parser.parse_args()

    log.info("Pipeline started  (force=%s, skip_api=%s)", args.force, args.skip_api)
    log.info("Log file: %s", log_file)

    extra = ["--force"] if args.force else []

    steps: list[tuple[str, str]] = []
    if not args.skip_api:
        steps.extend(EXTRACT_STEPS)
    steps.extend(TRANSFORM_STEPS)

    passed = 0
    for name, script in steps:
        step_args = extra if "extract" in script else None
        ok = run_step(name, script, step_args)
        if ok:
            passed += 1
        else:
            log.error("Pipeline stopped at: %s", name)
            sys.exit(1)

    log.info("=== Pipeline complete: %d / %d steps passed ===", passed, len(steps))
    log.info("Outputs:")
    log.info("  data/clean/merged_complaints_air.csv  -- analysis-ready merged data")
    log.info("  data/clean/neighborhood_summary.csv   -- one row per neighborhood")
    log.info("  db/citizen_sensor.db                  -- SQLite database")


if __name__ == "__main__":
    main()
