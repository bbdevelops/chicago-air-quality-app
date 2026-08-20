"""Theme definitions for the Chicago Air Quality Explorer.

Two palettes are supported and switchable at runtime from the sidebar:

* **Terminal** — the original dark "matrix green" look (monospace, neon green).
* **Accessible** — a light, high-contrast, sans-serif palette that uses the
  official EPA AQI health colors for pollution metrics. Better for the general
  public and for colour-vision accessibility.

`.streamlit/config.toml` still sets the *initial* chrome theme (dark); the
runtime toggle restyles the Plotly figures, the custom map legend, the AQI
banner, and injects CSS to flip the Streamlit chrome to match.

Each theme is a plain dict so callers can read palette entries directly.
"""

from __future__ import annotations

from typing import Any

import plotly.graph_objects as go

# ── AQI band colorscale (shared by both themes) ─────────────────────────────
# Official EPA category colors as a stepped continuous scale over AQI 0–500.
# Used with range_color=[0, 500] so the map colors mean the same thing every
# time regardless of the data range in view.
_AQI_STOPS = [
    (0, "#00e400"),   # Good
    (50, "#00e400"),
    (50, "#ffff00"),  # Moderate
    (100, "#ffff00"),
    (100, "#ff7e00"),  # USG
    (150, "#ff7e00"),
    (150, "#ff0000"),  # Unhealthy
    (200, "#ff0000"),
    (200, "#8f3f97"),  # Very Unhealthy
    (300, "#8f3f97"),
    (300, "#7e0023"),  # Hazardous
    (500, "#7e0023"),
]
AQI_COLORSCALE = [[value / 500.0, color] for value, color in _AQI_STOPS]
AQI_RANGE = (0, 500)

# CSS linear-gradient mirroring AQI_COLORSCALE, for the mobile HTML legend bar.
AQI_CSS_GRADIENT = (
    "linear-gradient(to right,"
    "#00e400 0%,#00e400 10%,#ffff00 10%,#ffff00 20%,"
    "#ff7e00 20%,#ff7e00 30%,#ff0000 30%,#ff0000 40%,"
    "#8f3f97 40%,#8f3f97 60%,#7e0023 60%,#7e0023 100%)"
)


TERMINAL: dict[str, Any] = {
    "name": "Terminal",
    "paper_bg": "#0a0a0a",
    "plot_bg": "#0a0a0a",
    "app_bg": "#0a0a0a",
    "secondary_bg": "#111111",
    "font_color": "#e0e0e0",
    "font_family": "monospace",
    "accent": "#00ff41",
    "grid": "#1a3a1a",
    "muted": "#888888",
    "map_style": "carto-darkmatter",
    "sequential": [[0, "#001a00"], [0.25, "#005500"], [0.5, "#00aa33"], [0.75, "#00ff41"], [1, "#aaffaa"]],
    "density": [[0, "#000000"], [0.25, "#003300"], [0.5, "#00aa33"], [0.75, "#00ff41"], [1, "#ccffcc"]],
    "diverging": [[0, "#550000"], [0.5, "#1a3a1a"], [1, "#00ff41"]],
    "boundary_line": "rgba(0, 255, 65, 0.25)",
    "marker_scale": [[0, "#003300"], [0.25, "#00aa33"], [0.5, "#00ff41"], [0.75, "#aaff44"], [1, "#ffffff"]],
    "marker_solid": "#00ff41",
    "panel_bg": "rgba(10, 10, 10, 0.88)",
    "panel_border": "rgba(0, 255, 65, 0.40)",
    "bar_secondary": "#4a9a5a",
    "css_gradient": "linear-gradient(to right,#001a00,#005500,#00aa33,#00ff41,#aaffaa)",
}

