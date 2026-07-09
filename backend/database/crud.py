"""
crud.py
 
The ONLY module permitted to execute SQL against the database.
Every function here is small, parameterized (no string-formatted SQL),
and returns either plain dicts/lists or the dataclasses defined in models.py.
 
Organized by table group:
    Facilities & Beds
    Scenarios & Operations
    Incidents
    Casualties
    Treatments
    Waiting Queue
    Resources (Ambulances / Helicopters / Medical Teams)
    Aggregate statistics (for dashboard/analytics/reports)
"""
 
from __future__ import annotations
from typing import Optional
import sqlite3
 
from backend.database.db import get_connection
from .models import (
    Facility, Bed, Scenario, Operation, Incident,
    Casualty, Treatment, QueueEntry, Ambulance, Helicopter, MedicalTeam,
)
from backend.utils.constants import (
    UTILIZATION_WARNING_THRESHOLD,
    UTILIZATION_HIGH_THRESHOLD,
    UTILIZATION_CRITICAL_THRESHOLD,
    FACILITY_STATUS_OPERATIONAL,
    FACILITY_STATUS_BUSY,
    FACILITY_STATUS_HIGH_LOAD,
    FACILITY_STATUS_CRITICAL,
)
 
 
# ==========================================================================
# FACILITIES & BEDS
# ==========================================================================
 
def get_all_facilities() -> list[Facility]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM Facilities ORDER BY facility_id").fetchall()
    return [Facility.from_row(r) for r in rows]
 
 
def get_facility_by_code(facility_code: str) -> Optional[Facility]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM Facilities WHERE facility_code = ?", (facility_code,)
        ).fetchone()
    return Facility.from_row(row) if row else None
 
 
def get_facility_by_id(facility_id: int) -> Optional[Facility]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM Facilities WHERE facility_id = ?", (facility_id,)
        ).fetchone()
    return Facility.from_row(row) if row else None
 
 
def _recompute_facility_counts(conn: sqlite3.Connection, facility_id: int) -> None:
    """Internal helper: recompute occupied/available/queue counts for one facility."""
    occupied = conn.execute(
        "SELECT COUNT(*) AS c FROM Beds WHERE facility_id = ? AND status = 'Occupied'",
        (facility_id,),
    ).fetchone()["c"]
    capacity = conn.execute(
        "SELECT capacity FROM Facilities WHERE facility_id = ?", (facility_id,)
    ).fetchone()["capacity"]
    queue_length = conn.execute(
        "SELECT COUNT(*) AS c FROM Waiting_Queue WHERE facility_id = ?", (facility_id,)
    ).fetchone()["c"]
 
    utilization = (occupied / capacity * 100) if capacity else 0
    if utilization >= UTILIZATION_CRITICAL_THRESHOLD:
        status = FACILITY_STATUS_CRITICAL
    elif utilization >= UTILIZATION_HIGH_THRESHOLD:
        status = FACILITY_STATUS_HIGH_LOAD
    elif utilization >= UTILIZATION_WARNING_THRESHOLD:
        status = FACILITY_STATUS_BUSY
    else:
        status = FACILITY_STATUS_OPERATIONAL
 
    conn.execute(
        """
        UPDATE Facilities
        SET occupied_beds = ?, available_beds = ?, queue_length = ?, facility_status = ?
        WHERE facility_id = ?
        """,
        (occupied, capacity - occupied, queue_length, status, facility_id),
    )
 
 
def get_available_bed(facility_id: int) -> Optional[Bed]:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT * FROM Beds
            WHERE facility_id = ? AND status = 'Available'
            ORDER BY bed_number LIMIT 1
            """,
            (facility_id,),
        ).fetchone()
    return Bed.from_row(row) if row else None
 
 
def occupy_bed(bed_id: int, casualty_id: str, occupied_since: str, expected_release_time: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE Beds
            SET status = 'Occupied', current_casualty = ?,
                occupied_since = ?, expected_release_time = ?
            WHERE bed_id = ?
            """,
            (casualty_id, occupied_since, expected_release_time, bed_id),
        )
        facility_id = conn.execute(
            "SELECT facility_id FROM Beds WHERE bed_id = ?", (bed_id,)
        ).fetchone()["facility_id"]
        _recompute_facility_counts(conn, facility_id)
 
 
