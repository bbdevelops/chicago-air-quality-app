import math

import pandas as pd

from scripts.clean_epa import clean_epa_frame


def _raw_aqs() -> pd.DataFrame:
    # Mimics the AQS dailyData/byCounty payload columns we rely on.
    return pd.DataFrame(
        [
            # Site 4002 — two PM2.5 rows same day (mean 10.0, aqi max 50) + one NO2 row.
            dict(state_code=17, county_code=31, site_number=4002, parameter_code=88101,
                 date_local="2026-01-01", arithmetic_mean=12.0, aqi=50,
                 local_site_name="Com Ed", latitude=41.75, longitude=-87.71),
            dict(state_code=17, county_code=31, site_number=4002, parameter_code=88101,
                 date_local="2026-01-01", arithmetic_mean=8.0, aqi=float("nan"),
                 local_site_name="Com Ed", latitude=41.75, longitude=-87.71),
            dict(state_code=17, county_code=31, site_number=4002, parameter_code=42602,
                 date_local="2026-01-01", arithmetic_mean=20.0, aqi=19,
                 local_site_name="Com Ed", latitude=41.75, longitude=-87.71),
            # Site 4002 next day — PM2.5 only.
            dict(state_code=17, county_code=31, site_number=4002, parameter_code=88101,
                 date_local="2026-01-02", arithmetic_mean=30.0, aqi=89,
                 local_site_name="Com Ed", latitude=41.75, longitude=-87.71),
            # Site 76 — NO2 only (no PM2.5). Tests zero-padding of site id.
            dict(state_code=17, county_code=31, site_number=76, parameter_code=42602,
                 date_local="2026-01-01", arithmetic_mean=40.0, aqi=38,
                 local_site_name="Springfield Pump", latitude=41.98, longitude=-87.79),
        ]
    )


def test_clean_epa_frame_collapses_and_merges() -> None:
    out = clean_epa_frame(_raw_aqs())

    row = out[(out["site_id"] == "17-031-4002") & (out["date"] == pd.to_datetime("2026-01-01").date())].iloc[0]
    assert row["pm25_mean"] == 10.0        # mean of 12.0 and 8.0
    assert row["pm25_aqi"] == 50           # max of 50 and NaN
    assert row["no2_mean"] == 20.0
    assert row["no2_aqi"] == 19
    assert row["site_name"] == "Com Ed"


def test_clean_epa_frame_zero_pads_site_id_and_handles_missing_param() -> None:
    out = clean_epa_frame(_raw_aqs())

    no2_only = out[out["site_id"] == "17-031-0076"].iloc[0]
    assert no2_only["no2_mean"] == 40.0
    assert math.isnan(no2_only["pm25_mean"])


def test_clean_epa_frame_empty_input_returns_schema() -> None:
    out = clean_epa_frame(pd.DataFrame())
    assert list(out.columns) == [
        "site_id", "date", "site_name", "latitude", "longitude",
        "pm25_mean", "pm25_aqi", "no2_mean", "no2_aqi",
    ]
    assert out.empty
