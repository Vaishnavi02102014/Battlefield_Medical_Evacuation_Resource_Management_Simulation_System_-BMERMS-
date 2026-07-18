"""
simulation.py
 
Simulation page — Phases 1-8 (structural layout, visual refinement, the
Manual Incident Generator, emoji-to-badge cleanup, the Streamlit 1.51.0
HTML fix in shared components, the hierarchy/compaction pass, and the
hero-layout row reorganization) are preserved. Phase 9 is a layout
*architecture* pass, not another compression pass: it stops treating the
page as a set of independent dashboard cards and treats it as regions of
one Tactical Operations Center (TOC) screen, each with a single, clear
purpose and a visual weight proportional to that purpose.
 
PHASE 9 — screen regions, not cards
-----------------------------------------------------------------------
Reading order top-to-bottom is now the operator's actual workflow, not
an accident of where panels happened to fit:
 
    Region 1  Command console      Simulation Controls | Manual Incident
                                    Generator — a slim instrument strip,
                                    not a KPI dashboard. Status/Tick/
                                    Elapsed collapse to one inline HUD
                                    line (no metric_card — that card was
                                    the single biggest source of wasted
                                    vertical space here). Incident-type
                                    buttons now render as one single row
                                    (INCIDENT_TYPES_PER_ROW = all 7)
                                    instead of two, since the strip is
                                    wide enough, and the slider/Generate
                                    row no longer carries an empty
                                    alignment spacer line.
    Region 2  Battlefield Map      the hero. HERO_ROW_RATIO keeps it at
              (the hero)           ~70% of the workspace width, with the
                                    threat/weather/visibility HUD line
                                    collapsed from 3 st.columns() into
                                    one flush inline string so it reads
                                    as a status bar over the map, not a
                                    row of its own mini-cards.
    Region 3  Intel flank          AI Tactical Recommendation, then
                                    Current Operation — beside the map,
                                    each now a single merged HTML block
                                    per panel instead of several separate
                                    st.caption()/st.markdown() calls, so
                                    there's no accumulated inter-element
                                    margin between a label and its value.
                                    Current Operation's metric_card
                                    (Threat Level) is gone entirely,
                                    replaced by one compact
                                    Operation/Threat/Sector/Phase/
                                    Weather/Visibility stack.
    Region 4  Readiness band       Resource Status | Facility Status,
                                    side by side. Both are single dense
                                    HTML blocks per item (name, stats,
                                    status, and — for facilities — a
                                    thin custom occupancy bar built from
                                    a styled <div> instead of
                                    st.progress(), which carries its own
                                    fixed widget padding). A hairline
                                    inline border-bottom replaces
                                    st.divider() between items, since a
                                    full st.divider() element's margin is
                                    disproportionate at this density.
                                    Resource stat labels are the backend's
                                    own vocabulary in full (Available /
                                    Busy / Returning / Maintenance) —
                                    Phase 8's abbreviations (Avail / RTB /
                                    Maint) are reverted so the label text
                                    stays a direct, unambiguous match to
                                    the underlying field names.
    Region 5  Mission feed         Live Mission Log, deliberately kept
                                    narrower than the page (see
                                    MISSION_LOG_WIDTH_RATIO) so a short
                                    operational feed doesn't visually
                                    claim the same width as the
                                    Battlefield Map above it — full-width
                                    was correct for a report, not a feed.
                                    Compact rows, hairline separators
                                    (same technique as Region 4) instead
                                    of st.divider().
    Region 6  Alert ribbon         Bottom Alert Bar, restyled as a row of
                                    severity-colored chips (background
                                    tint + left accent border per chip)
                                    instead of plain bold-severity text
                                    inside the panel border, so urgency
                                    reads at a glance rather than being
                                    inferred from a word.
 
Nothing structural changed below the surface: session_state keys,
INCIDENT_TYPES / short-label mapping, _handle_generate_incident_click,
button mechanics, the underlying RESOURCE_STATUS / FACILITY_STATUS /
MISSION_LOG_ENTRIES / ALERTS data shapes, and the no-timer/no-random/
no-autorefresh constraints are all identical to Phase 8. metric_card.py,
panel.py, buttons.py, theme.py, and theme.css are unmodified — every
visual change here comes from how this page arranges and feeds its own
markup into components those files already exposed (panel()'s `toolbar`
argument, resolve_color(), COLOR_TEXT_SECONDARY). metric_card() itself is
no longer imported by this page: Phase 9 removes both call sites that
used it (Simulation Controls' status, Current Operation's Threat Level),
replacing them with the same inline-HTML technique already used
elsewhere on this page, since a bordered/padded card is what made those
two sections feel oversized in the first place.
 
No backend, simulation engine, database, or API integration. Everything
below is one consistent mock simulation state (never random values, per
spec) so every panel agrees with every other panel. Placeholder vocabulary
(facility codes, treatment durations, fleet sizes, threat/weather/severity
terms, incident types) is deliberately drawn from the same enums the
backend (backend/Phase 1/constants.py, backend/Phase 1/config.py) already
defines, so wiring this page to the real simulation later is a
data-source swap, not a redesign. The Generate Incident button's handler
(_handle_generate_incident_click) is a single, isolated function for the
same reason — its body is the only thing that needs to change when real
incident generation is wired in. Note for whoever wires Resource Status
to the live backend: backend/Phase 1/constants.py's RESOURCE_STATUSES is
["Available", "Dispatched", "Returning", "Under Maintenance"] — this
page's "busy"/"maintenance" session/dict keys and their "Busy"/
"Maintenance" display labels are the placeholder vocabulary requested for
this UI pass; reconcile the "Busy"/"Dispatched" and "Maintenance"/"Under
Maintenance" naming against whichever the real API response uses at
integration time.
 
Uses only st.columns()/st.container()/st.markdown()/st.write()/st.caption()/
st.selectbox()/st.slider()/st.code() plus the existing panel(),
primary_button(), and secondary_button() components, plus
utils.theme.resolve_color()/COLOR_TEXT_SECONDARY/COLOR_BORDER for the
inline-HTML helpers below — no metric_card(), no st.progress(), no
st.divider() (replaced by inline hairline borders baked into the same
HTML block as each item, so there's one fewer Streamlit element's margin
per separator), no st.error()/st.warning()/st.info(). Button/slider state is tracked in
st.session_state purely for visual highlighting and UI acknowledgement —
no timers, no auto-refresh, no background tasks, and the Manual Incident
Generator never touches the Mission Log.
"""
 
