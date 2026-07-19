"""
transport_queue.py

Runtime-only transport queue for the evacuation simulation.

This module holds casualties that have been triaged (severity + destination
facility already decided by decision_engine) but have NOT yet had a vehicle
dispatched to them, because no ambulance/helicopter was available at the
moment of triage.

Deliberately excluded from this module, per architectural decision:
    - No SQLite / no `crud` imports / no database access of any kind.
      The queue exists only for the lifetime of the running simulation
      process; it is NOT persisted, and a simulation reset simply clears it.
    - No dispatch logic, no vehicle-selection logic, no severity->facility
      mapping logic. This module only stores and retrieves queue entries in
      FIFO order; deciding WHICH vehicle to assign, or WHEN to pop an entry,
      is entirely the responsibility of resource_manager.py.

Storage:
    Backed by Streamlit's st.session_state when running inside a Streamlit
    app (so queue state survives Streamlit's per-interaction reruns), and
    transparently falls back to a plain in-memory module-level dict when
    Streamlit isn't available or no session is active (e.g. unit tests,
    scripts). Either way, this is "runtime only" storage — nothing here
    touches disk or a database.

Severity keys match backend.utils.constants.SEVERITY_LIST exactly
("Critical", "Serious", "Moderate", "Mild") so this module stays in sync
with the single source of truth for severity strings.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

try:
    import streamlit as st
    _STREAMLIT_AVAILABLE = True
except ImportError:
    _STREAMLIT_AVAILABLE = False

# Matches backend.utils.constants.SEVERITY_LIST. Duplicated here as a plain
# literal (rather than importing constants.py) to keep this module fully
# self-contained with zero dependencies beyond the standard library and an
# optional Streamlit import, per the "no simulation logic" constraint.
from collections import deque
from backend.utils.constants import SEVERITY_LIST

QUEUE_SEVERITIES = SEVERITY_LIST

_SESSION_STATE_KEY = "transport_queues"

# Fallback store used whenever Streamlit's session_state isn't available
# (e.g. running outside a Streamlit app — tests, scripts, this module
# imported standalone).
_fallback_store = {
    severity: deque()
    for severity in QUEUE_SEVERITIES
}


@dataclass(frozen=True)
class TransportQueueEntry:
    """One casualty waiting for a transport vehicle. Vehicle-agnostic by
    design — no vehicle type is ever stored here; vehicle selection is
    always performed live, at dispatch time, by resource_manager.py."""
    casualty_id: str
    severity: str
    facility_code: str
    queued_at: str


def _validate_severity(severity: str) -> None:
    if severity not in QUEUE_SEVERITIES:
        raise ValueError(
            f"Unknown transport queue severity '{severity}'. "
            f"Expected one of {QUEUE_SEVERITIES}."
        )


def _get_store() -> dict[str, list[TransportQueueEntry]]:
    """Return the active backing store: Streamlit session_state if running
    inside a live Streamlit session, otherwise the module-level fallback."""
    if _STREAMLIT_AVAILABLE:
        try:
            if _SESSION_STATE_KEY not in st.session_state:
                st.session_state[_SESSION_STATE_KEY] = {
                    severity: deque() for severity in QUEUE_SEVERITIES
                }
            return st.session_state[_SESSION_STATE_KEY]
        except Exception:
            # No active Streamlit runtime/session (e.g. imported outside
            # an app context) — fall through to the in-memory fallback.
            pass
    return _fallback_store


def initialize_queue() -> None:
    """Ensure all four FIFO queues exist and are ready to use. Safe to call
    multiple times — does not clear existing entries if already present."""
    store = _get_store()
    for severity in QUEUE_SEVERITIES:
        store.setdefault(severity, deque())


def reset_queue() -> None:
    """Clear all four queues completely. Intended to be called alongside
    crud.reset_simulation_data() so a simulation reset doesn't leave stale
    queued casualties referencing rows that no longer exist."""
    store = _get_store()
    for severity in QUEUE_SEVERITIES:
        store[severity] = deque()


def enqueue(severity: str, casualty_id: str, facility_code: str, queued_at: str) -> None:
    """Append a casualty to the back of its severity's FIFO queue."""
    _validate_severity(severity)
    store = _get_store()
    store.setdefault(severity, deque())
    store[severity].append(
        TransportQueueEntry(
            casualty_id=casualty_id,
            severity=severity,
            facility_code=facility_code,
            queued_at=queued_at,
        )
    )


def peek_front(severity: str) -> Optional[TransportQueueEntry]:
    """Return (without removing) the earliest-enqueued entry for one
    severity's queue, or None if that queue is empty."""
    _validate_severity(severity)
    store = _get_store()
    queue = store.get(severity, [])
    return queue[0] if queue else None


def pop_front(severity: str) -> Optional[TransportQueueEntry]:
    """Remove and return the earliest-enqueued entry for one severity's
    queue, or None if that queue is empty."""
    _validate_severity(severity)
    store = _get_store()
    queue = store.get(severity, [])
    if not queue:
        return None
    return queue.popleft()


def is_empty(severity: str) -> bool:
    """Whether the given severity's queue currently has no waiting casualties."""
    _validate_severity(severity)
    store = _get_store()
    return len(store.get(severity, [])) == 0


def get_queue_snapshot() -> dict[str, list[TransportQueueEntry]]:
    """Read-only view of all four queues' current contents, in FIFO order,
    keyed by severity. Intended for dashboard/debug display; callers must
    not mutate the returned lists."""
    store = _get_store()
    return {
        severity: list(store.get(severity, deque()))
        for severity in QUEUE_SEVERITIES
    }

def get_queue_lengths() -> dict[str, int]:
    """
    Return the number of casualties waiting in each severity queue.
    Useful for dashboard metrics and analytics.
    """
    store = _get_store()
    return {
        severity: len(store.get(severity, []))
        for severity in QUEUE_SEVERITIES
    }