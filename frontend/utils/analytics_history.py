
"""
analytics_history.py
 
Phase 1 — lightweight, session-only persistence layer for analytics metrics.
 
Stores a rolling history of simulation snapshots in
st.session_state["analytics_history"] so the Analytics page can eventually
swap its placeholder trend data for real history, without any database,
schema, or backend dependency.
 
Scope (Phase 1 only):
    - No database tables.
    - No backend/project-specific imports.
    - No integration with analytics.py or simulation.py.
    - Session-state only; history does not persist across sessions/restarts.
"""
 
from __future__ import annotations
 
from datetime import datetime
from typing import TypedDict
 
import streamlit as st
 
# --------------------------------------------------------------------------
# CONSTANTS
# --------------------------------------------------------------------------
 
ANALYTICS_HISTORY_KEY = "analytics_history"
MAX_ANALYTICS_HISTORY = 500
 
 
class AnalyticsSnapshot(TypedDict):
    """Structure of a single analytics history entry."""
 
    timestamp: datetime
    incidents: int
    casualties: int
    recoveries: int
    returned_to_duty: int
    critical_casualties: int
    occupied_beds: int
    queue_length: int
 
 
# --------------------------------------------------------------------------
# INITIALIZATION
# --------------------------------------------------------------------------
 
def initialize_analytics_history() -> None:
    """Create st.session_state["analytics_history"] if it does not exist.
 
    Safe to call multiple times (e.g. on every page render) — it is a no-op
    once the key is present.
    """
    if ANALYTICS_HISTORY_KEY not in st.session_state:
        st.session_state[ANALYTICS_HISTORY_KEY] = []
 
 
# --------------------------------------------------------------------------
# SNAPSHOT CREATION / APPEND
# --------------------------------------------------------------------------
 
def build_analytics_snapshot(
    timestamp: datetime,
    incidents: int,
    casualties: int,
    recoveries: int,
    returned_to_duty: int,
    critical_casualties: int,
    occupied_beds: int,
    queue_length: int,
) -> AnalyticsSnapshot:
    """Build a single snapshot dict stamped with the given simulation time.
 
    Does not touch session state — pure construction only, so callers can
    build a snapshot and decide separately whether/when to append it.
    Uses simulation time (caller-supplied) rather than wall-clock time, so
    history stays consistent with however the simulation clock runs.
    """
    return {
        "timestamp": timestamp,
        "incidents": incidents,
        "casualties": casualties,
        "recoveries": recoveries,
        "returned_to_duty": returned_to_duty,
        "critical_casualties": critical_casualties,
        "occupied_beds": occupied_beds,
        "queue_length": queue_length,
    }
 
 
def append_analytics_snapshot(snapshot: AnalyticsSnapshot) -> None:
    """Append a snapshot to session state, trimming oldest entries over the cap.
 
    Initializes history first if needed, so this is safe to call standalone.
    """
    initialize_analytics_history()
    history: list[AnalyticsSnapshot] = st.session_state[ANALYTICS_HISTORY_KEY]
    history.append(snapshot)
 
    overflow = len(history) - MAX_ANALYTICS_HISTORY
    if overflow > 0:
        del history[:overflow]
 
 
# --------------------------------------------------------------------------
# INTERNAL HELPERS
# --------------------------------------------------------------------------
 
def _get_history() -> list[AnalyticsSnapshot]:
    """Return the raw history list, initializing it first if necessary."""
    initialize_analytics_history()
    return st.session_state[ANALYTICS_HISTORY_KEY]
 
 
def _mean(values: list[int]) -> float:
    """Average of a list of numbers, safely returning 0.0 for an empty list."""
    if not values:
        return 0.0
    return sum(values) / len(values)
 
 