from __future__ import annotations
import html
import re
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from backend.database import crud
from backend.simulation.simulation_controller import SimulationController
from services import resources_service
from services import facilities_service
from services import ai_service
 
from components.panel import panel
from components.buttons import primary_button, secondary_button
from components.map_adapter import get_map_data
from components.tactical_map import render_tactical_map
from utils.theme import (
    resolve_color,
    COLOR_TEXT_SECONDARY,
    COLOR_BORDER,
    COLOR_BACKGROUND,
    COLOR_DANGER,
    COLOR_WARNING,
    COLOR_PRIMARY,
)
 
# --------------------------------------------------------------------------
# CONSISTENT MOCK SIMULATION STATE
# One fixed scenario, referenced identically across every panel below —
# never randomized. Facility codes/capacities/treatment durations match
# backend/Phase 1/constants.py's FACILITY_CONFIG exactly; threat/weather/
# visibility values are drawn from THREAT_LEVELS/WEATHER_CONDITIONS/
# VISIBILITY_LEVELS; fleet totals match AMBULANCE_FLEET_SIZE (20),
# HELICOPTER_FLEET_SIZE (6), and MEDICAL_TEAM_COUNT (16).
# --------------------------------------------------------------------------
DEFAULT_SIM_STATUS: str = "Stopped"
DEFAULT_SIM_SPEED: int = 1
SIM_SPEEDS: list[int] = [1, 2, 5, 10]
 
TICK_INTERVAL_MS: int = 2000
CURRENT_TICK: str = "12,842"
 
# Current Operation: live from crud (Phase 6B.3).
# Rebuilt on every render() call.

def _build_current_operation() -> dict:
    operation = crud.get_active_operation()
    operation_name = (
        operation.operation_name
        if operation
        else "No Active Operation"
    )

    recent_incidents = crud.get_recent_incidents()
    sector = (
        recent_incidents[0].battle_sector
        if recent_incidents
        else "No Active Incidents"
    )

    return {
        "operation_name": operation_name,
        "sector": sector,
    }


CURRENT_OPERATION: dict = {}

# Resource fleets: (name, icon, available, busy, returning, maintenance).
# Totals match the backend's fixed fleet sizes exactly.
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


RESOURCE_STATUS: list[dict] = _build_resource_status()
 
# Facility cards: live from facilities_service (Phase 6B.1).
# Rebuilt on every render() call, same pattern as RESOURCE_STATUS.

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


FACILITY_STATUS: list[dict] = []
 
def _build_ai_recommendation() -> dict:
    return ai_service.get_ai_recommendation()


AI_RECOMMENDATION: dict = {}
 
# Live Mission Log entries — newest first. Categories match the set
# required by spec (and the backend's mission_log.py category constants).
MISSION_LOG_CATEGORIES: list[str] = [
    "Incident", "Dispatch", "Admission", "Queue", "Recovery", "Return to Duty", "Resource",
]
MISSION_LOG_ENTRIES: list[dict] = [
    {"time": "11:04:55", "category": "Incident",
     "description": "IED explosion reported in Sector Bravo. 4 casualties confirmed, evacuation requested."},
    {"time": "11:03:10", "category": "Dispatch",
     "description": "Helicopter H-02 dispatched to Sector Bravo for casualty extraction."},
    {"time": "11:01:42", "category": "Admission",
     "description": "CAS-114 admitted to RAP — Alpha 1 for triage and stabilization."},
    {"time": "10:58:20", "category": "Queue",
     "description": "ADS — Bravo 2 waiting queue increased to 15 personnel."},
    {"time": "10:52:07", "category": "Recovery",
     "description": "CAS-098 recovered at HMV — Delta 9, pending discharge review."},
    {"time": "10:47:33", "category": "Return to Duty",
     "description": "CAS-081 cleared for return to duty from RAP — Alpha 1."},
]
# How many entries the compact feed shows per filter selection — a
# reporting page shows everything; an operational feed shows the latest
# handful. "View All" (below) is the escape hatch to the rest.
MISSION_LOG_FEED_SIZE: int = 4
 
# Column ratios. Three distinct ratios now (one per row shape) rather
# than one ratio reused for two visually different rows — Phase 7 shared
# a single ROW_COLUMN_RATIO across the map row and a second, separately
# invoked columns() call purely to force alignment; Phase 8 has no such
# alignment trick to preserve, since the command strip, hero row, and
# support band are three genuinely different row shapes.
COMMAND_STRIP_RATIO: list[int] = [1, 1]        # Simulation Controls | Manual Incident Generator
HERO_ROW_RATIO: list[int] = [78, 22]             # Battlefield Map (~70%) | Intel flank (AI Rec, Current Operation)
SUPPORT_ROW_RATIO: list[int] = [1, 1]          # Resource Status | Facility Status
# Live Mission Log is a compact operational feed, not a report — it gets
# side gutters so it reads as a narrower region than the Battlefield Map
# above it, rather than claiming the full page width.
 
