"""
queue_manager.py

Responsible ONLY for priority-queue bookkeeping that isn't already covered
by bed_manager's enqueue/dequeue calls: keeping each queue entry's
waiting_time current as the simulation clock advances, and producing
queue summaries for the Dashboard / Waiting Queue section.

Priority ordering itself (Critical > Serious > Moderate > Mild, earliest
arrival wins ties) is enforced in database/crud.py's dequeue_next_casualty,
since that is where the queue is actually consumed.
"""

from __future__ import annotations

from backend.database import crud
from backend.simulation.simulation_clock import SimulationClock

PRIORITY_RANK: dict[str, int] = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


def update_waiting_times(clock: SimulationClock) -> None:
    """Recompute waiting_time (in simulated minutes) for every queued casualty."""
    for entry in crud.get_all_queues():
        arrival = SimulationClock.parse(entry.arrival_time)
        waiting_minutes = (clock.current_time - arrival).total_seconds() / 60.0
        crud.update_queue_waiting_time(entry.queue_id, round(waiting_minutes, 1))


def get_queue_summary() -> dict:
    """
    Aggregate view used by the Dashboard's Waiting Queue section:
    total waiting, longest wait, critical-waiting count, per-facility counts.
    """
    entries = crud.get_all_queues()
    if not entries:
        return {
            "total_waiting": 0,
            "longest_waiting_minutes": 0,
            "longest_waiting_casualty": None,
            "critical_waiting": 0,
            "by_facility": {},
        }

    longest = max(entries, key=lambda e: e.waiting_time or 0)
    critical_waiting = sum(1 for e in entries if e.priority == "P0")

    by_facility: dict[int, int] = {}
    for e in entries:
        by_facility[e.facility_id] = by_facility.get(e.facility_id, 0) + 1

    return {
        "total_waiting": len(entries),
        "longest_waiting_minutes": longest.waiting_time or 0,
        "longest_waiting_casualty": longest.casualty_id,
        "critical_waiting": critical_waiting,
        "by_facility": by_facility,
    }


def get_sorted_queue_for_facility(facility_id: int) -> list:
    """Queue entries for one facility, sorted by priority then arrival (display order)."""
    entries = crud.get_queue_for_facility(facility_id)
    return sorted(entries, key=lambda e: (PRIORITY_RANK.get(e.priority, 9), e.arrival_time))
