"""
app.py

Root Streamlit entry point. Deliberately minimal: load the theme, render
the sidebar, render the header, ask the page router to render whichever
page is currently selected. No page logic lives here — see frontend/pages/.

Run with:
    streamlit run frontend/app.py

Import note: Streamlit adds this file's own directory (frontend/) to
sys.path automatically, which is why the package imports below resolve
correctly with no path manipulation, regardless of which directory you run
the `streamlit run` command from.
"""

import streamlit as st
from collections import deque
from datetime import datetime

from utils.theme import inject_global_theme
from utils.page_router import render_page
from components.sidebar import render_sidebar
from components.header import render_header

st.set_page_config(
    page_title="BMERMS — Battlefield Medical Evacuation & Resource Management System",
    layout="wide",
    initial_sidebar_state="expanded",
)

import sys
from pathlib import Path

# ROOT = Path(__file__).resolve().parent.parent
# if str(ROOT) not in sys.path:
#     sys.path.insert(0, str(ROOT))

if "mission_log" not in st.session_state:
    st.session_state.mission_log = deque(maxlen=200)

# if "sim_clock" not in st.session_state:
#     st.session_state.sim_clock = SimulationClock(
#         start_time=datetime.now()
#     )

inject_global_theme()
current_page = render_sidebar(default_page="Dashboard")

# clock = st.session_state.sim_clock
render_header(
    simulation_day=1,
    simulation_time=datetime.now().strftime("%H:%M"),
    operational_status="Operational",
)
render_page(current_page)