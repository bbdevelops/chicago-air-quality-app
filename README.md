# Chicago Air Quality — Complaint & Sensor Analysis

An end-to-end data pipeline that links **311 air-pollution complaints** with
**Open Air Chicago sensor readings** (PM2.5 and NO2) to explore whether
citizen complaints align with measured air quality across Chicago's
neighborhoods.

See active demo here:
<a href="https://chicago-air-quality-app.onrender.com/">https://chicago-air-quality-app.onrender.com/</a>
---

## Project Goals

| Goal | Data Source |
|------|------------|
| Average **PM2.5** by sensor and by neighborhood | Open Air Chicago daily aggregations (Socrata) |
| Average **NO2** by sensor and by neighborhood | Open Air Chicago daily aggregations (Socrata) |
| **311 complaint counts** by neighborhood | CDPH Environmental Complaints (Socrata) |
| **Correlation analysis** between complaints and air quality | Merged dataset |

---

## Repository Structure

```
chicago-air-quality-app/
├── run_pipeline.py                 # Orchestrator — runs all steps in order
├── config.ini                      # API endpoints, thresholds, date range
├── .env                            # Local API tokens (ignored by git)
├── .env.example                    # Safe template for token variables
├── requirements.txt                # App + pipeline dependencies
├── pyproject.toml                  # Project + testing configuration
├── aqi.py                          # AQI calculation functions
│
├── scripts/
│   ├── extract_complaints.py       # Pull 311 complaints from Socrata API
│   ├── extract_openair.py          # Pull Open Air daily aggregations from Socrata
│   ├── extract_epa.py              # Pull EPA AQS regulatory monitors (Cook County)
│   ├── clean_complaints.py         # Clean complaints, assign nearest sensor
│   ├── clean_openair.py            # Clean sensor data, flag PM2.5 outliers
│   ├── clean_epa.py                # Clean EPA AQS data
│   ├── export_neighborhoods_geojson.py  # Convert boundary CSV → GeoJSON
│   ├── assign_neighborhoods.py     # Point-in-polygon neighborhood assignment
│   ├── merge_datasets.py           # Join sensor readings + complaint counts
│   ├── build_neighborhood_summary.py   # One-row-per-neighborhood summary
│   ├── load_sqlite.py              # Load clean CSVs → SQLite database
│   ├── sql_queries.sql             # Example analytical SQL queries
│   ├── _common.py                  # Shared logic and paths
│   ├── _socrata.py                 # Shared Socrata client setup
│   └── _neighborhoods.py           # Shared spatial joins
│
├── data/
│   ├── Neighborhoods_2012b_20260228.csv  # Official Chicago neighborhood boundaries
│   ├── raw/                        # Raw API extracts (cached CSVs)
│   └── clean/                      # Cleaned, analysis-ready outputs
│
├── db/
│   └── chicago_air_quality.db      # SQLite database (3 tables)
│
├── notebooks/
│   ├── eda.ipynb                   # Exploratory analysis notebook
│   ├── architecture_tour.ipynb    # Step-by-step tour of the dashboard's data layer
│   └── complaint_air_correlation.ipynb  # Guided correlation walkthrough
│
├── logs/                           # Pipeline run logs (timestamped)
│
├── tests/                          # Pytest suite
│
└── streamlit_app/                  # Streamlit dashboard app
    ├── app.py                      # Entrypoint: load -> sidebar -> filter -> render
    ├── sidebar.py                  # Filter widgets -> SidebarState
    ├── banner.py                   # AQI banner + KPI cards
    ├── constants.py                # Labels, map metrics, map defaults
    ├── map_layers.py               # Map overlays (boundaries, sensors, complaints)
    ├── views/                      # One module per tab
    ├── loading.py                  # Read + validate data/clean files
    ├── metrics.py                  # Filtering and aggregation
    ├── estimation.py               # IDW estimates for uncovered neighborhoods
    ├── analytics.py                # Lead-lag and spike analysis
    ├── dashboard_data.py           # Re-exports the data layer above
    └── theme.py                    # Accessible UI theme definition
```

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