def _aggregate_bucket(bucket: list[AnalyticsSnapshot], bucket_label: datetime) -> dict:
    """Collapse a list of snapshots into a single aggregated record.
 
    Cumulative metrics (incidents, casualties, recoveries, returned_to_duty)
    represent running system totals, not per-snapshot events, so the bucket
    takes the latest value observed (bucket[-1]) rather than a sum.
    Gauge-like metrics (occupied_beds, queue_length, critical_casualties)
    are averaged since they represent a point-in-time state.
    """
    latest = bucket[-1]
    return {
        "timestamp": bucket_label,
        "incidents": latest["incidents"],
        "casualties": latest["casualties"],
        "recoveries": latest["recoveries"],
        "returned_to_duty": latest["returned_to_duty"],
        "critical_casualties": _mean([s["critical_casualties"] for s in bucket]),
        "occupied_beds": _mean([s["occupied_beds"] for s in bucket]),
        "queue_length": _mean([s["queue_length"] for s in bucket]),
    }
 
 
# --------------------------------------------------------------------------
# READ / QUERY FUNCTIONS
# --------------------------------------------------------------------------
 
def get_hour_history(reference_time: datetime | None = None) -> list[AnalyticsSnapshot]:
    """Return snapshots from the most recent hour, most-recent-last.
 
    Args:
        reference_time: Simulation time to treat as "now". Defaults to
            wall-clock time if not provided.
 
    Returns an empty list if there is no history yet or nothing falls
    within the last hour.
    """
    history = _get_history()
    if not history:
        return []
 
    now = reference_time if reference_time is not None else datetime.now()
    cutoff = now.timestamp() - 3600
    return [s for s in history if s["timestamp"].timestamp() >= cutoff]
 
 
def get_day_history(reference_time: datetime | None = None) -> list[dict]:
    """Return the last 24 hours of history, aggregated into one bucket per hour.
 
    Args:
        reference_time: Simulation time to treat as "now". Defaults to
            wall-clock time if not provided.
 
    Each returned record has the same fields as a snapshot. Cumulative
    metrics (incidents, casualties, recoveries, returned_to_duty) use the
    latest value in each hourly bucket; gauge-like metrics are hourly
    averages. Buckets are labeled with the hour they represent
    (minutes/seconds zeroed) and returned oldest-first. Returns an empty
    list if there is no history in the last 24 hours.
    """
    history = _get_history()
    if not history:
        return []
 
    now = reference_time if reference_time is not None else datetime.now()
    cutoff = now.timestamp() - (24 * 3600)
    recent = [s for s in history if s["timestamp"].timestamp() >= cutoff]
    if not recent:
        return []
 
    buckets: dict[datetime, list[AnalyticsSnapshot]] = {}
    for snapshot in recent:
        hour_key = snapshot["timestamp"].replace(minute=0, second=0, microsecond=0)
        buckets.setdefault(hour_key, []).append(snapshot)
 
    return [
        _aggregate_bucket(buckets[hour_key], hour_key)
        for hour_key in sorted(buckets.keys())
    ]
 
 
def get_week_history(reference_time: datetime | None = None) -> list[dict]:
    """Return the last 7 days of history, aggregated into one bucket per day.
 
    Args:
        reference_time: Simulation time to treat as "now". Defaults to
            wall-clock time if not provided.
 
    Each returned record has the same fields as a snapshot. Cumulative
    metrics (incidents, casualties, recoveries, returned_to_duty) use the
    latest value in each daily bucket; gauge-like metrics are daily
    averages. Buckets are labeled with the calendar day they represent and
    returned oldest-first. Returns an empty list if there is no history in
    the last 7 days.
    """
    history = _get_history()
    if not history:
        return []
 
    now = reference_time if reference_time is not None else datetime.now()
    cutoff = now.timestamp() - (7 * 24 * 3600)
    recent = [s for s in history if s["timestamp"].timestamp() >= cutoff]
    if not recent:
        return []
 
    buckets: dict[datetime, list[AnalyticsSnapshot]] = {}
    for snapshot in recent:
        day_key = snapshot["timestamp"].replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        buckets.setdefault(day_key, []).append(snapshot)
 
    return [
        _aggregate_bucket(buckets[day_key], day_key)
        for day_key in sorted(buckets.keys())
    ]