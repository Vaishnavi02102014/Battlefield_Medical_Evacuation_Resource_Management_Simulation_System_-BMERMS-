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
import plotly.graph_objects as go
 
from components.metric_card import metric_card
from components.panel import panel
from services import dashboard_service
from backend.database import crud
from services import facilities_service
from services import resources_service

from components.map_adapter import get_map_data
from components.tactical_map import render_tactical_map
 
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

def _build_facility_status() -> list[dict]:
    return [
        {
            "name": facility["facility_type"],
            "full_name": facility["name"],
            "facility_code": facility["facility_code"],
            "capacity": facility["capacity"],
            "occupied": facility["occupied"],
            "waiting": facility["queue"],
            "avg_treatment": facility["avg_treatment"],
            "status": facility["status"],
        }
        for facility in facilities_service.get_facility_overview()
    ]


def _build_resource_status() -> list[dict]:
    fleet = resources_service.get_fleet_status()
    teams = resources_service.get_medical_team_status()

    return [
        {
            "name": "Ambulances",
            "icon": "🚑",
            "available": fleet["ambulances"]["available"],
            "dispatched": fleet["ambulances"]["dispatched"],
        },
        {
            "name": "Helicopters",
            "icon": "🚁",
            "available": fleet["helicopters"]["available"],
            "dispatched": fleet["helicopters"]["dispatched"],
        },
        {
            "name": "Medical Teams",
            "icon": "🧑‍⚕️",
            "available": teams["available_teams"],
            "dispatched": teams["deployed_teams"],
        },
    ]
 
def _render_battlefield_map():
    facility_status = _build_facility_status()
    resource_status = _build_resource_status()

    map_data = get_map_data(
        facility_status,
        resource_status,
        crud.get_recent_incidents(),
        crud.get_active_casualties(),
        crud.get_all_ambulances(),
        crud.get_all_helicopters(),
        crud.get_all_medical_teams(),
    )

    render_tactical_map(
        map_data,
        mode="dashboard",
    )
 
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
 

def render():
    _render_kpi_row()
    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
    
    with panel("Battlefield Evacuation Workflow"):
        _render_evacuation_workflow()
 
    map_col, asset_col = st.columns([8, 4])

    with map_col:
        with panel("Battlefield Map"):
            _render_battlefield_map()

    with asset_col:
        with panel("Asset Inventory"):
            _render_asset_inventory()
