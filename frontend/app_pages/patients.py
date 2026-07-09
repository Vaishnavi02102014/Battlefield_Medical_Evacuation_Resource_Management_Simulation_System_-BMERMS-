"""
patients.py

Patients page — Patient Registry reverted to a table-based layout
(st.dataframe with native selection_mode="single-row"/on_select="rerun")
after the tactical row-card version was not approved. Search, filters,
sorting, and the casualty_id-based selection/default-fallback logic are
unchanged from Phase 3 — only how the registry is drawn changed back.

The table shows the same 10 columns as before (Casualty ID, Rank, Soldier
Unit, Battle Sector, Injury Type, Severity, Priority, Assigned Facility,
Status, Waiting Time), with semantic color on Severity/Priority/Status via
pandas Styler (_style_registry_table).

Selection is tracked by casualty_id in
st.session_state["patients_selected_casualty_id"], with the same
highest-operational-priority fallback (Priority, then Severity, then
oldest Arrival Time) when nothing valid is selected, so it still survives
search/filter/sort changes and still selects the correct patient on first
load — Streamlit's dataframe selection has no supported way to
pre-highlight a row without a user click, so the row itself won't
visually light up until clicked, but Patient Detail/Current Treatment
already reflect the correct default patient from the first render.

KPI Summary and Patient Distribution are unchanged — both still read from
the full, unfiltered dataset.
"""

from __future__ import annotations
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components.metric_card import metric_card
from components.panel import panel
from data.patients_mock_data import (
    get_all_casualties,
    get_all_facility_names,
    get_facility_name,
    get_bed_number,
    get_queue_entry,
    get_latest_treatment,
)

MAX_KPI_CARDS = 6

# Same accent hex values Facilities' console design uses, so badges/text
# colors match exactly across both pages.
_ACCENT = {
    "primary": "#3ddc84",
    "warning": "#f2b84b",
    "danger": "#ef5959",
    "info": "#7aa7ff",
}

SEVERITY_ACCENT: dict[str, str] = {
    "Critical": "danger", "Serious": "warning", "Moderate": "info", "Mild": "primary",
}
PRIORITY_ACCENT: dict[str, str] = {"P1": "danger", "P2": "warning", "P3": "primary"}
STATUS_ACCENT: dict[str, str] = {
    "Waiting": "warning", "In Treatment": "info", "Recovered": "primary", "Returned to Duty": "primary",
}

# Operational (not alphabetical) ordering for sort options.
PRIORITY_ORDER: dict[str, int] = {"P1": 0, "P2": 1, "P3": 2}
SEVERITY_ORDER: dict[str, int] = {"Critical": 0, "Serious": 1, "Moderate": 2, "Mild": 3}
SORT_OPTIONS: tuple[str, ...] = ("Priority", "Severity", "Arrival Time", "Waiting Time")


def _arrival_time_sort_key(arrival_time: str) -> float:
    """
    Best-effort chronological key for the mock data's arrival_time
    strings, which mix same-day 'HH:MM' values with relative phrases
    ('yesterday ...', 'N days ago') rather than a single parseable
    timestamp format. Once the real backend supplies a proper timestamp
    for Casualty.arrival_time, this reduces to ordinary datetime
    comparison and this helper can be simplified accordingly — the field
    itself is unchanged either way, only how it's compared for sorting.

    Lower = older = sorts first for "oldest first".
    """
    text = arrival_time.strip().lower()
    if "days ago" in text:
        digits = "".join(ch for ch in text if ch.isdigit())
        days = int(digits) if digits else 1
        return -1000.0 - days
    if "yesterday" in text:
        return -500.0
    if ":" in text:
        hours, _, minutes = text.partition(":")
        try:
            return float(int(hours) * 60 + int(minutes))
        except ValueError:
            return 0.0
    return 0.0


def _waiting_time_sort_key(waiting_time: float | None) -> tuple[int, float]:
    """Highest waiting time first; casualties with no queue entry sort last."""
    if waiting_time is None:
        return (1, 0.0)
    return (0, -waiting_time)


def _format_waiting_time(minutes: float | None) -> str:
    """Human-readable waiting time, e.g. 18.0 -> '18 min'. Presentation only — the raw value from QueueEntry.waiting_time is untouched."""
    if minutes is None:
        return "—"
    return f"{int(round(minutes))} min"


