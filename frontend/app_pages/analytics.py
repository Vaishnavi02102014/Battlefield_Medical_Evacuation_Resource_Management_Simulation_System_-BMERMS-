"""
analytics.py
 
Analytics page — Phase 2. Command-intelligence / decision-support surface:
trends, forecasts, resource utilization, and AI-assisted panels.
 
Deliberately does NOT duplicate:
    Dashboard  -> operational snapshot
    Facilities -> per-facility console
    Resources  -> fleet inventory management
    Patients   -> casualty registry / history
 
BACKEND STATUS
    Live data (KPIs, current facility/resource state) has real crud.py
    sources — see the TODO Integration comment on each helper below.
    Trend/history data has no persistence yet, so every helper here
    returns placeholder data shaped like its eventual real source, so a
    later phase can swap function bodies only, with zero caller/UI changes.
 
    AI panels (AI-Assisted Decision Support, AI Model Performance) have no
    backend today. Integration points are reserved for:
        backend/ai/predictor.py
        backend/ai/model.pkl
        backend/ai/metrics.json
    No model loading, training, or predictor code is implemented here.
 
This file only. No backend, database, or other page changes.
"""
 
from __future__ import annotations
 
from datetime import datetime, timedelta
 
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
 
from components.metric_card import metric_card
from components.panel import panel
 
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
 
 
# --------------------------------------------------------------------------
# DATA LAYER
# Placeholder data only. Each function is shaped to match its eventual real
# source so Phase 3 wiring replaces function bodies, not callers.
# --------------------------------------------------------------------------
 
def _get_kpi_metrics() -> list[dict]:
    """
    # TODO Integration:
    # Source -> crud.get_dashboard_stats() + crud.get_resource_availability_counts()
    """
    return [
        {"title": "Total Incidents", "value": 46, "color": "danger"},
        {"title": "Total Casualties", "value": 1250, "color": "info"},
        {"title": "Critical Casualties", "value": 138, "color": "danger"},
        {"title": "Avg Wait Time", "value": "...", "color": "warning"},
        {"title": "Bed Occupancy", "value": "72%", "color": "warning"},
        {"title": "Returned To Duty", "value": 210, "color": "primary"},
    ]
  
def _get_casualty_trend() -> dict:
    """
    # TODO:
    # Replace this placeholder implementation after analytics history persistence
    # (st.session_state["analytics_history"] or Analytics_Snapshots table)
    # is implemented in the backend.
    """
    hours = [(datetime.now() - timedelta(hours=h)).strftime("%H:00") for h in range(TREND_HOURS, 0, -1)]
    return {
        "hours": hours,
        "series": {
            "Incidents":        [1, 2, 1, 3, 2, 4, 3, 5, 4, 6, 5, 7],
            "Casualties":       [4, 7, 5, 10, 8, 13, 11, 16, 14, 19, 17, 22],
            "Recoveries":       [0, 1, 2, 2, 3, 4, 5, 6, 7, 8, 9, 10],
            "Returned To Duty": [0, 0, 1, 1, 2, 2, 3, 4, 4, 5, 6, 7],
        },
    }
 
 
def _get_facility_load() -> dict:
    """
    # TODO Integration:
    # Source -> crud.get_all_facilities() for current load. Historical
    # trend from Treatments.treatment_start grouped by facility_id
    # (requires one additive, read-only crud function per the Phase 1
    # roadmap — no schema change).
    """
    facilities = ["RAP", "ADS", "HMV", "FDC"]
    return {
        "facilities": facilities,
        "occupied": [58, 180, 190, 205],
        "capacity": [100, 300, 300, 300],
        "occupancy_pct": [58, 60, 63, 68],
        "queue_length": [4, 11, 9, 14],
        "deployed_teams": [1, 3, 2, 4],
    }
 
 
def _get_resource_utilization() -> dict:
    """
    # TODO Integration:
    # Source -> crud.get_resource_availability_counts(), snapshotted each
    # rerun into st.session_state["analytics_resource_history"] (no DB
    # write — same session-state-only pattern Mission Log already uses).
    """
    snapshot = {
        "Ambulances": 65,
        "Helicopters": 50,
        "Medical Teams": 60,
        "Beds": 72,
    }
    history = st.session_state.setdefault("analytics_resource_history", [])
    history.append(dict(snapshot))
    del history[:-RESOURCE_HISTORY_LIMIT]
    return snapshot
 
 
