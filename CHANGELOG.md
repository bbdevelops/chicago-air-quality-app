# Changelog — Chicago Air Quality Project

## 2026-02-28 — Pipeline Cleanup & Documentation

### Added
- **README.md** — Comprehensive project documentation with structure, setup, and analysis guide
- **CHANGELOG.md** — This file, tracking project progress
- **Pipeline file logging** — Each `run_pipeline.py` execution now writes a timestamped log to `logs/`
- **`export_neighborhoods_geojson.py`** added to pipeline steps (was missing)
- **`notebooks/complaint_air_correlation.ipynb`** — Guided correlation analysis notebook for novice analysts

### Fixed
- **Bug**: `BATCH_SIDE` typo in `extract_complaints.py` → corrected to `BATCH_SIZE`
- **`--skip-api` flag** in `run_pipeline.py` now correctly skips ALL extraction steps (previously only skipped 2 of 4, and 2 of those were non-functional stubs)

### Removed (non-functional stubs)
- **`extract_epa.py`** — EPA AirNow extraction was never implemented (placeholder only, always returned empty DataFrame). Open Air Chicago already provides the PM2.5 and NO2 data needed.
- **`clean_epa.py`** — Corresponding cleaner for non-existent EPA data
- **`extract_weather.py`** — Visual Crossing weather extraction was never implemented (placeholder only)
- **`clean_weather.py`** — Corresponding cleaner for non-existent weather data
- **`clean_census.py`** — Census cleaning was never implemented (placeholder only)
- **EPA and Weather config sections** removed from `config.ini`

### Changed
- **`run_pipeline.py`** — Restructured with separate `EXTRACT_STEPS` and `TRANSFORM_STEPS` lists for clarity; added dual console+file logging
- **`config.ini`** — Simplified to only Socrata and cleaning sections

---

## Status as of 2026-02-28

### Working Pipeline Steps
| Step | Status |
|------|--------|
| Extract 311 complaints | ✅ Working (Socrata API) |
| Extract Open Air sensor data | ✅ Working (Socrata API) |
| Clean complaints + assign nearest sensor | ✅ Working |
| Clean Open Air data | ✅ Working |
| Export neighborhoods GeoJSON | ✅ Working |
| Assign neighborhoods (point-in-polygon) | ✅ Working |
| Merge datasets | ✅ Working |
| Build neighborhood summary | ✅ Working |
| Load SQLite | ✅ Working |

### Data Coverage
- **Date range**: September 2025 – February 2026 (configurable in `config.ini`)
- **Sensors**: ~286 Open Air Chicago sensors
- **Pollutants**: PM2.5 daily mean, NO2 daily mean
- **Complaints**: CDPH Air Pollution Work Orders
- **Neighborhoods**: All 98 official Chicago neighborhoods

### Known Limitations
- Complaint-to-sensor assignment uses Haversine distance to the nearest sensor — neighborhoods without sensors have no direct air quality reading
- Sensor coverage varies; some neighborhoods have no sensors at all
- PM2.5 outlier flagging threshold is set at 150 µg/m³ (configurable)
