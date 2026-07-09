"""
facilities.py
 
Facilities page — refined Phase 1: KPI summary, Operational Facility
Overview table (search/filter/sort, fixed height, empty state, facility
count in the panel toolbar), and a command-console-style Facility Detail
panel grouped into Status / Capacity / Operations.
 
All data comes from data/facilities_mock_data.py (the single centralized
mock provider, unchanged) — nothing is hardcoded here. Search/filter/sort
are real, functional, client-side operations over that in-memory mock
data (no backend calls).
"""
 
from __future__ import annotations
import pandas as pd
import streamlit as st
 
from components.metric_card import metric_card
from components.panel import panel
from services.facilities_service import (
    get_facility_overview,
    get_facility_detail,
    get_kpi_summary,
)
 
OVERVIEW_TABLE_HEIGHT_PX = 240
 
# Semantic colors kept in one place so the console badges/typography and
# the KPI/occupancy logic stay visually consistent.
_ACCENT = {
    "primary": "#3ddc84",
    "warning": "#f2b84b",
    "danger": "#ef5959",
    "info": "#7aa7ff",
}
 
 
def _occupancy_color(occupancy_pct: int) -> str:
    """Semantic occupancy color: green <70%, amber 70-90%, red >90%."""
    if occupancy_pct < 70:
        return "primary"
    if occupancy_pct <= 90:
        return "warning"
    return "danger"
 
 