def release_bed(bed_id: int) -> None:
    with get_connection() as conn:
        facility_id = conn.execute(
            "SELECT facility_id FROM Beds WHERE bed_id = ?", (bed_id,)
        ).fetchone()["facility_id"]
        conn.execute(
            """
            UPDATE Beds
            SET status = 'Available', current_casualty = NULL,
                occupied_since = NULL, expected_release_time = NULL
            WHERE bed_id = ?
            """,
            (bed_id,),
        )
        _recompute_facility_counts(conn, facility_id)
 
 
def get_beds_for_facility(facility_id: int) -> list[Bed]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM Beds WHERE facility_id = ? ORDER BY bed_number", (facility_id,)
        ).fetchall()
    return [Bed.from_row(r) for r in rows]
 
 
# ==========================================================================
# SCENARIOS & OPERATIONS
# ==========================================================================
 
def create_scenario(scenario_name: str, start_time: str, description: str = "") -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO Scenarios (scenario_name, start_time, status, description)
            VALUES (?, ?, 'Active', ?)
            """,
            (scenario_name, start_time, description),
        )
        return cursor.lastrowid
 
 
def get_active_scenario() -> Optional[Scenario]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM Scenarios WHERE status = 'Active' ORDER BY scenario_id DESC LIMIT 1"
        ).fetchone()
    return Scenario.from_row(row) if row else None
 
 
def create_operation(scenario_id: int, operation_name: str, start_time: str, description: str = "") -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO Operations (scenario_id, operation_name, start_time, status, description)
            VALUES (?, ?, ?, 'Active', ?)
            """,
            (scenario_id, operation_name, start_time, description),
        )
        return cursor.lastrowid
 
 
def get_active_operation() -> Optional[Operation]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM Operations WHERE status = 'Active' ORDER BY operation_id DESC LIMIT 1"
        ).fetchone()
    return Operation.from_row(row) if row else None
 
 
def end_operation(operation_id: int, end_time: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE Operations SET status = 'Concluded', end_time = ? WHERE operation_id = ?",
            (end_time, operation_id),
        )
 
 
# ==========================================================================
# INCIDENTS
# ==========================================================================
 
