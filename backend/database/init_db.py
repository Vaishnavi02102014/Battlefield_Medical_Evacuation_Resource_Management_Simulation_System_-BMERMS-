"""
init_db.py
 
Creates the database schema (10 tables) and seeds static/reference data:
    - the four fixed treatment facilities and their beds
    - the fixed resource fleets (ambulances, helicopters, medical teams)
 
This module is idempotent: running it multiple times will not duplicate
facilities, beds, or fleet resources.
 
Run standalone with:
    python -m database.init_db
"""
 
from __future__ import annotations
import logging
 
from backend.database.db import get_connection
from backend.utils.constants import (
    FACILITY_CONFIG,
    FACILITY_ORDER,
    AMBULANCE_FLEET_SIZE,
    HELICOPTER_FLEET_SIZE,
    MEDICAL_TEAM_COUNT,
    MEDICAL_TEAM_ROLES,
    FACILITY_STATUS_OPERATIONAL,
    DATABASE_PATH,
)
 
logger = logging.getLogger(__name__)
 
# --------------------------------------------------------------------------
# SCHEMA
# --------------------------------------------------------------------------
SCHEMA_STATEMENTS: list[str] = [
    # 1. FACILITIES
    """
    CREATE TABLE IF NOT EXISTS Facilities (
        facility_id INTEGER PRIMARY KEY AUTOINCREMENT,
        facility_name TEXT NOT NULL,
        facility_code TEXT NOT NULL UNIQUE,
        capacity INTEGER NOT NULL,
        occupied_beds INTEGER NOT NULL DEFAULT 0,
        available_beds INTEGER NOT NULL,
        queue_length INTEGER NOT NULL DEFAULT 0,
        treatment_duration_hours REAL NOT NULL,
        facility_status TEXT NOT NULL DEFAULT 'Operational',
        grid_x REAL NOT NULL,
        grid_y REAL NOT NULL
    );
    """,
    # 2. BEDS
    """
    CREATE TABLE IF NOT EXISTS Beds (
        bed_id INTEGER PRIMARY KEY AUTOINCREMENT,
        facility_id INTEGER NOT NULL,
        bed_number INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'Available',
        current_casualty TEXT,
        occupied_since TEXT,
        expected_release_time TEXT,
        FOREIGN KEY (facility_id) REFERENCES Facilities(facility_id),
        UNIQUE (facility_id, bed_number)
    );
    """,
    # 3. SCENARIOS (top of hierarchy)
    """
    CREATE TABLE IF NOT EXISTS Scenarios (
        scenario_id INTEGER PRIMARY KEY AUTOINCREMENT,
        scenario_name TEXT NOT NULL,
        start_time TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'Active',
        description TEXT
    );
    """,
    # 4. OPERATIONS
    """
    CREATE TABLE IF NOT EXISTS Operations (
        operation_id INTEGER PRIMARY KEY AUTOINCREMENT,
        scenario_id INTEGER NOT NULL,
        operation_name TEXT NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT,
        status TEXT NOT NULL DEFAULT 'Active',
        description TEXT,
        FOREIGN KEY (scenario_id) REFERENCES Scenarios(scenario_id)
    );
    """,
    # 5. INCIDENTS
    """
    CREATE TABLE IF NOT EXISTS Incidents (
        incident_id TEXT PRIMARY KEY,
        operation_id INTEGER NOT NULL,
        incident_time TEXT NOT NULL,
        event_type TEXT NOT NULL,
        battle_sector TEXT NOT NULL,
        grid_x REAL NOT NULL,
        grid_y REAL NOT NULL,
        number_of_casualties INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'Active',
        FOREIGN KEY (operation_id) REFERENCES Operations(operation_id)
    );
    """,
    # 6. CASUALTIES
    """
    CREATE TABLE IF NOT EXISTS Casualties (
        casualty_id TEXT PRIMARY KEY,
        incident_id TEXT NOT NULL,
        battle_sector TEXT NOT NULL,
        grid_x REAL NOT NULL,
        grid_y REAL NOT NULL,
        soldier_unit TEXT NOT NULL,
        rank TEXT NOT NULL,
        age INTEGER NOT NULL,
        injury_type TEXT NOT NULL,
        severity TEXT NOT NULL,
        priority TEXT NOT NULL,
        arrival_time TEXT NOT NULL,
        assigned_facility INTEGER,
        bed_id INTEGER,
        queue_position INTEGER,
        evacuation_mode TEXT NOT NULL,
        evacuation_arrival_time TEXT,
        medical_officer TEXT,
        status TEXT NOT NULL DEFAULT 'Waiting',
        expected_recovery TEXT,
        return_to_duty TEXT,
        FOREIGN KEY (incident_id) REFERENCES Incidents(incident_id),
        FOREIGN KEY (assigned_facility) REFERENCES Facilities(facility_id),
        FOREIGN KEY (bed_id) REFERENCES Beds(bed_id)
    );
    """,
    # 7. TREATMENTS
    """
    CREATE TABLE IF NOT EXISTS Treatments (
        treatment_id INTEGER PRIMARY KEY AUTOINCREMENT,
        casualty_id TEXT NOT NULL,
        facility_id INTEGER NOT NULL,
        treatment_start TEXT NOT NULL,
        treatment_end TEXT,
        treatment_duration REAL NOT NULL,
        current_status TEXT NOT NULL DEFAULT 'Under Treatment',
        FOREIGN KEY (casualty_id) REFERENCES Casualties(casualty_id),
        FOREIGN KEY (facility_id) REFERENCES Facilities(facility_id)
    );
    """,
    # 8. WAITING_QUEUE
    """
    CREATE TABLE IF NOT EXISTS Waiting_Queue (
        queue_id INTEGER PRIMARY KEY AUTOINCREMENT,
        facility_id INTEGER NOT NULL,
        casualty_id TEXT NOT NULL,
        priority TEXT NOT NULL,
        arrival_time TEXT NOT NULL,
        waiting_time REAL DEFAULT 0,
        FOREIGN KEY (facility_id) REFERENCES Facilities(facility_id),
        FOREIGN KEY (casualty_id) REFERENCES Casualties(casualty_id)
    );
    """,
    # 9. AMBULANCES
    """
    CREATE TABLE IF NOT EXISTS Ambulances (
        ambulance_id INTEGER PRIMARY KEY AUTOINCREMENT,
        call_sign TEXT NOT NULL UNIQUE,
        status TEXT NOT NULL DEFAULT 'Available',
        assigned_casualty TEXT,
        release_time TEXT,
        grid_x REAL,
        grid_y REAL,
        FOREIGN KEY (assigned_casualty) REFERENCES Casualties(casualty_id)
    );
    """,
    # 10. HELICOPTERS
    """
    CREATE TABLE IF NOT EXISTS Helicopters (
        helicopter_id INTEGER PRIMARY KEY AUTOINCREMENT,
        call_sign TEXT NOT NULL UNIQUE,
        status TEXT NOT NULL DEFAULT 'Available',
        assigned_casualty TEXT,
        release_time TEXT,
        grid_x REAL,
        grid_y REAL,
        FOREIGN KEY (assigned_casualty) REFERENCES Casualties(casualty_id)
    );
    """,
    # 11. MEDICAL_TEAMS
    """
    CREATE TABLE IF NOT EXISTS Medical_Teams (
        team_id INTEGER PRIMARY KEY AUTOINCREMENT,
        team_name TEXT NOT NULL UNIQUE,
        status TEXT NOT NULL DEFAULT 'Available',
        assigned_facility INTEGER,
        specialization TEXT NOT NULL,
        FOREIGN KEY (assigned_facility) REFERENCES Facilities(facility_id)
    );
    """,
]
 
