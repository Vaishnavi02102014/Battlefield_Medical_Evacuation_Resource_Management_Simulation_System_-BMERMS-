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
from services import dashboard_service
 
KPI_CARD_META = [
    ("total_casualties_processed", "Total Casualties Processed", "■", "info"),
    ("in_treatment", "In Treatment", "■", "warning"),
    ("waiting_in_queue", "Waiting in Queue", "■", "warning"),
    ("recovered", "Recovered", "■", "primary"),
    ("returned_to_duty", "Returned to Duty", "■", "primary"),
    ("active_incidents", "Active Incidents", "■", "danger"),
]
 
WORKFLOW_START_STAGE = {
    "name": "Battlefield",
    "icon": "◉",
    "endpoint": True,
    "subtitle": "Incident Source",
}

WORKFLOW_END_STAGE = {
    "name": "Recovery",
    "icon": "★",
    "endpoint": True,
    "subtitle": "Returned To Duty",
}

FACILITY_STAGE_ICON = "✚"
 
AI_RECOMMENDATION = {
    "priority": "HIGH",
    "recommendation": "Deploy Ambulance A-03 to RAP.",
    "reason": "Predicted occupancy exceeds threshold.",
    "confidence": 94,
}
 
def _render_kpi_row():
    summary = dashboard_service.get_kpi_summary()
    cols = st.columns(len(KPI_CARD_META))

    for col, (key, title, icon, color) in zip(cols, KPI_CARD_META):
        with col:
            metric_card(
                title=title,
                value=summary.get(key, 0),
                icon=icon,
                color=color,
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
    facility_stages = dashboard_service.get_evacuation_workflow()

    stages = [WORKFLOW_START_STAGE]

    for facility_stage in facility_stages:
        stages.append(
            {
                "name": facility_stage["name"],
                "icon": FACILITY_STAGE_ICON,
                "occupancy": facility_stage["occupancy_label"],
            }
        )

    stages.append(WORKFLOW_END_STAGE)

    cols = st.columns([3] + [0.5, 3] * (len(stages) - 1))

    idx = 0
    for i, col in enumerate(cols):
        with col:
            if i % 2 == 0:
                _render_workflow_stage(stages[idx])
                idx += 1
            else:
                st.markdown("➜")
 
def _render_mission_log():
    entries = dashboard_service.get_mission_log(limit=5)

    if not entries:
        st.caption("No recent activity.")
        return

    for i, entry in enumerate(entries):
        st.markdown(
            f"""
            <span style='color:#8B97A5'>[{entry["time"]}]</span>
            <span style='font-weight:600'>{entry["category"].upper()}</span>
            """,
            unsafe_allow_html=True,
        )

        st.caption(entry["description"])

        if i < len(entries) - 1:
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
    for r in dashboard_service.get_asset_inventory():
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