def insert_incident(
    incident_id: str, operation_id: int, incident_time: str, event_type: str,
    battle_sector: str, grid_x: float, grid_y: float, number_of_casualties: int,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO Incidents (
                incident_id, operation_id, incident_time, event_type,
                battle_sector, grid_x, grid_y, number_of_casualties, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Active')
            """,
            (incident_id, operation_id, incident_time, event_type,
             battle_sector, grid_x, grid_y, number_of_casualties),
        )
 
 
def get_next_incident_id() -> str:
    """Generate the next sequential incident identifier (e.g. 'INC-0001')."""
    with get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) AS c FROM Incidents").fetchone()["c"]
    return f"INC-{count + 1:04d}"
 
 
def get_recent_incidents(limit: int = 20) -> list[Incident]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM Incidents ORDER BY incident_time DESC LIMIT ?", (limit,)
        ).fetchall()
    return [Incident.from_row(r) for r in rows]
 
 
# ==========================================================================
# CASUALTIES
# ==========================================================================
 
def get_next_casualty_id() -> str:
    """Generate the next sequential casualty identifier (e.g. 'CAS-0001')."""
    with get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) AS c FROM Casualties").fetchone()["c"]
    return f"CAS-{count + 1:04d}"
 
 
def insert_casualty(casualty: dict) -> None:
    """casualty is a dict with keys matching the Casualties table columns."""
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO Casualties (
                casualty_id,
                incident_id,
                battle_sector,
                grid_x,
                grid_y,
                soldier_unit,
                rank,
                age,
                injury_type,
                severity,
                priority,
                arrival_time,
                assigned_facility,
                bed_id,
                queue_position,
                evacuation_mode,
                evacuation_arrival_time,
                medical_officer,
                status,
                expected_recovery,
                return_to_duty
            )
            VALUES (
                :casualty_id,
                :incident_id,
                :battle_sector,
                :grid_x,
                :grid_y,
                :soldier_unit,
                :rank,
                :age,
                :injury_type,
                :severity,
                :priority,
                :arrival_time,
                :assigned_facility,
                :bed_id,
                :queue_position,
                :evacuation_mode,
                :evacuation_arrival_time,
                :medical_officer,
                :status,
                :expected_recovery,
                :return_to_duty
            )
            """,
            casualty,
        )
 
 
def update_casualty_facility_and_bed(casualty_id: str, facility_id: int, bed_id: Optional[int], status: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE Casualties
            SET assigned_facility = ?, bed_id = ?, status = ?
            WHERE casualty_id = ?
            """,
            (facility_id, bed_id, status, casualty_id),
        )
 
 
def update_casualty_status(casualty_id: str, status: str, return_to_duty: Optional[str] = None) -> None:
    with get_connection() as conn:
        if return_to_duty is not None:
            conn.execute(
                "UPDATE Casualties SET status = ?, return_to_duty = ? WHERE casualty_id = ?",
                (status, return_to_duty, casualty_id),
            )
        else:
            conn.execute(
                "UPDATE Casualties SET status = ? WHERE casualty_id = ?",
                (status, casualty_id),
            )
 
 
def get_casualty(casualty_id: str) -> Optional[Casualty]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM Casualties WHERE casualty_id = ?", (casualty_id,)
        ).fetchone()
    return Casualty.from_row(row) if row else None
 
 
def get_active_casualties() -> list[Casualty]:
    """Casualties not yet Recovered/Returned To Duty."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM Casualties
            WHERE status NOT IN ('Recovered', 'Returned To Duty')
            ORDER BY arrival_time DESC
            """
        ).fetchall()
    return [Casualty.from_row(r) for r in rows]
 
 
def get_recent_casualties(limit: int = 50) -> list[Casualty]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM Casualties ORDER BY arrival_time DESC LIMIT ?", (limit,)
        ).fetchall()
    return [Casualty.from_row(r) for r in rows]
 
 
def get_casualties_filtered(
    severity: Optional[str] = None,
    facility_id: Optional[int] = None,
    status: Optional[str] = None,
    battle_sector: Optional[str] = None,
) -> list[Casualty]:
    query = "SELECT * FROM Casualties WHERE 1=1"
    params: list = []
    if severity:
        query += " AND severity = ?"
        params.append(severity)
    if facility_id:
        query += " AND assigned_facility = ?"
        params.append(facility_id)
    if status:
        query += " AND status = ?"
        params.append(status)
    if battle_sector:
        query += " AND battle_sector = ?"
        params.append(battle_sector)
    query += " ORDER BY arrival_time DESC"
 
    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [Casualty.from_row(r) for r in rows]
 
 
def get_due_evacuations(current_time: str) -> list[Casualty]:
    """Casualties still 'Being Evacuated' whose evacuation_arrival_time has elapsed."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM Casualties WHERE status = 'Being Evacuated' AND evacuation_arrival_time <= ?",
            (current_time,),
        ).fetchall()
    return [Casualty.from_row(r) for r in rows]
 
 
# ==========================================================================
# TREATMENTS
# ==========================================================================
 
def insert_treatment(
    casualty_id: str, facility_id: int, treatment_start: str,
    treatment_end: str, treatment_duration: float,
) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO Treatments (
                casualty_id, facility_id, treatment_start, treatment_end,
                treatment_duration, current_status
            ) VALUES (?, ?, ?, ?, ?, 'Under Treatment')
            """,
            (casualty_id, facility_id, treatment_start, treatment_end, treatment_duration),
        )
        return cursor.lastrowid
 
 
def complete_treatment(treatment_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE Treatments SET current_status = 'Completed' WHERE treatment_id = ?",
            (treatment_id,),
        )
 
 
def get_due_treatments(current_sim_time: str) -> list[Treatment]:
    """Treatments whose end time has passed and are still marked Under Treatment."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM Treatments
            WHERE current_status = 'Under Treatment' AND treatment_end <= ?
            """,
            (current_sim_time,),
        ).fetchall()
    return [Treatment.from_row(r) for r in rows]

def get_due_return_to_duty(current_time: str) -> list[Casualty]:
    """
    Recovered casualties whose scheduled return_to_duty time has elapsed.
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM Casualties
            WHERE status = 'Recovered'
              AND return_to_duty IS NOT NULL
              AND return_to_duty <= ?
            """,
            (current_time,),
        ).fetchall()

    return [Casualty.from_row(r) for r in rows]
 
 
# ==========================================================================
# WAITING QUEUE
# ==========================================================================
 
def enqueue_casualty(facility_id: int, casualty_id: str, priority: str, arrival_time: str) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO Waiting_Queue (facility_id, casualty_id, priority, arrival_time, waiting_time)
            VALUES (?, ?, ?, ?, 0)
            """,
            (facility_id, casualty_id, priority, arrival_time),
        )
        _recompute_facility_counts(conn, facility_id)
        return cursor.lastrowid
 
 
