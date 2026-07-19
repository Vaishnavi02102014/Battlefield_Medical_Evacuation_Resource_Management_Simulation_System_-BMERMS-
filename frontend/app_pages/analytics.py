"""
analytics.py

Analytics page for the Battlefield Medical Evacuation Resource
Management Simulation System (BMERMS).

The page presents operational analytics derived from the current
simulation state, combining backend data with lightweight frontend
aggregations and visualizations.

Displayed analytics include:

• KPI Summary
• Casualty Trend Analysis
• Facility Load Analysis
• Resource Utilization
• Sector Hotspots
• Triage Severity Distribution
• AI Model Performance

Data is obtained through the frontend service layer
(dashboard_service, facilities_service, resources_service and
patients_service), with a small number of direct backend queries where
an existing service abstraction does not already exist.

Time-series charts maintain rolling, session-scoped history using
st.session_state so trends remain visible while the application is
running. This history is intentionally non-persistent and is cleared
whenever the application session ends.

The module is organised into four logical layers:

1. Data collection and aggregation.
2. Plotly figure construction.
3. Streamlit rendering helpers.
4. Page composition.

The Analytics page performs no database writes and does not modify the
simulation state. It is a read-only operational reporting interface
built on the current state of the simulation.
"""

from __future__ import annotations
 
from datetime import datetime, timedelta
 
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
 
from components.metric_card import metric_card
from components.panel import panel
from services import dashboard_service
from services import facilities_service
from services import resources_service
from services import patients_service
from backend.database import crud
from backend.utils.constants import SEVERITY_LIST

# --------------------------------------------------------------------------
# CONSTANTS
# --------------------------------------------------------------------------
 
CHART_HEIGHT_PX = 280
GAUGE_HEIGHT_PX = 260
TREND_HOURS = 12
RESOURCE_HISTORY_LIMIT = 50
 
_ACCENT = {
    "primary": "#3ddc84",
    "warning": "#f2b84b",
    "danger": "#ef5959",
    "info": "#7aa7ff",
}
 
SEVERITY_ACCENT = {
    "Critical": "danger", "Serious": "warning", "Moderate": "info", "Mild": "primary",
}
 
# Category -> accent for the Casualty Trend chart's four series.
TREND_ACCENT = {
    "Incidents": "danger", "Casualties": "info", "Recoveries": "primary", "Returned To Duty": "warning",
}
 

 
def _get_kpi_metrics() -> list[dict]:
    """
    Live KPI values sourced from the existing service layer.
    """

    dashboard_stats = dashboard_service.get_kpi_summary()
    facility_stats = facilities_service.get_kpi_summary()

    occupied_beds = facility_stats.get("occupied_beds", 0)
    available_beds = facility_stats.get("available_beds", 0)

    total_beds = occupied_beds + available_beds

    occupancy_pct = (
        occupied_beds / total_beds * 100
        if total_beds
        else 0.0
    )

    avg_wait = dashboard_stats.get(
        "average_waiting_minutes",
        0.0,
    )

    return [
        {
            "title": "Active Incidents",
            "value": dashboard_stats.get("active_incidents", 0),
            "color": "danger",
        },
        {
            "title": "Total Casualties",
            "value": dashboard_stats.get("total_casualties_processed", 0),
            "color": "info",
        },
        {
            "title": "Critical Casualties",
            "value": dashboard_stats.get("critical_casualties", 0),
            "color": "danger",
        },
        {
            "title": "Avg Wait Time",
            "value": f"{avg_wait:.1f} min",
            "color": "warning",
        },
        {
            "title": "Bed Occupancy",
            "value": f"{occupancy_pct:.0f}%",
            "color": "warning",
        },
        {
            "title": "Returned To Duty",
            "value": dashboard_stats.get("returned_to_duty", 0),
            "color": "primary",
        },
    ]
  
