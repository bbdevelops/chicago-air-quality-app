"""
scripts/_common.py — Shared paths, filenames, logging, and cache helpers.

Every pipeline script should ``from _common import *`` (or import specific
names) instead of re-declaring PROJECT_ROOT, directory constants, and the
logging setup.
"""

from __future__ import annotations

import configparser
import logging
import time
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
CLEAN_DIR = DATA_DIR / "clean"

# ── Canonical filenames (single source of truth) ───────────────────────────
NEIGHBORHOODS_CSV = DATA_DIR / "Neighborhoods_2012b_20260228.csv"

COMPLAINTS_RAW = RAW_DIR / "cdph_air_complaints.csv"
OPENAIR_RAW = RAW_DIR / "openair_daily.csv"
EPA_RAW = RAW_DIR / "epa_aqs_daily.csv"

COMPLAINTS_CLEANED = CLEAN_DIR / "complaints_cleaned.csv"
OPENAIR_CLEANED = CLEAN_DIR / "openair_daily_cleaned.csv"
EPA_CLEANED = CLEAN_DIR / "epa_reference_daily.csv"
MERGED_FILE = CLEAN_DIR / "merged_complaints_air.csv"
NEIGHBORHOOD_SUMMARY = CLEAN_DIR / "neighborhood_summary.csv"
GEOJSON_FILE = CLEAN_DIR / "chicago_neighborhoods.geojson"

# ── Config ─────────────────────────────────────────────────────────────────
CONFIG_FILE = PROJECT_ROOT / "config.ini"

_config = configparser.ConfigParser()
_config.read(CONFIG_FILE)


def get_config_section(section: str) -> configparser.SectionProxy:
    """Return a config.ini section proxy."""
    return _config[section]


# ── Logging ────────────────────────────────────────────────────────────────
def setup_logging(name: str | None = None) -> logging.Logger:
    """Configure root logging and return a named logger.

    Safe to call multiple times — ``basicConfig`` is a no-op after the first.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
    )
    return logging.getLogger(name or __name__)


# ── Cache helper ───────────────────────────────────────────────────────────
def cache_is_fresh(path: Path, max_age_hours: float) -> bool:
    """Return True if *path* exists and was modified less than *max_age_hours* ago."""
    if not path.exists():
        return False
    age_hours = (time.time() - path.stat().st_mtime) / 3600
    return age_hours < max_age_hours