def _get_sector_hotspots() -> list[dict]:
    """
    # TODO Integration:
    # Source -> Casualty.battle_sector / Incident.battle_sector, grouped
    # via a page-local aggregation helper. No new crud function required.
    """
    rows = [
        {"sector": "Bravo", "incidents": 12, "casualties": 52, "severity": "Critical"},
        {"sector": "Alpha", "incidents": 9, "casualties": 41, "severity": "Serious"},
        {"sector": "Charlie", "incidents": 7, "casualties": 33, "severity": "Serious"},
        {"sector": "Delta", "incidents": 5, "casualties": 22, "severity": "Moderate"},
        {"sector": "Echo", "incidents": 2, "casualties": 9, "severity": "Mild"},
    ]
    return sorted(rows, key=lambda r: r["casualties"], reverse=True)
 
 
# def _get_forecast_data() -> dict:
#     """
#     # TODO Integration:
#     # Source -> statistical projection (moving average / linear trend)
#     # computed over _get_casualty_trend()'s bucketed history. This is
#     # explicitly a trend projection, not a predictive model — reflected
#     # in the panel title "Operational Forecast".
#     """
#     forecast = {
#         "Bed Availability": {
#             "actual": [80, 76, 74, 70, 68, 64, 62, 58],
#             "projected": [55, 52, 50, 47],
#         },
#         "Recoveries": {
#             "actual": [0, 1, 2, 2, 3, 4, 5, 6],
#             "projected": [7, 8, 8, 9],
#         },
#     }
#     return forecast
 
 
def _get_ai_recommendations() -> list[dict]:
    try:
        from backend.ai.recommendation_engine import generate_recommendations

        simulation_state = {
            "occupancy_rate": 72,
            "queue_length": 9,
            "critical_casualties": 4,
            "available_medical_teams": 6,
            "available_helicopters": 2,
        }

        recommendation = generate_recommendations(simulation_state)

        confidence = recommendation.get("confidence", 0)

        if confidence >= 80:
            priority = "HIGH"
        elif confidence >= 60:
            priority = "MEDIUM"
        else:
            priority = "LOW"

        return [{
            "priority": priority,
            "recommendation": recommendation["recommendation"],
            "reason": recommendation["reason"],
            "confidence": int(confidence),
        }]

    except Exception:
        return [
            {
                "priority": "LOW",
                "recommendation": "AI recommendation unavailable.",
                "reason": "Simulation state unavailable.",
                "confidence": 0,
            }
        ]
 
 
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
 
 
def _get_insight_entries() -> list[dict]:
    """
    # TODO Integration:
    # Source -> st.session_state mission log entries (mission_log.py),
    # filtered to CATEGORY_RESOURCE / CATEGORY_QUEUE / CATEGORY_ADMISSION.
    """
    return [
        {
            "time": "09:45", "category": "Resource",
            "message": "Medical Team Bravo dispatched to RAP (queue surge)",
            "details": "Queue length exceeded surge threshold (10) at RAP; nearest available team dispatched.",
        },
        {
            "time": "09:32", "category": "Admission",
            "message": "CAS-017 admitted to RAP, bed 14",
            "details": "Priority P1, Critical severity. Assigned on arrival after transit from Sector Bravo.",
        },
        {
            "time": "09:05", "category": "Queue",
            "message": "CAS-004 queued at ADS (no beds available)",
            "details": "ADS at full capacity; casualty placed in priority-ordered waiting queue.",
        },
    ]
 
 
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
 
 
_PRIORITY_COLOR = {"HIGH": "danger", "MEDIUM": "warning", "LOW": "info"}
 
 
def _render_ai_decision_support_panel() -> None:
    recommendations = _get_ai_recommendations()[:4]
    for i, rec in enumerate(recommendations):
        color = _ACCENT[_PRIORITY_COLOR.get(rec["priority"], "info")]
        st.markdown(
            f'<span style="font-size:0.68rem;font-weight:700;letter-spacing:0.06em;'
            f'color:{color};">{rec["priority"]}</span>',
            unsafe_allow_html=True,
        )
        st.markdown(f"**{rec['recommendation']}**")
        st.caption(rec["reason"])
        st.progress(rec["confidence"] / 100)
        st.caption(f"{rec['confidence']}% confidence")
        if i < len(recommendations) - 1:
            st.divider()
 
 
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
 
 
def _render_insights_timeline_panel() -> None:
    for entry in _get_insight_entries():
        with st.expander(f"{entry['time']} · {entry['category']}"):
            st.caption(entry["message"])
            st.caption(entry["details"])
 
 
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

        with panel("AI Insights Timeline"):
            _render_insights_timeline_panel()


    with top_right:
        with panel("AI-Assisted Decision Support"):
            _render_ai_decision_support_panel()


    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)

    bottom_left, bottom_right = st.columns([1, 1])

    with bottom_left:
        with panel("Resource Utilization"):
            _render_resource_utilization_panel()

    with bottom_right:
        with panel("AI Model Performance"):
            _render_ai_model_performance_panel()