# --------------------------------------------------------------------------
# MANUAL INCIDENT GENERATOR (UI-only)
# Incident type labels overlap with backend/Phase 1/constants.py's
# INCIDENT_TYPES where the wording matches exactly (Mortar Attack, Sniper
# Fire, Ambush, Artillery Strike, Border Skirmish), so those five need no
# translation when this panel is eventually wired to the real event
# generator. "IED Blast" and "Convoy Attack" map to the backend's "IED
# Explosion" and "Convoy Attack" respectively — noted here for whoever
# does that wiring later.
# --------------------------------------------------------------------------
INCIDENT_TYPES: list[str] = [
    "Mortar Attack", "IED Blast", "Sniper Fire", "Ambush",
    "Convoy Attack", "Artillery Strike", "Border Skirmish",
]
# Frontend labels are intentionally preserved for readability.
# During backend integration, use this mapping before sending
# incident types to the simulation engine.
INCIDENT_TYPE_SHORT_LABELS: dict[str, str] = {
    "Mortar Attack": "Mortar",
    "IED Blast": "IED Blast",
    "Sniper Fire": "Sniper",
    "Ambush": "Ambush",
    "Convoy Attack": "Convoy",
    "Artillery Strike": "Artillery",
    "Border Skirmish": "Border",
}
BACKEND_INCIDENT_MAPPING = {
    "Mortar Attack": "Mortar Attack",
    "IED Blast": "IED Explosion",
    "Sniper Fire": "Sniper Fire",
    "Ambush": "Ambush",
    "Convoy Attack": "Convoy Attack",
    "Artillery Strike": "Artillery Strike",
    "Border Skirmish": "Border Skirmish",
}
DEFAULT_INCIDENT_TYPE: str = INCIDENT_TYPES[0]
DEFAULT_CASUALTY_COUNT: int = 10
MIN_CASUALTY_COUNT: int = 1
MAX_CASUALTY_COUNT: int = 50
# Buttons per row for the command strip's status/speed button grids (both
# have exactly 4 items, so this stays a 4-across single row).
BUTTONS_PER_ROW: int = 4
# Incident-type buttons render as ONE row spanning every entry in
# INCIDENT_TYPES, rather than wrapping onto a second row — the command
# strip is wide enough, and a single row reads as one compact tactical
# control panel instead of a two-row button grid with a visible seam.
INCIDENT_TYPES_PER_ROW: int = len(INCIDENT_TYPES)
 
 
def _init_session_state() -> None:
    """Seed the button-visual-feedback session_state keys once, on first render."""
    st.session_state.setdefault("simulation_tick", 0)
    st.session_state.setdefault("simulation_status", DEFAULT_SIM_STATUS)
    st.session_state.setdefault("simulation_speed", DEFAULT_SIM_SPEED)
    st.session_state.setdefault("manual_incident_type", DEFAULT_INCIDENT_TYPE)
    st.session_state.setdefault("manual_casualty_count", DEFAULT_CASUALTY_COUNT)
    st.session_state.setdefault("manual_incident_counter", 0)
    st.session_state.setdefault("last_manual_incident", None)
 
 
def _inline_status_html(text: str, color: str) -> str:
    """
    One inline, bold, semantically-colored status word — no card, no
    border, no padding, and `white-space: nowrap` so a two-word status
    like "High Load" can never wrap onto a second line even inside a
    narrow flex/column context. Reuses metric_card()'s own
    resolve_color() tokens so severity colors stay identical to the rest
    of the app.
 
    Built as a single flush-left string (no embedded newlines) — the
    same rule metric_card.py and panel.py document and depend on.
    """
    accent = resolve_color(color)
    safe_text = html.escape(text)
    return f'<span style="color:{accent};font-weight:600;white-space:nowrap;">{safe_text}</span>'

def _get_current_tick() -> int:
    return st.session_state.get("simulation_tick", 0)
 
def _run_pending_tick() -> None:
    clock = st.session_state["sim_clock"]

    if not clock.is_running:
        return

    controller = st.session_state["sim_controller"]
    new_entries = controller.run_tick()

    print(f"TICK = {st.session_state['simulation_tick']}")
    print(f"NEW ENTRIES = {len(new_entries)}")
    print(new_entries)

    if new_entries:
        st.session_state["mission_log"].extend(new_entries)

    st.session_state["simulation_tick"] += 1

def _render_status_button_row() -> None:
    """Start / Pause / Resume / Reset as one 4-across row — the command strip is wide enough now that this no longer wraps."""
    clock = st.session_state["sim_clock"]
    status = st.session_state["simulation_status"]

    labels_and_keys = [
        ("▶ Start", "simulation_ctrl_start", "Running"),
        ("⏸ Pause", "simulation_ctrl_pause", "Paused"),
        ("↻ Resume", "simulation_ctrl_resume", "Running"),
        ("⟳ Reset", "simulation_ctrl_reset", "Stopped"),
    ]

    columns = st.columns(4, gap="small")

    for column, (label, key, target_status) in zip(columns, labels_and_keys):
        with column:
            button = primary_button if status == target_status else secondary_button

            if button(label, key=key):

                if label == "⟳ Reset":
                    crud.reset_simulation_data()
                    clock.reset()

                    st.session_state["sim_controller"] = (
                        SimulationController(clock)
                    )

                    st.session_state["simulation_status"] = "Stopped"
                    st.session_state["simulation_speed"] = 1
                    clock.set_speed(1)

                    st.session_state["simulation_tick"] = 0
                    st.session_state["manual_incident_counter"] = 0
                    st.session_state["last_manual_incident"] = None

                    st.session_state["mission_log"].clear()

                    if "tactical_map_reset_counter" in st.session_state:
                        st.session_state["tactical_map_reset_counter"] += 1
                    # Clear Analytics casualty trend history so the
                    # trend chart starts empty after Reset Simulation.
                    if "analytics_casualty_history" in st.session_state:
                        st.session_state["analytics_casualty_history"].clear()

                else:
                    st.session_state["simulation_status"] = target_status

                    if target_status == "Running":
                        clock.start()

                    elif target_status == "Paused":
                        clock.pause()

                st.rerun()
 
 