# Helpful indexes for the query patterns the dashboard will hit repeatedly.
INDEX_STATEMENTS: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_casualties_status ON Casualties(status);",
    "CREATE INDEX IF NOT EXISTS idx_casualties_facility ON Casualties(assigned_facility);",
    "CREATE INDEX IF NOT EXISTS idx_casualties_incident ON Casualties(incident_id);",
    "CREATE INDEX IF NOT EXISTS idx_beds_facility ON Beds(facility_id);",
    "CREATE INDEX IF NOT EXISTS idx_queue_facility ON Waiting_Queue(facility_id);",
    "CREATE INDEX IF NOT EXISTS idx_treatments_casualty ON Treatments(casualty_id);",
    "CREATE INDEX IF NOT EXISTS idx_incidents_operation ON Incidents(operation_id);",
]
 
 
def create_schema() -> None:
    """Create all tables and indexes if they do not already exist."""
    with get_connection() as conn:
        for statement in SCHEMA_STATEMENTS:
            conn.execute(statement)
        for statement in INDEX_STATEMENTS:
            conn.execute(statement)
    logger.info("Schema created (or already present).")
 
 
def seed_facilities_and_beds() -> None:
    """
    Insert the four fixed facilities (RAP, ADS, HMV, FDC) and their beds,
    only if they do not already exist. Safe to call on every app startup.
    """
    with get_connection() as conn:
        existing = conn.execute("SELECT COUNT(*) AS c FROM Facilities").fetchone()["c"]
        if existing > 0:
            logger.info("Facilities already seeded, skipping.")
            return
 
        for code in FACILITY_ORDER:
            cfg = FACILITY_CONFIG[code]
            cursor = conn.execute(
                """
                INSERT INTO Facilities (
                    facility_name, facility_code, capacity, occupied_beds,
                    available_beds, queue_length, treatment_duration_hours,
                    facility_status, grid_x, grid_y
                ) VALUES (?, ?, ?, 0, ?, 0, ?, ?, ?, ?)
                """,
                (
                    cfg["facility_name"],
                    code,
                    cfg["capacity"],
                    cfg["capacity"],
                    cfg["treatment_duration_hours"],
                    FACILITY_STATUS_OPERATIONAL,
                    cfg["grid_x"],
                    cfg["grid_y"],
                ),
            )
            facility_id = cursor.lastrowid
 
            bed_rows = [
                (facility_id, bed_number, "Available", None, None, None)
                for bed_number in range(1, cfg["capacity"] + 1)
            ]
            conn.executemany(
                """
                INSERT INTO Beds (
                    facility_id, bed_number, status,
                    current_casualty, occupied_since, expected_release_time
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                bed_rows,
            )
        logger.info("Facilities and beds seeded.")
 
 
def seed_resource_fleets() -> None:
    """Insert the fixed pools of ambulances, helicopters, and medical teams."""
    with get_connection() as conn:
        existing = conn.execute("SELECT COUNT(*) AS c FROM Ambulances").fetchone()["c"]
        if existing > 0:
            logger.info("Resource fleets already seeded, skipping.")
            return
 
        ambulance_rows = [(f"AMB-{i:02d}", "Available") for i in range(1, AMBULANCE_FLEET_SIZE + 1)]
        conn.executemany(
            "INSERT INTO Ambulances (call_sign, status) VALUES (?, ?)",
            ambulance_rows,
        )
 
        helicopter_rows = [(f"HELI-{i:02d}", "Available") for i in range(1, HELICOPTER_FLEET_SIZE + 1)]
        conn.executemany(
            "INSERT INTO Helicopters (call_sign, status) VALUES (?, ?)",
            helicopter_rows,
        )
 
        team_rows = [
            (f"MED-TEAM-{i:02d}", "Available", MEDICAL_TEAM_ROLES[i % len(MEDICAL_TEAM_ROLES)])
            for i in range(1, MEDICAL_TEAM_COUNT + 1)
        ]
        conn.executemany(
            "INSERT INTO Medical_Teams (team_name, status, specialization) VALUES (?, ?, ?)",
            team_rows,
        )
        logger.info("Resource fleets seeded.")
 
 
def initialize_database() -> None:
    """Full idempotent initialization: schema + seed data. Call this at app startup."""
    create_schema()
    seed_facilities_and_beds()
    seed_resource_fleets()
 
 
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    initialize_database()
    print(f"Database initialized at: {DATABASE_PATH}")