def _inject_console_css() -> None:
    """Compact, high-density, command-console styling. Presentation only —
    no new data, no new panels, no change to component usage."""
    st.markdown(
        """
        <style>
        /* ---- Overview table: tighter, disciplined, scan-friendly ---- */
        div[data-testid="stDataFrame"] {
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 4px;
        }
        div[data-testid="stDataFrame"] table {
            font-size: 0.83rem;
            letter-spacing: 0.01em;
        }
        div[data-testid="stDataFrame"] thead th {
            font-size: 0.68rem !important;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            color: rgba(255,255,255,0.55) !important;
            font-weight: 600 !important;
        }
        div[data-testid="stDataFrame"] [aria-selected="true"] {
            background-color: rgba(61,220,132,0.12) !important;
            box-shadow: inset 3px 0 0 #3ddc84;
        }
 
        /* ---- Facility Detail: bordered operational console blocks ---- */
        .console-wrap { padding-top: 2px; }
        .console-strip {
            display: flex;
            align-items: baseline;
            justify-content: space-between;
            padding-bottom: 10px;
            margin-bottom: 12px;
            border-bottom: 1px solid rgba(255,255,255,0.10);
        }
        .console-name { font-size: 1.25rem; font-weight: 800; letter-spacing: 0.01em; }
        .console-type { font-size: 0.70rem; letter-spacing:0.05em; text-transform:uppercase; color: rgba(255,255,255,0.50); margin-left: 8px; }
        .console-status-badge {
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.06em;
            text-transform: uppercase;
            padding: 3px 10px;
            border-radius: 3px;
            border: 1px solid currentColor;
            white-space: nowrap;
        }
 
        .console-blocks {
            display: flex;
            gap: 14px;
            align-items: stretch;
            flex-wrap: wrap;
        }
        .console-block {
            background: rgba(255,255,255,0.01);
            border: 1px solid rgba(255,255,255,0.05);
            border-radius: 6px;
            padding: 16px 18px;
            flex: 1 1 0;
            min-width: 150px;
        }
        .console-block-title {
            font-size: 0.65rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.10em;
            color: rgba(255,255,255,0.42);
            margin-bottom: 10px;
        }
        .console-row {
            display: flex;
            justify-content: space-between;
            align-items: baseline;
            padding: 4px 0;
            border-bottom: 1px dashed rgba(255,255,255,0.06);
        }
        .console-row:last-child { border-bottom: none; }
        .console-row-label {
            font-size: 0.71rem;
            color: rgba(255,255,255,0.55);
            letter-spacing: 0.01em;
        }
        .console-row-value {
            font-size: 0.90rem;
            font-weight: 650;
            font-variant-numeric: tabular-nums;
            text-align: right;
        }
 
        /* Occupancy block — the prominent operational metric */
        .console-block-occupancy { flex: 1.15 1 0; text-align: center; }
        .console-occ-value {
            font-size: 2.4rem;
            font-weight: 800;
            line-height: 1.1;
            font-variant-numeric: tabular-nums;
        }
        .console-occ-caption {
            font-size: 0.68rem;
            color: rgba(255,255,255,0.42);
            margin-top: 2px;
            letter-spacing: 0.03em;
        }
        .console-occ-bar {
            width: 100%;
            height: 12px;
            border-radius: 5px;
            background: rgba(255,255,255,0.08);
            margin-top: 10px;
            overflow: hidden;
        }
        .console-occ-fill { height: 100%; border-radius: 5px; }
 
        /* Estimated availability block */
        .console-block-eta { flex: 1.1 1 0; text-align: center; }
        .console-eta-value {
            font-size: 1.35rem;
            font-weight: 800;
            font-variant-numeric: tabular-nums;
            line-height: 1.15;
        }
        .console-eta-note {
            font-size: 0.66rem;
            color: rgba(255,255,255,0.38);
            margin-top: 6px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
 
 
def _render_kpi_row() -> None:
    """Row 1 — 6 KPI cards, derived from get_kpi_summary(). No fabricated trend/deltas."""
    summary = get_kpi_summary()
    cards = [
        {"title": "Total Facilities", "value": summary["total_facilities"], "color": "info"},
        {"title": "Operational", "value": summary["operational_facilities"], "color": "primary"},
        {"title": "Heavy Load", "value": summary["heavy_load_facilities"], "color": "warning"},
        {"title": "Available Beds", "value": summary["available_beds"], "color": "primary"},
        {"title": "Occupied Beds", "value": summary["occupied_beds"], "color": "warning"},
        {"title": "Waiting Casualties", "value": summary["waiting_casualties"], "color": "danger"},
    ]
    columns = st.columns(len(cards))
    for column, card in zip(columns, cards):
        with column:
            metric_card(title=card["title"], value=card["value"], color=card["color"])
 
 
def _facility_overview_dataframe(search_text: str, status_filter: str) -> pd.DataFrame:
    """Builds the display-ready DataFrame for the overview table from the mock provider, filtered/searched client-side."""
    rows = get_facility_overview()
    if status_filter != "All":
        rows = [r for r in rows if r["status"] == status_filter]
    if search_text:
        needle = search_text.strip().lower()
        rows = [r for r in rows if needle in r["name"].lower() or needle in r["facility_type"].lower()]
 
    records = []
    for r in rows:
        available = r["capacity"] - r["occupied"]
        occupancy_pct = round((r["occupied"] / r["capacity"]) * 100) if r["capacity"] else 0
        records.append({
            "Facility": r["name"],
            "Total Beds": r["capacity"],
            "Occupied": r["occupied"],
            "Available": available,
            "Queue": r["queue"],
            "Avg. Treatment": r["avg_treatment"],
            "Teams": r["medical_teams"],
            "Status": r["status"],
            "Occupancy %": occupancy_pct,
        })
    return pd.DataFrame.from_records(records)
 
 
def _style_overview(dataframe: pd.DataFrame):
    """Adds status-aware color to the Status column only; all other columns
    render exactly as before. Same DataFrame, same st.dataframe call —
    presentation-only."""
    hex_by_status = {
        "Operational": _ACCENT["primary"],
        "Busy": _ACCENT["info"],
        "High Load": _ACCENT["warning"],
        "Critical": _ACCENT["danger"],
    }
 
    def _status_style(value: str) -> str:
        color = hex_by_status.get(value, "#7aa7ff")
        return f"color: {color}; font-weight: 700;"
 
    return dataframe.style.map(_status_style, subset=["Status"])
 
 
def _render_facility_overview() -> str | None:
    """Operational Facility Overview: search/filter, fixed-height sortable table, empty state. Returns the selected facility name, if any."""
    search_col, filter_col = st.columns([3, 1])
    with search_col:
        search_text = st.text_input(
            "Search facilities", key="facilities_search", placeholder="Search facility name or type...",
            label_visibility="collapsed",
        )
    with filter_col:
        status_filter = st.selectbox(
            "Filter by status", options=["All", "Operational", "Busy", "High Load", "Critical"],
            key="facilities_status_filter", label_visibility="collapsed",
        )
 
    dataframe = _facility_overview_dataframe(search_text, status_filter)
 
    if dataframe.empty:
        st.caption("No facilities match the current filters.")
        return None
 
    selection = st.dataframe(
        _style_overview(dataframe),
        hide_index=True,
        use_container_width=True,
        height=OVERVIEW_TABLE_HEIGHT_PX,
        selection_mode="single-row",
        on_select="rerun",
        key="facilities_overview_table",
        column_config={
            "Occupancy %": st.column_config.ProgressColumn(
                "Occupancy %", min_value=0, max_value=100, format="%d%%",
            ),
        },
    )
 
    selected_rows = selection.selection.rows if hasattr(selection, "selection") else []
    if selected_rows:
        return dataframe.iloc[selected_rows[0]]["Facility"]
    return None
 
 
def _console_row(label: str, value: str) -> str:
    return (
        f'<div class="console-row">'
        f'<span class="console-row-label">{label}</span>'
        f'<span class="console-row-value">{value}</span>'
        f'</div>'
    )
 
 
def _render_facility_detail(facility_name: str | None) -> None:
    """Command-console detail panel: one compact operating picture split
    into STATUS / CAPACITY / OPERATIONS — hierarchy from typography and
    spacing rather than repeated cards or dividers."""
    overview = get_facility_overview()
    if facility_name is None and overview:
        facility_name = overview[0]["name"]
 
    facility = get_facility_detail(facility_name) if facility_name else None
    if facility is None:
        st.caption("Select a facility in the table above to view details.")
        return
 
    available = facility["capacity"] - facility["occupied"]
    occupancy_pct = round((facility["occupied"] / facility["capacity"]) * 100) if facility["capacity"] else 0
    status_hex = {
        "Operational": _ACCENT["primary"],
        "Busy": _ACCENT["info"],
        "High Load": _ACCENT["warning"],
        "Critical": _ACCENT["danger"],
    }.get(facility["status"], _ACCENT["info"])
    occ_hex = _ACCENT[_occupancy_color(occupancy_pct)]
 
    st.markdown('<div class="console-wrap">', unsafe_allow_html=True)
 
    # Header strip: name + type on the left, status badge on the right.
    st.markdown(
        f'<div class="console-strip">'
        f'<div><span class="console-name">{facility["name"]}</span>'
        f'<span class="console-type">{facility["facility_type"]}</span></div>'
        f'<div class="console-status-badge" style="color:{status_hex};">{facility["status"]}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
 
    # Bordered information blocks, reference-style: Status / Capacity /
    # Treatment / Occupancy (prominent) / Estimated Availability.
    status_rows = (
        _console_row("Facility Name", facility["name"])
        + _console_row("Facility Type", facility["facility_type"])
        + _console_row(
            "Operational Status",
            f'<span style="color:{status_hex};">{facility["status"]}</span>',
        )
    )
 
    capacity_rows = (
        _console_row("Total Beds", str(facility["capacity"]))
        + _console_row("Occupied Beds", str(facility["occupied"]))
        + _console_row("Available Beds", str(available))
        + _console_row("Queue Size", str(facility["queue"]))
    )
 
    # NOTE: built as one flat, unindented HTML string (no leading whitespace
    # per line) so Streamlit's markdown parser treats it as HTML instead of
    # a Markdown code block — that leading-whitespace-triggered code block
    # was the cause of the raw HTML text appearing on the page.
    operations_html = (
        f'<div class="console-block" style="flex:1.25 1 0;">'
        f'<div class="console-block-title">Operations</div>'
        f'{_console_row("Avg. Treatment", facility["avg_treatment"])}'
        f'<div style="margin-top:16px;"></div>'
        f'<div class="console-row">'
        f'<span class="console-row-label">Bed Utilization</span>'
        f'<span class="console-row-value" style="color:{occ_hex};font-size:1.15rem;font-weight:800;">{occupancy_pct}%</span>'
        f'</div>'
        f'<div class="console-occ-bar">'
        f'<div class="console-occ-fill" style="width:{occupancy_pct}%; background:{occ_hex};"></div>'
        f'</div>'
        f'</div>'
    )
 
    st.markdown(
        f'<div class="console-blocks">'
        # STATUS
        f'<div class="console-block" style="flex:1.3 1 0;">'
        f'<div class="console-block-title">Status</div>{status_rows}</div>'
        # CAPACITY
        f'<div class="console-block" style="flex:1.3 1 0;">'
        f'<div class="console-block-title">Capacity</div>{capacity_rows}</div>'
        # OPERATIONS
        f'{operations_html}'
        f'</div>',
        unsafe_allow_html=True,
    )
 
    st.markdown('</div>', unsafe_allow_html=True)
 
 
def render() -> None:
    """Render the Facilities page: KPI row, Operational Facility Overview, Facility Detail."""
    _inject_console_css()
    _render_kpi_row()
 
    facility_count = len(get_facility_overview())
    with panel("Operational Facility Overview", toolbar=f"{facility_count} Facilities"):
        selected_facility = _render_facility_overview()
 
    with panel("Facility Detail"):
        _render_facility_detail(selected_facility)