def _render_speed_button_row() -> None:
    """1x / 2x / 5x / 10x as one 4-across row (SIM_SPEEDS has exactly 4 entries, so this is a single row)."""
    clock = st.session_state["sim_clock"]
    selected_speed = st.session_state["simulation_speed"]
    columns = st.columns([1,1,1,1], gap="small")
    for column, speed in zip(columns, SIM_SPEEDS):
        with column:
            button = primary_button if speed == selected_speed else secondary_button
            if button(f"{speed}x", key=f"simulation_ctrl_speed_{speed}"):
                st.session_state["simulation_speed"] = speed
                clock.set_speed(speed)
                st.rerun()
 
 
def _render_simulation_controls() -> None:
    """
    Command console, left half — Simulation Controls.
 
    A compact instrument strip, not a KPI dashboard: Status/Tick/Elapsed
    collapse into one inline HUD line (no metric_card — a bordered/
    padded card per value is exactly what made this section oversized),
    the action buttons sit directly beneath with no intervening caption
    row, and Speed/Seed now share one tightened row instead of each
    getting its own labeled block.
    """
    clock = st.session_state["sim_clock"]
    elapsed_str = str(
        clock.current_time - clock.start_time
    ).split(".")[0]
    status = st.session_state["simulation_status"]
    status_color = {"Running": "primary", "Paused": "warning", "Stopped": "danger"}.get(status, "info")
    status_html = _inline_status_html(status.upper(), status_color)
    st.markdown(
        f'STATUS&nbsp;{status_html}'
        f'&nbsp;&nbsp;·&nbsp;&nbsp;TICK&nbsp;<b>{_get_current_tick()}</b>'
        f'&nbsp;&nbsp;·&nbsp;&nbsp;ELAPSED&nbsp;<b>{html.escape(elapsed_str)}</b>',
        unsafe_allow_html=True,
    )
 
    _render_status_button_row()
    _render_speed_button_row()
 
def _render_incident_type_buttons() -> None:
    """One tactical button row spanning every INCIDENT_TYPES entry — a single dense row reads as one control panel, not a two-row grid with a seam. The selected type renders as primary."""
    selected_type = st.session_state["manual_incident_type"]
    columns = st.columns([1.35]*7, gap="small")
    for column, incident_type in zip(columns, INCIDENT_TYPES):
        with column:
            button = primary_button if incident_type == selected_type else secondary_button
            label = {
                "Mortar Attack": "Mortar",
                "IED Blast": "IED",
                "Sniper Fire": "Sniper",
                "Ambush": "Ambush",
                "Convoy Attack": "Convoy",
                "Artillery Strike": "Artillery",
                "Border Skirmish": "Border",
            }[incident_type]
            if button(label, key=f"manual_incident_type_{incident_type}"):
                st.session_state["manual_incident_type"] = incident_type
                st.rerun()
 
 
def _handle_generate_incident_click() -> None:
    incident_type = st.session_state["manual_incident_type"]
    casualty_count = st.session_state["manual_casualty_count"]

    controller = st.session_state["sim_controller"]

    new_entries = controller.trigger_manual_incident(
        event_type=incident_type,
        casualty_count=casualty_count,
    )

    if new_entries:
        st.session_state["mission_log"].extend(new_entries)

    global RESOURCE_STATUS
    RESOURCE_STATUS = _build_resource_status()

    st.session_state["manual_incident_counter"] += 1
    st.session_state["last_manual_incident"] = {
        "type": incident_type,
        "casualties": casualty_count,
        "sequence": st.session_state["manual_incident_counter"],
    }
 
 
def _render_manual_incident_generator() -> None:
    """Command console, right half — a tactical control panel: incident type, casualty count, Generate Incident, with no spacer rows between controls."""
    _render_incident_type_buttons()
 
    slider_col, generate_col = st.columns([3, 1])
    with slider_col:
        st.slider(
            "Casualties",
            min_value=MIN_CASUALTY_COUNT,
            max_value=MAX_CASUALTY_COUNT,
            key="manual_casualty_count",
        )
    with generate_col:
        primary_button(
            "Generate Incident",
            key="manual_generate_incident",
            on_click=_handle_generate_incident_click,
        )
 
    last = st.session_state["last_manual_incident"]
    if last is not None:
        st.caption(f"Last Manual Incident #{last['sequence']}: **{last['type']}** — {last['casualties']} casualties")
 
 
def _render_battlefield_map() -> None:
    """
    Region 2 (the hero) — Battlefield Map.
 
    Does not share its row with a tall Controls column (that lives in
    the command console above), so this panel takes ~70% of the
    workspace width outright (HERO_ROW_RATIO). Live-tracking status
    lives in the panel's own toolbar (panel()'s existing `toolbar`
    argument). The threat/weather/visibility line is one flush inline
    HTML string rather than 3 st.columns() — three side-by-side mini
    stats read as three small cards; one HUD line over the map reads as
    a status bar belonging to the map itself.
 
    The map itself is delegated to components/tactical_map.py (a
    dedicated, reusable component — see that module's docstring). This
    function stays a thin wrapper: it hands simulation.py's existing mock
    state to the map's one data provider (get_map_data), then passes the
    single resulting MapData object to the renderer — it never assembles
    map-specific data itself.
    """ 
    map_data = get_map_data(
        FACILITY_STATUS,
        RESOURCE_STATUS,
        crud.get_recent_incidents(),
        crud.get_active_casualties(),
        crud.get_all_ambulances(),
        crud.get_all_helicopters(),
        crud.get_all_medical_teams(),
    )

    render_tactical_map(map_data)
 
 
