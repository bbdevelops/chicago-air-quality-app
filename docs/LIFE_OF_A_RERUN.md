# Life of a rerun

The single most useful idea for reading this dashboard: **Streamlit re-executes `app.py` from top to bottom every time the user touches a widget.** There is no "event handler" for the date picker. Changing the date simply runs the whole script again with the new value.

This page follows one action, changing the date range, through the code in the order it executes. Open [app.py](../streamlit_app/app.py) next to this page; `main()` reads in the same order as the steps below.

## 0. What persists between reruns, and what does not

| Persists | Re-runs every time |
|---|---|
| Imported modules (Python caches them), so `import` lines are cheap | The body of `app.py` and everything `main()` calls |
| Widget values (Streamlit remembers them by widget identity) | Filtering, aggregation, IDW estimation, and every chart build |
| The result of `cached_load_data` (`st.cache_data`) | Anything not decorated with a cache |

Two consequences:

- A widget function such as `st.date_input(...)` is not "creating a widget once". It is called on every rerun and returns the *current* value.
- All five tabs are built on every rerun, even the ones you are not looking at. Streamlit tabs are layout only; they are not lazy.

## 1. The user picks a new end date

Streamlit notices the change and starts a new run of `app.py`. (Sliders only trigger a run when the thumb is released.)

## 2. Module level in `app.py`

```
imports -> add repo root to sys.path -> st.set_page_config -> define cached_load_data / main
```

Nothing heavy happens here. `set_page_config` must be the first Streamlit call, which is why it sits above `main()`.

## 3. `main()` loads the data (cached)

`cached_load_data(str(PROJECT_ROOT))` calls [loading.py](../streamlit_app/loading.py) the first time only. After that it returns the stored `PipelineData`. On this project the first load reads about 15 MB of CSV and takes roughly 0.17 s.

If a file is missing or has the wrong columns, `load_pipeline_data` raises, `main()` shows the message with `st.error` and calls `st.stop()`. Nothing below runs.

## 4. `render_sidebar(...)` returns the choices

[sidebar.py](../streamlit_app/sidebar.py) draws every widget and returns one frozen `SidebarState`. For the date range:

1. `st.date_input` returns a tuple, but only a one-element tuple while the user is mid-selection.
2. `normalize_date_range` turns whatever came back into a guaranteed `(start, end)`.
3. Those land in `ui.start_date` and `ui.end_date`.

From here on, the rest of the script never touches a widget. It reads `ui`.

## 5. Filter and aggregate

Still in `main()`, in this order:

| Step | Function | Result |
|---|---|---|
| Rows in the window (and chosen neighborhoods) | `filter_by_date_range` | `filtered`, `complaint_points` |
| Per-neighborhood averages | `build_neighborhood_metrics` | `base_map_metrics` |
| One row per calendar day | `build_city_daily_metrics`, then re-index to every day in the window | `city_daily` |
| One row per sensor | `build_sensor_snapshot`, then `add_aqi_columns` | `sensors` |
| Fill neighborhoods without sensors | `enrich_neighborhood_metrics_with_estimates` | `map_metrics` |
| Neighborhood AQI | `pm25_to_aqi` applied to `pm25_map_value` | `map_metrics["pm25_aqi_map_value"]` |

Re-indexing `city_daily` to every calendar day is deliberate: days with no readings become gaps in the line chart instead of being silently skipped.

## 6. The headline

`main()` builds `previous_filtered`: the same number of days, ending the day before the selection starts. [banner.py](../streamlit_app/banner.py)'s `render_summary` compares the two windows to produce the AQI banner and the four KPI cards with their "vs prior period" deltas.

## 7. The tabs

```python
with tab_map:          render_map_tab(ui, data, map_metrics, sensors, complaint_points)
with tab_trends:       render_trends_tab(ui, city_daily)
with tab_neighborhood: render_neighborhood_tab(ui, map_metrics)
with tab_lag:          render_lag_tab(ui, city_daily)
with tab_quality:      render_quality_tab(map_metrics)
```

Each view takes `ui` plus only the frames it needs. If a view needs something new, add it to this call; do not load or filter inside a view.

## 8. Streamlit sends the page

Streamlit diffs the elements produced by this run against the previous run and updates the browser.

## What a rerun costs

Measured on the real data (steady state, headless):

- A rerun takes roughly **0.45 s**, whichever widget changed (theme, map height, IDW *k*).
- The data work (filter, aggregate, IDW) is only about **0.1 to 0.2 s** of that.
- Most of the rest is Plotly: building six figures and serializing them. The choropleth alone embeds the neighborhood GeoJSON, which is why its figure is about 1.3 MB (it was 2.2 MB before the browser copy of the geometry was rounded to 6 decimal places, about 11 cm).

So caching the filter and aggregation steps would save very little. Anything that shrinks the figures matters more.

## Seeing it yourself

- **Print the state.** Temporarily add `st.write(ui)` after `render_sidebar(...)`, change a widget, and watch it update.
- **Run it without a browser.** `streamlit.testing.v1.AppTest` runs the script in-process, lets you set widget values and read back every chart. [tests/test_app_smoke.py](../tests/test_app_smoke.py) is a working example.
- **Step through the data layer.** [notebooks/architecture_tour.ipynb](../notebooks/architecture_tour.ipynb) runs steps 3 to 5 cell by cell with no Streamlit involved.