def _get_casualty_trend() -> dict:
    """
    Live casualty trend.

    Source:
    dashboard_service.get_kpi_summary()

    Session history is maintained in
    st.session_state["analytics_casualty_history"].
    """

    stats = dashboard_service.get_kpi_summary()

    snapshot = {
        "timestamp": datetime.now(),
        "active_incidents": stats.get("active_incidents", 0),
        "total_casualties": stats.get("total_casualties_processed", 0),
        "recoveries": stats.get("recovered", 0),
        "returned_to_duty": stats.get("returned_to_duty", 0),
    }

    history = st.session_state.setdefault(
        "analytics_casualty_history",
        []
    )

    history.append(dict(snapshot))
    del history[:-TREND_HOURS]

    return {
        "hours": [
            entry["timestamp"].strftime("%H:%M")
            for entry in history
        ],
        "series": {
            "Incidents": [
                entry["active_incidents"]
                for entry in history
            ],
            "Casualties": [
                entry["total_casualties"]
                for entry in history
            ],
            "Recoveries": [
                entry["recoveries"]
                for entry in history
            ],
            "Returned To Duty": [
                entry["returned_to_duty"]
                for entry in history
            ],
        },
    }
 
 
def _get_facility_load() -> dict:
    """
    Live Facility Load data.

    Source -> facilities_service.get_facility_overview()

    occupancy_pct is computed locally from occupied/capacity.
    """

    overview = facilities_service.get_facility_overview()

    facilities = []
    occupied = []
    capacity = []
    occupancy_pct = []
    queue_length = []
    deployed_teams = []

    for facility in overview:
        facilities.append(facility["name"])
        occupied.append(facility["occupied"])
        capacity.append(facility["capacity"])

        occupancy_pct.append(
            (
                facility["occupied"] / facility["capacity"] * 100
            )
            if facility["capacity"]
            else 0.0
        )

        queue_length.append(facility["queue"])
        deployed_teams.append(facility["medical_teams"])

    return {
        "facilities": facilities,
        "occupied": occupied,
        "capacity": capacity,
        "occupancy_pct": occupancy_pct,
        "queue_length": queue_length,
        "deployed_teams": deployed_teams,
    }
 
 
def _get_resource_utilization() -> dict:
    """
    Live resource utilization snapshot.

    Sources:
    - resources_service.get_fleet_status()
    - resources_service.get_medical_team_status()
    - facilities_service.get_kpi_summary()
    """

    fleet = resources_service.get_fleet_status()
    teams = resources_service.get_medical_team_status()
    facility_kpis = facilities_service.get_kpi_summary()

    ambulances_available = fleet["ambulances"]["available"]
    ambulances_dispatched = fleet["ambulances"]["dispatched"]
    ambulances_total = ambulances_available + ambulances_dispatched

    ambulances_pct = (
        ambulances_dispatched / ambulances_total * 100
        if ambulances_total
        else 0.0
    )

    helicopters_available = fleet["helicopters"]["available"]
    helicopters_dispatched = fleet["helicopters"]["dispatched"]
    helicopters_total = helicopters_available + helicopters_dispatched

    helicopters_pct = (
        helicopters_dispatched / helicopters_total * 100
        if helicopters_total
        else 0.0
    )

    teams_available = teams["available_teams"]
    teams_deployed = teams["deployed_teams"]
    teams_total = teams_available + teams_deployed

    teams_pct = (
        teams_deployed / teams_total * 100
        if teams_total
        else 0.0
    )

    beds_occupied = facility_kpis.get("occupied_beds", 0)
    beds_available = facility_kpis.get("available_beds", 0)
    beds_total = beds_occupied + beds_available

    beds_pct = (
        beds_occupied / beds_total * 100
        if beds_total
        else 0.0
    )

    snapshot = {
        "Ambulances": ambulances_pct,
        "Helicopters": helicopters_pct,
        "Medical Teams": teams_pct,
        "Beds": beds_pct,
    }

    history = st.session_state.setdefault(
        "analytics_resource_history",
        []
    )

    history.append(dict(snapshot))
    del history[:-RESOURCE_HISTORY_LIMIT]

    return snapshot
 
 