def _render_current_operation() -> None:
    """
    Region 3 (intel flank, card 2) — Current Operation.
 
    No metric_card: a bordered/padded card for one field (Threat Level)
    is what made this section disproportionately tall next to its five
    plain-text neighbors. Operation/Threat/Sector/Phase/Weather/
    Visibility now render as one merged HTML block (a single st.markdown
    call), so there's no per-line Streamlit element margin stacking up —
    a compact operational-metadata stack rather than a metric dashboard.
    """
    lines = [
        f"<b>Operation:</b> {html.escape(CURRENT_OPERATION['operation_name'])}",
        f"<b>Sector:</b> {html.escape(CURRENT_OPERATION['sector'])}",
    ]
    st.markdown(
        f'<div style="line-height:1.55;">{"<br/>".join(lines)}</div>',
        unsafe_allow_html=True,
    )
 
 
def _readiness_status(available: int, total: int) -> tuple[str, str]:
    """Map available/total ratio to a readiness label and semantic color tier — no emoji."""
    if total == 0:
        return "Unknown", "info"
    ratio = available / total
    if ratio >= 0.5:
        return "Nominal", "primary"
    if ratio >= 0.25:
        return "Reduced", "warning"
    return "Critical", "danger"
 
 
def _resource_summary_html(resource: dict, is_last: bool) -> str:
    """
    One resource, rendered as a single flat HTML block — deliberately
    not st.columns() for the stat values, so a word can never wrap
    mid-word inside a narrow sub-column (the original cause of an
    earlier "Returning" mid-word wrap bug).
 
    Stat labels are the backend's own vocabulary in full — Available /
    Busy / Returning / Maintenance — not abbreviations, so this stays a
    direct, unambiguous match to RESOURCE_STATUS's field names for
    future backend wiring. A hairline `border-bottom` (skipped on the
    last item via `is_last`) replaces st.divider() as the separator:
    st.divider() is a full Streamlit element with its own margin, which
    is disproportionate at this line-per-item density.
 
    Built as one flush-left string (implicit adjacent-string-literal
    concatenation — no real newline characters in the result), the same
    pattern metric_card.py's card_html uses.
    """
    total = (
        resource["available"]
        + resource["dispatched"]
    )
    label, color = _readiness_status(resource["available"], total)
    status_span = _inline_status_html(label, color)
    name_html = html.escape(f"{resource['icon']} {resource['name']}")
    stats_html = (
        f"Available: {resource['available']}<br>"
        f"Dispatched: {resource['dispatched']}"
    )
    border_style = "" if is_last else f"border-bottom:1px solid {COLOR_BORDER};padding-bottom:6px;margin-bottom:6px;"
    return (
        f'<div style="{border_style}">'
        f'<span style="font-weight:600;">{name_html}</span>'
        '&nbsp;&nbsp;'
        f'{status_span}'
        '<br/>'
        f'<span style="font-size:0.85rem;color:{COLOR_TEXT_SECONDARY};">{stats_html}</span>'
        '</div>'
    )
 
 
def _render_resource_status() -> None:
    """Region 4 (readiness band, left) — Resource Status: one dense HTML block per resource, hairline separators (no st.divider(), no per-item cards)."""
    last_index = len(RESOURCE_STATUS) - 1
    for index, resource in enumerate(RESOURCE_STATUS):
        st.markdown(_resource_summary_html(resource, index == last_index), unsafe_allow_html=True)
 
 
def _occupancy_color(occupancy_pct: int) -> str:
    """Occupancy colour semantics: green <70%, yellow 70-90%, red >90% — no emoji, drives the inline status word."""
    if occupancy_pct < 70:
        return "primary"
    if occupancy_pct <= 90:
        return "warning"
    return "danger"
 
 
def _facility_summary_html(facility: dict, occupancy_pct: int, is_last: bool) -> str:
    """
    One facility, rendered as a single merged HTML block: name/type,
    status word, a thin custom occupancy bar, and the stats line — all
    in one st.markdown() call. The occupancy bar is a plain styled
    <div> rather than st.progress(): st.progress() is a full Streamlit
    widget with its own fixed vertical padding, which is exactly what
    made every facility read as its own independent card. A hairline
    `border-bottom` (skipped on the last item via `is_last`) replaces
    st.divider() between facilities for the same reason Resource Status
    does the same thing.
 
    The status word stays inline in the stats line (not a separate
    st.columns([4, 1]) slot) with the nowrap-protected span from
    _inline_status_html, so a two-word status like "High Load" can never
    wrap onto a second line.
    """
    status_color = _occupancy_color(occupancy_pct)
    status_span = _inline_status_html(facility["status"], status_color)
    header_html = html.escape(f"{facility['name']} · {facility['full_name']}")
    stats_html = html.escape(
        f"Occ {occupancy_pct}%  ·  Beds {facility['occupied']}/{facility['capacity']}  ·  "
        f"Waiting {facility['waiting']}  ·  Tx {facility['avg_treatment']}"
    )
    bar_color = resolve_color(status_color)
    occupancy_bar_html = (
        f'<div style="height:4px;border-radius:2px;background:{COLOR_BORDER};margin:3px 0 4px;">'
        f'<div style="height:100%;width:{occupancy_pct}%;border-radius:2px;background:{bar_color};"></div>'
        '</div>'
    )
    border_style = "" if is_last else f"border-bottom:1px solid {COLOR_BORDER};padding-bottom:6px;margin-bottom:6px;"
    return (
        f'<div style="{border_style}">'
        f'<div style="font-weight:600;">{header_html}</div>'
        f'{occupancy_bar_html}'
        f'<div style="font-size:0.85rem;color:{COLOR_TEXT_SECONDARY};">'
        f'{stats_html}&nbsp;&nbsp;·&nbsp;&nbsp;Status: {status_span}'
        '</div>'
        '</div>'
    )
 
 