For notebooks only (optional):

```bash
pip install -r requirements-notebooks.txt
```

For development / CI tooling (ruff, pre-commit, nbstripout):

```bash
pip install -r requirements-dev.txt
```

### 2. Configure API tokens

Create `.env` from the template in the project root:

```bash
copy .env.example .env
```

Then edit `.env`:

```dotenv
SOCRATA_APP_TOKEN=your_token_here
SOCRATA_APP_SECRET=your_secret_here
```

Register a free token at: https://data.cityofchicago.org/profile/edit/developer

### 3. Run the pipeline

```bash
# Full run (extracts data from APIs, cleans, merges, loads SQLite)
python run_pipeline.py

# Skip API calls (use cached raw data)
python run_pipeline.py --skip-api

# Force re-download from API
python run_pipeline.py --force

# Also pull EPA AQS regulatory reference monitors (needs EPA_API_* in .env)
python run_pipeline.py --with-epa
```

### 4. Explore the data

- Open `notebooks/eda.ipynb` for exploratory analysis
- Open `notebooks/complaint_air_correlation.ipynb` for guided correlation analysis
- Launch Streamlit app: `python -m python -m streamlit run streamlit_app/app.py`
- Query `db/chicago_air_quality.db` with any SQL client

---

## Streamlit Dashboard (Self-Hosted)

The repository now includes a Streamlit dashboard that mirrors the Tableau workflow
using the same pipeline outputs in `data/clean/`:

- `streamlit_app/app.py` — UI and visualizations
- `streamlit_app/loading.py`, `metrics.py`, `estimation.py`, `analytics.py` — reusable analytics functions (also importable via `streamlit_app/dashboard_data.py`)

**Understanding the code:** start with [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) (module map and data flow), then [docs/LIFE_OF_A_RERUN.md](docs/LIFE_OF_A_RERUN.md) (how one widget change runs through the code). Extending it? See [docs/HOW_TO.md](docs/HOW_TO.md). For a runnable walkthrough with real data, open `notebooks/architecture_tour.ipynb`.

### Features

- **EPA Air Quality Index (AQI)** using the official 2024-revised PM2.5 breakpoints — an AQI hero banner with health guidance, an AQI map metric, and AQI health-color bands
- **Theme toggle**: dark "Terminal" look or a light, high-contrast **Accessible** palette (EPA health colors), switchable from the sidebar
- Dual map modes: **Neighborhood choropleth** (default) and **Continuous heatmap**
- Neighborhood polygon overlay from `chicago_neighborhoods.geojson`
- Sensor marker overlay (PM2.5 and complaint totals)
- IDW placeholder estimates for neighborhoods with no direct sensor-period values, with adjustable k / distance-power / max-distance controls
- Dual-axis daily trend chart (PM2.5 vs complaints)
- Lead-lag correlation chart and spike-window concordance view
- Coverage QA tab with `coverage_source` diagnostics (`direct`, `estimated_idw`, `unavailable`)

### Map Modes and Coverage Logic

- **Neighborhood choropleth**
	- Colors polygons using direct period metrics where available.
	- For neighborhoods without direct period coverage, the app computes placeholder values
		from nearby sensors using **inverse-distance weighting (IDW)**.
	- Hover fields and Coverage QA explicitly indicate whether a value is direct or estimated.

- **Continuous heatmap**
	- Renders a sensor-driven density surface for the selected metric.
	- Neighborhood boundaries are overlaid for orientation, but color is not constrained by polygon fill.

- **QA transparency**
	- The Coverage QA tab includes estimation metadata such as nearby sensor count and nearest sensor distance.

### Run locally

```bash
pip install -r requirements.txt
python run_pipeline.py --skip-api
python -m streamlit run streamlit_app/app.py
```

If you see `ModuleNotFoundError: No module named 'streamlit_app'`, pull the
latest code and re-run the command above from the project root.

