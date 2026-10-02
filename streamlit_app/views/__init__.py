"""Dashboard tab views, one module per tab.

Purpose: keep each tab's layout and charts in its own module.
Inputs:  the sidebar state plus the already-computed frames each tab needs.
Outputs: each ``render_*`` function draws its tab; none load or filter data themselves.
Used by: streamlit_app/app.py.
"""