def _render_facility_status() -> None:
    """Region 4 (readiness band, right) — Facility Status: one merged HTML block per facility (name/type, custom occupancy bar, stats-plus-status line), hairline separators (no st.progress(), no st.divider(), no per-item cards)."""
    last_index = len(FACILITY_STATUS) - 1
    for index, facility in enumerate(FACILITY_STATUS):
        occupancy_pct = round((facility["occupied"] / facility["capacity"]) * 100)
        st.markdown(_facility_summary_html(facility, occupancy_pct, index == last_index), unsafe_allow_html=True)
 
 
# --------------------------------------------------------------------------
# AI Tactical Recommendation — command-decision card
#
# recommendation_engine.py's output ({"recommendation", "reason",
# "expected_benefit", "confidence"}) carries no "priority" field, and
# backend/recommendation logic is out of scope for this UI pass, so the
# priority badge level is inferred here, display-only, from confidence
# (with the engine's own "standard operations" sentinel always treated
# as NORMAL). Some "reason" strings can currently embed raw
# resource_assessment.py metrics (occupancy=, queue=, critical=,
# weighted load score, primary driver) and predictor.py fields
# (transfer_required=) — those never reach the screen; their meaning is
# translated into plain language and every raw fragment is stripped
# below, without touching any backend text.
# --------------------------------------------------------------------------

_STANDARD_MONITORING_TEXT = "Continue standard operations and monitoring."

PRIORITY_BADGE_COLORS = {
    "CRITICAL": COLOR_DANGER,
    "HIGH": "#F2984B",  # orange — no dedicated theme.py token; reserved for this badge only
    "MEDIUM": COLOR_WARNING,
    "NORMAL": COLOR_PRIMARY,
}

_PRIMARY_DRIVER_LABELS = {
    "occupancy": "Facility occupancy is the primary constraint.",
    "queue": "Casualty queue length is the primary constraint.",
    "critical": "Critical casualty volume is the primary constraint.",
    "resources": "Available resource shortage is the primary constraint.",
}

_DEBUG_MARKER_PATTERN = re.compile(
    r"occupancy=|queue=|critical=|resources=|weighted load score|primary driver|transfer_required=",
    re.IGNORECASE,
)


def _ai_priority_level(recommendation: dict) -> str:
    """
    Display-only priority badge.

    Until the backend provides an explicit priority field,
    infer it from the recommendation text instead of AI confidence.
    """

    text = recommendation.get("recommendation", "").lower()

    if "contingency evacuation" in text:
        return "CRITICAL"

    elif "deploy" in text:
        return "HIGH"

    elif "reroute" in text:
        return "HIGH"

    elif "prepare" in text:
        return "MEDIUM"

    return "NORMAL"


def _priority_badge_html(level: str) -> str:
    color = PRIORITY_BADGE_COLORS.get(level, COLOR_PRIMARY)
    return (
        f'<span style="display:inline-block;padding:3px 10px;border-radius:4px;'
        f'font-size:0.70rem;font-weight:700;letter-spacing:0.06em;'
        f'color:{COLOR_BACKGROUND};background:{color};">{html.escape(level)}</span>'
    )


def _build_reason_bullets(reason: str) -> list[str]:
    """Translates a recommendation_engine.py `reason` string into 1+
    clean, human-readable bullets, extracting the meaning of any raw
    metric fields into plain language first, then stripping every
    remaining raw fragment (see module note above)."""
    text = reason or ""
    bullets: list[str] = []

    driver_match = re.search(r"primary driver:\s*(\w+)", text, re.IGNORECASE)
    if driver_match:
        bullets.append(
            _PRIMARY_DRIVER_LABELS.get(
                driver_match.group(1).lower(), "Resource load is currently elevated."
            )
        )

    transfer_match = re.search(r"transfer_required=(\w+)", text, re.IGNORECASE)
    if transfer_match:
        verdict = "required" if transfer_match.group(1).lower() == "yes" else "not required"
        bullets.append(f"Transfer is predicted to be {verdict}.")

    # Peel off parenthetical groups that embed raw metrics, innermost
    # first, re-running until none remain (handles the one level of
    # nesting a caller can wrap resource_assessment.py's reason in).
    scrubbed = text
    for _ in range(4):
        next_scrubbed = re.sub(
            r"\([^()]*\)",
            lambda m: "" if _DEBUG_MARKER_PATTERN.search(m.group(0)) else m.group(0),
            scrubbed,
        )
        if next_scrubbed == scrubbed:
            break
        scrubbed = next_scrubbed

    scrubbed = re.sub(r"\s*;\s*", " ", scrubbed)
    scrubbed = re.sub(r"\s{2,}", " ", scrubbed)
    scrubbed = re.sub(r"\s+\.", ".", scrubbed)
    scrubbed = scrubbed.strip()

    for sentence in re.split(r"(?<=[.])\s+", scrubbed):
        sentence = sentence.strip(" .")
        if not sentence or _DEBUG_MARKER_PATTERN.search(sentence):
            continue
        bullets.append(sentence + ".")

    if not bullets:
        bullets.append("Resource load is currently elevated.")

    return bullets