def dequeue_next_casualty(facility_id: int) -> Optional[QueueEntry]:
    """
    Pop the highest-priority, earliest-arrived casualty for a facility.
    Priority ordering: P0 > P1 > P2 > P3 (alphabetical happens to match here,
    but we sort explicitly for clarity and future-proofing).
    """
    priority_rank = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM Waiting_Queue WHERE facility_id = ?", (facility_id,)
        ).fetchall()
        if not rows:
            return None
        entries = [QueueEntry.from_row(r) for r in rows]
        entries.sort(key=lambda e: (priority_rank.get(e.priority, 9), e.arrival_time))
        next_entry = entries[0]
        conn.execute("DELETE FROM Waiting_Queue WHERE queue_id = ?", (next_entry.queue_id,))
        _recompute_facility_counts(conn, facility_id)
    return next_entry
 
 
def get_queue_for_facility(facility_id: int) -> list[QueueEntry]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM Waiting_Queue WHERE facility_id = ? ORDER BY arrival_time",
            (facility_id,),
        ).fetchall()
    return [QueueEntry.from_row(r) for r in rows]
 
 
def get_all_queues() -> list[QueueEntry]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM Waiting_Queue ORDER BY arrival_time").fetchall()
    return [QueueEntry.from_row(r) for r in rows]

def update_queue_waiting_time(queue_id: int, waiting_time: int) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE Waiting_Queue
            SET waiting_time = ?
            WHERE queue_id = ?
            """,
            (waiting_time, queue_id),
        )
 
 
# ==========================================================================
# RESOURCES: AMBULANCES / HELICOPTERS / MEDICAL TEAMS
# ==========================================================================
 
def get_available_ambulance() -> Optional[Ambulance]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM Ambulances WHERE status = 'Available' LIMIT 1"
        ).fetchone()
    return Ambulance.from_row(row) if row else None
 
 
def get_available_helicopter() -> Optional[Helicopter]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM Helicopters WHERE status = 'Available' LIMIT 1"
        ).fetchone()
    return Helicopter.from_row(row) if row else None
 
 
def get_available_medical_team() -> Optional[MedicalTeam]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM Medical_Teams WHERE status = 'Available' LIMIT 1"
        ).fetchone()
    return MedicalTeam.from_row(row) if row else None
 
 
def dispatch_ambulance(ambulance_id: int, release_time: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE Ambulances SET status = 'Dispatched', release_time = ? WHERE ambulance_id = ?",
            (release_time, ambulance_id),
        )
 
 
def dispatch_helicopter(helicopter_id: int, release_time: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE Helicopters SET status = 'Dispatched', release_time = ? WHERE helicopter_id = ?",
            (release_time, helicopter_id),
        )
 
 
def attach_casualty_to_ambulance(ambulance_id: int, casualty_id: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE Ambulances SET assigned_casualty = ? WHERE ambulance_id = ?",
            (casualty_id, ambulance_id),
        )
 
 
def attach_casualty_to_helicopter(helicopter_id: int, casualty_id: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE Helicopters SET assigned_casualty = ? WHERE helicopter_id = ?",
            (casualty_id, helicopter_id),
        )
 
 
def dispatch_medical_team(team_id: int, facility_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE Medical_Teams SET status = 'Dispatched', assigned_facility = ? WHERE team_id = ?",
            (facility_id, team_id),
        )
 
 
def release_ambulance(ambulance_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE Ambulances SET status = 'Available', assigned_casualty = NULL, release_time = NULL WHERE ambulance_id = ?",
            (ambulance_id,),
        )
 
 
def release_helicopter(helicopter_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE Helicopters SET status = 'Available', assigned_casualty = NULL, release_time = NULL WHERE helicopter_id = ?",
            (helicopter_id,),
        )
 
 
def release_medical_team(team_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE Medical_Teams SET status = 'Available', assigned_facility = NULL WHERE team_id = ?",
            (team_id,),
        )
 
 
def get_due_ambulances(current_time: str) -> list[Ambulance]:
    """Dispatched ambulances whose release_time has elapsed."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM Ambulances WHERE status = 'Dispatched' AND release_time <= ?",
            (current_time,),
        ).fetchall()
    return [Ambulance.from_row(r) for r in rows]
 
 
