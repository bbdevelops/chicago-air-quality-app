# Testing Guide

This project uses `pytest` to validate core transformations and geospatial logic.
The goal is to catch regressions in pipeline math, neighborhood assignment,
and dashboard aggregation behavior before deployment.

## Scope

The suite currently covers:

- `scripts/clean_complaints.py`
  - `build_sensor_locations`
  - `find_nearest_sensor`
- `scripts/assign_neighborhoods.py`
  - `load_neighborhoods`
  - `assign_neighborhood` (exact and snap-fallback behavior)
- `scripts/aggregate_hourly_to_daily.py`
  - `weighted_reaggregate_daily`
- `streamlit_app/dashboard_data.py`
  - filtering, city/day aggregation, neighborhood-preserving joins,
    lag correlations, and spike-window summaries

## Run Tests

Install dependencies once:

```bash
pip install -r requirements.txt
```

Run all tests:

```bash
pytest
```

Run one file:

```bash
pytest tests/test_dashboard_data.py
```

Run one test:

```bash
pytest tests/test_assign_neighborhoods.py::test_assign_neighborhood_snaps_to_nearest_boundary
```

## Test Design Notes

- Tests use small synthetic data frames and temporary files for deterministic behavior.
- Geospatial tests use tiny square polygons in WKT to isolate exact/fallback matching.
- Dashboard tests validate the critical anti-NULL-bucket behavior by ensuring all
  neighborhoods remain present after merges, even with no sensor rows.
- Weighted aggregation tests verify reading-count weighting, not simple averages.

## Manual Checks for False Positives and Broken Tests

Use the checks below periodically to ensure tests fail when logic is wrong
(and are therefore not just "green by accident").

1. Mutation check: weighted means
- In `scripts/aggregate_hourly_to_daily.py`, temporarily replace weighted means
  with simple `.mean()` inside `weighted_reaggregate_daily`.
- Expected: `tests/test_aggregate_hourly_to_daily.py` fails.
- Revert after confirming failure.

2. Mutation check: neighborhood snap fallback
- In `scripts/assign_neighborhoods.py`, temporarily set `SNAP_TOLERANCE_DEG = 0`.
- Expected: `test_assign_neighborhood_snaps_to_nearest_boundary` fails.
- Revert after confirming failure.

3. Mutation check: drop neighborhood-preserving merge
- In `streamlit_app/dashboard_data.py`, temporarily change
  `build_neighborhood_metrics` to return only grouped rows from merged data
  (skip merge with authority list).
- Expected: `test_build_neighborhood_metrics_preserves_neighborhoods_without_data` fails.
- Revert after confirming failure.

4. Pipeline smoke check (integration)
- Run `python run_pipeline.py --skip-api`.
- Verify outputs exist and are non-empty:
  - `data/clean/merged_complaints_air.csv`
  - `data/clean/neighborhood_summary.csv`
  - `data/clean/chicago_neighborhoods.geojson`
- Start app: `streamlit run streamlit_app/app.py`
- In Coverage QA tab, confirm neighborhoods without sensors appear as separate named rows.

## Interpreting Failures

- `test_clean_complaints.py` failures usually indicate schema changes in raw Open Air files.
- `test_assign_neighborhoods.py` failures indicate geospatial behavior changes, often due to
  tolerance or geometry parsing edits.
- `test_aggregate_hourly_to_daily.py` failures indicate chunk re-aggregation logic regressions.
- `test_dashboard_data.py` failures indicate mismatch between app metrics and pipeline semantics.

## CI Recommendation

If you add CI later, run this command in pull requests:

```bash
pytest
```

Optional stricter gate:

```bash
python run_pipeline.py --skip-api
pytest
```