def _build_benefit_bullets(benefit: str) -> list[str]:
    """expected_benefit strings from recommendation_engine.py are always
    already clean prose — this just splits them into bullet sentences."""
    text = (benefit or "").strip()
    bullets = [s.strip(" .") + "." for s in re.split(r"(?<=[.])\s+", text) if s.strip(" .")]
    return bullets or ["No additional benefit information available."]


def _render_ai_recommendation() -> None:
    """
    Region 3 (intel flank, card 1, directly beside the map) — AI
    Tactical Recommendation, redesigned as a scannable command-decision
    card: a colored priority badge, the recommendation as the single
    largest element, Reason and Expected Benefit as short bullet lists
    instead of a dense paragraph, and AI Confidence as a labeled
    progress bar (no metric_card, no raw backend/debug fields — see
    _build_reason_bullets()).
    """
    level = _ai_priority_level(AI_RECOMMENDATION)
    reason_bullets = _build_reason_bullets(AI_RECOMMENDATION.get("reason", ""))
    benefit_bullets = _build_benefit_bullets(AI_RECOMMENDATION.get("expected_benefit", ""))

    reason_html = "".join(f"<div>• {html.escape(b)}</div>" for b in reason_bullets)
    benefit_html = "".join(f"<div>• {html.escape(b)}</div>" for b in benefit_bullets)
    divider = f'<div style="border-top:1px solid {COLOR_BORDER};margin:8px 0;"></div>'
    label_style = f"font-size:0.70rem;letter-spacing:0.05em;color:{COLOR_TEXT_SECONDARY};"
    body_style = f"font-size:0.82rem;line-height:1.5;color:{COLOR_TEXT_SECONDARY};margin:2px 0;"

    st.markdown(
        f'{_priority_badge_html(level)}'
        f'{divider}'
        f'<div style="{label_style}">RECOMMENDATION</div>'
        f'<div style="font-weight:700;font-size:1.15rem;line-height:1.3;margin:2px 0 0;">{html.escape(AI_RECOMMENDATION.get("recommendation", ""))}</div>'
        f'{divider}'
        f'<div style="{label_style}">REASON</div>'
        f'<div style="{body_style}">{reason_html}</div>'
        f'{divider}'
        f'<div style="{label_style}">EXPECTED BENEFIT</div>'
        f'<div style="{body_style}">{benefit_html}</div>'
        f'{divider}'
        f'<div style="{label_style}">AI CONFIDENCE</div>',
        unsafe_allow_html=True,
    )

    confidence = AI_RECOMMENDATION.get("confidence") or 0.0
    st.progress(min(max(confidence / 100, 0.0), 1.0))
    st.caption(f"{confidence:.0f}%")
 
 
def _get_filtered_mission_log_entries() -> list[dict]:
    """
    Shared filter logic for both the panel's toolbar count and its rendered feed.
    """

    selected_filter = st.session_state.get(
        "simulation_mission_log_filter",
        "All",
    )

    mission_log = st.session_state.get(
        "mission_log",
        []
    )

    entries = []

    for entry in reversed(mission_log):
        entries.append(
            {
                "time": entry.timestamp,
                "category": entry.category,
                "description": entry.message,
            }
        )

    return [
        entry
        for entry in entries
        if (
            selected_filter == "All"
            or entry["category"] == selected_filter
        )
    ]
 
 
def _render_live_mission_log() -> None:
    """
    Region 5 — Live Mission Log: a compact operational communication
    feed, not a report. render() now wraps this panel in
    MISSION_LOG_WIDTH_RATIO side gutters so the feed reads as a narrower
    region than the Battlefield Map above it, rather than claiming the
    same full page width. Each entry is one compact line built as a
    single flush HTML block with a hairline `border-bottom` (skipped on
    the last entry) instead of st.divider() — a full divider element's
    margin between four-line-max entries is disproportionate here.
    Filter / Export / View All controls stay in the body; the "Showing
    latest N of M" count lives in the panel's toolbar (see render()), so
    the body opens directly with the filter row.
    """
    st.selectbox(
        "Filter by category",
        options=["All"] + MISSION_LOG_CATEGORIES,
        key="simulation_mission_log_filter",
        label_visibility="collapsed",
    )
 
    filtered_entries = _get_filtered_mission_log_entries()
    if not filtered_entries:
        selected_filter = st.session_state.get("simulation_mission_log_filter", "All")
        st.caption(f"No entries for category: {selected_filter}")
        return
 
    feed_entries = filtered_entries[:MISSION_LOG_FEED_SIZE]
    last_index = len(feed_entries) - 1
    for index, entry in enumerate(feed_entries):
        border_style = (
            "" if index == last_index
            else f"border-bottom:1px solid {COLOR_BORDER};padding-bottom:4px;margin-bottom:4px;"
        )
        st.markdown(
            f'<div style="{border_style}font-size:0.9rem;">'
            f'<code>{html.escape(entry["time"])}</code>&nbsp;&nbsp;'
            f'<b>{html.escape(entry["category"])}</b> — {html.escape(entry["description"])}'
            '</div>',
            unsafe_allow_html=True,
        )
 
 
ALERT_SEVERITY_COLOR: dict[str, str] = {"Critical": "danger", "Warning": "warning", "Information": "info"}