def _get_sector_hotspots() -> list[dict]:
    """
    Live Sector Hotspots.

    Source:
        patients_service.get_all_casualties()

    Aggregation:
        - casualties = number of casualty rows
        - incidents = number of distinct incident_id values
        - severity = highest severity present in the sector
    """

    casualties = patients_service.get_all_casualties()

    severity_rank = {
        severity: index
        for index, severity in enumerate(SEVERITY_LIST)
    }

    sectors = {}

    for casualty in casualties:

        sector = casualty.get("battle_sector")

        if not sector:
            continue

        bucket = sectors.setdefault(
            sector,
            {
                "incident_ids": set(),
                "casualties": 0,
                "severity": None,
            },
        )

        bucket["casualties"] += 1

        incident_id = casualty.get("incident_id")

        if incident_id is not None:
            bucket["incident_ids"].add(incident_id)

        severity = casualty.get("severity")

        if severity in severity_rank:

            if (
                bucket["severity"] is None
                or severity_rank[severity]
                < severity_rank[bucket["severity"]]
            ):
                bucket["severity"] = severity

    rows = []

    for sector, data in sectors.items():

        rows.append(
            {
                "sector": sector,
                "incidents": len(data["incident_ids"]),
                "casualties": data["casualties"],
                "severity": data["severity"] or SEVERITY_LIST[-1],
            }
        )

    return sorted(
        rows,
        key=lambda row: row["casualties"],
        reverse=True,
    )
 
def _get_triage_distribution() -> dict:
    counts = {
        "Critical": 0,
        "Serious": 0,
        "Moderate": 0,
        "Mild": 0,
    }

    for casualty in crud.get_active_casualties():
        severity = getattr(casualty, "severity", None)

        if severity in counts:
            counts[severity] += 1

    return counts


def _build_triage_chart() -> go.Figure:
    data = _get_triage_distribution()

    figure = go.Figure(
        go.Bar(
            x=list(data.keys()),
            y=list(data.values()),
            text=list(data.values()),
            textposition="outside",
        )
    )

    figure.update_layout(
        height=CHART_HEIGHT_PX,
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="#AEBBC7",
        xaxis=dict(showgrid=False),
        yaxis=dict(
            showgrid=True,
            gridcolor="rgba(255,255,255,0.06)",
        ),
    )

    return figure


def _render_triage_panel() -> None:
    st.plotly_chart(
        _build_triage_chart(),
        use_container_width=True,
    )
 
 
def _get_ai_model_metrics():
    try:
        from backend.ai.model_loader import load_metrics

        metrics = load_metrics()

        return {
            "transfer_accuracy":
                f"{metrics['transfer_model']['accuracy']*100:.1f}%",

            "duty_accuracy":
                f"{metrics['duty_model']['accuracy']*100:.1f}%",

            "recovery_r2":
                f"{metrics['recovery_model']['r2']:.2f}",

            "recovery_mae":
                f"{metrics['recovery_model']['mae']:.1f} d",
        }

    except Exception:
        return {
            "transfer_accuracy": "Not Trained",
            "duty_accuracy": "Not Trained",
            "recovery_r2": "Not Trained",
            "recovery_mae": "Not Trained",
        }
  
# --------------------------------------------------------------------------
# CHART LAYER — pure figure builders, no Streamlit calls.
# --------------------------------------------------------------------------
 
def _build_casualty_trend_chart(data: dict) -> go.Figure:
    figure = go.Figure()
    for category, values in data["series"].items():
        color = _ACCENT[TREND_ACCENT.get(category, "info")]
        figure.add_trace(go.Scatter(
            x=data["hours"], y=values, mode="lines", name=category,
            line=dict(color=color, width=2),
        ))
    figure.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        height=CHART_HEIGHT_PX,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="#AEBBC7",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.06)"),
    )
    return figure
 
 