ACCESSIBLE: dict[str, Any] = {
    "name": "Accessible",
    "paper_bg": "#ffffff",
    "plot_bg": "#ffffff",
    "app_bg": "#ffffff",
    "secondary_bg": "#f0f2f6",
    "font_color": "#1a1a1a",
    "font_family": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
    "accent": "#0b6bcb",
    "grid": "#dcdcdc",
    "muted": "#5a5a5a",
    "map_style": "carto-positron",
    # Sequential/heat scales use YlOrRd — a perceptually ordered, colour-vision
    # friendly ramp that reads naturally as "more pollution = hotter".
    "sequential": "YlOrRd",
    "density": "YlOrRd",
    "diverging": "RdBu_r",
    "boundary_line": "rgba(40, 40, 40, 0.35)",
    "marker_scale": "YlOrRd",
    "marker_solid": "#d62728",
    "panel_bg": "rgba(255, 255, 255, 0.92)",
    "panel_border": "rgba(0, 0, 0, 0.22)",
    "bar_secondary": "#f4a259",
    "css_gradient": "linear-gradient(to right,#ffffb2,#fecc5c,#fd8d3c,#f03b20,#bd0026)",
}

THEMES: dict[str, dict[str, Any]] = {"Terminal": TERMINAL, "Accessible": ACCESSIBLE}


def get_theme(name: str | None) -> dict[str, Any]:
    """Return a theme dict by name, defaulting to Terminal."""
    return THEMES.get(name or "Terminal", TERMINAL)


def style_fig(fig: go.Figure, theme: dict[str, Any], *, axes: bool = True) -> go.Figure:
    """Apply the theme's backgrounds, fonts, and axis grids to a Plotly figure.

    ``axes=False`` skips axis styling (for maps / imshow that have no x/y grid).
    """
    fig.update_layout(
        paper_bgcolor=theme["paper_bg"],
        plot_bgcolor=theme["plot_bg"],
        font={"color": theme["font_color"], "family": theme["font_family"]},
        title_font={"color": theme["accent"]},
    )
    if axes:
        fig.update_xaxes(gridcolor=theme["grid"], color=theme["font_color"])
        fig.update_yaxes(gridcolor=theme["grid"], color=theme["font_color"])
    return fig


def chrome_css(theme: dict[str, Any]) -> str:
    """CSS to flip the Streamlit chrome (background, text, sidebar) to the theme.

    Only emitted for the non-default (Accessible) theme, since config.toml
    already paints the default dark chrome.

    IMPORTANT: ``font-family`` is deliberately NOT applied to bare ``<span>``.
    Streamlit renders Material Symbols icons (the sidebar ``>>`` collapse control,
    expander chevrons) as ``<span>`` ligatures backed by the "Material Symbols
    Rounded" font. Overriding their font turns the glyph into raw ligature text
    like ``keyboard_double_arrow_right`` / ``arrow_right``, which also overlaps
    nearby text. Color is safe to set broadly (icons render in ``currentColor``).
    """
    return f"""
    <style>
    .stApp {{ background-color: {theme['app_bg']}; }}
    /* Text color — safe on spans (does not affect icon glyph rendering). */
    .stApp, .stApp p, .stApp label, .stApp span, .stApp li,
    .stMarkdown, [data-testid="stMetricValue"], [data-testid="stMetricLabel"] {{
        color: {theme['font_color']};
    }}
    /* Font family — text containers only, NEVER bare span (see docstring). */
    .stApp, .stApp p, .stApp label, .stApp li, .stMarkdown,
    .stApp h1, .stApp h2, .stApp h3, .stApp h4,
    [data-testid="stMetricValue"], [data-testid="stMetricLabel"] {{
        font-family: {theme['font_family']};
    }}
    .stApp h1, .stApp h2, .stApp h3, .stApp h4 {{ color: {theme['font_color']}; }}
    [data-testid="stSidebar"] {{ background-color: {theme['secondary_bg']}; }}
    [data-testid="stHeader"] {{ background-color: {theme['app_bg']}; }}
    /* Belt-and-suspenders: keep Material icon glyphs rendering as icons even if
       a future rule tries to restyle their font. */
    [data-testid="stIconMaterial"],
    [data-testid="stExpanderIcon"],
    [data-testid="stSidebarCollapseButton"] span {{
        font-family: "Material Symbols Rounded" !important;
    }}
    </style>
    """