def _generate_alerts() -> list[dict]:
    """
    Generate operational alerts directly from facility and resource data.
    Uses only data already displayed on the Simulation page, so the same
    logic can later be wired to backend responses without redesign.
    """
    alerts = []

    # ------------------------------
    # Facility occupancy alerts
    # ------------------------------
    for facility in FACILITY_STATUS:
        occupancy_pct = round(
            facility["occupied"] / facility["capacity"] * 100
        )

        if occupancy_pct >= 90:
            alerts.append({
                "severity": "Critical",
                "message":
                    f"{facility['name']} occupancy has reached "
                    f"{occupancy_pct}%.",
            })

        if facility["waiting"] >= 20:
            alerts.append({
                "severity": "Warning",
                "message":
                    f"{facility['name']} waiting queue has reached "
                    f"{facility['waiting']} personnel.",
            })

    # ------------------------------
    # Resource availability alerts
    # ------------------------------
    for resource in RESOURCE_STATUS:
        total = (
            resource["available"]
            + resource["dispatched"]
        )

        if total == 0:
            continue

        availability_pct = resource["available"] / total

        if resource["available"] == 0:
            alerts.append({
                "severity": "Critical",
                "message":
                    f"No {resource['name'].lower()} are currently available.",
            })

        elif availability_pct <= 0.20:
            alerts.append({
                "severity": "Warning",
                "message":
                    f"Only {resource['available']} of {total} "
                    f"{resource['name'].lower()} are currently available.",
            })

    return alerts
 
 
def _render_bottom_alert_bar() -> None:
    """
    Region 6 (full width, last on the page) — Bottom Alert Bar.
 
    Restyled as a row of severity-colored chips (tinted background +
    left accent border, using resolve_color() so the palette matches the
    rest of the app) instead of plain bold-severity text inside the
    panel's own border — an operational alert ribbon should communicate
    urgency visually, not require reading the severity word to register
    it. One merged HTML block, flex-wrapped so it degrades gracefully at
    narrower widths.
    """
    alerts = _generate_alerts()

    if not alerts:
        st.caption("No active alerts.")
        return
    chips = []
 
    for alert in alerts:
        accent = resolve_color(ALERT_SEVERITY_COLOR.get(alert["severity"], "info"))
 
        chips.append(
            (
                f'<div style="'
                f'border-left:4px solid {accent};'
                f'background:{accent}22;'
                f'padding:8px 10px;'
                f'border-radius:4px;'
                f'margin-bottom:8px;'
                f'font-size:0.85rem;'
                f'">'
                f'<b style="color:{accent};">'
                f'{html.escape(alert["severity"].upper())}'
                f'</b>&nbsp;'
                f'{html.escape(alert["message"])}'
                f'</div>'
            )
        )
 
    # ← LOOP ENDS HERE
 
    html_output = (
        '<div style="display:flex;flex-direction:column;gap:6px;">'
        + "".join(chips)
        + "</div>"
    )
 
    st.markdown(html_output, unsafe_allow_html=True)
    
 
def render() -> None:
    """
    Render the Simulation page as one Tactical Operations Center screen,
    organized into six screen regions read top-to-bottom in the
    operator's actual workflow order rather than by where panels
    happened to fit:
 
    Region 1 — command console: a slim instrument strip (Simulation
    Controls | Manual Incident Generator), deliberately NOT sharing a
    row with the map, so the map is free to dominate Region 2's width.
    Region 2 — the hero: Battlefield Map, ~70% of the workspace width
    (HERO_ROW_RATIO), ready for a drop-in Folium replacement.
    Region 3 — intel flank beside the map: AI Tactical Recommendation,
    then Current Operation.
    Region 4 — readiness band, full width: Resource Status | Facility
    Status, side by side.
    Region 5 — mission feed: Live Mission Log, deliberately narrower
    than the page (MISSION_LOG_WIDTH_RATIO gutters) so a short
    operational feed doesn't visually compete with the map above it.
    Region 6 — alert ribbon: the Bottom Alert Bar, full width, last.
    """
    global RESOURCE_STATUS, FACILITY_STATUS, CURRENT_OPERATION, AI_RECOMMENDATION

    _init_session_state()
    _run_pending_tick()

    RESOURCE_STATUS = _build_resource_status()
    FACILITY_STATUS = _build_facility_status()
    CURRENT_OPERATION = _build_current_operation()
    AI_RECOMMENDATION = _build_ai_recommendation()

    clock = st.session_state["sim_clock"]

    if clock.is_running:
        st_autorefresh(
            interval=TICK_INTERVAL_MS,
            key="simulation_autorefresh",
        )
 
    controls_col, incident_col = st.columns(COMMAND_STRIP_RATIO)
    with controls_col:
        with panel("Simulation Controls"):
            _render_simulation_controls()
    with incident_col:
        with panel("Manual Incident Generator"):
            _render_manual_incident_generator()
 
    map_col, intel_col = st.columns(HERO_ROW_RATIO)
    with map_col:
        with panel("Battlefield Map", toolbar=f"Live Tracking — {st.session_state['simulation_status']}"):
            _render_battlefield_map()
    with intel_col:
        with panel("AI Tactical Recommendation"):
            _render_ai_recommendation()
        with panel("Current Operation"):
            _render_current_operation()
 
    resource_col, facility_col = st.columns(SUPPORT_ROW_RATIO)
    with resource_col:
        with panel("Resource Status"):
            _render_resource_status()
    with facility_col:
        with panel("Facility Status"):
            _render_facility_status()
 
    mission_log_entry_count = len(_get_filtered_mission_log_entries())
    mission_log_toolbar = (
        f"Showing latest {min(MISSION_LOG_FEED_SIZE, mission_log_entry_count)} of {mission_log_entry_count}"
        if mission_log_entry_count
        else None
    )
    mission_col, alert_col = st.columns([3,2])
 
    with mission_col:
        with panel("Live Mission Log", toolbar=mission_log_toolbar):
            _render_live_mission_log()
 
    with alert_col:
        with panel("Bottom Alert Bar"):
            _render_bottom_alert_bar()