def _build_facility_load_chart(data: dict) -> go.Figure:
    hover_extra = list(zip(data["occupancy_pct"], data["queue_length"], data["deployed_teams"]))
    figure = make_subplots(specs=[[{"secondary_y": True}]])
    figure.add_trace(
        go.Bar(
            x=data["facilities"], y=data["occupied"], name="Occupied", marker_color="#7aa7ff",
            customdata=hover_extra,
            hovertemplate=(
                "Occupied: %{y}<br>Occupancy: %{customdata[0]}%"
                "<br>Queue: %{customdata[1]}<br>Deployed Teams: %{customdata[2]}<extra></extra>"
            ),
        ),
        secondary_y=False,
    )
    figure.add_trace(
        go.Bar(x=data["facilities"], y=data["capacity"], name="Capacity", marker_color="rgba(122,167,255,0.25)"),
        secondary_y=False,
    )
    figure.add_trace(
        go.Scatter(x=data["facilities"], y=data["occupancy_pct"], name="Occupancy %",
                    mode="lines+markers", line=dict(color="#f2b84b", width=2)),
        secondary_y=True,
    )
    figure.update_layout(
        barmode="group",
        margin=dict(l=10, r=10, t=10, b=10),
        height=CHART_HEIGHT_PX,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="#AEBBC7",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    figure.update_yaxes(showgrid=True, gridcolor="rgba(255,255,255,0.06)", secondary_y=False)
    figure.update_yaxes(showgrid=False, range=[0, 100], ticksuffix="%", secondary_y=True)
    return figure
 
 
def _build_resource_utilization_gauges(snapshot: dict) -> go.Figure:
    labels = ["Ambulances", "Helicopters", "Medical Teams", "Beds"]
    domains = [(0.0, 0.22), (0.26, 0.48), (0.52, 0.74), (0.78, 1.0)]
    figure = go.Figure()
    for label, (x0, x1) in zip(labels, domains):
        value = snapshot[label]
        color = _ACCENT["danger"] if value >= 85 else _ACCENT["warning"] if value >= 65 else _ACCENT["primary"]
        figure.add_trace(go.Indicator(
            mode="gauge+number",
            value=value,
            title={"text": label, "font": {"size": 12, "color": "#AEBBC7"}},
            number={"suffix": "%", "font": {"size": 20, "color": "#F4F6F8"}},
            gauge={
                "axis": {"range": [0, 100], "tickcolor": "#AEBBC7"},
                "bar": {"color": color},
                "bgcolor": "rgba(255,255,255,0.05)",
                "borderwidth": 0,
            },
            domain={"x": [x0, x1], "y": [0, 1]},
        ))
    figure.update_layout(
        margin=dict(l=10, r=10, t=30, b=10),
        height=GAUGE_HEIGHT_PX,
        paper_bgcolor="rgba(0,0,0,0)",
        font_color="#AEBBC7",
    )
    return figure
 
 
def _build_sector_hotspot_chart(rows: list[dict]) -> go.Figure:
    rows_sorted = sorted(rows, key=lambda r: r["casualties"])
    sectors = [r["sector"] for r in rows_sorted]
    values = [r["casualties"] for r in rows_sorted]
    figure = go.Figure(go.Bar(
        x=values, y=sectors, orientation="h",
        marker_color="#ef5959",
        text=values, textposition="outside",
    ))
    figure.update_layout(
        margin=dict(l=10, r=20, t=10, b=10),
        height=CHART_HEIGHT_PX,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="#AEBBC7",
        xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.06)"),
        yaxis=dict(showgrid=False),
    )
    return figure
 
 
_FORECAST_METRIC_ACCENT = {
    "Bed Availability": "primary",
    "Recoveries": "primary",
}
 