def get_due_helicopters(current_time: str) -> list[Helicopter]:
    """Dispatched helicopters whose release_time has elapsed."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM Helicopters WHERE status = 'Dispatched' AND release_time <= ?",
            (current_time,),
        ).fetchall()
    return [Helicopter.from_row(r) for r in rows]
 
 
def get_dispatched_teams_for_facility(facility_id: int) -> list[MedicalTeam]:
    """Medical teams currently dispatched to a given facility."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM Medical_Teams WHERE status = 'Dispatched' AND assigned_facility = ?",
            (facility_id,),
        ).fetchall()
    return [MedicalTeam.from_row(r) for r in rows]
 
 
def get_resource_availability_counts() -> dict:
    with get_connection() as conn:
        amb_total = conn.execute("SELECT COUNT(*) AS c FROM Ambulances").fetchone()["c"]
        amb_avail = conn.execute("SELECT COUNT(*) AS c FROM Ambulances WHERE status='Available'").fetchone()["c"]
        heli_total = conn.execute("SELECT COUNT(*) AS c FROM Helicopters").fetchone()["c"]
        heli_avail = conn.execute("SELECT COUNT(*) AS c FROM Helicopters WHERE status='Available'").fetchone()["c"]
        team_total = conn.execute("SELECT COUNT(*) AS c FROM Medical_Teams").fetchone()["c"]
        team_avail = conn.execute("SELECT COUNT(*) AS c FROM Medical_Teams WHERE status='Available'").fetchone()["c"]
    return {
        "ambulances": {"available": amb_avail, "total": amb_total},
        "helicopters": {"available": heli_avail, "total": heli_total},
        "medical_teams": {"available": team_avail, "total": team_total},
    }
 
 
# ==========================================================================
# AGGREGATE STATISTICS (Dashboard / Analytics / Reports)
# ==========================================================================
 
