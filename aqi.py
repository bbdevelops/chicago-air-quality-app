"""
aqi.py — Single source of truth for AQI constants, breakpoints, and helpers.

Importable by both the pipeline (scripts/) and the dashboard (streamlit_app/).

All PM2.5 breakpoints are the **2024-revised** 24-hour values (effective
2024-05-06).  The EPA annual standard was lowered from 12 to 9 µg/m³ in the
same rulemaking.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

# ── EPA Air Quality Index (AQI) ────────────────────────────────────────────
# US EPA AQI breakpoints as (conc_low, conc_high, aqi_low, aqi_high).
PM25_AQI_BREAKPOINTS: list[tuple[float, float, int, int]] = [
    (0.0, 9.0, 0, 50),
    (9.1, 35.4, 51, 100),
    (35.5, 55.4, 101, 150),
    (55.5, 125.4, 151, 200),
    (125.5, 225.4, 201, 300),
    (225.5, 325.4, 301, 500),
]

# NO2 1-hour breakpoints in ppb (unchanged in 2024).
NO2_AQI_BREAKPOINTS: list[tuple[float, float, int, int]] = [
    (0, 53, 0, 50),
    (54, 100, 51, 100),
    (101, 360, 101, 150),
    (361, 649, 151, 200),
    (650, 1249, 201, 300),
    (1250, 2049, 301, 500),
]

# (aqi_low, aqi_high, label, hex_color, short health guidance).
AQI_CATEGORIES: list[tuple[int, int, str, str, str]] = [
    (0, 50, "Good", "#00e400", "Air quality is satisfactory; little or no risk."),
    (51, 100, "Moderate", "#ffff00", "Acceptable; unusually sensitive people should consider limiting prolonged outdoor exertion."),
    (101, 150, "Unhealthy for Sensitive Groups", "#ff7e00", "Sensitive groups should limit prolonged outdoor exertion."),
    (151, 200, "Unhealthy", "#ff0000", "Everyone may begin to feel effects; sensitive groups feel stronger effects."),
    (201, 300, "Very Unhealthy", "#8f3f97", "Health alert: everyone may experience more serious health effects."),
    (301, 500, "Hazardous", "#7e0023", "Health warning of emergency conditions; everyone should avoid outdoor exertion."),
]

_AQI_UNAVAILABLE = ("Unavailable", "#666666", "No reading available for this selection.")

# ── Key thresholds ─────────────────────────────────────────────────────────
PM25_SPIKE_THRESHOLD = 35.0        # µg/m³  — 24-hour standard
PM25_OUTLIER_UPPER = 150.0         # µg/m³  — flag, don't remove
PM25_OUTLIER_LOWER = 0.0
EPA_ANNUAL_STANDARD = 9.0          # µg/m³  — 2024 revision (was 12)


# ── AQI computation ───────────────────────────────────────────────────────
def _conc_to_aqi(
    concentration: float,
    breakpoints: list[tuple[float, float, int, int]],
    trunc_decimals: int,
) -> float:
    """Piecewise-linear AQI from a pollutant concentration. NaN in → NaN out."""
    if concentration is None:
        return float("nan")
    try:
        conc = float(concentration)
    except (TypeError, ValueError):
        return float("nan")
    if math.isnan(conc) or conc < 0:
        return float("nan")

    # EPA truncates the concentration before applying the formula.
    factor = 10 ** trunc_decimals
    conc = math.floor(conc * factor) / factor

    for c_lo, c_hi, i_lo, i_hi in breakpoints:
        if conc <= c_hi:
            aqi = (i_hi - i_lo) / (c_hi - c_lo) * (conc - c_lo) + i_lo
            return float(round(aqi))
    # Above the highest breakpoint: cap at the top of the scale.
    return float(breakpoints[-1][3])


def pm25_to_aqi(concentration: float) -> float:
    """US EPA AQI (2024 breakpoints) from a 24-hour mean PM2.5 in µg/m³."""
    return _conc_to_aqi(concentration, PM25_AQI_BREAKPOINTS, trunc_decimals=1)


def no2_to_aqi(concentration_ppb: float) -> float:
    """INFORMATIONAL NO2 sub-index from ppb.

    EPA's official NO2 sub-index needs the daily 1-hour maximum; the pipeline
    only carries a daily mean, so treat this as a rough indicator, never as an
    official AQI.  Callers must label it accordingly.
    """
    return _conc_to_aqi(concentration_ppb, NO2_AQI_BREAKPOINTS, trunc_decimals=0)


def aqi_category(aqi: float) -> tuple[str, str]:
    """Return the (label, hex_color) for an AQI value; ('Unavailable', grey) for NaN."""
    try:
        value = float(aqi)
    except (TypeError, ValueError):
        return _AQI_UNAVAILABLE[0], _AQI_UNAVAILABLE[1]
    if math.isnan(value) or value < 0:
        return _AQI_UNAVAILABLE[0], _AQI_UNAVAILABLE[1]
    for _i_lo, i_hi, label, color, _ in AQI_CATEGORIES:
        if value <= i_hi:
            return label, color
    last = AQI_CATEGORIES[-1]
    return last[2], last[3]


def aqi_health_message(aqi: float) -> str:
    """Return the short health-guidance string for an AQI value."""
    try:
        value = float(aqi)
    except (TypeError, ValueError):
        return _AQI_UNAVAILABLE[2]
    if math.isnan(value) or value < 0:
        return _AQI_UNAVAILABLE[2]
    for _i_lo, i_hi, _, _, message in AQI_CATEGORIES:
        if value <= i_hi:
            return message
    return AQI_CATEGORIES[-1][4]


def add_aqi_columns(df: pd.DataFrame, pm25_col: str = "pm25_mean") -> pd.DataFrame:
    """Add ``pm25_aqi`` and ``aqi_category`` columns from a PM2.5 column.

    Vectorized over the frame. Rows with a missing/NaN PM2.5 get NaN AQI and
    ``Unavailable`` category.
    Returns a copy; input is not mutated.
    """
    out = df.copy()
    if pm25_col not in out.columns:
        out["pm25_aqi"] = np.nan
        out["aqi_category"] = "Unavailable"
        return out

    out["pm25_aqi"] = pd.to_numeric(out[pm25_col], errors="coerce").map(pm25_to_aqi)
    out["aqi_category"] = out["pm25_aqi"].map(lambda value: aqi_category(value)[0])
    return out


# ── Theme helpers (derived from AQI_CATEGORIES) ───────────────────────────
def build_aqi_colorscale(max_aqi: int = 500) -> list[list[float | str]]:
    """Build a Plotly-compatible stepped colorscale from AQI_CATEGORIES."""
    stops: list[tuple[int, str]] = []
    for lo, hi, _label, color, _msg in AQI_CATEGORIES:
        stops.append((lo, color))
        stops.append((hi, color))
    return [[v / max_aqi, c] for v, c in stops]


def build_aqi_css_gradient() -> str:
    """Build a CSS linear-gradient string from AQI_CATEGORIES."""
    max_aqi = 500
    parts: list[str] = []
    for lo, hi, _label, color, _msg in AQI_CATEGORIES:
        pct_lo = lo / max_aqi * 100
        pct_hi = hi / max_aqi * 100
        parts.append(f"{color} {pct_lo:.0f}%")
        parts.append(f"{color} {pct_hi:.0f}%")
    return "linear-gradient(to right," + ",".join(parts) + ")"


# ── Shared spatial utility ─────────────────────────────────────────────────
def haversine_km(
    lat: float, lon: float, lat_series: pd.Series, lon_series: pd.Series
) -> pd.Series:
    """Return great-circle distance from one point to many points (km).

    Vectorized — operates on entire pandas Series at once.
    """
    lat1 = np.radians(lat)
    lon1 = np.radians(lon)
    lat2 = np.radians(lat_series.astype(float))
    lon2 = np.radians(lon_series.astype(float))

    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    c = 2.0 * np.arcsin(np.sqrt(a))

    earth_radius_km = 6371.0088
    return pd.Series(earth_radius_km * c, index=lat_series.index)
