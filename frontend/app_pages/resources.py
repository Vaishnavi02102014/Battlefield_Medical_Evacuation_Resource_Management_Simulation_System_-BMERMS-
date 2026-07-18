
"""
resources.py
 
Resources page — final UI refinement pass before backend integration.
 
    Row 1 — 6 KPI cards
    Row 2 — Fleet Status (3) | Medical Team Status (2)
    Row 3 — Resource Allocation (2) | Dispatch Timeline (2) | Resource Availability (1)
 
Data access is fully separated from rendering: every panel reads only
from the helper functions below. Each returns hardcoded mock data today,
but is named and shaped so a later phase can swap the body for a real
crud.get_...()/resource_manager.get_...() call with zero UI changes.
No backend imports yet — this remains mock data only.
 
Panel heights are reserved via a nested st.container(height=...) inside
each `with panel(...):` block (panel.py itself is not modified). Fleet
Status and Medical Team Status use compact tactical rows/progress bars
instead of metric cards, per the command-console design direction —
metric_card is still used only for the top KPI strip.
"""
 
import streamlit as st
import plotly.graph_objects as go
 
from components.metric_card import metric_card
from components.panel import panel
from services.resources_service import (
    get_fleet_status,
    get_medical_team_status,
    get_resource_summary,
    get_dispatch_history,
    get_resource_availability,
)
 
FLEET_PANEL_HEIGHT_PX = 180
TEAM_PANEL_HEIGHT_PX = 180
CHART_PANEL_HEIGHT_PX = 300

# --------------------------------------------------------------------------
# RENDERING
# --------------------------------------------------------------------------
 
def _render_kpi_row() -> None:
    """Row 1 — 6 KPI cards, derived from get_resource_summary()."""
    summary = get_resource_summary()
    cards = [
        {
            "title": "Total Ambulances",
            "value": summary["total_ambulances"],
            "color": "info",
        },
        {
            "title": "Total Helicopters",
            "value": summary["total_helicopters"],
            "color": "info",
        },
        {
            "title": "Medical Teams",
            "value": summary["total_medical_teams"],
            "color": "info",
        },
        {
            "title": "Deployed Teams",
            "value": summary["deployed_medical_teams"],
            "color": "primary",
        },
        {
            "title": "Active Dispatches",
            "value": (
                get_fleet_status()["ambulances"]["dispatched"]
                + get_fleet_status()["helicopters"]["dispatched"]
                + summary["deployed_medical_teams"]
            ),
            "color": "primary",
        },
        {
            "title": "Resource Utilization %",
            "value": f"{summary['resource_utilization_percent']}%",
            "color": "warning",
        },
    ]
    columns = st.columns(len(cards))
    for column, card in zip(columns, cards):
        with column:
            metric_card(title=card["title"], value=card["value"], color=card["color"])
 
 
def _render_tactical_bar(percent: float, color: str) -> None:
    """Single-row tactical utilization/availability bar — no card, no chrome."""
    pct = max(0, min(100, round(percent * 100)))
    st.markdown(
        f'<div style="width:100%;height:6px;background:rgba(255,255,255,0.08);'
        f'border-radius:2px;margin:4px 0 8px 0;overflow:hidden;">'
        f'<div style="width:{pct}%;height:100%;background:{color};"></div>'
        f'</div>',
        unsafe_allow_html=True,
    )
 
 
def _render_fleet_status() -> None:
    """Compact fleet command sections — utilization bar + single summary line per vehicle type."""
    fleet = get_fleet_status()
    sections = [
        ("AMBULANCE FLEET", fleet["ambulances"], "#3ddc84"),
        ("HELICOPTER FLEET", fleet["helicopters"], "#f2b84b"),
    ]
    with st.container(height=FLEET_PANEL_HEIGHT_PX, border=False):
        for label, data, color in sections:
            total = data["available"] + data["dispatched"]
            utilization = data["dispatched"] / total if total else 0
            st.markdown(
                f'<div style="font-size:0.72rem;font-weight:700;letter-spacing:0.08em;'
                f'color:#F4F6F8;font-family:monospace;margin-bottom:2px;">{label}</div>',
                unsafe_allow_html=True,
            )
            _render_tactical_bar(utilization, color)
            st.markdown(
                f"""
                <div style="
                    font-size:0.75rem;
                    color:#AEBBC7;
                    font-family:monospace;
                    margin-bottom:14px;
                ">
                    {round(utilization * 100)}% DEPLOYED
                </div>
                """,
                unsafe_allow_html=True,
            )
 
 
