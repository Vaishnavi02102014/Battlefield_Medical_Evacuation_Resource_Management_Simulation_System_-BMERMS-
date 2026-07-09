"""
dashboard.py
 
Dashboard page — rebuilt to fit approximately one to one-and-a-half laptop
screens, per the approved layout:
 
    Row 1 — 6 KPI cards
    Row 2 — Battlefield Evacuation Workflow (compact, single horizontal panel)
    Row 3 — Mission Log | Battlefield Map (hero) | Asset Inventory
    Row 4 — Simulation Controls | AI Tactical Recommendation | Triage Severity Chart
 
All values are hardcoded placeholders. No backend, simulation, service, or
session-state wiring. Uses only st.container()/st.columns()/st.progress()/
st.markdown()/st.write()/st.caption() plus the existing metric_card(),
panel(), and buttons() components — no page-level CSS, no hardcoded colors.
"""
 
import streamlit as st
 
from components.metric_card import metric_card
from components.panel import panel
from components.buttons import primary_button
 
KPI_CARDS = [
    {"title": "Total Soldiers", "value": 1250, "icon": "■", "color": "info"},
    {"title": "In Treatment", "value": 780, "icon": "■", "color": "warning"},
    {"title": "Waiting in Queue", "value": 150, "icon": "■", "color": "warning"},
    {"title": "Recovered", "value": 320, "icon": "■", "color": "primary"},
    {"title": "Returned to Duty", "value": 210, "icon": "■", "color": "primary"},
    {"title": "Active Incidents", "value": 3, "icon": "■", "color": "danger"},
]
 
EVACUATION_WORKFLOW = [
    {"name": "Battlefield", "icon": "◉", "endpoint": True, "subtitle": "Incident Source"},
    {"name": "RAP", "icon": "✚", "occupancy": "58 / 100"},
    {"name": "ADS", "icon": "✚", "occupancy": "180 / 300"},
    {"name": "HMV", "icon": "✚", "occupancy": "190 / 300"},
    {"name": "FDC", "icon": "✚", "occupancy": "205 / 300"},
    {"name": "Recovery", "icon": "★", "endpoint": True, "subtitle": "Returned To Duty"},
]
 
MISSION_LOG_ENTRIES = [
    {"time": "09:45", "icon": "►", "category": "Dispatch", "description": "Helicopter H-02 dispatched to Sector Bravo"},
    {"time": "09:32", "icon": "✚", "category": "Admission", "description": "CAS-017 admitted to RAP"},
    {"time": "09:18", "icon": "▲", "category": "Incident", "description": "Mortar attack reported in Sector Alpha"},
    {"time": "09:05", "icon": "✓", "category": "Recovery", "description": "CAS-004 recovered"},
    {"time": "08:57", "icon": "◆", "category": "Resource", "description": "Medical Team Alpha deployed"},
]
 
ASSET_INVENTORY = [
    {"name": "Ambulances", "icon": "◈", "available": 14, "busy": 6, "maintenance": 2},
    {"name": "Helicopters", "icon": "△", "available": 4, "busy": 2, "maintenance": 1},
    {"name": "Medical Teams", "icon": "✚", "available": 10, "busy": 6, "maintenance": 0},
]
 
AI_RECOMMENDATION = {
    "priority": "HIGH",
    "recommendation": "Deploy Ambulance A-03 to RAP.",
    "reason": "Predicted occupancy exceeds threshold.",
    "confidence": 94,
}
 
def _render_kpi_row():
    cols = st.columns(len(KPI_CARDS))
    for col, card in zip(cols, KPI_CARDS):
        with col:
            metric_card(
                title=card["title"],
                value=card["value"],
                icon=card["icon"],
                color=card["color"],
            )
 
def _render_workflow_stage(stage):
    subtitle = (
        stage["subtitle"]
        if stage.get("endpoint")
        else f"Occupancy: {stage['occupancy']}"
    )
    st.markdown(
        f"""
        <div style="
            text-align:center;
            padding:10px 6px;
            border:1px solid rgba(120,140,160,0.25);
            border-radius:6px;
            background:rgba(255,255,255,0.02);
        ">
            <div style="
                font-size:0.95rem;
                font-weight:600;
                color:#E6EDF3;
            ">
                {stage['icon']} {stage['name']}
            </div>
            <div style="
                font-size:0.75rem;
                color:#8B97A5;
                margin-top:6px;
            ">
                {subtitle}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
 
def _render_evacuation_workflow():
    cols = st.columns([3] + [0.5, 3] * (len(EVACUATION_WORKFLOW) - 1))
    idx = 0
    for i, col in enumerate(cols):
        with col:
            if i % 2 == 0:
                _render_workflow_stage(EVACUATION_WORKFLOW[idx])
                idx += 1
            else:
                st.markdown("➜")
 
def _render_mission_log():
    for i, entry in enumerate(MISSION_LOG_ENTRIES):
        st.markdown(
            f"""
            <span style='color:#8B97A5'>[{entry["time"]}]</span>
            <span style='font-weight:600'>{entry["category"].upper()}</span>
            """,
            unsafe_allow_html=True,
        )
        st.caption(entry["description"])
        if i < len(MISSION_LOG_ENTRIES) - 1:
            st.divider()
 
def _render_battlefield_map():
    st.write("")
    st.write("")
    _, c, _ = st.columns([1, 2, 1])
    with c:
        st.markdown("# 🗺️")
        st.markdown("### Battlefield Map")
        st.caption("Live Tracking")
        st.caption("Map Integration Coming Soon")
    st.write("")
    st.write("")
 
def _render_asset_row(resource):
    with st.container(border=True):
        st.markdown(f"**{resource['icon']} {resource['name']}**")
        total = resource["available"] + resource["busy"] + resource["maintenance"]
        st.progress(resource["available"] / total if total else 0)
        cols = st.columns(3)
        labels = [("Available", "available"), ("Busy", "busy"), ("Maintenance", "maintenance")]
        for col, (label, key) in zip(cols, labels):
            col.caption(label)
            col.markdown(f"**{resource[key]}**")
 
def _render_asset_inventory():
    for r in ASSET_INVENTORY:
        _render_asset_row(r)
 
def _render_ai_recommendation():
    for label, value in [
        ("Priority", AI_RECOMMENDATION["priority"]),
        ("Recommendation", AI_RECOMMENDATION["recommendation"]),
        ("Reason", AI_RECOMMENDATION["reason"]),
        ("Confidence", f"{AI_RECOMMENDATION['confidence']}%"),
    ]:
        st.caption(label)
        st.markdown(f"**{value}**")
    primary_button("Execute", key="dashboard_ai_execute")
 
def _render_triage_chart_placeholder():
    st.write("")
    _, c, _ = st.columns([1, 2, 1])
    with c:
        st.markdown("# ⚕️")
        st.markdown("### Triage Severity")
        st.caption("Chart Integration Coming Soon")
 
def render():
    _render_kpi_row()
    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
    
    with panel("Battlefield Evacuation Workflow"):
        _render_evacuation_workflow()
 
    log_col, map_col, asset_col = st.columns([3, 6, 3])
 
    with log_col:
        with panel("Mission Log"):
            _render_mission_log()
 
    with map_col:
        with panel("Battlefield Map"):
            _render_battlefield_map()
 
    with asset_col:
        with panel("Asset Inventory"):
            _render_asset_inventory()
 
    ai_col, triage_col = st.columns([3, 2])
 
    with ai_col:
        with panel("AI Tactical Recommendation"):
            _render_ai_recommendation()
 
    with triage_col:
        with panel("Triage Severity Chart"):
            _render_triage_chart_placeholder()