def _inject_console_css() -> None:
    """Identical console styling to Facilities' page-local CSS injection — same class names, same accent values."""
    st.markdown(
        """
        <style>
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
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_kpi_row() -> None:
    """
    Row 1 — fixed 6-column KPI strip. Cards are derived from whichever
    distinct Casualty.status values exist in the loaded dataset (capped
    at MAX_KPI_CARDS) — the layout itself never grows beyond 6 columns
    even if more status values appear later.
    """
    casualties = get_all_casualties()
    distinct_statuses: list[str] = []
    for casualty in casualties:
        if casualty["status"] not in distinct_statuses:
            distinct_statuses.append(casualty["status"])
    distinct_statuses = distinct_statuses[:MAX_KPI_CARDS]

    columns = st.columns(MAX_KPI_CARDS)
    for column, status in zip(columns, distinct_statuses):
        count = sum(1 for c in casualties if c["status"] == status)
        with column:
            metric_card(title=status, value=count, color=STATUS_ACCENT.get(status, "info"))


def _style_registry_table(dataframe: pd.DataFrame):
    """Semantic color on Severity/Priority/Status — bold, colored cell text via pandas Styler."""
    def _colored(accent_map: dict[str, str]):
        def _style(value: str) -> str:
            color = _ACCENT.get(accent_map.get(value, "info"), _ACCENT["info"])
            return f"color:{color}; font-weight:700;"
        return _style

    return (
        dataframe.style
        .map(_colored(SEVERITY_ACCENT), subset=["Severity"])
        .map(_colored(PRIORITY_ACCENT), subset=["Priority"])
        .map(_colored(STATUS_ACCENT), subset=["Status"])
    )


def _default_priority_casualty(casualties: list[dict]) -> dict | None:
    """Highest operational priority patient: Priority, then Severity, then oldest Arrival Time — not simply the first record."""
    if not casualties:
        return None
    return min(
        casualties,
        key=lambda c: (
            PRIORITY_ORDER.get(c["priority"], 99),
            SEVERITY_ORDER.get(c["severity"], 99),
            _arrival_time_sort_key(c["arrival_time"]),
        ),
    )


def _apply_search_and_filters(
    casualties: list[dict], search_text: str, severity_filter: str, status_filter: str, facility_filter: str,
) -> list[dict]:
    """Search and filters combine (AND). Facility filter compares against the resolved facility name, same as the table column."""
    results = casualties
    if severity_filter != "All":
        results = [c for c in results if c["severity"] == severity_filter]
    if status_filter != "All":
        results = [c for c in results if c["status"] == status_filter]
    if facility_filter != "All":
        results = [c for c in results if get_facility_name(c["assigned_facility"]) == facility_filter]
    if search_text.strip():
        needle = search_text.strip().lower()
        results = [
            c for c in results
            if needle in c["casualty_id"].lower()
            or needle in c["rank"].lower()
            or needle in c["soldier_unit"].lower()
            or needle in c["battle_sector"].lower()
            or needle in c["injury_type"].lower()
        ]
    return results


def _apply_sort(casualties: list[dict], sort_by: str) -> list[dict]:
    if sort_by == "Priority":
        return sorted(casualties, key=lambda c: PRIORITY_ORDER.get(c["priority"], 99))
    if sort_by == "Severity":
        return sorted(casualties, key=lambda c: SEVERITY_ORDER.get(c["severity"], 99))
    if sort_by == "Arrival Time":
        return sorted(casualties, key=lambda c: _arrival_time_sort_key(c["arrival_time"]))
    if sort_by == "Waiting Time":
        def key(c: dict) -> tuple[int, float]:
            queue_entry = get_queue_entry(c["casualty_id"])
            return _waiting_time_sort_key(queue_entry["waiting_time"] if queue_entry else None)
        return sorted(casualties, key=key)
    return casualties


def _render_patient_registry() -> dict | None:
    """Row 2, left — functional search/filters/sort + native table single-row selection. Returns the selected casualty, or None on empty results."""
    search_col, severity_col, status_col, facility_col, sort_col = st.columns([2, 1, 1, 1, 1])
    with search_col:
        search_text = st.text_input(
            "Search patients", key="patients_search", placeholder="Search patients...",
            label_visibility="collapsed",
        )
    with severity_col:
        severity_filter = st.selectbox(
            "Filter by severity", options=["All", "Critical", "Serious", "Moderate", "Mild"],
            key="patients_severity_filter", label_visibility="collapsed",
        )
    with status_col:
        all_casualties = get_all_casualties()
        distinct_statuses: list[str] = []
        for c in all_casualties:
            if c["status"] not in distinct_statuses:
                distinct_statuses.append(c["status"])
        status_filter = st.selectbox(
            "Filter by status", options=["All"] + distinct_statuses,
            key="patients_status_filter", label_visibility="collapsed",
        )
    with facility_col:
        facility_filter = st.selectbox(
            "Filter by facility", options=["All"] + get_all_facility_names(),
            key="patients_facility_filter", label_visibility="collapsed",
        )
    with sort_col:
        sort_by = st.selectbox(
            "Sort by", options=SORT_OPTIONS,
            key="patients_sort_by", label_visibility="collapsed",
        )

    casualties = get_all_casualties()
    filtered = _apply_search_and_filters(casualties, search_text, severity_filter, status_filter, facility_filter)
    filtered = _apply_sort(filtered, sort_by)

    if not filtered:
        st.caption("No patients match the current search and filters.")
        st.session_state["patients_selected_casualty_id"] = None
        return None

    records = []
    for c in filtered:
        queue_entry = get_queue_entry(c["casualty_id"])
        records.append({
            "Casualty ID": c["casualty_id"],
            "Rank": c["rank"],
            "Soldier Unit": c["soldier_unit"],
            "Battle Sector": c["battle_sector"],
            "Injury Type": c["injury_type"],
            "Severity": c["severity"],
            "Priority": c["priority"],
            "Assigned Facility": get_facility_name(c["assigned_facility"]) or "—",
            "Status": c["status"],
            "Waiting Time": _format_waiting_time(queue_entry["waiting_time"] if queue_entry else None),
        })
    dataframe = pd.DataFrame.from_records(records)

    # Native Streamlit 1.51 table row selection
    # (selection_mode="single-row"/on_select="rerun") — lightweight,
    # no custom click-handling. Selection is tracked by casualty_id
    # (not raw row index) below, so it survives search/filter/sort
    # changes.
    selection = st.dataframe(
        _style_registry_table(dataframe),
        hide_index=True, use_container_width=True, height=320,
        selection_mode="single-row", on_select="rerun", key="patients_registry_table",
    )

    selected_rows = selection.selection.rows if hasattr(selection, "selection") else []
    if selected_rows:
        st.session_state["patients_selected_casualty_id"] = filtered[selected_rows[0]]["casualty_id"]

    # Selection is tracked by casualty_id (not raw row index) precisely
    # so it survives search/filter/sort changes cleanly: if the
    # previously selected patient is filtered out (or on first load,
    # before any click), fall back to the highest-operational-priority
    # patient within the currently visible set rather than an arbitrary
    # row. Streamlit's dataframe selection has no supported way to
    # pre-highlight a row without a user click, so the row itself won't
    # visually light up until clicked — but the Detail/Current Treatment
    # panels below already reflect the correct default patient from the
    # very first render.
    selected_id = st.session_state.get("patients_selected_casualty_id")
    valid_ids = {c["casualty_id"] for c in filtered}
    if selected_id not in valid_ids:
        default_casualty = _default_priority_casualty(filtered)
        selected_id = default_casualty["casualty_id"] if default_casualty else None
        st.session_state["patients_selected_casualty_id"] = selected_id

    return next((c for c in filtered if c["casualty_id"] == selected_id), None)


def _render_patient_distribution() -> None:
    """Row 2, right — Severity Distribution as a compact donut, computed from the same loaded casualty dataset."""
    casualties = get_all_casualties()
    severities = [c["severity"] for c in casualties]
    counts = pd.Series(severities).value_counts()

    labels = list(counts.index)
    values = list(counts.values)
    colors = [_ACCENT[SEVERITY_ACCENT.get(label, "info")] for label in labels]

    figure = go.Figure(data=[go.Pie(
        labels=labels, values=values, hole=0.68,
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
        annotations=[dict(
            text=f"{len(casualties)}<br><span style='font-size:0.6em;'>TOTAL</span>",
            x=0.5, y=0.5, font=dict(size=20, color="#F4F6F8"), showarrow=False,
        )],
    )
    st.plotly_chart(figure, use_container_width=True)


def _console_row(label: str, value) -> str:
    display_value = value if value not in (None, "") else "—"
    return (
        f'<div class="console-row">'
        f'<span class="console-row-label">{label}</span>'
        f'<span class="console-row-value">{display_value}</span>'
        f'</div>'
    )


def _render_patient_detail(casualty: dict | None) -> None:
    """
    Row 3 — one compact operating picture split into STATUS / CLINICAL /
    LOGISTICS / CURRENT TREATMENT, one line per field (label left, value
    right) instead of stacked captions — the same density technique
    Facilities' detail panel uses. Driven by the Patient Registry's
    current selection (see _render_patient_registry).
    """
    if casualty is None:
        st.caption("No patient selected.")
        return

    queue_entry = get_queue_entry(casualty["casualty_id"])
    waiting_time = _format_waiting_time(queue_entry["waiting_time"] if queue_entry else None)
    treatment = get_latest_treatment(casualty["casualty_id"])

    status_hex = _ACCENT.get(STATUS_ACCENT.get(casualty["status"], "info"), _ACCENT["info"])
    severity_hex = _ACCENT.get(SEVERITY_ACCENT.get(casualty["severity"], "info"), _ACCENT["info"])
    priority_hex = _ACCENT.get(PRIORITY_ACCENT.get(casualty["priority"], "info"), _ACCENT["info"])

    st.markdown('<div class="console-wrap">', unsafe_allow_html=True)

    st.markdown(
        f'<div class="console-strip">'
        f'<div><span class="console-name">{casualty["casualty_id"]}</span>'
        f'<span class="console-type">{casualty["rank"]} · {casualty["soldier_unit"]}</span></div>'
        f'<div class="console-status-badge" style="color:{status_hex};">{casualty["status"]}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    status_rows = (
        _console_row("Casualty ID", casualty["casualty_id"])
        + _console_row("Rank", casualty["rank"])
        + _console_row("Soldier Unit", casualty["soldier_unit"])
        + _console_row("Age", casualty["age"])
        + _console_row("Status", f'<span style="color:{status_hex};">{casualty["status"]}</span>')
    )

    clinical_rows = (
        _console_row("Injury Type", casualty["injury_type"])
        + _console_row("Severity", f'<span style="color:{severity_hex};">{casualty["severity"]}</span>')
        + _console_row("Priority", f'<span style="color:{priority_hex};">{casualty["priority"]}</span>')
        + _console_row("Medical Officer", casualty["medical_officer"])
    )

    logistics_rows = (
        _console_row("Assigned Facility", get_facility_name(casualty["assigned_facility"]))
        + _console_row("Bed ID", get_bed_number(casualty["bed_id"]))
        + _console_row("Waiting Time", waiting_time)
        + _console_row("Battle Sector", casualty["battle_sector"])
        + _console_row("Arrival Time", casualty["arrival_time"])
        + _console_row("Evacuation Mode", casualty["evacuation_mode"])
        + _console_row("Expected Recovery", casualty["expected_recovery"])
        + _console_row("Return to Duty", casualty["return_to_duty"])
    )

    treatment_rows = (
        _console_row("Treatment Start", treatment["treatment_start"] if treatment else None)
        + _console_row("Treatment End", treatment["treatment_end"] if treatment else None)
        + _console_row("Treatment Duration", treatment["treatment_duration"] if treatment else None)
        + _console_row("Current Status", treatment["current_status"] if treatment else None)
    )

    st.markdown(
        f'<div class="console-blocks">'
        f'<div class="console-block" style="flex:1.1 1 0;">'
        f'<div class="console-block-title">Status</div>{status_rows}</div>'
        f'<div class="console-block" style="flex:1 1 0;">'
        f'<div class="console-block-title">Clinical</div>{clinical_rows}</div>'
        f'<div class="console-block" style="flex:1.3 1 0;">'
        f'<div class="console-block-title">Logistics</div>{logistics_rows}</div>'
        f'<div class="console-block" style="flex:1.1 1 0;">'
        f'<div class="console-block-title">Current Treatment</div>{treatment_rows}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    st.markdown('</div>', unsafe_allow_html=True)


def render() -> None:
    """Render the Patients page: KPI row, Registry | Distribution, Detail."""
    _inject_console_css()
    _render_kpi_row()

    registry_col, distribution_col = st.columns([2, 1])
    with registry_col:
        facility_count = len(get_all_casualties())
        with panel("Patient Registry", toolbar=f"{facility_count} Patients"):
            selected_casualty = _render_patient_registry()
    with distribution_col:
        with panel("Patient Distribution"):
            _render_patient_distribution()

    with panel("Patient Detail"):
        _render_patient_detail(selected_casualty)