_FORECAST_CARD_TITLES = {
    "Bed Availability": "Bed Availability",
    "Recoveries": "Predicted Recoveries",
}
 
 
# def _build_forecast_cards(data: dict) -> list[dict]:
#     """Reduces each metric's actual/projected series to a single compact
#     forecast card — next-tick projected value, colored by metric."""
#     cards = []
#     for metric, series in data.items():
#         cards.append({
#             "title": _FORECAST_CARD_TITLES.get(metric, metric),
#             "value": series["projected"][0],
#             "color": _FORECAST_METRIC_ACCENT.get(metric, "info"),
#         })
#     return cards
 
 
# --------------------------------------------------------------------------
# RENDER LAYER
# --------------------------------------------------------------------------
 
def _render_kpi_row() -> None:
    cards = _get_kpi_metrics()
    columns = st.columns(len(cards))
    for column, card in zip(columns, cards):
        with column:
            metric_card(title=card["title"], value=card["value"], color=card["color"])
 
 
def _render_casualty_trend_panel() -> None:
    st.plotly_chart(
        _build_casualty_trend_chart(
            _get_casualty_trend()
        ),
        use_container_width=True,
    )
 
def _render_facility_load_panel() -> None:
    data = _get_facility_load()
    st.plotly_chart(_build_facility_load_chart(data), use_container_width=True)
    columns = st.columns(len(data["facilities"]))
    for column, facility, queue, teams in zip(columns, data["facilities"], data["queue_length"], data["deployed_teams"]):
        with column:
            st.caption(f"{facility} · Queue: {queue} · Teams: {teams}")
 
 
def _render_resource_utilization_panel() -> None:
    snapshot = _get_resource_utilization()
    st.plotly_chart(_build_resource_utilization_gauges(snapshot), use_container_width=True)
 
 
# def _render_forecast_panel() -> None:
#     cards = _build_forecast_cards(_get_forecast_data())
#     columns = st.columns(len(cards))
#     for column, card in zip(columns, cards):
#         with column:
#             metric_card(title=card["title"], value=card["value"], color=card["color"])
#     st.caption("Statistical trend projection — not a predictive model.")
 
 
def _render_sector_hotspot_panel() -> None:
    st.plotly_chart(_build_sector_hotspot_chart(_get_sector_hotspots()), use_container_width=True)
 
def _render_ai_model_performance_panel() -> None:
    metrics = _get_ai_model_metrics()
    cards = [
        {
            "title": "Transfer Accuracy",
            "value": metrics["transfer_accuracy"],
            "color": "info",
        },
        {
            "title": "Duty Accuracy",
            "value": metrics["duty_accuracy"],
            "color": "info",
        },
        {
            "title": "Recovery R²",
            "value": metrics["recovery_r2"],
            "color": "primary",
        },
        {
            "title": "Recovery MAE",
            "value": metrics["recovery_mae"],
            "color": "warning",
        },
    ]
    columns = st.columns(len(cards))
    for column, card in zip(columns, cards):
        with column:
            metric_card(title=card["title"], value=card["value"], color=card["color"])
 
 
def render() -> None:
    """Render the Analytics page: KPIs, trends, forecast, and AI panels."""
    _render_kpi_row()
 
    st.markdown(
        "<div style='height:18px;'></div>",
        unsafe_allow_html=True,
    )

    top_left, top_right = st.columns([3, 2])

    with top_left:
        with panel("Casualty Trend Analysis"):
            _render_casualty_trend_panel()

        st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)

        with panel("Facility Load Analysis"):
            _render_facility_load_panel()

        st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)

        with panel("Sector Hotspots"):
            _render_sector_hotspot_panel()

    with top_right:

        with panel("Resource Utilization"):
            _render_resource_utilization_panel()

        st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)

        with panel("Triage Severity Distribution"):
            _render_triage_panel()

        st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)

        with panel("AI Model Performance"):
            _render_ai_model_performance_panel()