def get_dashboard_stats() -> dict:
    """Single call returning every headline number the Dashboard needs."""
    with get_connection() as conn:
        total_casualties = conn.execute("SELECT COUNT(*) AS c FROM Casualties").fetchone()["c"]
        critical_active = conn.execute(
            "SELECT COUNT(*) AS c FROM Casualties WHERE severity='Critical' "
            "AND status NOT IN ('Recovered','Returned To Duty')"
        ).fetchone()["c"]
        recovered = conn.execute(
            "SELECT COUNT(*) AS c FROM Casualties WHERE status='Recovered'"
        ).fetchone()["c"]
        returned_to_duty = conn.execute(
            "SELECT COUNT(*) AS c FROM Casualties WHERE status='Returned To Duty'"
        ).fetchone()["c"]
        beds_occupied = conn.execute("SELECT SUM(occupied_beds) AS s FROM Facilities").fetchone()["s"] or 0
        beds_available = conn.execute("SELECT SUM(available_beds) AS s FROM Facilities").fetchone()["s"] or 0
        avg_wait = conn.execute("SELECT AVG(waiting_time) AS a FROM Waiting_Queue").fetchone()["a"] or 0.0
        waiting_total = conn.execute("SELECT COUNT(*) AS c FROM Waiting_Queue").fetchone()["c"]
        active_incidents = conn.execute(
            "SELECT COUNT(*) AS c FROM Incidents WHERE status='Active'"
        ).fetchone()["c"]
 
    return {
        "total_casualties": total_casualties,
        "critical_active": critical_active,
        "recovered": recovered,
        "returned_to_duty": returned_to_duty,
        "in_treatment": beds_occupied,
        "beds_available": beds_available,
        "average_waiting_minutes": round(avg_wait, 1),
        "waiting_total": waiting_total,
        "active_incidents": active_incidents,
    }
 
 
def get_severity_distribution() -> dict[str, int]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT severity, COUNT(*) AS c FROM Casualties GROUP BY severity"
        ).fetchall()
    return {r["severity"]: r["c"] for r in rows}

def count_dispatched_teams_for_facility(facility_id: int) -> int:
    """
    Number of medical teams currently dispatched to a facility.
    Used by bed_manager to reduce treatment duration.
    """
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*)
            FROM Medical_Teams
            WHERE assigned_facility = ?
              AND status = 'Dispatched'
            """,
            (facility_id,),
        ).fetchone()

    return row[0] if row else 0

def get_treatments_for_casualty(casualty_id: str) -> list[Treatment]:
    """
    All Treatment rows for one casualty, most recent (by treatment_start)
    first.

    Added to support per-patient treatment history lookups (e.g. the
    Patients page's "Current Treatment" panel) — no existing function
    provided this: insert_treatment()/complete_treatment() only write,
    and get_due_treatments()/get_due_return_to_duty() are tick-scoped
    bulk queries across all casualties, not a per-casualty lookup.
    """
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM Treatments WHERE casualty_id = ? ORDER BY treatment_start DESC",
            (casualty_id,),
        ).fetchall()
    return [Treatment.from_row(r) for r in rows]

# ==========================================================================
# SIMULATION RESET
# ==========================================================================

def reset_simulation_data() -> None:
    """
    Reset all runtime simulation data so every app start begins from a
    completely fresh battlefield state.

    Infrastructure tables (Facilities, Beds, Resources) are preserved and
    merely reset to their default states.
    """
    with get_connection() as conn:

        # ----------------------------------------------------------
        # IMPORTANT:
        # Clear foreign-key references FIRST.
        # Ambulances and Helicopters reference Casualties.
        # ----------------------------------------------------------
        conn.execute(
            """
            UPDATE Ambulances
            SET
                status = 'Available',
                assigned_casualty = NULL,
                release_time = NULL
            """
        )

        conn.execute(
            """
            UPDATE Helicopters
            SET
                status = 'Available',
                assigned_casualty = NULL,
                release_time = NULL
            """
        )

        # ----------------------------------------------------------
        # Now it is safe to delete runtime data.
        # ----------------------------------------------------------
        conn.execute("DELETE FROM Treatments")
        conn.execute("DELETE FROM Waiting_Queue")
        conn.execute("DELETE FROM Casualties")
        conn.execute("DELETE FROM Incidents")

        # Reset beds
        conn.execute(
            """
            UPDATE Beds
            SET
                status = 'Available',
                current_casualty = NULL,
                occupied_since = NULL,
                expected_release_time = NULL
            """
        )

        # Reset facilities
        conn.execute(
            """
            UPDATE Facilities
            SET
                occupied_beds = 0,
                available_beds = capacity,
                queue_length = 0,
                facility_status = 'Operational'
            """
        )

        # Reset medical teams
        conn.execute(
            """
            UPDATE Medical_Teams
            SET
                status = 'Available',
                assigned_facility = NULL
            """
        )

        conn.commit()