### Deploy to your own site/server

Option A: Docker

```bash
docker build -t chicago-air-quality .
docker run --rm -p 8501:8501 chicago-air-quality
```

Then reverse-proxy `:8501` behind your domain (Nginx/Caddy/Traefik).

Option B: Native process manager (systemd/PM2/supervisor)

- Run `python -m streamlit run streamlit_app/app.py --server.address=0.0.0.0 --server.port=8501`
- Put a reverse proxy in front of it for HTTPS and domain routing.

---

## Testing

Unit tests are under `tests/` and target core pipeline and analytics logic. See [TESTING.md](TESTING.md) for details.

Run tests:

```bash
pytest
```

---

## Pipeline Steps

Run python run_pipeline.py --help for the full list of steps.

---

## Key Output Files

### `merged_complaints_air.csv`
The primary analysis dataset — one row per sensor per day:

| Column | Description |
|--------|-------------|
| `sensor_name` | Open Air sensor identifier |
| `date` | Calendar date |
| `pm25_mean` | Daily mean PM2.5 (µg/m³) |
| `no2_mean` | Daily mean NO2 (ppb) |
| `complaint_count` | 311 complaints assigned to this sensor that day |
| `pm25_lag1` / `pm25_lag2` | Previous 1-2 days PM2.5 |
| `pm25_7d_mean` | Rolling 7-day mean PM2.5 |
| `pm25_spike` | Binary: PM2.5 > 35 µg/m³ (EPA 24-hr standard) |
| `neighborhood` | Chicago neighborhood name |

### `neighborhood_summary.csv`
One row per neighborhood (all 98), with:
- Sensor coverage info
- Mean/median/max PM2.5 and NO2
- Total complaint counts
- Spike day counts

### `epa_reference_daily.csv` (optional, `--with-epa`)
One row per EPA regulatory reference site per day (Cook County):
- `site_id`, `date`, `site_name`, `latitude`, `longitude`
- `pm25_mean` / `pm25_aqi` — daily mean PM2.5 and EPA's reported AQI
- `no2_mean` / `no2_aqi` — daily mean NO2 and AQI (NO2 present only at NO2 sites)

---

## Removed / Deferred Components

The following were planned but removed as non-functional stubs:

| Component | Reason | Status |
|-----------|--------|--------|
| EPA AirNow (real-time) integration | AirNow API stub, extraction never implemented | **Removed** — Removed in initial versions, re-added as optional EPA AQS integration (regulatory monitors), added as an optional reference source (`--with-epa`; see [Data Sources](#data-sources)) |
| Visual Crossing weather | API stub only, no downstream usage | **Removed** — can be re-added if weather correlation is needed |
| Census data cleaning | Stub only, no downstream usage | **Removed** — can be re-added for demographic analysis |

---

## Data Sources

| Source | Type | Access |
|--------|------|--------|
| [CDPH Environmental Complaints](https://data.cityofchicago.org/d/fypr-ksnz) | 311 air pollution work orders | Socrata API (free) |
| [Open Air Chicago Day Aggregations](https://data.cityofchicago.org/d/rtmx-vkjr) | PM2.5 and NO2 daily means | Socrata API (free) |
| [EPA Air Quality System (AQS)](https://aqs.epa.gov/aqsweb/documents/data_api.html) | Regulatory PM2.5/NO2 reference monitors + AQI (Cook County) | AQS API (free; optional, `--with-epa`) |
| Chicago Neighborhoods 2012b | Official boundary polygons | Included in `data/` |

---

## Analysis Guide

See `notebooks/complaint_air_correlation.ipynb` for a step-by-step notebook
that walks through:

1. Loading the merged dataset
2. Basic descriptive statistics by neighborhood
3. Pearson/Spearman correlation between PM2.5 and complaint counts
4. Time-lagged cross-correlation (do complaints follow spikes?)
5. Visual scatter plots and heatmaps
6. Neighborhood-level comparison charts

No advanced statistics knowledge required — each cell has explanatory comments.
