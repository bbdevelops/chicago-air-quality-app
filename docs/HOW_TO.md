# How to extend the dashboard

Step-by-step recipes. Each one lists the files you touch, in order. Run `ruff check .` and `pytest -q` at the end; the smoke test in [tests/test_app_smoke.py](../tests/test_app_smoke.py) runs the real app, so a wiring mistake shows up as a failing test.

Background: [ARCHITECTURE.md](ARCHITECTURE.md) (module map) and [LIFE_OF_A_RERUN.md](LIFE_OF_A_RERUN.md) (execution order).

## Add a map metric

A map metric is one entry in the sidebar's "Map metric" dropdown.

1. **Make sure the column exists.** The map needs two columns:
   - a neighborhood-level one in `map_metrics` for the choropleth (built in [metrics.py](../streamlit_app/metrics.py) `build_neighborhood_metrics`, or in [estimation.py](../streamlit_app/estimation.py) if it needs IDW);
   - a sensor-level one in the `sensors` snapshot for the heatmap (`build_sensor_snapshot` in `metrics.py`).

   Several existing columns already work, for example `pm25_mean_period`.
2. **Register it** in `MAP_METRICS` in [constants.py](../streamlit_app/constants.py):

   ```python
   "My metric (selected period)": MapMetric(
       choropleth_col="my_neighborhood_col",
       heatmap_col="my_sensor_col",
       colorbar_title="My metric",
       is_aqi=False,
   ),
   ```

   The dropdown is built from `list(MAP_METRICS)`, so nothing else is needed for it to appear. Use `is_aqi=True` only for the fixed 0 to 500 EPA color scale.
3. **Optional: hover and table labels.** To show the new neighborhood column in the choropleth hover card, add it to `hover_data` in [views/map_tab.py](../streamlit_app/views/map_tab.py) and give it a label in `COLUMN_LABELS`. To show it in the Coverage QA tables, add it to the column lists in [views/quality_tab.py](../streamlit_app/views/quality_tab.py).
4. **Tests.** The smoke test builds its list from `MAP_METRICS`, so the new metric is exercised in both themes and both map modes automatically. If you added a data function, add a small unit test next to the others in `tests/test_dashboard_data.py`.

## Add a sidebar control

1. Add a field to `SidebarState` in [sidebar.py](../streamlit_app/sidebar.py).
2. Create the widget inside `render_sidebar` and pass its value into the `SidebarState(...)` call at the end of the function.
3. Use it as `ui.my_field` in whichever view needs it. If it changes the data (a new filter, say), apply it in `app.py` where the other filters are applied, not inside a view.
4. In the smoke test, `_run(...)` sets sidebar widgets by label (spaces written as double underscores), so add a case that sets yours.

## Add a tab

1. Create `streamlit_app/views/my_tab.py` with a function `render_my_tab(ui: SidebarState, <frames it needs>) -> None`. Copy the four-line docstring (Purpose / Inputs / Outputs / Used by) from a neighboring tab.
2. In [app.py](../streamlit_app/app.py):
   - import the function;
   - add the tab title to the `st.tabs([...])` list and unpack one more variable;
   - add `with tab_my: render_my_tab(ui, ...)`.
3. Update `assert len(at.tabs) == 5` in the smoke test.

Keep the view free of loading and filtering; compute what it needs in `app.py` and pass it in.

## Add a pollutant to the trend charts

1. Add an entry to `POLLUTANTS` in `constants.py` with the merged-table column (`column`), a display `label`, and a `unit`.
2. Add the name to the "Primary trend metric" options in `sidebar.py`, and to "Calendar heatmap metric" if wanted.
3. The Neighborhood Trends ranking reads `f"{column}_period"`, so `build_neighborhood_metrics` must produce that column.

## Change a theme color

All palette entries live in the `TERMINAL` and `ACCESSIBLE` dicts in [theme.py](../streamlit_app/theme.py). Views read them by key, for example `theme["accent"]`. To add a new key, add it to **both** dicts; a missing key fails at runtime with a `KeyError` in the first view that reads it.

AQI colors are the exception: they are defined once in `AQI_CATEGORIES` in [aqi.py](../aqi.py), and the colorscale and CSS gradient are derived from it.

## Add a new pipeline output for the dashboard

1. Produce the file in a script under `scripts/` and register the step in `run_pipeline.py`.
2. Add its path to `_clean_paths` and a column check to [loading.py](../streamlit_app/loading.py), and carry it on `PipelineData`.
3. Run `python run_pipeline.py --skip-api`, then open the app once; unit tests alone do not exercise the pipeline end to end.

## Refactoring checklist

Use this when moving code without meaning to change behavior:

1. `ruff check .` and `pytest -q` pass.
2. The app still starts with plain `streamlit run streamlit_app/app.py`. The import-path test covers this.
3. If you can, snapshot the rendered output across widget combinations with `AppTest` before and after, and compare. See the last section of [ARCHITECTURE.md](ARCHITECTURE.md).