def _render_label_value_row(label: str, value: str) -> None:
    """One compact 'label ... value' row — plain text, no cards. Inline style only, no injected stylesheet."""
    st.markdown(
        f'<div style="display:flex;justify-content:space-between;align-items:center;'
        f'padding:6px 2px;border-bottom:1px dashed rgba(255,255,255,0.08);">'
        f'<span style="font-size:0.8rem;color:#AEBBC7;">{label}</span>'
        f'<span style="font-size:0.85rem;font-weight:700;color:#F4F6F8;">{value}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
 
 
def _render_medical_team_status() -> None:
    """Tactical operational summary — ready/deployed/facilities figures plus deployment rate."""
    teams = get_medical_team_status()
    total_teams = teams["available_teams"] + teams["deployed_teams"]
    deployment_rate = round((teams["deployed_teams"] / total_teams) * 100) if total_teams else 0
 
    stats = [
        ("READY", teams["available_teams"], "#3ddc84"),
        ("DEPLOYED", teams["deployed_teams"], "#7aa7ff"),
        ("FACILITIES", teams["facilities_supported"], "#f2b84b"),
    ]
 
    with st.container(height=TEAM_PANEL_HEIGHT_PX, border=False):
        columns = st.columns(3)
        for column, (label, value, color) in zip(columns, stats):
            with column:
                st.markdown(
                    f'<div style="text-align:center;padding:6px 0;">'
                    f'<div style="font-size:1.6rem;font-weight:800;color:{color};'
                    f'font-family:monospace;line-height:1.1;">{value}</div>'
                    f'<div style="font-size:0.65rem;letter-spacing:0.08em;color:#AEBBC7;'
                    f'font-family:monospace;margin-top:2px;">{label}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
 
        st.markdown(
            '<div style="height:1px;background:rgba(255,255,255,0.08);margin:10px 0;"></div>',
            unsafe_allow_html=True,
        )
 
        st.markdown(
            f'<div style="font-size:0.72rem;font-weight:700;letter-spacing:0.08em;'
            f'color:#F4F6F8;font-family:monospace;margin-bottom:2px;">DEPLOYMENT RATE</div>',
            unsafe_allow_html=True,
        )
        _render_tactical_bar(deployment_rate / 100, "#7aa7ff")
        st.markdown(
            f'<div style="font-size:0.75rem;color:#AEBBC7;font-family:monospace;">'
            f'{deployment_rate}% OF TEAMS CURRENTLY DEPLOYED</div>',
            unsafe_allow_html=True,
        )
 
 
def _render_resource_allocation() -> None:
    """Donut chart — currently allocated/deployed resources (dispatched ambulances, dispatched helicopters, deployed medical teams)."""
    fleet = get_fleet_status()
    teams = get_medical_team_status()
    labels = ["Ambulances", "Helicopters", "Medical Teams"]
    values = [fleet["ambulances"]["dispatched"], fleet["helicopters"]["dispatched"], teams["deployed_teams"]]
    colors = ["#3ddc84", "#f2b84b", "#7aa7ff"]
 
    with st.container(height=CHART_PANEL_HEIGHT_PX, border=False):
        if sum(values) == 0:
            st.caption("No resources currently deployed.")
            return
        figure = go.Figure(data=[go.Pie(
            labels=labels, values=values, hole=0.65,
            marker=dict(colors=colors, line=dict(color="#0B1522", width=2)),
            textinfo="label+value", textfont=dict(size=11, color="#F4F6F8"),
            sort=False,
        )])
        figure.update_layout(
            margin=dict(l=10, r=10, t=10, b=10),
            height=260,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            showlegend=False,
        )
        st.plotly_chart(figure, use_container_width=True)
 
def _render_resource_availability() -> None:
    """Operational readiness at a glance — availability bar + 'X OF Y AVAILABLE' per resource pool."""
    colors = {
        "Ambulances": "#3ddc84",
        "Helicopters": "#f2b84b",
        "Medical Teams": "#7aa7ff",
    }
    with st.container(height=CHART_PANEL_HEIGHT_PX, border=False):
        for entry in get_resource_availability():
            label = entry["label"]
            available = entry["available"]
            total = entry["total"]
            ratio = available / total if total else 0
            color = colors.get(label, "#7aa7ff")
 
            st.markdown(
                f'<div style="font-size:0.72rem;font-weight:700;letter-spacing:0.08em;'
                f'color:#F4F6F8;font-family:monospace;margin-bottom:2px;">{label.upper()}</div>',
                unsafe_allow_html=True,
            )

            _render_tactical_bar(ratio, color)

            st.markdown(
                f'<div style="font-size:0.72rem;color:#AEBBC7;'
                f'font-family:monospace;">'
                f'{round(ratio * 100)}% AVAILABLE'
                f'</div>',
                unsafe_allow_html=True,
            )

            st.markdown(
                f'<div style="font-size:0.75rem;color:#AEBBC7;'
                f'font-family:monospace;margin-bottom:14px;">'
                f'{available} OF {total} AVAILABLE'
                f'</div>',
                unsafe_allow_html=True,
            )
 
 
def render() -> None:
    """Render the Resources page."""
    _render_kpi_row()
    st.markdown(
        "<div style='height:16px'></div>",
        unsafe_allow_html=True,
    )
    fleet_col, team_col = st.columns([3, 2])
    with fleet_col:
        with panel("Fleet Status"):
            _render_fleet_status()
    with team_col:
        with panel("Medical Team Status"):
            _render_medical_team_status()
 
    left_margin, allocation_col, availability_col, right_margin = st.columns([0.15, 1.5, 1, 1.35])

    with allocation_col:
        with panel("Resource Allocation"):
            _render_resource_allocation()

    with availability_col:
        with panel("Resource Availability"):
            _render_resource_availability()