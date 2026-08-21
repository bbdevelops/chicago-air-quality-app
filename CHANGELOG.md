# Changelog — Chicago Air Quality Project

## 2026-08-20 — EPA AQI, Accessible Theme Toggle & Repo Hygiene

### Added
- **EPA Air Quality Index (2024 breakpoints)** as a first-class metric: `pm25_to_aqi`, `no2_to_aqi` (informational), `aqi_category`, `aqi_health_message`, and vectorized `add_aqi_columns` in `dashboard_data.py`, all unit-tested.
- **AQI hero banner** above the KPI cards showing the selection-average AQI, category, and plain-language health guidance in the official health color.
- **"Air Quality Index (PM2.5)" map metric** rendering neighborhoods/heatmap on the fixed EPA 0–500 band scale (choropleth + continuous heatmap), plus an AQI column in Coverage QA.
- **Theme toggle** (`streamlit_app/theme.py`): switch between the dark "Terminal" look and a light, high-contrast **Accessible** palette (sans-serif, EPA health colors) at runtime.
- **IDW estimation controls** (k, distance power, max distance) exposed in the sidebar.
- **EPA AQS live integration** (opt-in via `python run_pipeline.py --with-epa`): `scripts/extract_epa.py` pulls Cook County regulatory PM2.5 (88101) + NO2 (42602) daily data from the AQS API (year-chunked, cached), and `scripts/clean_epa.py` collapses it to one tidy row per site/day (`data/clean/epa_reference_daily.csv`) with EPA's own AQI. Validated live against the API; EPA's reported AQI matches our `pm25_to_aqi` (e.g. 23.6 µg/m³ → AQI 78). Cleaner logic is unit-tested (`tests/test_clean_epa.py`).
- **EPA AQS credentials documented** in `.env.example` (`EPA_API_EMAIL` / `EPA_API_KEY`) and a new `[epa]` section in `config.ini`.

### Changed
- `compute_spike_concordance` is **vectorized** (was an O(offsets × spike-days) nested scan) and now accepts an absolute `threshold` in addition to the percentile.
- All charts route background/font/grid styling through `theme.style_fig`; colorscales follow the active theme.
- Migrated deprecated `use_container_width=True` → `width="stretch"`.
- Consolidated duplicated map/QA column-label dictionaries into a single module-level `COLUMN_LABELS` constant in `streamlit_app/app.py`.
- `.streamlit/config.toml`: set `enableCORS = false` so `enableXsrfProtection` stays effective (the two conflict).

### Tooling & Notebooks
- **CI**: added `.github/workflows/ci.yml` running `ruff` + `pytest` on pushes/PRs.
- **Tooling config**: added `pyproject.toml` (ruff + pytest config, project metadata), `requirements-dev.txt`, `.python-version` (3.13), and `.pre-commit-config.yaml` (ruff + nbstripout); removed the now-redundant `pytest.ini`.
- **Notebooks**: stripped committed cell outputs from `eda.ipynb` (1.05 MB → 30 KB), fixed duplicated Section 5/6 headers (now 1–9), corrected a `4a`→`6a` comment, and renamed the stale "Citizen Sensor Tracker" title.

### Fixed
- **Accessible theme rendered Material Symbols icons as raw text**: the chrome CSS applied `font-family` to all `<span>` elements, overriding Streamlit's Material Symbols font on icon spans, so the sidebar `>>` collapse control and expander chevrons showed ligature text (`keyboard_double_arrow_right`, `arrow_right`) and overlapped nearby text. The chrome CSS is now scoped to leave icon fonts untouched.
- `page_icon` now uses the `:wind_face:` shortcode (previously rendered as literal text).
- Removed stray colorbar border typo (`colorbar_borderwidth=.11` → `1`) and a copy-pasted `yaxis2` grid style on the single-axis ranking chart.
- Deleted orphan/backup data artifacts (`merged_complaints_air_backup.csv`, old Tableau `neighborhood - avg *.csv` exports) and a stale editor lock file.

### Notes
- Backfilled changelog for prior untracked feature work: **Temporal Trends** tab (calendar heatmap + NO2 timeline), **Neighborhood Trends** tab, mobile-friendly map legend/layout, and the dark "terminal" UI color scheme.

## 2026-03-16 — Map Overlay Controls, Legend Readability, and MapLibre Migration

### Added
- **Map layer toggles** for sensor markers and complaint locations in the Neighborhood Map tab
- **Complaint location overlay** using filtered geocoded complaint points
- **Complaint-size legend helper bins** that choose visually distinct marker-size steps

### Changed
- **Sensor marker sizing** remains complaint-driven and now uses clearer legend labeling for interpretability
- **Legend styling** updated for high contrast and improved readability on map backgrounds
- **Plotly map rendering migrated to MapLibre APIs**:
	- `choropleth_mapbox` -> `choropleth_map`
	- `density_mapbox` -> `density_map`
	- `Scattermapbox` -> `Scattermap`
	- `mapbox_style` -> `map_style`

### Fixed
- **Runtime error fix**: removed unsupported `marker.line` usage on map marker legend traces
- **Deprecation cleanup**: eliminated Plotly Mapbox deprecation warnings in the Streamlit app

### Testing
- Full test suite passing after map overlay and migration updates

## 2026-03-16 — Dual Map Modes & Neighborhood Placeholder Estimates

### Added
- **Dual map modes in Streamlit**: `Neighborhood choropleth` (default) and `Continuous heatmap`
- **IDW placeholder estimation** for neighborhoods without direct sensor-period values
- **Coverage metadata fields** in dashboard metrics:
	- `coverage_source` (`direct`, `estimated_idw`, `unavailable`)
	- `estimated_sensor_count`
	- `estimated_nearest_km`
- **Neighborhood boundary overlay** in continuous heatmap mode for geographic orientation

### Changed
- **Choropleth rendering** now uses map-value columns that preserve direct measurements and only apply estimated values where direct period metrics are missing
- **Coverage QA tab** now surfaces direct vs estimated status and estimation diagnostics

### Testing
- Added dashboard tests for IDW enrichment behavior and unavailable fallback behavior in `tests/test_dashboard_data.py`
- Full test suite passing after feature integration

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
